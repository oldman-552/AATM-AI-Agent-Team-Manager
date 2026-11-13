"""FastAPI entry point with loopback-oriented security defaults."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api import router
from app.auth import AuthConfig, LocalAuthMiddleware
from app.core.config import settings
from app.db import build_engine, make_session_factory
from app.migrate import upgrade_database
from app.models import Agent, AuditEvent
from app.orchestrator_api import router as orchestrator_router
from app.memory_api import router as memory_router
from app.quality_api import router as quality_router
from app.system_api import router as system_router
from app.checkpoint_api import router as checkpoint_router
from app.github_api import router as github_router
from app.analytics_api import router as analytics_router
from app.notification_api import router as notification_router
from app.settings_api import router as settings_router
from app.planning_api import router as planning_router
from app.agent_api import router as agent_router
from app.browser_api import router as browser_router
from app.timeline_api import router as timeline_router
from app.blueprint_api import router as blueprint_router
from app.hardening import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.recovery import classify_database_error
from app.events import router as events_router
from app.intelligence_api import router as intelligence_router
from app.recovery_api import router as recovery_router
from app.workspace_api import router as workspace_router
from app.provider_api import ops_router, provider_router
from app.provider_store import seed_provider_defaults
from app.workflow_api import router as workflow_router


def initialize_default_manager(session_factory) -> None:
    """Create an unconfigured manager identity once; this does not execute AI."""
    with session_factory() as db:
        manager = db.get(Agent, "manager")
        if manager is None:
            manager = Agent(
                id="manager",
                name="Manager",
                role="Manager Agent",
                description="Central coordinator identity. Provider is unconfigured; task execution is not enabled yet.",
                system_instructions="",
                provider="unconfigured",
                model=None,
                status="idle",
                is_manager=True,
            )
            db.add(manager)
            db.add(
                AuditEvent(
                    entity_type="system",
                    entity_id=None,
                    event_type="system.manager_initialized",
                    summary="Default Manager Agent identity initialized with no provider configured.",
                )
            )
            db.commit()


def create_app(
    database_url: str | None = None,
    *,
    allowed_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    """Create an app instance; injectable DB URL makes isolated tests straightforward."""
    resolved_database_url = database_url or settings.database_url
    engine = build_engine(resolved_database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        upgrade_database(engine, resolved_database_url)
        initialize_default_manager(session_factory)
        with session_factory() as db:
            seed_provider_defaults(db)
        yield
        engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="AATM local-first project and agent management API. Agent execution is not enabled in this foundation build.",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts or settings.allowed_hosts,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    # Order matters: routers with literal paths must be registered before the
    # core router, otherwise `GET /agents` can shadow `GET /agents/{id}/state`.
    app.include_router(agent_router)
    app.include_router(browser_router)
    app.include_router(timeline_router)
    app.include_router(blueprint_router)
    app.include_router(intelligence_router)
    app.include_router(events_router)
    app.include_router(recovery_router)
    app.include_router(router)
    app.include_router(workflow_router)
    app.include_router(provider_router)
    app.include_router(ops_router)
    app.include_router(orchestrator_router)
    app.include_router(quality_router)
    app.include_router(workspace_router)
    app.include_router(memory_router)
    app.include_router(system_router)
    app.include_router(checkpoint_router)
    app.include_router(github_router)
    app.include_router(analytics_router)
    app.include_router(notification_router)
    app.include_router(settings_router)
    app.include_router(planning_router)
    resolved_origins = allowed_origins or settings.cors_origins
    app.add_middleware(LocalAuthMiddleware, config=AuthConfig.from_settings(resolved_origins))
    # Outermost: bound the body before any parser or handler touches it, and
    # stamp hardening headers on every response including middleware rejections.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Return a classified cause instead of an opaque 500.

        The message is deliberately operational, not a stack trace: it names the
        category and what to do, and states that the transaction was rolled back.
        """
        detail = classify_database_error(exc)
        status_code = 409 if detail["category"] in {"locked", "constraint"} else 503
        return JSONResponse({"detail": detail}, status_code=status_code)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": "AATM", "version": __version__, "api": "/api/v1"}

    return app


app = create_app()
