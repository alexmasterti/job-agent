---
name: job-agent project
description: Phases 1-4 done; multi-resume, location filter, tailoring all wired; Phase 5 (auto-submit) is next blocker
type: project
originSessionId: 09c717ae-2136-40da-a607-ac01853a9174
---
Autonomous job application agent (like usemassive.com but self-hosted) at `C:\Users\Administrator\projects\job-agent`. Branch `feature/phase-1-foundation` on https://github.com/alexmasterti/job-agent. Alex is the only user but multi-tenant from day 1.

**Why:** Build for Alex now, sell to others later. Moat = outcome data flywheel, Gmail reply integration, ATS-aware tailoring, truthfulness guarantee.

**How to apply:** Always check `CLAUDE.md` in repo for non-negotiables (multi-tenant, truthfulness, kill switch, budget cap, idempotency). Server runs on port 8080 via `uv run uvicorn job_agent.interfaces.api.app:create_app --factory --host 0.0.0.0 --port 8080`. Always use Alex's real resume at `C:/Users/Administrator/Downloads/Alex-Costa-Souza-Resume-03-18-2026.docx` for testing — never invent data.

## Phase status

- Phase 1 (Foundation): DONE — hexagonal scaffold, DB schema, OAuth, resume parser, LLM client
- Phase 2 (Discovery): DONE — Greenhouse + Lever `JobSourcePort` adapters
- Phase 3 (Matching): DONE — `MatchingService` with embeddings + LLM judge, scoring 0-100
- Phase 4 (Tailoring): DONE — `TailorAndApplyUseCase` rewrites resume per role with Sonnet, stores in `applications.form_fields_snapshot.tailored_resume`
- **Phase 5 (Auto-submit): NOT STARTED** — currently "Apply Me" only tailors and marks `applied_manual`; user must paste tailored resume into ATS by hand. Need Greenhouse/Lever HTTP form submitters with idempotency.
- Phase 6 (Worker + deploy): NOT STARTED — arq worker + Railway
- Phase 7 (Gmail inbox): NOT STARTED — placeholder UI only

## What works in the UI today

- `/jobs?tab=matched|applying|applied` — single 3-tab page; Apply Me button fires background tailor
- `/api/applications/{app_id}/resume/download` — downloads tailored resume as Arial-formatted DOCX (matches Alex's original layout exactly: 0.5" margins, 18pt name, 12pt section headers, 11pt job titles, 10pt body, List Bullet style)
- `/profile` — shows parsed profile + multi-resume management + location preferences
- Multi-resume: each resume has a name + is_primary flag stored in `user_resumes` table (added in alembic 002). Primary resume is what `TailorAndApplyUseCase` uses. Set-primary re-runs LLM profile parse from that resume.
- Location filter: `Profile.preferred_locations` (list[str]) + `remote_preference` ("remote_only"|"hybrid_ok"|"any") in profile JSON `data` column. Filter applied in matched tab via `_location_ok()` in `jobs_routes.py`.
- Theme toggle works (CSS in `tokens.css` hides correct icon/label based on `[data-theme=light]`).

## Known gotchas

- HTMX `hx-boost="true"` on `<body>` intercepts `<a>` clicks and breaks file downloads. Always add `hx-boost="false"` on download links.
- Port 8080 sometimes gets stuck behind ghost python.exe processes that don't show in `Get-Process`. Use `powershell.exe Get-Process | Where ProcessName -match python | Stop-Process -Force` to clear.
- Uvicorn `--reload` watcher missed file changes once during this session — when in doubt, kill all python processes and restart without `--reload`.
- `python-docx` returns paragraph styles as `None` for default-styled paragraphs (not `'Normal'`); guard with `p.style.name if p.style else 'None'`.
- LLM responses sometimes wrap JSON in markdown fences — both `parser.py` and `matching.py` strip ```json fences before `json.loads()`.
- The `data/resumes/` directory was used as filesystem storage early on but is now superseded by the `user_resumes` DB table (`file_data` LargeBinary column). The filesystem dir is gitignored.

## Key files

- `composition_root.py` — single wiring point; `Container` dataclass holds all repos + use cases
- `domain/models/profile.py` — Pydantic Profile with `preferred_locations`, `remote_preference`, `LocationPreference`
- `infrastructure/persistence/repositories/resume_repo.py` — `UserResumeRepository.create/list/set_primary/delete`
- `infrastructure/resume/builder.py` — DOCX generator that mimics Alex's resume format
- `application/use_cases/tailor_and_apply.py` — uses primary resume from `resume_repo`, falls back to `profile.resume_text`
- `interfaces/api/routes/jobs_routes.py` — 3-tab logic + `_location_ok()` filter + apply/status/download endpoints
- `interfaces/api/routes/profile_routes.py` — full resume CRUD + preferences
- `alembic/versions/002_user_resumes.py` — adds `user_resumes` table

## DB

PostgreSQL via `asyncpg`. `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/job_agent` in `.env`. Apply migrations with `uv run alembic upgrade head`.

## Next session

User wants Phase 5 (auto-submit). Build:
1. `JobSubmitterPort` protocol in `domain/ports/`
2. `GreenhouseSubmitter` + `LeverSubmitter` adapters in `infrastructure/submission/`
3. Wire into `TailorAndApplyUseCase` — after tailoring, call submitter, set status to `auto_applied` on success
4. Idempotency: check `application.submission_url` / `ats_confirmation_id` before re-submitting
5. ToS-aware: never auto-submit to LinkedIn/Indeed (those stay assist-only)

Also pending: location matcher could be smarter (geo-distance with metro presets like "Boston Metro" expanding to ~30 suburbs) instead of pure substring matching.
