"""FastAPI application factory."""

from __future__ import annotations

import traceback
from pathlib import Path

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import make_asgi_app
from starlette.middleware.sessions import SessionMiddleware

from job_agent.composition_root import build_container
from job_agent.config import Settings
from job_agent.interfaces.api.middleware.correlation import CorrelationIdMiddleware
from job_agent.interfaces.api.routes.applications_routes import router as apps_router
from job_agent.interfaces.api.routes.auth_routes import router as auth_router
from job_agent.interfaces.api.routes.dashboard import router as dashboard_router
from job_agent.interfaces.api.routes.health import router as health_router
from job_agent.interfaces.api.routes.inbox_routes import router as inbox_router
from job_agent.interfaces.api.routes.jobs_routes import router as jobs_router
from job_agent.interfaces.api.routes.profile_routes import router as profile_router
from job_agent.interfaces.api.routes.queue_routes import router as queue_router
from job_agent.logging_config import configure_logging

log = structlog.get_logger()

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app() -> FastAPI:
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.app_env)

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    app = FastAPI(
        title="Job Agent",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    # Prometheus metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Static files and templates
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.state.settings = settings
    app.state.container = build_container(settings)

    # Middleware (outermost first)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        SessionMiddleware, secret_key=settings.secret_key, https_only=settings.is_production
    )

    # Routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(jobs_router)
    app.include_router(queue_router)
    app.include_router(apps_router)
    app.include_router(inbox_router)
    app.include_router(profile_router)

    @app.exception_handler(Exception)
    async def debug_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        tb = traceback.format_exc()
        log.error("unhandled_exception", path=str(request.url), error=str(exc), traceback=tb)
        return HTMLResponse(f"<pre>{tb}</pre>", status_code=500)

    log.info("app.startup", env=settings.app_env, port=settings.port)
    return app
