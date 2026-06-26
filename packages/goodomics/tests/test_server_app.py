from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import goodomics.server.app as server_app
import pytest
from fastapi.testclient import TestClient
from fixtures import write_multiqc_fixture
from goodomics.ingest.multiqc import ingest_multiqc
from goodomics.projects import DEFAULT_PROJECT_ID, new_project_id
from goodomics.server.ai import GoodomicsChatService, ProviderResponse, ProviderToolCall
from goodomics.server.app import create_app
from goodomics.server.logging import build_uvicorn_log_config
from goodomics.server.mcp.server import create_mcp_server
from goodomics.server.query_tools import GoodomicsQueryTools
from goodomics.server.settings import Settings
from goodomics.storage.database import DEFAULT_DATABASE_URL


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )
    with TestClient(create_app()) as test_client:
        yield test_client


def _state(client: TestClient) -> Any:
    return cast(Any, client.app).state


def _portal(client: TestClient) -> Any:
    return cast(Any, client.portal)


def test_health_endpoint_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_debug_log_config_enables_goodomics_package_logger() -> None:
    config = build_uvicorn_log_config("debug")

    assert config["loggers"]["goodomics"] == {
        "handlers": ["default"],
        "level": "DEBUG",
        "propagate": False,
    }
    assert config["loggers"]["uvicorn"]["level"] == "INFO"


def test_project_id_generator_uses_prefixed_lowercase_ref() -> None:
    assert re.fullmatch(r"prj_[a-z]{20}", new_project_id())


def test_project_api_scopes_runs_and_searches_samples(client: TestClient) -> None:
    default_projects = client.get("/api/v1/projects")
    assert default_projects.status_code == 200
    assert any(
        project["project_id"] == DEFAULT_PROJECT_ID
        for project in default_projects.json()
    )

    created = client.post(
        "/api/v1/projects",
        json={"name": "RNA-seq Core", "slug": "rnaseq-core"},
    )
    assert created.status_code == 201
    project = created.json()
    assert re.fullmatch(r"prj_[a-z]{20}", project["project_id"])
    assert project["slug"] == "rnaseq-core"

    client.post(
        "/api/v1/runs",
        json={
            "run_id": "rna-run",
            "project": "rnaseq-core",
            "samples": [{"sample_id": "S1", "sample_name": "Tumor RNA"}],
        },
    )
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "default-run",
            "samples": [{"sample_id": "S2", "sample_name": "Control DNA"}],
        },
    )

    scoped_runs = client.get(f"/api/v1/projects/{project['project_id']}/runs")
    assert scoped_runs.status_code == 200
    assert [run["run_id"] for run in scoped_runs.json()["items"]] == ["rna-run"]

    scoped_run = client.get(f"/api/v1/projects/{project['project_id']}/runs/rna-run")
    assert scoped_run.status_code == 200
    assert scoped_run.json()["project_id"] == project["project_id"]

    search = client.get(
        "/api/v1/search",
        params={"project_id": project["project_id"], "q": "rna"},
    )
    assert search.status_code == 200
    search_body = search.json()
    assert search_body[0]["kind"] == "sample"
    assert search_body[0]["sample_id"] == "S1"
    assert any(
        item["kind"] == "run" and item["run_id"] == "rna-run" for item in search_body
    )

    samples = client.get(f"/api/v1/projects/{project['project_id']}/samples")
    assert samples.status_code == 200
    assert samples.json()["items"][0]["sample_id"] == "S1"
    assert samples.json()["items"][0]["latest_run_id"] == "rna-run"
    assert samples.json()["items"][0]["run_count"] == 1

    sample = client.get(f"/api/v1/projects/{project['project_id']}/samples/S1")
    assert sample.status_code == 200
    assert sample.json()["sample_name"] == "Tumor RNA"

    renamed = client.patch(
        f"/api/v1/projects/{project['project_id']}",
        json={"name": "RNA-seq Production Core"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["project_id"] == project["project_id"]
    assert renamed.json()["name"] == "RNA-seq Production Core"


def test_project_sample_list_and_sample_runs_are_sample_first(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"name": "Sample Core", "slug": "sample-core"},
    ).json()
    project_id = created["project_id"]
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "run-old",
            "project": "sample-core",
            "samples": [{"sample_id": "S1", "sample_name": "Tumor RNA"}],
        },
    )
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "run-new",
            "project": "sample-core",
            "samples": [
                {"sample_id": "S1", "sample_name": "Tumor RNA"},
                {"sample_id": "S2", "sample_name": "Control DNA"},
            ],
        },
    )

    samples = client.get(f"/api/v1/projects/{project_id}/samples")
    assert samples.status_code == 200
    body = samples.json()
    assert body["total"] == 2
    sample_by_id = {sample["sample_id"]: sample for sample in body["items"]}
    assert sample_by_id["S1"]["run_count"] == 2
    assert sample_by_id["S1"]["latest_run_id"] == "run-new"
    assert sample_by_id["S2"]["run_count"] == 1
    assert sample_by_id["S2"]["latest_run_id"] == "run-new"

    runs = client.get(f"/api/v1/projects/{project_id}/samples/S1/runs")
    assert runs.status_code == 200
    run_body = runs.json()
    assert [run["run_id"] for run in run_body] == ["run-new", "run-old"]
    assert run_body[0]["run_sample_id"] == "run-new:S1"


