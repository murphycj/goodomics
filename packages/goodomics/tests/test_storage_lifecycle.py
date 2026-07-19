from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from goodomics.server.auth import authorize_api_request
from goodomics.server.db.session import SessionDep
from goodomics.server.settings import DatabaseSettings, Settings
from goodomics.storage.duckdb import AnalyticsStoreRegistry
from goodomics.storage.sqlalchemy import (
    ProjectRecord,
    SQLModelGoodomicsStore,
    initialized_store,
)
from sqlmodel import select


def _settings(tmp_path: Path) -> Settings:
    """Return isolated server settings for lifecycle tests."""

    return Settings(
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    )


def test_app_initializes_schema_once_and_disposes_on_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initialize SQL before serving and dispose exactly once on shutdown."""

    from goodomics.server.app import create_app

    app = create_app(_settings(tmp_path))
    store = app.state.store
    ensure_calls = 0
    dispose_calls = 0
    original_ensure = store.ensure_schema
    original_dispose = store.dispose

    async def ensure_schema() -> None:
        """Count application schema initialization calls."""

        nonlocal ensure_calls
        ensure_calls += 1
        await original_ensure()

    async def dispose() -> None:
        """Count application engine disposal calls."""

        nonlocal dispose_calls
        dispose_calls += 1
        await original_dispose()

    monkeypatch.setattr(store, "ensure_schema", ensure_schema)
    monkeypatch.setattr(store, "dispose", dispose)

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200

    assert ensure_calls == 1
    assert dispose_calls == 1


def test_startup_failure_prevents_serving_and_still_disposes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Propagate initialization failures while still releasing the engine."""

    from goodomics.server.app import create_app

    app = create_app(_settings(tmp_path))
    store = app.state.store
    disposed = False

    async def fail_schema() -> None:
        """Simulate catalog initialization failure."""

        raise RuntimeError("schema failed")

    async def dispose() -> None:
        """Record shutdown disposal after failed initialization."""

        nonlocal disposed
        disposed = True

    monkeypatch.setattr(store, "ensure_schema", fail_schema)
    monkeypatch.setattr(store, "dispose", dispose)

    with pytest.raises(RuntimeError, match="schema failed"), TestClient(app):
        pass
    assert disposed


def test_initialized_store_disposes_after_initialization_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release the context-owned engine when schema initialization fails."""

    disposed = False

    async def fail_schema(self: SQLModelGoodomicsStore) -> None:
        raise RuntimeError("schema failed")

    async def dispose(self: SQLModelGoodomicsStore) -> None:
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(SQLModelGoodomicsStore, "ensure_schema", fail_schema)
    monkeypatch.setattr(SQLModelGoodomicsStore, "dispose", dispose)

    async def open_store() -> None:
        async with initialized_store(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}"):
            pytest.fail("store should not be yielded after initialization fails")

    with pytest.raises(RuntimeError, match="schema failed"):
        asyncio.run(open_store())

    assert disposed


def test_request_dependencies_share_sessions_and_requests_are_isolated(
    tmp_path: Path,
) -> None:
    """Reuse one session inside a request and isolate concurrent requests."""

    settings = _settings(tmp_path)
    store = SQLModelGoodomicsStore(settings.database_url)
    asyncio.run(store.ensure_schema())
    app = FastAPI()
    app.state.settings = settings
    app.state.store = store

    async def capture_dependency(request: Request, session: SessionDep) -> None:
        """Capture the authorization-shared dependency session identity."""

        request.state.dependency_session_id = id(session)

    @app.get(
        "/probe",
        dependencies=[Depends(authorize_api_request), Depends(capture_dependency)],
    )
    async def probe(request: Request, session: SessionDep) -> dict[str, int]:
        """Return session identities after overlapping with another request."""

        await asyncio.sleep(0.02)
        return {
            "dependency": request.state.dependency_session_id,
            "handler": id(session),
        }

    async def run_requests() -> list[dict[str, int]]:
        """Execute two overlapping ASGI requests."""

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            responses = await asyncio.gather(client.get("/probe"), client.get("/probe"))
        return [response.json() for response in responses]

    responses = asyncio.run(run_requests())
    assert all(item["dependency"] == item["handler"] for item in responses)
    assert responses[0]["handler"] != responses[1]["handler"]
    asyncio.run(store.dispose())


def test_request_close_rolls_back_uncommitted_work(tmp_path: Path) -> None:
    """Persist explicit commits and discard pending work after endpoint errors."""

    settings = _settings(tmp_path)
    store = SQLModelGoodomicsStore(settings.database_url)
    asyncio.run(store.ensure_schema())
    app = FastAPI()
    app.state.settings = settings
    app.state.store = store

    @app.post("/projects/{project_id}")
    async def write_project(project_id: str, session: SessionDep) -> None:
        """Add a project and fail before commit for one sentinel ID."""

        session.add(
            ProjectRecord(
                project_id=project_id,
                slug=project_id,
                name=project_id,
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        if project_id == "pending":
            raise HTTPException(status_code=500, detail="failed")
        await session.commit()

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/projects/committed").status_code == 200
        assert client.post("/projects/pending").status_code == 500

    async def project_ids() -> set[str]:
        """Read persisted project IDs after both requests close."""

        async with store.session() as session:
            return set((await session.exec(select(ProjectRecord.project_id))).all())

    assert asyncio.run(project_ids()) == {"committed"}
    asyncio.run(store.dispose())


def test_analytics_registry_reuses_normalized_paths_and_initializes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cache stores per path and serialize concurrent first initialization."""

    registry = AnalyticsStoreRegistry()
    path = tmp_path / "nested" / "analytics.duckdb"
    store = registry.get(path)
    assert store is registry.get(path.parent / "." / path.name)

    initialize_calls = 0
    original_initialize = store._initialize_schema

    def initialize_schema() -> None:
        """Count and widen the concurrent initialization window."""

        nonlocal initialize_calls
        initialize_calls += 1
        time.sleep(0.02)
        original_initialize()

    monkeypatch.setattr(store, "_initialize_schema", initialize_schema)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: store.ensure_schema(), range(4)))

    store.ensure_schema()
    assert initialize_calls == 1
    assert registry.get(tmp_path / "other.duckdb") is not store


def test_missing_duckdb_reads_remain_empty_without_creating_a_file(
    tmp_path: Path,
) -> None:
    """Avoid creating project analytics files during empty reads."""

    path = tmp_path / "missing.duckdb"
    store = AnalyticsStoreRegistry().get(path)

    assert store.row_counts()
    assert not path.exists()

    store.ensure_schema()
    assert path.exists()
