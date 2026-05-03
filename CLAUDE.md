# Job Agent — Claude Code Instructions

## Stack & Key Commands

```bash
# Install (uv required)
uv pip install -e ".[dev]"

# Run dashboard
uv run uvicorn job_agent.interfaces.api.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Or via CLI
uv run job-agent serve  # (Phase 6 — not yet implemented)

# Apply DB migrations
uv run alembic upgrade head

# CLI commands
uv run job-agent profile load --user-email alex.master.ti@gmail.com resume.pdf
uv run job-agent profile show --user-email alex.master.ti@gmail.com

# Tests
uv run pytest -q

# Lint / format / typecheck
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
```

## Pre-Code Checklist

Before writing code in any file:
1. Run `mypy` and `ruff check` on the file you're about to change.
2. If the file is already failing, fix that first before making new changes.
3. No function longer than 40 lines — refactor if needed.

## Architecture — Hexagonal (Ports & Adapters)

```
src/job_agent/
├── domain/          ← Pure Python. ZERO I/O. No SQLAlchemy. No httpx. No Anthropic SDK.
│   ├── models/      ← Pydantic models: User, Profile, Job, Match, Application
│   ├── services/    ← MatchingService, TailoringService (Phase 3+)
│   ├── ports/       ← Protocol classes (LLMPort, JobSourcePort, RepositoryPort, …)
│   └── exceptions.py
├── infrastructure/  ← Concrete adapters that implement the ports
│   ├── persistence/ ← SQLAlchemy ORM + Alembic migrations + repositories/
│   ├── llm/         ← AnthropicClient
│   ├── profile/     ← Resume PDF parser
│   ├── sources/     ← Greenhouse, Lever, LinkedIn, … adapters (Phase 2+)
│   ├── submission/  ← ATS submitters (Phase 5+)
│   ├── auth/        ← Google OAuth adapter
│   └── billing/     ← LocalBillingService (always allows; swap for Stripe later)
├── application/     ← Use cases: LoadProfileUseCase, DiscoverJobsUseCase, …
├── interfaces/
│   ├── cli/         ← Typer CLI (Command classes per verb)
│   ├── api/         ← FastAPI routes + HTMX templates
│   └── worker/      ← arq task definitions (Phase 6+)
└── composition_root.py  ← Wire adapters to ports at startup (single source of truth)
```

**Rule:** `domain/` never imports from `infrastructure/`. `infrastructure/` imports from `domain/`.

## Glossary

| Term | Meaning |
|---|---|
| **Port** | A `Protocol` class in `domain/ports/` defining what the domain needs |
| **Adapter** | A concrete class in `infrastructure/` that implements a port |
| **Source** | A `JobSourcePort` adapter (Greenhouse, Lever, LinkedIn, …) |
| **Submitter** | A `JobSubmitterPort` adapter (full-auto ATS submission) |
| **Drafter** | An `EasyApplyDrafterPort` (prepare-only, no final submit — LinkedIn) |
| **Match** | The output of the scoring pipeline for one (user, job) pair |
| **Tailor** | Generate a per-role `.docx` resume + cover letter |
| **Submit** | Send the tailored application to an ATS endpoint |

## Non-Negotiables (read every session)

1. **Truthfulness.** Never invent jobs, certs, or skills the user doesn't have. Tailoring = rephrase + reorder + emphasize. Never fabricate.
2. **ToS-aware.** LinkedIn/Indeed = assist mode only. Never auto-submit there.
3. **Multi-tenant from day 1.** Every domain table has `user_id` FK. Every repo method filters by `user_id`. No exceptions.
4. **Kill switch always wired.** Worker checks `system_state.paused` before every external action.
5. **No user-specific values hardcoded.** Every user preference is a DB field. Nothing about Alex (or anyone) is hardcoded in production code.
6. **Budget cap enforced.** `AnthropicClient` checks per-user daily spend before every LLM call.
7. **Idempotency.** Re-running any task must not double-submit or double-store.

## STRATEGIC NOTES

Goal: build for myself now, sell it later. The moat is:
1. Outcome data flywheel (capture every reply with rich metadata from day 1).
2. Inbox integration (Gmail reply loop — Phase 6, not Phase 7).
3. ATS-aware tailoring (per-ATS quirks, not generic PDF).
4. Truthfulness guarantee (competitors can't easily match without rebuilding).

Kill criterion: if reply rate < 2% at week 4 with 200+ submissions, pause autopilot.
Headline metric = reply rate + interview rate, NOT applications sent.