def test_query_tools_resolve_project_and_list_read_only_context(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"name": "RNA-seq Production Core", "slug": "rnaseq-prod"},
    ).json()
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "rna-prod-run",
            "project": "rnaseq-prod",
            "assay": "RNA-seq",
            "samples": [{"sample_id": "S1 Read 1", "sample_name": "Tumor RNA"}],
        },
    )

    tools = GoodomicsQueryTools(_state(client).query_context)

    async def query_context() -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        return (
            await tools.resolve_project("RNA seq production"),
            await tools.list_project_runs(created["project_id"], assay="RNA-seq"),
            await tools.list_project_samples("rnaseq-prod", query="tumor"),
            await tools.get_run("rna-prod-run", project="rnaseq-prod"),
            await tools.list_run_samples("rna-prod-run", project="rnaseq-prod"),
            await tools.list_run_metrics(
                "rna-prod-run", project="rnaseq-prod", metric_query="mapped"
            ),
        )

    resolution, runs, samples, run, run_samples, metrics = _portal(client).call(
        query_context
    )

    assert resolution["status"] == "matched"
    assert resolution["project"]["project_id"] == created["project_id"]
    assert resolution["project"]["app_path"] == f"/project/{created['project_id']}"
    assert runs["runs"][0]["run_id"] == "rna-prod-run"
    assert runs["runs"][0]["app_path"] == (
        f"/project/{created['project_id']}/runs/rna-prod-run"
    )
    assert runs["runs"][0]["markdown_link"] == (
        f"[rna-prod-run](/project/{created['project_id']}/runs/rna-prod-run)"
    )
    assert samples["samples"][0]["sample_id"] == "S1 Read 1"
    assert (
        samples["samples"][0]["app_path"]
        == f"/project/{created['project_id']}/samples/S1%20Read%201"
    )
    assert samples["samples"][0]["markdown_link"] == (
        f"[Tumor RNA](/project/{created['project_id']}/samples/S1%20Read%201)"
    )
    assert run["run"]["sample_count"] == 1
    assert (
        run["run"]["app_path"] == f"/project/{created['project_id']}/runs/rna-prod-run"
    )
    assert run_samples["samples"][0]["sample_name"] == "Tumor RNA"
    assert (
        run_samples["samples"][0]["app_path"]
        == f"/project/{created['project_id']}/samples/S1%20Read%201"
    )
    assert metrics["metrics"] == []


