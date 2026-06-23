from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fixtures import write_multiqc_fixture
from goodomics.ingest.multiqc import ingest_multiqc, ingest_multiqc_runs
from goodomics.parsers.multiqc import discover_multiqc_outputs, parse_multiqc_bundle
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import ArtifactRecord, SQLModelGoodomicsStore
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


def test_discover_multiqc_outputs(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)

    outputs = discover_multiqc_outputs(multiqc_dir)

    assert len(outputs) == 1
    assert outputs[0].report_html == multiqc_dir / "demo_multiqc_report.html"
    assert outputs[0].data_dir.name == "demo_multiqc_report_data"


def test_parse_multiqc_bundle_extracts_metrics_sources_versions_and_payloads(
    tmp_path: Path,
) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)

    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")

    metric_keys = {metric.metric_key for metric in parsed.metrics}
    assert "general_stats.salmon_percent_mapped" in metric_keys
    assert "multiqc_salmon.percent_mapped" in metric_keys
    assert parsed.data_sources[0].source_path == "/work/S1/libParams/flenDist.txt"
    assert {version.tool for version in parsed.tool_versions} == {"fastqc", "salmon"}
    salmon_payloads = [
        payload for payload in parsed.payloads if payload.payload_name == "salmon_plot"
    ]
    assert len(salmon_payloads) == 1
    assert salmon_payloads[0].sample_id == "S1"
    assert salmon_payloads[0].columns == ["Sample", "0", "1", "2"]


def test_duckdb_store_round_trips_metrics_and_payloads(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)
    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")

    store.replace_run_data(
        "run-1",
        metrics=parsed.metrics,
        definitions=parsed.definitions,
        payloads=parsed.payloads,
        tool_versions=parsed.tool_versions,
        data_sources=parsed.data_sources,
    )

    metrics = store.list_metric_values("run-1")
    payloads = store.list_table_payloads("run-1")

    assert any(metric.metric_key == "general_stats.salmon_percent_mapped" for metric in metrics)
    assert any(payload.payload_name == "salmon_plot" for payload in payloads)
    assert payloads[0].rows


def test_duckdb_store_keeps_json_looking_string_metrics_as_strings(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path)
    parsed = parse_multiqc_bundle(multiqc_dir, run_id="run-1")
    store = DuckDBAnalyticsStore(tmp_path / "analytics.duckdb")

    parsed.sample_metric_string[0] = parsed.sample_metric_string[0].model_copy(
        update={"value": "[330, 612, 1140, 1989, 4614]"}
    )
    store.replace_run_data("run-1", parsed.to_batch(run_id="run-1"))

    metrics = store.list_metric_values("run-1")

    assert any(
        metric.value == "[330, 612, 1140, 1989, 4614]"
        for metric in metrics
        if metric.metric_key == parsed.sample_metric_string[0].metric_key
    )


def test_ingest_multiqc_creates_control_analytics_and_artifacts(tmp_path: Path) -> None:
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-1",
        project="demo",
        assay="rnaseq",
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
    )

    assert result.metrics_ingested > 0
    assert analytics_path.exists()
    assert (artifact_root / "run-1" / "multiqc").exists()

    control_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(control_store.get_run("run-1"))
    assert run is not None
    assert run.project == "demo"

    async def load_artifacts() -> list[ArtifactRecord]:
        async with AsyncSession(control_store._get_engine()) as session:
            rows = (
                await session.exec(
                    select(ArtifactRecord).where(ArtifactRecord.run_id == "run-1")
                )
            ).all()
        return list(rows)

    artifacts = asyncio.run(load_artifacts())
    assert {artifact.kind for artifact in artifacts} == {"multiqc_data", "multiqc_report"}


def test_ingest_multiqc_defaults_to_project_analytics_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    artifact_root = tmp_path / "state" / "artifacts"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-default-project",
        database_url=database_url,
        artifact_root=artifact_root,
    )

    expected_path = Path(".goodomics") / "projects" / DEFAULT_PROJECT_ID / "analytics.duckdb"
    assert result.analytics_path == expected_path
    assert (tmp_path / expected_path).exists()
    assert DuckDBAnalyticsStore(expected_path).list_metric_values("run-default-project")


def test_ingest_multiqc_project_slug_uses_generated_project_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    artifact_root = tmp_path / "state" / "artifacts"

    result = ingest_multiqc(
        multiqc_dir,
        run_id="run-project-slug",
        project="rnaseq-core",
        database_url=database_url,
        artifact_root=artifact_root,
    )

    control_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(control_store.get_run("run-project-slug"))
    assert run is not None
    assert run.project_id is not None
    assert run.project_id.startswith("prj_")
    assert run.project_id != "rnaseq-core"
    assert result.analytics_path == (
        Path(".goodomics") / "projects" / run.project_id / "analytics.duckdb"
    )


def test_ingest_multiqc_runs_splits_parent_results_directory(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    write_multiqc_fixture(
        results_dir / "WT_REP1",
        sample_id="WT_REP1",
        report_prefix="WT_REP1",
    )
    write_multiqc_fixture(
        results_dir / "RAP1_IAA_30M_REP1",
        sample_id="RAP1_IAA_30M_REP1",
        report_prefix="RAP1_IAA_30M_REP1",
    )
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"

    results = ingest_multiqc_runs(
        results_dir,
        project="demo",
        assay="rnaseq",
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
    )

    run_ids = {result.run_id for result in results}
    assert run_ids == {"RAP1_IAA_30M_REP1", "WT_REP1"}
    assert all(result.outputs_found == 1 for result in results)

    control_store = SQLModelGoodomicsStore(database_url)
    wt_run = asyncio.run(control_store.get_run("WT_REP1"))
    rap1_run = asyncio.run(control_store.get_run("RAP1_IAA_30M_REP1"))
    assert wt_run is not None
    assert rap1_run is not None
    assert "WT_REP1" in {sample.sample_id for sample in wt_run.samples}
    assert "RAP1_IAA_30M_REP1" in {sample.sample_id for sample in rap1_run.samples}
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("WT_REP1")
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("RAP1_IAA_30M_REP1")
    assert (artifact_root / "WT_REP1" / "multiqc").exists()
    assert (artifact_root / "RAP1_IAA_30M_REP1" / "multiqc").exists()
