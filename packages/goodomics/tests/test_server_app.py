from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import goodomics.server.app as server_app
import pytest
from fastapi.testclient import TestClient
from fixtures import write_cbioportal_fixture, write_multiqc_fixture
from goodomics.contracts.cbioportal import (
    CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
    CBIOPORTAL_COPY_NUMBER_SEGMENTS,
    CBIOPORTAL_GENE_PANEL_MATRIX,
    CBIOPORTAL_MUTATIONS_MAF,
)
from goodomics.ingest.cbioportal import ingest_cbioportal_study
from goodomics.ingest.multiqc import ingest_multiqc
from goodomics.projects import DEFAULT_PROJECT_ID, new_project_id
from goodomics.server.ai import GoodomicsChatService, ProviderResponse, ProviderToolCall
from goodomics.server.app import create_app
from goodomics.server.insights import (
    compile_insight_result,
    validate_and_explain_config,
)
from goodomics.server.logging import build_uvicorn_log_config
from goodomics.server.mcp.server import create_mcp_server
from goodomics.server.query_tools import GoodomicsQueryTools
from goodomics.server.settings import Settings
from goodomics.storage.database import DEFAULT_DATABASE_URL
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataContractFieldRecord,
    DataContractRecord,
    ProjectRecord,
    RunSampleRecord,
    SampleRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


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


def _scalar(row: tuple[Any, ...] | None) -> Any:
    assert row is not None
    return row[0]


