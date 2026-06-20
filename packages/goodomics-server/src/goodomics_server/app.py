from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from goodomics_server.api.routes import router
from goodomics_server.db.session import create_store
from goodomics_server.mcp.server import mcp
from goodomics_server.settings import Settings

STATIC_DIR = Path(__file__).parent / "web" / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"


def _dashboard_setup_response() -> HTMLResponse:
    return HTMLResponse(
        content=(
            "<h1>Dashboard assets not found</h1>"
            "<p>Build the dashboard assets first:</p>"
            "<pre>cd packages/goodomics-server/dashboard && npm run build</pre>"
            "<p>For live dashboard development, set "
            "<code>GOODOMICS_DASHBOARD_DEV_URL</code> (for example "
            "<code>http://127.0.0.1:5173</code>) and run <code>npm run dev</code>.</p>"
        ),
        status_code=503,
    )


def _dashboard_dev_redirect(
    settings: Settings, path: str = ""
) -> RedirectResponse | None:
    if not settings.dashboard_dev_url:
        return None
    base = settings.dashboard_dev_url.rstrip("/")
    suffix = f"/{path}" if path else ""
    return RedirectResponse(url=f"{base}{suffix}", status_code=307)


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

    @app.get("/", include_in_schema=False)
    async def dashboard_index() -> Response:
        if not INDEX_HTML.exists():
            redirect = _dashboard_dev_redirect(settings)
            if redirect is not None:
                return redirect
            return _dashboard_setup_response()
        return FileResponse(INDEX_HTML)

    @app.get("/{path:path}", include_in_schema=False)
    async def dashboard_fallback(path: str) -> Response:
        if path.startswith(("api/v1", "mcp", "assets")):
            raise HTTPException(status_code=404, detail="Not found")
        if not INDEX_HTML.exists():
            redirect = _dashboard_dev_redirect(settings, path)
            if redirect is not None:
                return redirect
            return _dashboard_setup_response()
        return FileResponse(INDEX_HTML)

    return app
