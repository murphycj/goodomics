from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from goodomics.ingest.scanner import build_ingest_request
from goodomics.report.html import load_report_template, write_report

app = typer.Typer(help="Cohort-aware QC for omics pipelines.")
console = Console()
RESULTS_ARGUMENT = typer.Argument(..., help="Pipeline results directory.")
REPORT_OUT_OPTION = typer.Option(Path("goodomics_report.html"), "--out", "-o")
TEMPLATE_OPTION = typer.Option(None, "--template", help="YAML or JSON report template config.")
PROJECT_OPTION = typer.Option(None, "--project")
REPORT_OPTION = typer.Option(None, "--report")
COHORT_OPTION = typer.Option(None, "--cohort")
RUN_ID_OPTION = typer.Option(None, "--run-id")


@app.command()
def report(
    results: Path = RESULTS_ARGUMENT,
    out: Path = REPORT_OUT_OPTION,
    template: Path | None = TEMPLATE_OPTION,
) -> None:
    """Generate a standalone Goodomics HTML report."""
    console.print(f"Scanning [bold]{results}[/bold]")
    write_report(results, out, template=load_report_template(template))
    console.print(f"Writing report to [bold]{out}[/bold]")


@app.command()
def ingest(
    results: Path = RESULTS_ARGUMENT,
    project: str | None = PROJECT_OPTION,
    report_name: str | None = REPORT_OPTION,
    cohort: str | None = COHORT_OPTION,
    run_id: str | None = RUN_ID_OPTION,
) -> None:
    """Ingest a run into a local or remote Goodomics store."""
    payload = build_ingest_request(
        results,
        project=project,
        report_name=report_name,
        cohort=cohort,
        run_id=run_id,
    )
    console.print("Ingesting run")
    console.print(payload)


if __name__ == "__main__":
    app()
