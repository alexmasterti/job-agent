# Job Agent

Autonomous job application agent — discover, match, tailor, and submit applications 24/7.

## Quick Start

```bash
# 1. Copy and fill in secrets
cp .env.example .env

# 2. Install dependencies (requires uv)
uv pip install -e ".[dev]"

# 3. Run DB migrations
uv run alembic upgrade head

# 4. Load your resume
uv run job-agent profile load --user-email your@email.com resume.pdf

# 5. Start the dashboard
uv run uvicorn job_agent.interfaces.api.app:create_app --factory --port 8080 --reload
```

Then open http://localhost:8080 and sign in with your Google account.

## Architecture

Hexagonal (Ports & Adapters) — see `CLAUDE.md` for the full diagram and glossary.

## Phases

| Phase | Status | Description |
|---|---|---|
| 1 — Foundation | ✅ | Scaffold, DB, OAuth, resume parser, LLM client |
| 2 — Discovery | ⏳ | Greenhouse + Lever job sources |
| 3 — Matching | ⏳ | Embedding + LLM judge scoring pipeline |
| 4 — Tailoring | ⏳ | Per-role .docx + truthfulness guard |
| 5 — Submission | ⏳ | Auto-submit to Greenhouse/Lever/Ashby/Workable |
| 6 — Dashboard + Deploy | ⏳ | Full HTMX dashboard, arq worker, Railway deploy |
| 7 — Polish | ⏳ | Gmail inbox, weekly reports, anti-detection tuning |

## Deployment

Target: Railway. Services: `worker` (arq) + `dashboard` (FastAPI) + PostgreSQL + Redis.

```bash
# CI: GitHub Actions on push to main
# Deploy: Railway GitHub integration
```

## Requirements

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- Anthropic API key
- Google OAuth credentials