def _sample_pk(database_url: str, sample_id: str) -> int:
    async def load() -> int:
        store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(store._get_engine()) as session:
            row = (
                await session.exec(
                    select(SampleRecord).where(SampleRecord.sample_id == sample_id)
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _run_sample_pk(database_url: str, run_sample_id: str) -> int:
    async def load() -> int:
        store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(store._get_engine()) as session:
            row = (
                await session.exec(
                    select(RunSampleRecord).where(
                        RunSampleRecord.run_sample_id == run_sample_id
                    )
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _field_pk(database_url: str, field_id: str) -> int:
    async def load() -> int:
        store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(store._get_engine()) as session:
            row = (
                await session.exec(
                    select(DataContractFieldRecord).where(
                        DataContractFieldRecord.field_id == field_id
                    )
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _contract_project_ids(database_url: str) -> dict[str, str | None]:
    async def load() -> dict[str, str | None]:
        store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(store._get_engine()) as session:
            rows = (
                await session.exec(
                    select(DataContractRecord, ProjectRecord.project_id)
                    .join(
                        ProjectRecord,
                        cast(Any, DataContractRecord.project_id) == ProjectRecord.id,
                        isouter=True,
                    )
                    .order_by(DataContractRecord.data_contract_id)
                )
            ).all()
        return {row[0].data_contract_id: row[1] for row in rows}

    return asyncio.run(load())


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
            "assay": "RNA-seq",
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
    searched_runs = client.get(
        f"/api/v1/projects/{project['project_id']}/runs",
        params={"search": "rna-seq"},
    )
    assert searched_runs.status_code == 200
    assert searched_runs.json()["total"] == 1
    assert searched_runs.json()["items"][0]["run_id"] == "rna-run"

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

    sample_search = client.get(
        f"/api/v1/projects/{project['project_id']}/samples",
        params={"search": "tumor"},
    )
    assert sample_search.status_code == 200
    assert sample_search.json()["total"] == 1
    assert sample_search.json()["items"][0]["sample_id"] == "S1"

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


def test_control_tables_use_integer_primary_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "state.db"

    monkeypatch.setenv("GOODOMICS_DATABASE_URL", f"sqlite+aiosqlite:///{database_path}")

    with TestClient(create_app()) as test_client:
        response = test_client.get("/api/v1/projects")

    assert response.status_code == 200
    assert any(
        project["project_id"] == DEFAULT_PROJECT_ID for project in response.json()
    )
    readable_id_columns = {
        "projects": "project_id",
        "subjects": "subject_id",
        "samples": "sample_id",
        "data_imports": "data_import_id",
        "runs": "run_id",
        "run_samples": "run_sample_id",
        "data_contracts": "data_contract_id",
        "files": "file_id",
        "sample_sets": "sample_set_id",
    }
    expected_unique_key_columns = {
        table_name: [readable_column]
        for table_name, readable_column in readable_id_columns.items()
    }
    expected_unique_key_columns["data_contracts"] = ["project_id", "data_contract_id"]
    with sqlite3.connect(database_path) as connection:
        for table_name, readable_column in readable_id_columns.items():
            columns = {
                row[1]: {"type": row[2], "notnull": row[3], "pk": row[5]}
                for row in connection.execute(f"PRAGMA table_info({table_name})")
            }
            unique_indexes = [
                row[1]
                for row in connection.execute(f"PRAGMA index_list({table_name})")
                if row[2]
            ]
            unique_index_columns = {
                index_name: [
                    info[2]
                    for info in connection.execute(f"PRAGMA index_info({index_name})")
                ]
                for index_name in unique_indexes
            }

            assert columns["id"]["pk"] == 1
            assert columns["id"]["type"] == "INTEGER"
            assert columns[readable_column]["pk"] == 0
            assert (
                expected_unique_key_columns[table_name] in unique_index_columns.values()
            )


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
    contract_projects = _contract_project_ids(database_url)
    assert contract_projects["salmon:metrics"] == DEFAULT_PROJECT_ID
    assert contract_projects["fastqc:raw:metrics"] == DEFAULT_PROJECT_ID
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

    with TestClient(create_app()) as test_client:
        metrics = test_client.get("/api/v1/runs/run-1:S1:analysis/analytics/metrics")
        payloads = test_client.get("/api/v1/runs/run-1/analytics/payloads")
        files = test_client.get("/api/v1/runs/run-1/files").json()
        project_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/analytics/metrics"
        )
        upstream_project_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1:S1:analysis/analytics/metrics"
        )
        project_payloads = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/analytics/payloads"
        )
        sample_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/samples/S1/runs/run-1:S1:analysis/analytics/metrics"
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
            "/api/v1/database/analytics/tables/sample_metrics/rows",
            params={
                "project_id": DEFAULT_PROJECT_ID,
                "limit": 2,
                "sort_by": "field_id",
                "sort_direction": "asc",
            },
        )
        bad_preview = test_client.get(
            "/api/v1/database/analytics/tables/sample_metrics/rows",
            params={"sort_by": "missing_column"},
        )
        content = test_client.get(f"/api/v1/files/{report['file_id']}/content")
        project_content = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/files/{report['file_id']}/content"
        )
        removed_metrics = test_client.get("/api/v1/runs/run-1/metrics")
        removed_project_metrics = test_client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/runs/run-1/metrics"
        )

    assert metrics.status_code == 200
    percent_mapped_field_id = _field_pk(
        database_url, "general_stats.salmon_percent_mapped"
    )
    s1_sample_id = _sample_pk(database_url, "S1")
    s1_run_sample_id = _run_sample_pk(database_url, "run-1:S1:analysis:S1")
    assert any(item["field_id"] == percent_mapped_field_id for item in metrics.json())
    assert payloads.status_code == 200
    assert payloads.json() == []
    assert project_metrics.status_code == 200
    assert project_metrics.json() == []
    assert upstream_project_metrics.status_code == 200
    assert upstream_project_metrics.json() == metrics.json()
    assert project_payloads.status_code == 200
    assert project_payloads.json() == payloads.json()
    assert sample_metrics.status_code == 200
    assert sample_metrics.json()
    assert all(
        item["sample_id"] == s1_sample_id or item["run_sample_id"] == s1_run_sample_id
        for item in sample_metrics.json()
    )
    assert not any(item["sample_id"] == "S1 Read 1" for item in sample_metrics.json())
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
        table["store"] == "analytics" and table["name"] == "sample_metrics"
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
    assert metric_preview.json()["sort_by"] == "field_id"
    assert bad_preview.status_code == 400
    assert content.status_code == 200
    assert "MultiQC" in content.text
    assert project_content.status_code == 200
    assert "MultiQC" in project_content.text
    assert removed_metrics.status_code == 404
    assert removed_project_metrics.status_code == 404


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
    assert body["total_runs"] == 2
    assert body["total_scalar_metrics"] > 0
    assert body["total_payloads"] == 0


