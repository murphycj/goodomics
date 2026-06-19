from __future__ import annotations

from fastapi import FastAPI

from goodomics_server.api.routes import router
from goodomics_server.db.session import create_store
from goodomics_server.settings import Settings


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="Goodomics API",
        version="0.1.0",
        description="API for Goodomics runs, samples, metrics, cohorts, reports, and QC decisions.",
    )
    app.state.settings = settings
    app.state.store = create_store(settings.database_url)
    app.include_router(router)
    return app
