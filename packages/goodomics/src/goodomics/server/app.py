"""FastAPI application factory for API, MCP transport, and dashboard serving."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from goodomics.server.ai import GoodomicsChatService
from goodomics.server.api.routes import router
from goodomics.server.db.session import create_store
from goodomics.server.mcp.server import create_mcp_server
from goodomics.server.query_tools import QueryToolContext
from goodomics.server.settings import Settings

STATIC_DIR = Path(__file__).parent / "web" / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"


def _dashboard_setup_response() -> HTMLResponse:
    return HTMLResponse(
        content=(
            "<h1>Dashboard assets not found</h1>"
            "<p>Build the dashboard assets first:</p>"
            "<pre>cd packages/goodomics/dashboard && npm run build</pre>"
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
    """Build the Goodomics server app with API, MCP stream endpoint, and UI routes."""

    settings = Settings()
    store = create_store(settings.database_url)
    query_context = QueryToolContext(settings=settings, store=store)
    ai_chat = GoodomicsChatService(query_context)
    mcp = create_mcp_server(query_context)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield
        engine = store.engine
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="Goodomics API",
        version="0.1.0",
        description=(
            "API for Goodomics runs, samples, metrics, insights, reports, cohorts, "
            "QC policies, MCP integrations, and the React dashboard."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.query_context = query_context
    app.state.ai_chat = ai_chat
    app.include_router(router)
    app.router.routes.extend(
        Route("/mcp", endpoint=route.endpoint, name="mcp")
        for route in mcp_app.routes
        if isinstance(route, Route) and route.path == "/"
    )

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