def test_contract_browser_and_contract_first_insight_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"
    ingest_multiqc(
        write_multiqc_fixture(tmp_path / "results"),
        run_id="run-1",
        project="demo",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

    with TestClient(create_app()) as test_client:
        contracts = test_client.get(
            "/api/v1/contracts",
        )
        contract = test_client.get(
            "/api/v1/contracts/salmon:metrics",
        )
        result = test_client.post(
            "/api/v1/insights/execute",
            json={
                "refresh": True,
                "config": {
                    "title": "Average mapping",
                    "visualization": "table",
                    "query": {
                        "source": {
                            "kind": "data_contract",
                            "data_contract_id": "salmon:metrics",
                        },
                        "fields": ["general_stats.salmon_percent_mapped"],
                        "entity": "run_sample",
                        "measures": [
                            {
                                "field": "general_stats.salmon_percent_mapped",
                                "aggregation": "avg",
                                "label": "Average mapped",
                            }
                        ],
                    },
                },
            },
        )
    assert contracts.status_code == 200
    assert any(
        item["data_contract_id"] == "salmon:metrics" for item in contracts.json()
    )
    assert contract.status_code == 200
    field = next(
        item
        for item in contract.json()["fields"]
        if item["field_id"] == "general_stats.salmon_percent_mapped"
    )
    assert field["value_type"] == "numeric"
    assert field["summary"]["non_null_count"] > 0
    assert result.status_code == 200
    rows = result.json()["result"]["rows"]
    assert rows
    assert result.json()["result"]["columns"] == ["run_sample_id", "average_mapped"]


def test_contract_series_charts_match_catalog_field_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    ingest_multiqc(
        write_multiqc_fixture(tmp_path / "results"),
        run_id="run-1",
        project="demo",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))

    field_id = "general_stats.salmon_percent_mapped"
    field_alias = "general_stats_salmon_percent_mapped"
    base_config = {
        "version": 1,
        "title": "Salmon mapped",
        "context": {"kind": "cohort"},
        "mode": "contract_metrics",
        "query": {
            "source": {
                "kind": "data_contract",
                "data_contract_id": "salmon:metrics",
            },
            "fields": [field_id],
            "entity": "run_sample",
            "measures": [],
            "limit": 1000,
        },
        "series": [
            {
                "series_id": "series-0",
                "contract_id": "salmon:metrics",
                "field_id": field_id,
                "name": "Percent mapped",
                "aggregation": "avg",
                "filters": [],
            }
        ],
        "linker": {"kind": "auto"},
        "filters": [],
        "result_policy": {"mode": "preview", "limit": 1000},
        "display": {},
    }

    with TestClient(create_app()) as test_client:
        project_id = test_client.get("/api/v1/projects").json()[0]["project_id"]
        table_config = {
            **base_config,
            "visualization": "table",
            "query": {
                **base_config["query"],
                "columns": [field_alias],
            },
        }
        histogram_config = {
            **base_config,
            "visualization": "histogram",
            "query": {
                **base_config["query"],
                "y": field_alias,
            },
        }
        table_response = test_client.post(
            "/api/v1/insights/execute",
            json={"project_id": project_id, "refresh": True, "config": table_config},
        )
        histogram_response = test_client.post(
            "/api/v1/insights/execute",
            json={
                "project_id": project_id,
                "refresh": True,
                "config": histogram_config,
            },
        )

    assert table_response.status_code == 200
    table_result = table_response.json()["result"]
    assert table_result["rows"]
    assert table_result["columns"] == ["sample_id", "percent_mapped"]
    assert isinstance(table_result["rows"][0]["percent_mapped"], float)

    assert histogram_response.status_code == 200
    histogram_result = histogram_response.json()["result"]
    assert histogram_result["rows"]
    assert histogram_result["columns"] == ["percent_mapped"]
    assert (
        histogram_result["rows"][0]["percent_mapped"]
        == table_result["rows"][0]["percent_mapped"]
    )
    assert histogram_result["echarts_options"]["series"][0]["data"]


def test_contract_browser_scopes_contracts_and_fields_to_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from goodomics.contracts import contract
    from goodomics.custom_parser import ParserOutput, parser

    shared_contract = contract(
        "user:shared:metrics",
        name="Shared project metrics",
        data_type="sample_metrics",
        producer_tool="project-scope-test",
        value_type="numeric",
        query_modes=["sample", "cohort"],
    )

    @parser(key="project-scope-test", contracts=[shared_contract])
    def parse_metric(value: object, out: ParserOutput) -> None:
        metric_name = str(value)
        out.metric(
            metric_name,
            1.0,
            sample_id=f"{metric_name}_sample",
            contract=shared_contract,
        )

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    parse_metric.ingest(
        "alpha_metric",
        project="alpha",
        run_id="alpha-run",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    parse_metric.ingest(
        "beta_metric",
        project="beta",
        run_id="beta-run",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))

    with TestClient(create_app()) as test_client:
        projects = {
            item["slug"]: item["project_id"]
            for item in test_client.get("/api/v1/projects").json()
        }
        alpha_contracts = test_client.get(
            "/api/v1/contracts",
            params={"project_id": projects["alpha"]},
        )
        beta_contract = test_client.get(
            "/api/v1/contracts/user:shared:metrics",
            params={"project_id": projects["beta"]},
        )

    assert alpha_contracts.status_code == 200
    alpha_contract = next(
        item
        for item in alpha_contracts.json()
        if item["data_contract_id"] == "user:shared:metrics"
    )
    alpha_fields = {field["field_id"] for field in alpha_contract["fields"]}
    assert alpha_fields == {"user:shared:metrics:alpha_metric"}

    assert beta_contract.status_code == 200
    beta_fields = {field["field_id"] for field in beta_contract.json()["fields"]}
    assert beta_fields == {"user:shared:metrics:beta_metric"}