def test_query_tools_return_candidates_for_ambiguous_project(
    client: TestClient,
) -> None:
    client.post("/api/v1/projects", json={"name": "RNA Core", "slug": "rna-core"})
    client.post("/api/v1/projects", json={"name": "RNA Production", "slug": "rna-prod"})

    tools = GoodomicsQueryTools(_state(client).query_context)

    async def resolve() -> dict[str, Any]:
        return await tools.resolve_project("rna")

    resolution = _portal(client).call(resolve)

    assert resolution["status"] == "ambiguous"
    assert len(resolution["candidates"]) >= 2


def test_mcp_server_exposes_read_only_query_tools(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"name": "MCP Project", "slug": "mcp-project"})
    mcp = create_mcp_server(_state(client).query_context)

    async def query_mcp() -> tuple[set[str], dict[str, Any]]:
        tool_names = {tool.name for tool in await mcp.list_tools()}
        _, result = await mcp.call_tool("resolve_project", {"reference": "MCP Project"})
        return tool_names, cast(dict[str, Any], result)

    tool_names, result = _portal(client).call(query_mcp)

    assert {
        "list_projects",
        "resolve_project",
        "get_project_summary",
        "list_recent_runs",
        "list_project_runs",
        "list_project_samples",
        "get_run",
        "list_run_samples",
        "list_run_metrics",
        "list_run_files",
    }.issubset(tool_names)
    assert result["status"] == "matched"


def test_mcp_streamable_http_endpoint_is_mounted_at_single_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    )

    with TestClient(create_app(), base_url="http://localhost:8000") as test_client:
        response = test_client.post(
            "/mcp",
            json={},
            headers={"accept": "application/json, text/event-stream"},
        )
        nested_response = test_client.post(
            "/mcp/mcp",
            json={},
            headers={"accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 400
    assert response.json()["jsonrpc"] == "2.0"
    assert nested_response.status_code == 405


class FakeProvider:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses

    def is_configured(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        if self.responses:
            return self.responses.pop(0)
        return ProviderResponse(content="Done.")


def test_ai_chat_returns_503_without_provider_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "List projects"}]},
    )

    assert response.status_code == 503
    assert "GOODOMICS_AI_API_KEY" in response.json()["detail"]


def test_ai_chat_handles_direct_fake_provider_answer(client: TestClient) -> None:
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider([ProviderResponse(content="There are no failed runs.")]),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "Any failed runs?"}]},
    )

    assert response.status_code == 200
    assert response.json()["message"]["content"] == "There are no failed runs."
    assert response.json()["tool_calls"] == []


def test_ai_chat_executes_multiple_read_only_tool_calls(client: TestClient) -> None:
    project = client.post(
        "/api/v1/projects", json={"name": "AI Project", "slug": "ai-project"}
    ).json()
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider(
            [
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-1",
                            name="resolve_project",
                            arguments={"reference": "AI Project"},
                        ),
                        ProviderToolCall(
                            id="call-2",
                            name="list_projects",
                            arguments={"query": "AI"},
                        ),
                    ]
                ),
                ProviderResponse(content="AI Project is available."),
            ]
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "Find AI Project"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["message"]["content"]
        == f"[AI Project](/project/{project['project_id']}) is available."
    )
    assert [call["name"] for call in body["tool_calls"]] == [
        "resolve_project",
        "list_projects",
    ]
    assert body["tool_calls"][0]["result"]["status"] == "matched"


def test_ai_chat_links_projects_runs_and_samples_from_tool_evidence(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"name": "AI Links Project", "slug": "ai-links"},
    ).json()
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "WT_REP2",
            "project": "ai-links",
            "samples": [
                {
                    "sample_id": "WT_REP2 Read 1",
                    "sample_name": "WT_REP2 Read 1",
                }
            ],
        },
    )
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider(
            [
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-1",
                            name="list_project_runs",
                            arguments={"project": "ai-links"},
                        ),
                        ProviderToolCall(
                            id="call-2",
                            name="list_project_samples",
                            arguments={"project": "ai-links"},
                        ),
                    ]
                ),
                ProviderResponse(
                    content=(
                        "AI Links Project has run WT_REP2 and sample WT_REP2 Read 1."
                    ),
                ),
            ]
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "List links"}]},
    )

    assert response.status_code == 200
    content = response.json()["message"]["content"]
    assert f"[AI Links Project](/project/{project['project_id']})" in content
    assert f"[WT_REP2](/project/{project['project_id']}/runs/WT_REP2)" in content
    assert (
        f"[WT_REP2 Read 1](/project/{project['project_id']}/samples/WT_REP2%20Read%201)"
        in content
    )


