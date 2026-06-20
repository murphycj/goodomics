from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goodomics_server.app import create_app
import goodomics_server.app as server_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_endpoint_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_report_template_round_trips_to_yaml_and_json(client: TestClient) -> None:
    created = client.post(
        "/api/v1/report-templates",
        json={
            "template_id": "rnaseq-qc",
            "name": "RNA-seq QC",
            "config": {"sections": ["summary", "metrics"]},
        },
    )

    assert created.status_code == 201
    patched = client.patch(
        "/api/v1/report-templates/rnaseq-qc",
        json={"description": "Production RNA-seq QC"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Production RNA-seq QC"

    yaml_export = client.get("/api/v1/report-templates/rnaseq-qc/export.yaml")
    assert yaml_export.status_code == 200
    assert "template_id: rnaseq-qc" in yaml_export.text

    json_export = client.get("/api/v1/report-templates/rnaseq-qc/export.json")
    assert json_export.status_code == 200
    assert json_export.json()["config"] == {"sections": ["summary", "metrics"]}


def test_report_render_exports_standalone_html(client: TestClient) -> None:
    rendered = client.post(
        "/api/v1/reports/render",
        json={
            "report_id": "report-1",
            "results": "./examples/rnaseq",
            "title": "RNA report",
        },
    )

    assert rendered.status_code == 201
    html_export = client.get("/api/v1/reports/report-1/export.html")
    assert html_export.status_code == 200
    assert "<h1>RNA report</h1>" in html_export.text


def test_database_editor_rejects_untyped_columns(client: TestClient) -> None:
    client.post("/api/v1/runs", json={"run_id": "demo", "project": "before"})

    rejected = client.patch(
        "/api/v1/database/tables/runs/rows/demo",
        json={"values": {"created_at": "not editable"}},
    )
    assert rejected.status_code == 400

    updated = client.patch(
        "/api/v1/database/tables/runs/rows/demo",
        json={"values": {"project": "after"}, "audit_note": "test update"},
    )
    assert updated.status_code == 200
    assert updated.json()["project"] == "after"


def test_root_serves_dashboard_index_when_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static_dir = tmp_path / "web" / "static"
    static_dir.mkdir(parents=True)
    index_html = static_dir / "index.html"
    index_html.write_text("<html><body>dashboard</body></html>", encoding="utf-8")

    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setattr(server_app, "STATIC_DIR", static_dir)
    monkeypatch.setattr(server_app, "ASSETS_DIR", static_dir / "assets")
    monkeypatch.setattr(server_app, "INDEX_HTML", index_html)

    with TestClient(create_app()) as test_client:
        response = test_client.get("/")

    assert response.status_code == 200
    assert "dashboard" in response.text


def test_root_returns_setup_response_when_dashboard_not_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setattr(server_app, "INDEX_HTML", tmp_path / "missing.html")

    with TestClient(create_app()) as test_client:
        response = test_client.get("/")

    assert response.status_code == 503
    assert "Dashboard assets not found" in response.text


def test_root_redirects_to_dashboard_dev_server_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setenv("GOODOMICS_DASHBOARD_DEV_URL", "http://127.0.0.1:5173")
    monkeypatch.setattr(server_app, "INDEX_HTML", tmp_path / "missing.html")

    with TestClient(create_app()) as test_client:
        response = test_client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_spa_path_redirects_to_dashboard_dev_server_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    monkeypatch.setenv("GOODOMICS_DASHBOARD_DEV_URL", "http://127.0.0.1:5173")
    monkeypatch.setattr(server_app, "INDEX_HTML", tmp_path / "missing.html")

    with TestClient(create_app()) as test_client:
        response = test_client.get("/reports", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://127.0.0.1:5173/reports"