def test_contract_browser_keeps_legacy_default_project_contracts_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    store = SQLModelGoodomicsStore(database_url)
    default_project = asyncio.run(store.ensure_default_project())
    other_project = asyncio.run(store.ensure_project("other"))

    async def seed_legacy_contract() -> None:
        async with AsyncSession(store._get_engine()) as session:
            contract = DataContractRecord(
                data_contract_id="multiqc:legacy",
                project_id=None,
                name="Legacy MultiQC",
                data_type="sample_metrics",
            )
            session.add(contract)
            await session.flush()
            assert contract.id is not None
            session.add(
                DataContractFieldRecord(
                    data_contract_id=contract.id,
                    field_id="legacy_metric",
                    field_role="metric",
                    display_name="Legacy metric",
                    value_type="numeric",
                )
            )
            await session.commit()

    asyncio.run(seed_legacy_contract())
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)

    with TestClient(create_app()) as test_client:
        default_contracts = test_client.get(
            "/api/v1/contracts",
            params={"project_id": default_project.project_id},
        )
        default_contract = test_client.get(
            "/api/v1/contracts/multiqc:legacy",
            params={"project_id": default_project.project_id},
        )
        other_contracts = test_client.get(
            "/api/v1/contracts",
            params={"project_id": other_project.project_id},
        )

    assert default_contracts.status_code == 200
    assert any(
        item["data_contract_id"] == "multiqc:legacy"
        for item in default_contracts.json()
    )
    assert default_contract.status_code == 200
    assert {field["field_id"] for field in default_contract.json()["fields"]} == {
        "legacy_metric"
    }
    assert other_contracts.status_code == 200
    assert all(
        item["data_contract_id"] != "multiqc:legacy" for item in other_contracts.json()
    )