def test_ai_chat_links_plain_run_id_lists_from_tool_evidence(
    client: TestClient,
) -> None:
    for run_id in ["WT_REP2", "WT_REP1", "RAP1_UNINDUCED_REP2"]:
        client.post(
            "/api/v1/runs",
            json={"run_id": run_id, "project": DEFAULT_PROJECT_ID},
        )
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider(
            [
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-1",
                            name="list_project_runs",
                            arguments={"project": DEFAULT_PROJECT_ID},
                        )
                    ]
                ),
                ProviderResponse(
                    content=(
                        "The project [Default Project](http://127.0.0.1:8000/project/"
                        f"{DEFAULT_PROJECT_ID}) has 3 runs:\n\n"
                        "1. Run ID: WT_REP2\n"
                        "2. Run ID: WT_REP1\n"
                        "3. Run ID: RAP1_UNINDUCED_REP2"
                    ),
                ),
            ]
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "List runs in this project"}]},
    )

    assert response.status_code == 200
    content = response.json()["message"]["content"]
    assert f"Run ID: [WT_REP2](/project/{DEFAULT_PROJECT_ID}/runs/WT_REP2)" in content
    rap1_link = (
        f"Run ID: [RAP1_UNINDUCED_REP2](/project/{DEFAULT_PROJECT_ID}/runs/"
        "RAP1_UNINDUCED_REP2)"
    )
    assert (rap1_link) in content


def test_ai_chat_preserves_ambiguous_project_resolution(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"name": "RNA Core", "slug": "rna-core"})
    client.post("/api/v1/projects", json={"name": "RNA Production", "slug": "rna-prod"})
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider(
            [
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-1",
                            name="resolve_project",
                            arguments={"reference": "rna"},
                        )
                    ]
                ),
                ProviderResponse(content="I found multiple RNA projects. Which one?"),
            ]
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "Summarize RNA"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tool_calls"][0]["result"]["status"] == "ambiguous"
    assert "multiple RNA projects" in body["message"]["content"]


def test_ai_chat_stops_at_tool_round_limit(client: TestClient) -> None:
    _state(client).query_context.settings.ai_max_tool_rounds = 1
    _state(client).ai_chat = GoodomicsChatService(
        _state(client).query_context,
        provider=FakeProvider(
            [
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-1",
                            name="list_projects",
                            arguments={},
                        )
                    ]
                ),
                ProviderResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-2",
                            name="list_recent_runs",
                            arguments={},
                        )
                    ]
                ),
            ]
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "Keep looking"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "tool round limit" in body["message"]["content"]
    assert [call["name"] for call in body["tool_calls"]] == ["list_projects"]


