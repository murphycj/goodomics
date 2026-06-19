from __future__ import annotations

from pathlib import Path

from goodomics.cli import app
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


def test_ingest_command_prints_payload(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "ingest",
            str(results_dir),
            "--project",
            "demo",
            "--report",
            "weekly",
            "--cohort",
            "alpha",
            "--run-id",
            "run-1",
        ],
    )

    assert result.exit_code == 0
    assert "Ingesting run" in result.stdout
    assert "run-1" in result.stdout
    assert "weekly" in result.stdout
