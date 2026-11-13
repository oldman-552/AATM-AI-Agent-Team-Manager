"""FastAPI entry point with loopback-oriented security defaults."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api import router
from app.core.config import settings
from app.db import build_engine, make_session_factory
from app.migrate import upgrade_database
from app.models import Agent, AuditEvent
from app.orchestrator_api import router as orchestrator_router
from app.quality_api import router as quality_router
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
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.include_router(router)
    app.include_router(workflow_router)
    app.include_router(provider_router)
    app.include_router(ops_router)
    app.include_router(orchestrator_router)
    app.include_router(quality_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": "AATM", "version": __version__, "api": "/api/v1"}

    return app


app = create_app()
