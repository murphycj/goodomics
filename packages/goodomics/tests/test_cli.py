from __future__ import annotations

from pathlib import Path

from fixtures import write_multiqc_fixture
from goodomics.cli import app
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from typer.testing import CliRunner

runner = CliRunner()


def test_report_command_writes_html(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    output_path = tmp_path / "report.html"

    result = runner.invoke(app, ["report", str(results_dir), "--out", str(output_path)])

    assert result.exit_code == 0
    assert "Scanning" in result.stdout
    assert "Writing report" in result.stdout
    assert output_path.exists()
    assert "Goodomics Report" in output_path.read_text(encoding="utf-8")


def test_ingest_command_creates_local_state(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"

    result = runner.invoke(
        app,
        [
            "ingest",
            str(results_dir),
            "--project",
            "demo",
            "--assay",
            "rnaseq",
            "--run-id",
            "run-1",
            "--database-url",
            f"sqlite+aiosqlite:///{database_path}",
            "--analytics-path",
            str(analytics_path),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested run" in result.stdout
    assert "run-1" in result.stdout
    assert database_path.exists()
    assert analytics_path.exists()
    assert (artifact_root / "run-1" / "multiqc").exists()
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("run-1")


def test_default_path_argument_ingests_multiqc_output(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"

    result = runner.invoke(
        app,
        [
            str(results_dir),
            "--run-id",
            "run-default",
            "--database-url",
            f"sqlite+aiosqlite:///{database_path}",
            "--analytics-path",
            str(analytics_path),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested run" in result.stdout
    assert "run-default" in result.stdout
    assert database_path.exists()
    assert analytics_path.exists()
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("run-default")


def test_default_path_argument_splits_multiqc_parent_directory(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    write_multiqc_fixture(
        results_dir / "WT_REP1",
        sample_id="WT_REP1",
        report_prefix="WT_REP1",
    )
    write_multiqc_fixture(
        results_dir / "WT_REP2",
        sample_id="WT_REP2",
        report_prefix="WT_REP2",
    )
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    artifact_root = tmp_path / "state" / "artifacts"

    result = runner.invoke(
        app,
        [
            str(results_dir),
            "--database-url",
            f"sqlite+aiosqlite:///{database_path}",
            "--analytics-path",
            str(analytics_path),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested 2 runs" in result.stdout
    assert "WT_REP1" in result.stdout
    assert "WT_REP2" in result.stdout
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("WT_REP1")
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("WT_REP2")
    assert (artifact_root / "WT_REP1" / "multiqc").exists()
    assert (artifact_root / "WT_REP2" / "multiqc").exists()
