---
name: job-agent project
description: Phases 1-4 done + CI fixed + dashboard pipeline + location radius + match threshold + toasts; Phase 5 (auto-submit) is next
type: project
originSessionId: 09c717ae-2136-40da-a607-ac01853a9174
---
Autonomous job application agent (like usemassive.com but self-hosted). Branch `feature/phase-1-foundation` on https://github.com/alexmasterti/job-agent. Alex is the only user but multi-tenant from day 1. Alex develops on Windows but the Mac clone is at `/Users/alexcs/job-agent`.

**Why:** Build for Alex now, sell to others later. Moat = outcome data flywheel, Gmail reply integration, ATS-aware tailoring, truthfulness guarantee.

**How to run:** Always check `CLAUDE.md` in repo for non-negotiables. Server runs on port 8080 via `uv run uvicorn job_agent.interfaces.api.app:create_app --factory --host 0.0.0.0 --port 8080 --reload`. The .env file is NOT in the repo — grab it from `~/Downloads/job-agent/.env`.

## Phase status

- Phase 1 (Foundation): DONE — hexagonal scaffold, DB schema, OAuth, resume parser, LLM client
- Phase 2 (Discovery): DONE — Greenhouse + Lever `JobSourcePort` adapters
- Phase 3 (Matching): DONE — `MatchingService` with embeddings + LLM judge, scoring 0-100
- Phase 4 (Tailoring): DONE — `TailorAndApplyUseCase` rewrites resume per role with Sonnet
- **Phase 5 (Auto-submit): NOT STARTED** — "Apply Me" only tailors; user must paste into ATS by hand
- Phase 6 (Worker + deploy): NOT STARTED — arq worker + Railway
- Phase 7 (Gmail inbox): NOT STARTED — placeholder UI only

## What was done this session (2026-05-04)

### CI fixes (was fully broken)
- Fixed 157 ruff lint errors (N818 exception naming, TCH import rules, B904, E741, B008)
- Added `per-file-ignores` for TCH003 on Pydantic models (they need runtime imports)
- Fixed 41 mypy strict-mode errors across 23 files
- CI now passes all 4 steps: ruff check, ruff format, mypy, pytest (10/10)

### Distance-based location filtering
- Added `PreferredLocation` model with `name` + `radius_miles` (default 50mi)
- Added `infrastructure/geo/geocoder.py` — geopy/Nominatim geocoding with LRU cache + haversine distance
- `_location_ok()` now uses `is_within_radius()` instead of substring matching
- Falls back to substring match if geocoding fails
- Backward compatible: old `list[str]` data auto-converts with 50mi default
- Profile UI has per-location name + radius inputs with add/remove buttons
- Added `geopy` dependency to pyproject.toml

### Dashboard pipeline (discover + match from UI)
- Added `POST /api/pipeline/run` and `GET /api/pipeline/status` endpoints
- "Discover & Match Jobs" panel on dashboard with keyword input + source selector
- Live progress via HTMX polling (every 1s):
  - Step 1/2: Discovering — counters tick up per-source (fetched/new/dupes)
  - Step 2/2: Scoring — real percentage bar (scored/total), matches counter, sub-status text
- Per-user lock prevents concurrent pipeline runs
- Pipeline scores jobs one-by-one (not batched) for live progress updates
- Saves matches in batches of 10 (crash-safe)
- 0.3s delay between LLM calls to avoid Anthropic 429 rate limits

### Job deduplication (never re-process scored jobs)
- `list_unmatched()` now uses SQL `NOT IN` subquery to exclude already-scored jobs
- Pipeline saves zero-score Match entries for filtered/skipped jobs so they're never re-scored
- `list_top()` filters `final_score > 0` so zero-score entries don't appear in Matched tab
- Second pipeline run is instant: "No new jobs to score"

### Keyword matching improvements
- Changed from AND logic to OR logic: ANY query word in title matches
- Also searches job descriptions (not just titles)
- Added ~80 enterprise/fintech/.NET companies to Greenhouse + Lever slug lists

### Match threshold setting
- Added `min_match_score` (0-100) to Profile model, persisted in JSON data column
- Slider on profile page with 5 presets: Show all (0%), Relaxed (40%), Balanced (55%), Focused (70%), Sniper (80%)
- Context-aware hint text with expected reply rates per level
- Jobs page uses profile threshold as default filter (overridable via URL param)

