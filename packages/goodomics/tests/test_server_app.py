from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import goodomics.server.app as server_app
import pytest
from fastapi.testclient import TestClient
from fixtures import write_multiqc_fixture
from goodomics.ingest.multiqc import ingest_multiqc
from goodomics.server.app import create_app
from goodomics.server.settings import Settings


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


def test_runs_endpoint_paginates_results(client: TestClient) -> None:
    for index in range(5):
        client.post(
            "/api/v1/runs",
            json={"run_id": f"run-{index}", "project": "pagination"},
        )

    response = client.get("/api/v1/runs?limit=2&offset=2")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2


def test_run_analytics_and_file_content_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    ingest_multiqc(
        multiqc_dir,
        run_id="run-1",
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_ARTIFACT_ROOT", str(artifact_root))

    with TestClient(create_app()) as test_client:
        metrics = test_client.get("/api/v1/runs/run-1/analytics/metrics")
        payloads = test_client.get("/api/v1/runs/run-1/analytics/payloads")
        files = test_client.get("/api/v1/runs/run-1/files").json()
        report = next(file for file in files if file["kind"] == "multiqc_report")
        tables = test_client.get("/api/v1/database/tables").json()
        file_rows = test_client.get("/api/v1/database/tables/files/rows").json()
        content = test_client.get(f"/api/v1/files/{report['file_id']}/content")
        content_by_id = test_client.get(f"/api/v1/files/{report['id']}/content")

    assert metrics.status_code == 200
    assert any(
        item["metric_key"] == "general_stats.salmon_percent_mapped"
        for item in metrics.json()
    )
    assert payloads.status_code == 200
    assert any(item["payload_name"] == "salmon_plot" for item in payloads.json())
    assert "file_id" in report
    assert "artifact_id" not in report
    assert any(table["name"] == "files" for table in tables)
    assert all(table["name"] != "artifacts" for table in tables)
    assert "file_id" in file_rows[0]
    assert "artifact_id" not in file_rows[0]
    assert content.status_code == 200
    assert "MultiQC" in content.text
    assert content_by_id.status_code == 200
    assert "MultiQC" in content_by_id.text


def test_database_summary_reports_control_and_analytics_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"
    ingest_multiqc(
        write_multiqc_fixture(tmp_path / "results"),
        run_id="run-1",
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_ARTIFACT_ROOT", str(artifact_root))

    with TestClient(create_app()) as test_client:
        response = test_client.get("/api/v1/database/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["sqlite_size_bytes"] > 0
    assert body["duckdb_size_bytes"] > 0
    assert body["file_size_bytes"] > 0
    assert body["total_runs"] == 1
    assert body["total_scalar_metrics"] > 0
    assert body["total_payloads"] > 0


def test_missing_file_content_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/files/missing/content")

    assert response.status_code == 404


def test_server_default_database_matches_cli_local_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOODOMICS_DATABASE_URL", raising=False)

    assert Settings().database_url == "sqlite+aiosqlite:///.goodomics/goodomics.db"


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