def test_cbioportal_contract_browser_fields_and_categorical_pie_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"
    ingest_cbioportal_study(
        write_cbioportal_fixture(tmp_path / "study"),
        data_import_id="run-cbio",
        project="demo",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    sex_field_pk = _field_pk(database_url, "subject:sex")
    with DuckDBAnalyticsStore(analytics_path)._connect() as connection:
        connection.execute(
            "DELETE FROM dim_fields WHERE field_label = ?", ["subject:sex"]
        )
        connection.execute(
            "INSERT INTO dim_fields (field_id, field_label) VALUES (?, ?)",
            [900001, "subject:sex"],
        )
        connection.execute(
            "UPDATE entity_attributes SET field_id = ? WHERE field_id = ?",
            [900001, sex_field_pk],
        )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

    with TestClient(create_app()) as test_client:
        project_id = test_client.get("/api/v1/projects").json()[0]["project_id"]
        contracts = {
            contract_id: test_client.get(f"/api/v1/contracts/{contract_id}")
            for contract_id in [
                CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
                CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
                CBIOPORTAL_COPY_NUMBER_SEGMENTS,
                CBIOPORTAL_GENE_PANEL_MATRIX,
                CBIOPORTAL_MUTATIONS_MAF,
            ]
        }
        result = test_client.post(
            "/api/v1/insights/execute",
            json={
                "project_id": project_id,
                "refresh": True,
                "config": {
                    "title": "Patients by sex",
                    "visualization": "pie",
                    "query": {
                        "source": {
                            "kind": "data_contract",
                            "data_contract_id": CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
                        },
                        "fields": ["subject:sex"],
                        "dimensions": ["subject_sex"],
                        "measures": [
                            {
                                "field": "*",
                                "aggregation": "count",
                                "label": "Count",
                            }
                        ],
                    },
                    "display": {
                        "colors": {
                            "subject:sex": "#7c3aed",
                            "subject_sex": "#7c3aed",
                            "sex": "#7c3aed",
                        }
                    },
                },
            },
        )
        genotype_bar = test_client.post(
            "/api/v1/insights/execute",
            json={
                "project_id": project_id,
                "refresh": True,
                "config": {
                    "title": "Mutations by genotype",
                    "visualization": "bar",
                    "query": {
                        "source": {
                            "kind": "data_contract",
                            "data_contract_id": CBIOPORTAL_MUTATIONS_MAF,
                        },
                        "fields": ["genotype"],
                        "dimensions": ["genotype"],
                        "measures": [
                            {
                                "field": "*",
                                "aggregation": "count",
                                "label": "Count",
                            }
                        ],
                    },
                },
            },
        )

    assert all(response.status_code == 200 for response in contracts.values())
    assert any(
        field["field_id"] == "subject:sex"
        for field in contracts[CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES].json()["fields"]
    )
    assert any(
        field["field_id"] == "call_code"
        for field in contracts[CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS].json()["fields"]
    )
    assert any(
        field["field_id"] == "segment_mean"
        for field in contracts[CBIOPORTAL_COPY_NUMBER_SEGMENTS].json()["fields"]
    )
    assert any(
        field["field_id"] == "data_gene_panel_matrix"
        for field in contracts[CBIOPORTAL_GENE_PANEL_MATRIX].json()["fields"]
    )
    assert any(
        field["display_name"] == "Data Gene Panel Matrix"
        for field in contracts[CBIOPORTAL_GENE_PANEL_MATRIX].json()["fields"]
    )
    assert any(
        field["field_id"] == "allele_fraction"
        for field in contracts[CBIOPORTAL_MUTATIONS_MAF].json()["fields"]
    )
    assert result.status_code == 200
    body = result.json()["result"]
    assert body["columns"] == ["subject_sex", "count"]
    assert {row["subject_sex"] for row in body["rows"]} == {"Female", "Male"}
    pie_series = body["echarts_options"]["series"][0]
    assert "itemStyle" not in pie_series
    slice_colors = [
        item["itemStyle"]["color"] for item in pie_series["data"] if "itemStyle" in item
    ]
    assert len(slice_colors) == 2
    assert len(set(slice_colors)) == 2
    assert genotype_bar.status_code == 200
    genotype_body = genotype_bar.json()["result"]
    assert genotype_body["columns"] == ["genotype", "count"]
    assert genotype_body["rows"] == [{"genotype": "SOMATIC", "count": 1}]


def test_missing_file_content_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/files/missing/content")

    assert response.status_code == 404


def test_server_default_database_matches_cli_local_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOODOMICS_DATABASE_URL", raising=False)

    assert Settings().database_url == DEFAULT_DATABASE_URL


def test_insight_and_report_round_trip_execute_and_cache(
    client: TestClient,
) -> None:
    project = client.get("/api/v1/projects").json()[0]
    project_id = project["project_id"]
    created_run = client.post(
        "/api/v1/runs",
        json={"run_id": "report-run-1", "project_id": project_id, "assay": "rna"},
    )
    assert created_run.status_code == 201

    insight_config = {
        "version": 1,
        "title": "Runs by kind",
        "visualization": "bar",
        "query": {
            "source": {"store": "catalog", "table": "runs"},
            "dimensions": ["run_kind"],
            "measures": [{"field": "*", "aggregation": "count", "label": "Runs"}],
        },
    }
    created_insight = client.post(
        "/api/v1/insights",
        json={
            "insight_id": "runs-by-kind",
            "project_id": project_id,
            "name": "Runs by kind",
            "config": insight_config,
        },
    )
    assert created_insight.status_code == 201
    insight_slug = created_insight.json()["url_slug"]
    assert re.match(r"^ins_[0-9a-f]{10}-runs-by-kind$", insight_slug)

    fetched_insight_by_slug = client.get(f"/api/v1/insights/{insight_slug}")
    assert fetched_insight_by_slug.status_code == 200
    assert fetched_insight_by_slug.json()["insight_id"] == "runs-by-kind"

    first_result = client.post(
        "/api/v1/insights/runs-by-kind/execute",
        json={"project_id": project_id},
    )
    assert first_result.status_code == 200
    assert first_result.json()["result"]["cached"] is False
    second_result = client.post(
        "/api/v1/insights/runs-by-kind/execute",
        json={"project_id": project_id},
    )
    assert second_result.status_code == 200
    assert second_result.json()["result"]["cached"] is True

    created_report = client.post(
        "/api/v1/reports",
        json={
            "report_id": "project-overview",
            "project_id": project_id,
            "name": "Project overview",
            "config": {
                "version": 1,
                "items": [
                    {"insight_id": "runs-by-kind", "x": 0, "y": 0, "w": 6, "h": 4}
                ],
            },
        },
    )
    assert created_report.status_code == 201
    report_slug = created_report.json()["url_slug"]
    assert re.match(r"^rep_[0-9a-f]{10}-project-overview$", report_slug)

    fetched_report_by_slug = client.get(f"/api/v1/reports/{report_slug}")
    assert fetched_report_by_slug.status_code == 200
    assert fetched_report_by_slug.json()["report_id"] == "project-overview"

    yaml_export = client.get("/api/v1/reports/project-overview/export.yaml")
    assert yaml_export.status_code == 200
    assert "report_id: project-overview" in yaml_export.text

    report_result = client.post(
        f"/api/v1/reports/{report_slug}/execute",
        json={"project_id": project_id, "refresh": True},
    )
    assert report_result.status_code == 200
    assert report_result.json()["result"]["insights"][0]["insight_id"] == "runs-by-kind"

    default_project = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"default_report_id": "project-overview"},
    )
    assert default_project.status_code == 200
    assert default_project.json()["default_report_id"] == "project-overview"

    renamed_report = client.patch(
        f"/api/v1/reports/{report_slug}",
        json={"name": "Project summary"},
    )
    assert renamed_report.status_code == 200
    assert renamed_report.json()["url_slug"].endswith("-project-summary")
    assert (
        renamed_report.json()["url_slug"].split("-", 1)[0]
        == report_slug.split("-", 1)[0]
    )
    old_report_slug_after_rename = client.get(f"/api/v1/reports/{report_slug}")
    assert old_report_slug_after_rename.status_code == 200
    assert old_report_slug_after_rename.json()["name"] == "Project summary"

    deleted_report = client.delete(f"/api/v1/reports/{report_slug}")
    assert deleted_report.status_code == 204
    project_after_delete = client.get(f"/api/v1/projects/{project_id}")
    assert project_after_delete.status_code == 200
    assert project_after_delete.json()["default_report_id"] is None
    deleted_insight = client.delete(f"/api/v1/insights/{insight_slug}")
    assert deleted_insight.status_code == 204

    rejected = client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project_id,
            "config": {
                "query": {
                    "source": {"store": "catalog", "table": "runs"},
                    "sql": "DELETE FROM runs",
                }
            },
        },
    )
    assert rejected.status_code == 400


