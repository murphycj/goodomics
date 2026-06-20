from __future__ import annotations

import asyncio
import os
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
DATABASE_URL_OPTION = typer.Option(
    None,
    "--database-url",
    help="Database URL for local Goodomics state.",
)


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


@app.command()
def init(database_url: str | None = DATABASE_URL_OPTION) -> None:
    """Initialize a local Goodomics database."""
    resolved_url = database_url or os.environ.get(
        "GOODOMICS_DATABASE_URL",
        "sqlite+aiosqlite:///./goodomics.db",
    )
    try:
        from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore
    except ImportError as exc:
        raise typer.BadParameter(
            "Database support is not installed. Install `goodomics` for the full "
            "distribution or `goodomics-core[sqlite]` for local SQLite support."
        ) from exc

    try:
        asyncio.run(SQLModelGoodomicsStore(resolved_url).ensure_schema())
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            f"Missing database driver `{exc.name}`. Install `goodomics` for the full "
            "distribution or add the matching `goodomics-core` database extra."
        ) from exc
    console.print(f"Initialized Goodomics database at [bold]{resolved_url}[/bold]")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the Goodomics API, MCP server, and dashboard."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "Server support is not installed. Install `goodomics` for the full "
            "distribution or `goodomics-core[server]` for the server extra."
        ) from exc

    uvicorn.run(
        "goodomics.server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command()
def ui(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the local Goodomics dashboard."""
    serve(host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
