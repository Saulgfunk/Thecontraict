from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.routers import deadlines, organizations, workspaces


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
    app.include_router(deadlines.router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
