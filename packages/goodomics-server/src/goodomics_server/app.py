from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from goodomics_server.api.routes import router
from goodomics_server.db.session import create_store
from goodomics_server.mcp.server import mcp
from goodomics_server.settings import Settings

STATIC_DIR = Path(__file__).parent / "web" / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="Goodomics API",
        version="0.1.0",
        description=(
            "API for Goodomics runs, samples, metrics, reports, cohorts, QC policies, "
            "report templates, MCP integrations, and the React dashboard."
        ),
    )
    app.state.settings = settings
    app.state.store = create_store(settings.database_url)
    app.include_router(router)
    app.mount("/mcp", mcp.streamable_http_app(), name="mcp")

    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="dashboard-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def dashboard_fallback(path: str) -> FileResponse:
        if path.startswith(("api/v1", "mcp")) or not INDEX_HTML.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(INDEX_HTML)

    return app