def test_histogram_insight_compiles_numeric_bins() -> None:
    result = compile_insight_result(
        config={
            "title": "Value distribution",
            "visualization": "histogram",
            "query": {"y": "value", "bins": 2},
            "display": {"colors": {"value": "#7c3aed"}},
        },
        columns=["value"],
        rows=[
            {"value": 1},
            {"value": 2},
            {"value": 3},
            {"value": 4},
        ],
        insight_id="value-distribution",
        computed_at=datetime.now(UTC),
        cached=False,
    )

    assert result["visualization"] == "histogram"
    assert result["echarts_options"]["xAxis"]["type"] == "value"
    assert result["echarts_options"]["xAxis"]["name"] == "value"
    assert result["echarts_options"]["xAxis"]["nameLocation"] == "middle"
    assert result["echarts_options"]["xAxis"]["scale"] is True
    assert "min" not in result["echarts_options"]["xAxis"]
    assert "max" not in result["echarts_options"]["xAxis"]
    assert result["echarts_options"]["yAxis"]["nameLocation"] == "middle"
    assert result["echarts_options"]["series"][0]["type"] == "bar"
    assert result["echarts_options"]["series"][0]["itemStyle"]["color"] == "#7c3aed"
    assert result["echarts_options"]["series"][0]["data"] == [
        {"name": "1-2.5", "value": [1.75, 2]},
        {"name": "2.5-4", "value": [3.25, 2]},
    ]


def test_histogram_insight_compiles_multiple_numeric_series() -> None:
    result = compile_insight_result(
        config={
            "title": "Two distributions",
            "visualization": "histogram",
            "query": {"fields": ["age", "tmb"], "bins": 2},
            "display": {"colors": {"age": "#38bdf8", "tmb": "#7c3aed"}},
        },
        columns=["sample_id", "age", "tmb"],
        rows=[
            {"sample_id": "S1", "age": 30, "tmb": 1},
            {"sample_id": "S2", "age": 40, "tmb": 2},
            {"sample_id": "S3", "age": 50, "tmb": 3},
            {"sample_id": "S4", "age": 60, "tmb": 4},
        ],
        insight_id="two-distributions",
        computed_at=datetime.now(UTC),
        cached=False,
    )

    series = result["echarts_options"]["series"]
    assert [item["name"] for item in series] == ["age", "tmb"]
    assert [item["itemStyle"]["color"] for item in series] == ["#38bdf8", "#7c3aed"]
    assert [item["itemStyle"]["opacity"] for item in series] == [0.48, 0.48]


def test_insight_catalog_and_validator_explain_new_config(client: TestClient) -> None:
    catalog = client.get("/api/v1/insights/catalog")
    validation = client.post(
        "/api/v1/insights/validate",
        json={
            "config": {
                "visualization": "scatter",
                "mode": "comparison",
                "series": [
                    {
                        "contract_id": "salmon:metrics",
                        "field_id": "general_stats.salmon_percent_mapped",
                    },
                    {
                        "contract_id": "fastqc:raw:metrics",
                        "field_id": "general_stats.fastqc_raw_percent_gc",
                    },
                ],
                "linker": {"kind": "sample"},
                "result_policy": {"mode": "preview"},
            }
        },
    )

    assert catalog.status_code == 200
    body = catalog.json()
    assert {chart["id"] for chart in body["charts"]} >= {"scatter", "table"}
    assert {mode["id"] for mode in body["modes"]} >= {
        "contract_metrics",
        "comparison",
        "advanced_sql",
    }
    assert validation.status_code == 200
    validation_body = validation.json()
    assert validation_body["valid"] is True
    assert "matched by sample" in validation_body["explanation"]


