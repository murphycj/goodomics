"""FastAPI application factory for API, MCP transport, and dashboard serving."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from goodomics.server.ai import GoodomicsChatService
from goodomics.server.api.routes import router
from goodomics.server.auth import resolve_principal
from goodomics.server.auth_routes import router as auth_router
from goodomics.server.db.session import create_store
from goodomics.server.mcp.server import create_mcp_server
from goodomics.server.query_tools import QueryToolContext
from goodomics.server.rate_limits import AsyncRateLimiter
from goodomics.server.settings import Settings, load_settings
from goodomics.storage.duckdb import AnalyticsStoreRegistry
from goodomics.storage.files import FileStoreRegistry

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


def _dashboard_static_file(path: str) -> Path | None:
    candidate = (STATIC_DIR / path).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    if candidate.is_file() and candidate != INDEX_HTML.resolve():
        return candidate
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the Goodomics server app with API, MCP stream endpoint, and UI routes."""

    settings = settings or load_settings()
    store = create_store(settings.database_url)
    analytics_stores = AnalyticsStoreRegistry()
    query_context = QueryToolContext(
        settings=settings,
        store=store,
        analytics_stores=analytics_stores,
    )
    ai_chat = GoodomicsChatService(query_context)
    mcp = create_mcp_server(query_context)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await store.ensure_schema()
            async with mcp.session_manager.run():
                yield
        finally:
            await store.dispose()

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
    app.state.analytics_stores = analytics_stores
    app.state.ai_chat = ai_chat
    app.state.file_stores = FileStoreRegistry.from_settings(settings)
    app.state.rate_limiter = AsyncRateLimiter(settings.rate_limits)

    @app.middleware("http")
    async def resolve_mcp_principal(request: Request, call_next):
        # MCP transport routes bypass the FastAPI API router dependencies. Set
        # the same request-scoped principal so shared query tools enforce
        # project visibility and current SQL role permissions.
        if request.url.path == "/mcp" or request.url.path.startswith("/mcp/"):
            async with store.session() as session:
                await resolve_principal(request, session)
        return await call_next(request)

    app.include_router(router)
    app.include_router(auth_router)
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
        static_file = _dashboard_static_file(path)
        if static_file is not None:
            return FileResponse(static_file)
        if not INDEX_HTML.exists():
            redirect = _dashboard_dev_redirect(settings, path)
            if redirect is not None:
                return redirect
            return _dashboard_setup_response()
        return FileResponse(INDEX_HTML)

    return app