### Toast notifications (BookLibrary style)
- Global `showToast()` JS function using existing toast CSS
- Toasts for: save preferences, upload/delete/set-primary resume, pipeline complete/error, OAuth login
- Toast from URL params after redirects (auto-cleaned from URL)
- 5s auto-dismiss with fade-out animation
- Added `hx-boost="false"` to all profile forms so redirects execute JS properly

### Spinner + progress bar CSS
- Added `.spinner` class with keyframe animation to `components.css`
- Animated progress bar in pipeline panel (percentage-based, not indeterminate)

## What works in the UI today

- `/` (Dashboard) — stats grid + "Discover & Match Jobs" pipeline panel + LLM budget + profile summary
- `/jobs?tab=matched|applying|applied` — 3-tab job page; Apply Me fires background tailor; min_score from profile threshold
- `/profile` — parsed profile + multi-resume CRUD + location prefs with radius + match threshold slider + remote preference
- `/api/pipeline/run` + `/api/pipeline/status` — background discover+match with live progress
- `/api/applications/{app_id}/resume/download` — tailored DOCX download
- Toast notifications on all user actions
- Theme toggle (dark/light)
- Google OAuth login

## Known gotchas

- HTMX `hx-boost="true"` on `<body>` intercepts form POSTs — must add `hx-boost="false"` on forms that redirect with toast params or need JS to re-execute after page load.
- Anthropic API rate limits (429) when scoring many jobs — pipeline throttles with 0.3s delay between LLM calls. The tenacity retry on `AnthropicClient.complete()` handles transient 429s with exponential backoff.
- First pipeline run downloads the embedding model (~1.3GB) from HuggingFace — subsequent runs use the cache at `~/.cache/huggingface/`.
- `python-docx` returns paragraph styles as `None` for default-styled paragraphs; guard with `p.style.name if p.style else 'None'`.
- LLM responses sometimes wrap JSON in markdown fences — both `parser.py` and `matching.py` strip them.
- The `data/resumes/` directory is obsolete (superseded by `user_resumes` DB table).
- On Mac: Postgres/Redis installed via Homebrew (`brew services start postgresql@16` / `brew services start redis`). DB user is `postgres` with password `postgres`.

## Key files

- `composition_root.py` — single wiring point; `Container` dataclass holds all repos + use cases
- `domain/models/profile.py` — Profile with `PreferredLocation`, `min_match_score`, `remote_preference`
- `infrastructure/geo/geocoder.py` — Nominatim geocoding + haversine + LRU cache
- `infrastructure/sources/_company_lists.py` — ~200 Greenhouse + Lever company slugs
- `infrastructure/sources/greenhouse.py` / `lever.py` — OR-based keyword matching + description search
- `interfaces/api/routes/pipeline_routes.py` — dashboard pipeline (discover + match with live progress)
- `interfaces/api/routes/jobs_routes.py` — 3-tab logic + `_location_ok()` + apply/status/download
- `interfaces/api/routes/profile_routes.py` — resume CRUD + preferences + match threshold
- `interfaces/api/templates/base.html` — toast container + `showToast()` JS
- `interfaces/api/static/css/components.css` — spinner, toast, progress bar CSS

## DB

PostgreSQL via `asyncpg`. `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/job_agent` in `.env`. Apply migrations with `uv run alembic upgrade head`. Tables: users, profiles, jobs, matches, applications, llm_calls, credentials, events, system_state, user_resumes.

## Next session — Phase 5 (Auto-submit)

User wants Phase 5 (auto-submit to ATS). Build:
1. `JobSubmitterPort` protocol in `domain/ports/`
2. `GreenhouseSubmitter` + `LeverSubmitter` adapters in `infrastructure/submission/`
3. Wire into `TailorAndApplyUseCase` — after tailoring, call submitter, set status to `auto_applied`
4. Idempotency: check `application.submission_url` / `ats_confirmation_id` before re-submitting
5. ToS-aware: never auto-submit to LinkedIn/Indeed (those stay assist-only)
6. May need Playwright for form submission on ATS sites that don't have API endpoints