def test_scatter_requires_two_numeric_measures_and_visible_linker() -> None:
    with pytest.raises(ValueError, match="visible Matched by"):
        compile_insight_result(
            config={
                "visualization": "scatter",
                "linker": {"kind": "auto"},
                "query": {"x": "x", "y": "y"},
            },
            columns=["sample_id", "x", "y"],
            rows=[{"sample_id": "S1", "x": 1, "y": 2}],
            insight_id=None,
            computed_at=datetime.now(UTC),
            cached=False,
        )

    with pytest.raises(ValueError, match="exactly two numeric"):
        compile_insight_result(
            config={
                "visualization": "scatter",
                "linker": {"kind": "sample"},
                "query": {"x": "x", "y": "y"},
            },
            columns=["sample_id", "x", "y"],
            rows=[{"sample_id": "S1", "x": 1, "y": "high"}],
            insight_id=None,
            computed_at=datetime.now(UTC),
            cached=False,
        )


def test_line_area_and_stacked_bar_series_rules() -> None:
    line = compile_insight_result(
        config={"visualization": "line"},
        columns=["sample_id", "rna", "protein"],
        rows=[
            {"sample_id": "S1", "rna": 1.2, "protein": 3.4},
            {"sample_id": "S2", "rna": 2.0, "protein": 4.1},
        ],
        insight_id=None,
        computed_at=datetime.now(UTC),
        cached=False,
    )
    assert [series["name"] for series in line["echarts_options"]["series"]] == [
        "rna",
        "protein",
    ]

    area = compile_insight_result(
        config={"visualization": "area"},
        columns=["sample_id", "rna"],
        rows=[{"sample_id": "S1", "rna": 1.2}],
        insight_id=None,
        computed_at=datetime.now(UTC),
        cached=False,
    )
    assert area["echarts_options"]["series"][0]["areaStyle"] == {}

    stacked = compile_insight_result(
        config={
            "visualization": "stacked_bar",
            "_runtime": {"series_aliases": ["kras", "kras_2"]},
        },
        columns=["sample_id", "kras", "kras_2"],
        rows=[{"sample_id": "S1", "kras": 1.0, "kras_2": 2.0}],
        insight_id=None,
        computed_at=datetime.now(UTC),
        cached=False,
    )
    assert [series["name"] for series in stacked["echarts_options"]["series"]] == [
        "kras",
        "kras_2",
    ]
    assert all(
        series["stack"] == "total" for series in stacked["echarts_options"]["series"]
    )


def test_invalid_non_numeric_chart_errors_and_pie_validation() -> None:
    with pytest.raises(ValueError, match="line charts require numeric fields"):
        compile_insight_result(
            config={"visualization": "line"},
            columns=["sample_id", "status"],
            rows=[{"sample_id": "S1", "status": "pass"}],
            insight_id=None,
            computed_at=datetime.now(UTC),
            cached=False,
        )

    invalid = validate_and_explain_config(
        {
            "visualization": "pie",
            "series": [
                {"contract_id": "p", "field_id": "a"},
                {"contract_id": "p", "field_id": "b"},
            ],
        }
    )
    assert invalid["valid"] is False
    assert invalid["messages"][0]["code"] == "too_many_series"


def test_plot_table_and_result_size_policies(client: TestClient) -> None:
    project_id = client.get("/api/v1/projects").json()[0]["project_id"]
    for index in range(6):
        response = client.post(
            "/api/v1/runs",
            json={
                "run_id": f"policy-run-{index}",
                "project_id": project_id,
                "assay": "rna",
            },
        )
        assert response.status_code == 201

    more_rows = client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project_id,
            "refresh": True,
            "config": {
                "visualization": "table",
                "query": {
                    "source": {"store": "catalog", "table": "runs"},
                    "columns": ["run_id", "run_kind"],
                },
                "result_policy": {"mode": "more_rows", "limit": 3},
            },
        },
    )
    random_rows = client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project_id,
            "refresh": True,
            "config": {
                "visualization": "table",
                "query": {
                    "source": {"store": "catalog", "table": "runs"},
                    "columns": ["run_id", "run_kind"],
                },
                "result_policy": {
                    "mode": "random_sample",
                    "sample_size": 2,
                    "seed": "fixed",
                },
            },
        },
    )
    exported = client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project_id,
            "refresh": True,
            "config": {
                "visualization": "table",
                "query": {
                    "source": {"store": "catalog", "table": "runs"},
                    "columns": ["run_id", "run_kind"],
                },
                "result_policy": {"mode": "export_full_data"},
            },
        },
    )

    assert more_rows.status_code == 200
    more_body = more_rows.json()["result"]
    assert more_body["result_policy"]["embedded_row_count"] == 3
    assert len(more_body["plot_table"]["rows"]) == 3
    assert random_rows.status_code == 200
    assert random_rows.json()["result"]["result_policy"]["embedded_row_count"] == 2
    assert exported.status_code == 200
    artifact = exported.json()["result"]["result_policy"]["artifact"]
    assert Path(artifact["path"]).exists()


