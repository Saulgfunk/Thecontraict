from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import (
    amendments,
    chat,
    contracts,
    deadlines,
    documents_out,
    internal,
    notifications,
    organizations,
    workspaces,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TheContrAIct API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(organizations.router)
    app.include_router(workspaces.router)
    app.include_router(contracts.router)
    app.include_router(amendments.router)
    app.include_router(deadlines.router)
    app.include_router(notifications.router)
    app.include_router(chat.router)
    app.include_router(documents_out.router)
    app.include_router(internal.router)

    @app.get("/config", tags=["system"])
    def public_config() -> dict[str, bool]:
        """Feature flags the web app adapts to (no secrets)."""
        return {"ai_enabled": get_settings().ai_enabled}

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