def test_projects_endpoint_upgrades_legacy_project_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                project_id VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description VARCHAR,
                metadata_json JSON NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (project_id)
            )
            """
        )

    monkeypatch.setenv("GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    with TestClient(create_app()) as test_client:
        response = test_client.get("/api/v1/projects")

    assert response.status_code == 200
    assert any(
        project["project_id"] == DEFAULT_PROJECT_ID for project in response.json()
    )
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(projects)")}
    assert "slug" in columns


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
    file_root = tmp_path / "state" / "files"
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    ingest_multiqc(
        multiqc_dir,
        run_id="run-1",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

    with TestClient(create_app()) as test_client:
        metrics = test_client.get("/api/v1/runs/run-1/analytics/metrics")
        payloads = test_client.get("/api/v1/runs/run-1/analytics/payloads")
        files = test_client.get("/api/v1/runs/run-1/files").json()
        project_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/analytics/metrics"
        )
        project_payloads = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/analytics/payloads"
        )
        sample_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/samples/S1/runs/run-1/analytics/metrics"
        )
        project_files = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/files"
        )
        report = next(file for file in files if file["kind"] == "multiqc_report")
        tables = test_client.get("/api/v1/database/tables").json()
        file_rows = test_client.get("/api/v1/database/tables/files/rows").json()
        import_rows = test_client.get(
            "/api/v1/database/catalog/tables/data_imports/rows"
        ).json()
        catalog_preview = test_client.get(
            "/api/v1/database/catalog/tables/files/rows",
            params={
                "project_id": DEFAULT_PROJECT_ID,
                "limit": 1,
                "sort_by": "file_id",
                "sort_direction": "desc",
            },
        )
        metric_preview = test_client.get(
            "/api/v1/database/analytics/tables/sample_metric_numeric/rows",
            params={
                "project_id": DEFAULT_PROJECT_ID,
                "limit": 2,
                "sort_by": "metric_key",
                "sort_direction": "asc",
            },
        )
        bad_preview = test_client.get(
            "/api/v1/database/analytics/tables/sample_metric_numeric/rows",
            params={"sort_by": "missing_column"},
        )
        content = test_client.get(f"/api/v1/files/{report['file_id']}/content")
        project_content = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/files/{report['file_id']}/content"
        )
        legacy_metrics = test_client.get("/api/v1/runs/run-1/metrics")
        legacy_project_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/metrics"
        )

    assert metrics.status_code == 200
    assert any(
        item["metric_key"] == "general_stats.salmon_percent_mapped"
        for item in metrics.json()
    )
    assert payloads.status_code == 200
    assert any(item["payload_name"] == "salmon_plot" for item in payloads.json())
    assert project_metrics.status_code == 200
    assert project_metrics.json() == metrics.json()
    assert project_payloads.status_code == 200
    assert project_payloads.json() == payloads.json()
    assert sample_metrics.status_code == 200
    assert sample_metrics.json()
    assert all(
        item["sample_key"] == "S1" or item["run_sample_key"] == "run-1:S1"
        for item in sample_metrics.json()
    )
    assert not any(item["sample_key"] == "S1 Read 1" for item in sample_metrics.json())
    assert project_files.status_code == 200
    assert project_files.json() == files
    assert "file_id" in report
    assert any(
        table["store"] == "catalog"
        and table["name"] == "files"
        and "file_id" in table["columns"]
        for table in tables
    )
    assert any(
        table["store"] == "catalog"
        and table["name"] == "data_imports"
        and "data_import_id" in table["columns"]
        for table in tables
    )
    assert any(
        table["store"] == "analytics" and table["name"] == "sample_metric_numeric"
        for table in tables
    )
    assert "file_id" in file_rows[0]
    assert import_rows["rows"][0]["data_import_id"] == "run-1"
    assert catalog_preview.status_code == 200
    assert catalog_preview.json()["total"] >= 1
    assert catalog_preview.json()["rows"][0]["file_id"]
    assert metric_preview.status_code == 200
    assert metric_preview.json()["columns"]
    assert len(metric_preview.json()["rows"]) == 2
    assert metric_preview.json()["sort_by"] == "metric_key"
    assert bad_preview.status_code == 400
    assert content.status_code == 200
    assert "MultiQC" in content.text
    assert project_content.status_code == 200
    assert "MultiQC" in project_content.text
    assert legacy_metrics.status_code == 404
    assert legacy_project_metrics.status_code == 404


def test_database_summary_reports_control_and_analytics_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"
    ingest_multiqc(
        write_multiqc_fixture(tmp_path / "results"),
        run_id="run-1",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

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

    assert Settings().database_url == DEFAULT_DATABASE_URL


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
