from __future__ import annotations

import asyncio
from pathlib import Path

from fixtures import write_cbioportal_fixture, write_multiqc_fixture
from goodomics.cli import app
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore
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


def test_init_creates_default_project(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "goodomics.db"

    result = runner.invoke(
        app,
        ["init", "--database-url", f"sqlite+aiosqlite:///{database_path}"],
    )

    assert result.exit_code == 0
    project = asyncio.run(
        SQLModelGoodomicsStore(f"sqlite+aiosqlite:///{database_path}").get_project(
            DEFAULT_PROJECT_ID
        )
    )
    assert project is not None
    assert project.slug == "default"
    assert project.name == "Default Project"


def test_ingest_command_creates_local_state(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"

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
            "--file-root",
            str(file_root),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested run" in result.stdout
    assert "run-1" in result.stdout
    assert database_path.exists()
    assert analytics_path.exists()
    assert (file_root / "run-1" / "multiqc").exists()
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("run-1")


def test_ingest_command_accepts_cbioportal_type(tmp_path: Path) -> None:
    study_dir = write_cbioportal_fixture(tmp_path / "study")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = runner.invoke(
        app,
        [
            "ingest",
            str(study_dir),
            "--type",
            "cbioportal",
            "--project",
            "demo",
            "--run-id",
            "cbio-run",
            "--database-url",
            f"sqlite+aiosqlite:///{database_path}",
            "--analytics-path",
            str(analytics_path),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested 2 cBioPortal sample runs" in result.stdout
    assert "cbio-run" in result.stdout
    assert database_path.exists()
    assert analytics_path.exists()
    assert DuckDBAnalyticsStore(analytics_path).row_counts()["feature_value_numeric"]


def test_ingest_command_accepts_short_flags(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"

    result = runner.invoke(
        app,
        [
            "ingest",
            str(results_dir),
            "-t",
            "multiqc",
            "-p",
            "demo",
            "-a",
            "rnaseq",
            "-R",
            "short-run",
            "-d",
            f"sqlite+aiosqlite:///{database_path}",
            "-A",
            str(analytics_path),
            "-f",
            str(file_root),
            "-l",
            "debug",
        ],
    )

    assert result.exit_code == 0
    assert "short-run" in result.stdout
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("short-run")


def test_help_alias_uses_short_h() -> None:
    root_help = runner.invoke(app, ["-h"])
    ingest_help = runner.invoke(app, ["ingest", "-h"])

    assert root_help.exit_code == 0
    assert ingest_help.exit_code == 0
    assert root_help.stdout
    assert ingest_help.stdout


def test_default_path_argument_ingests_multiqc_output(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    database_path = tmp_path / "state" / "goodomics.db"
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    file_root = tmp_path / "state" / "files"

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
            "--file-root",
            str(file_root),
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
    file_root = tmp_path / "state" / "files"

    result = runner.invoke(
        app,
        [
            str(results_dir),
            "--database-url",
            f"sqlite+aiosqlite:///{database_path}",
            "--analytics-path",
            str(analytics_path),
            "--file-root",
            str(file_root),
        ],
    )

    assert result.exit_code == 0
    assert "Ingested 2 runs" in result.stdout
    assert "WT_REP1" in result.stdout
    assert "WT_REP2" in result.stdout
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("WT_REP1")
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values("WT_REP2")
    assert (file_root / "WT_REP1" / "multiqc").exists()
    assert (file_root / "WT_REP2" / "multiqc").exists()
