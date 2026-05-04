# Job Agent

Autonomous job application agent — discover, match, tailor, and submit applications 24/7.

## Prerequisites

- **Python** 3.12+
- **uv** (package manager) — https://docs.astral.sh/uv/getting-started/installation/
- **PostgreSQL** 16+ (running locally or via Docker)
- **Redis** 7+ (running locally or via Docker)
- **Anthropic API key** — https://console.anthropic.com/
- **Google OAuth credentials** (Client ID + Secret) — https://console.cloud.google.com/
- **Playwright system deps** (auto-installed by `playwright install`, used by Phase 5 submitters)

### Installing uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Starting Postgres + Redis with Docker

```bash
docker run -d --name job-agent-pg \
  -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=job_agent \
  -p 5432:5432 postgres:16

docker run -d --name job-agent-redis -p 6379:6379 redis:7
```

## Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/alexmasterti/job-agent.git
cd job-agent

# 2. Copy env template and fill in secrets (see "Environment variables" below)
cp .env.example .env

# 3. Install dependencies (creates a venv via uv)
uv pip install -e ".[dev]"

# 4. Install Playwright Chromium (required for ATS submission adapters)
uv run playwright install chromium

# 5. Apply DB migrations
uv run alembic upgrade head

# 6. Load your resume
uv run job-agent profile load --user-email your@email.com path/to/resume.pdf

# 7. Start the dashboard
uv run uvicorn job_agent.interfaces.api.app:create_app --factory --port 8080 --reload
```

Then open http://localhost:8080 and sign in with your Google account.

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|---|---|
| `APP_ENV` | `development` or `production` |
| `SECRET_KEY` | Session signing key — at least 32 chars |
| `DATABASE_URL` | `postgresql+asyncpg://user:password@localhost:5432/job_agent` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `ANTHROPIC_API_KEY` | From https://console.anthropic.com/ |
| `LLM_DAILY_BUDGET_USD` | Per-user daily LLM spend cap (e.g. `5.00`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth web client |
| `GOOGLE_REDIRECT_URI` | Must match the value registered in Google Cloud Console |
| `ALLOWED_GOOGLE_EMAILS` | Comma-separated allowlist of emails permitted to sign in |
| `SENTRY_DSN` | Optional — error reporting |
| `PORT` | Server port (default `8080`) |

### Google OAuth setup

1. Go to https://console.cloud.google.com/ → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (type: **Web application**)
3. Authorized redirect URI: `http://localhost:8080/auth/callback`
4. Copy the Client ID + Secret into `.env`
5. Add your email to `ALLOWED_GOOGLE_EMAILS`

## Common Commands

```bash
# Run server
uv run uvicorn job_agent.interfaces.api.app:create_app --factory --port 8080 --reload

# CLI
uv run job-agent profile load --user-email you@example.com resume.pdf
uv run job-agent profile show --user-email you@example.com

# DB migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe change"

# Tests
uv run pytest -q

# Lint / format / typecheck
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
```

## Architecture

Hexagonal (Ports & Adapters). Domain layer is pure Python — zero I/O. Concrete adapters live in `infrastructure/`. See `CLAUDE.md` for the full layout, glossary, and non-negotiables.

```
src/job_agent/
├── domain/          ← Pure: models, services, ports, exceptions
├── infrastructure/  ← Adapters: persistence, llm, sources, submission, auth, billing
├── application/     ← Use cases
├── interfaces/      ← cli (Typer), api (FastAPI + HTMX), worker (arq)
└── composition_root.py  ← Wires adapters to ports at startup
```

## Phases

| Phase | Status | Description |
|---|---|---|
| 1 — Foundation | ✅ | Scaffold, DB, OAuth, resume parser, LLM client |
| 2 — Discovery | ✅ | Greenhouse + Lever job sources |
| 3 — Matching | ✅ | Embedding + LLM judge scoring pipeline |
| 4 — Tailoring | ✅ | Per-role .docx + truthfulness guard |
| 5 — Submission | ⏳ | Auto-submit to Greenhouse/Lever/Ashby/Workable |
| 6 — Dashboard + Deploy | ⏳ | Full HTMX dashboard, arq worker, Railway deploy |
| 7 — Polish | ⏳ | Gmail inbox, weekly reports, anti-detection tuning |

## Deployment

Target: Railway. Services: `worker` (arq) + `dashboard` (FastAPI) + PostgreSQL + Redis. CI runs on GitHub Actions; Railway pulls from `main` via GitHub integration.

## Troubleshooting

- **`uv: command not found`** — uv isn't on PATH. Restart your shell after install, or add `~/.local/bin` (macOS/Linux) / `%USERPROFILE%\.local\bin` (Windows) to PATH.
- **`connection refused` on Postgres/Redis** — services aren't running. Check `docker ps` or your local installs.
- **OAuth redirect mismatch** — `GOOGLE_REDIRECT_URI` in `.env` must exactly match the URI registered in Google Cloud Console (including the port).
- **`playwright: Executable doesn't exist`** — run `uv run playwright install chromium`.
- **Migrations fail with `database does not exist`** — create it: `createdb job_agent` (or via `psql`).