def test_sample_set_context_endpoint_uses_canonical_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"
    study_path = write_cbioportal_fixture(tmp_path / "study")
    (study_path / "case_lists" / "case_list_demo.txt").write_text(
        "\n".join(
            [
                "stable_id: demo_cases",
                "case_list_name: Demo cohort",
                "case_list_category: selected_samples",
                "case_list_ids: S1 S2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ingest_cbioportal_study(
        study_path,
        data_import_id="run-cbio",
        project="demo",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    monkeypatch.setenv("GOODOMICS_FILE_ROOT", str(file_root))

    with TestClient(create_app()) as test_client:
        project_id = test_client.get("/api/v1/projects").json()[0]["project_id"]
        response = test_client.get(
            "/api/v1/sample-sets",
            params={"project_id": project_id, "kind": "cohort"},
        )

    assert response.status_code == 200
    sample_sets = response.json()
    assert sample_sets
    assert sample_sets[0]["sample_set_id"].startswith("run-cbio:")
    assert sample_sets[0]["member_count"] > 0
    assert sample_sets[0]["updated_at"]


def test_project_sample_group_lifecycle(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects",
        json={"name": "Sample Group Project", "slug": "sample-groups"},
    )
    assert created.status_code == 201
    project_id = created.json()["project_id"]
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "run-old",
            "project": "sample-groups",
            "samples": [
                {"sample_id": "S1", "sample_name": "Tumor A"},
                {"sample_id": "S2", "sample_name": "Normal B"},
            ],
        },
    )
    client.post(
        "/api/v1/runs",
        json={
            "run_id": "run-new",
            "project": "sample-groups",
            "samples": [{"sample_id": "S1", "sample_name": "Tumor A"}],
        },
    )

    created_group = client.post(
        f"/api/v1/projects/{project_id}/sample-groups",
        json={
            "name": "Responders",
            "description": "Samples with response",
            "sample_ids": ["S1", "S2"],
        },
    )
    assert created_group.status_code == 201
    group = created_group.json()
    assert group["sample_set_id"].startswith("sample-set-")
    assert re.match(r"^sg_[0-9a-f]{10}-responders$", group["url_slug"])
    assert group["kind"] == "cohort"
    assert group["member_count"] == 2
    assert group["updated_at"]

    listed = client.get(
        f"/api/v1/projects/{project_id}/sample-groups",
        params={"search": "responders"},
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["total"] == 1
    assert listed_body["items"][0]["sample_set_id"] == group["sample_set_id"]
    assert listed_body["items"][0]["url_slug"] == group["url_slug"]

    fetched = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Responders"
    assert fetched.json()["member_count"] == 2

    fetched_by_slug = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['url_slug']}"
    )
    assert fetched_by_slug.status_code == 200
    assert fetched_by_slug.json()["sample_set_id"] == group["sample_set_id"]

    members = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}/members"
    )
    assert members.status_code == 200
    member_body = members.json()
    assert member_body["total"] == 2
    members_by_sample = {item["sample_id"]: item for item in member_body["items"]}
    assert members_by_sample["S1"]["run_sample_id"] == "run-new:S1"
    assert members_by_sample["S1"]["run_id"] == "run-new"
    assert members_by_sample["S2"]["run_sample_id"] == "run-old:S2"

    duplicate_add = client.post(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}/members",
        json={"sample_ids": ["S1"]},
    )
    assert duplicate_add.status_code == 200
    assert duplicate_add.json()["member_count"] == 2

    renamed = client.patch(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}",
        json={"name": "Clinical responders", "kind": "reference_set"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Clinical responders"
    assert renamed.json()["kind"] == "reference_set"
    assert renamed.json()["url_slug"].endswith("-clinical-responders")
    assert (
        renamed.json()["url_slug"].split("-", 1)[0]
        == group["url_slug"].split("-", 1)[0]
    )

    old_slug_after_rename = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['url_slug']}"
    )
    assert old_slug_after_rename.status_code == 200
    assert old_slug_after_rename.json()["name"] == "Clinical responders"

    removed = client.request(
        "DELETE",
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}/members",
        json={"run_sample_ids": ["run-new:S1"]},
    )
    assert removed.status_code == 200
    assert removed.json()["member_count"] == 1

    remaining = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}/members"
    )
    assert remaining.status_code == 200
    assert remaining.json()["total"] == 1
    assert remaining.json()["items"][0]["sample_id"] == "S2"

    deleted = client.delete(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}"
    )
    assert deleted.status_code == 204
    empty = client.get(f"/api/v1/projects/{project_id}/sample-groups")
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    missing = client.get(
        f"/api/v1/projects/{project_id}/sample-groups/{group['sample_set_id']}"
    )
    assert missing.status_code == 404


def test_report_render_exports_standalone_html(client: TestClient) -> None:
    rendered = client.post(
        "/api/v1/reports/render",
        json={
            "rendered_report_id": "rendered-report-1",
            "results": "./examples/rnaseq",
            "title": "RNA report",
        },
    )

    assert rendered.status_code == 201
    html_export = client.get("/api/v1/rendered-reports/rendered-report-1/export.html")
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
