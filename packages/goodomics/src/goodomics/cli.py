from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console
from typer.core import TyperGroup

from goodomics.ingest.multiqc import ingest_multiqc_runs
from goodomics.report.html import load_report_template, write_report


class GoodomicsTyperGroup(TyperGroup):
    def resolve_command(
        self,
        ctx: typer.Context,
        args: list[str],
    ) -> tuple[str | None, object | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except Exception as exc:
            if (
                exc.__class__.__name__ == "UsageError"
                and args
                and _is_existing_path_arg(args[0])
            ):
                return "__default__", self.commands["__default__"], args
            raise


app = typer.Typer(cls=GoodomicsTyperGroup, help="Cohort-aware QC for omics pipelines.")
console = Console()
RESULTS_ARGUMENT = typer.Argument(..., help="Pipeline results directory.")
REPORT_OUT_OPTION = typer.Option(Path("goodomics_report.html"), "--out", "-o")
TEMPLATE_OPTION = typer.Option(None, "--template", help="YAML or JSON report template config.")
PROJECT_OPTION = typer.Option(None, "--project")
ASSAY_OPTION = typer.Option(None, "--assay")
REPORT_OPTION = typer.Option(None, "--report")
COHORT_OPTION = typer.Option(None, "--cohort")
RUN_ID_OPTION = typer.Option(None, "--run-id")
DATABASE_URL_OPTION = typer.Option(
    None,
    "--database-url",
    help="Database URL for local Goodomics state.",
)
ANALYTICS_PATH_OPTION = typer.Option(
    Path(".goodomics/analytics.duckdb"),
    "--analytics-path",
    help="DuckDB analytics database path.",
)
ARTIFACT_ROOT_OPTION = typer.Option(
    Path(".goodomics/artifacts"),
    "--artifact-root",
    help="Local artifact storage root.",
)
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///.goodomics/goodomics.db"


def _is_existing_path_arg(value: str) -> bool:
    if value.startswith("-"):
        return False
    return Path(value).exists()


def _run_multiqc_ingest(
    results: Path,
    *,
    project: str | None,
    assay: str | None,
    run_id: str | None,
    database_url: str | None,
    analytics_path: Path,
    artifact_root: Path,
) -> None:
    resolved_database_url = database_url or os.environ.get(
        "GOODOMICS_DATABASE_URL",
        DEFAULT_DATABASE_URL,
    )
    try:
        results_ingested = ingest_multiqc_runs(
            results,
            project=project,
            assay=assay,
            run_id=run_id,
            database_url=resolved_database_url,
            analytics_path=analytics_path,
            artifact_root=artifact_root,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if len(results_ingested) == 1:
        result = results_ingested[0]
        console.print(f"Ingested run [bold]{result.run_id}[/bold]")
    else:
        console.print(f"Ingested [bold]{len(results_ingested)}[/bold] runs")
    for result in results_ingested:
        console.print(
            {
                "run_id": result.run_id,
                "outputs_found": result.outputs_found,
                "metrics_ingested": result.metrics_ingested,
                "payloads_ingested": result.payloads_ingested,
                "artifacts_stored": result.artifacts_stored,
                "database_url": result.database_url,
                "analytics_path": str(result.analytics_path),
                "artifact_root": str(result.artifact_root),
            }
        )


@app.command(name="__default__", hidden=True)
def default_ingest(
    results: Path = RESULTS_ARGUMENT,
    project: str | None = PROJECT_OPTION,
    assay: str | None = ASSAY_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path = ANALYTICS_PATH_OPTION,
    artifact_root: Path = ARTIFACT_ROOT_OPTION,
) -> None:
    """Search a results directory for MultiQC output and ingest it."""
    _run_multiqc_ingest(
        results,
        project=project,
        assay=assay,
        run_id=run_id,
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
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
    assay: str | None = ASSAY_OPTION,
    report_name: str | None = REPORT_OPTION,
    cohort: str | None = COHORT_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path = ANALYTICS_PATH_OPTION,
    artifact_root: Path = ARTIFACT_ROOT_OPTION,
) -> None:
    """Ingest a run into a local or remote Goodomics store."""
    if report_name:
        console.print("[yellow]Ignoring --report for the MultiQC ingestion pilot.[/yellow]")
    if cohort:
        console.print("[yellow]Ignoring --cohort for the MultiQC ingestion pilot.[/yellow]")
    _run_multiqc_ingest(
        results,
        project=project,
        assay=assay,
        run_id=run_id,
        database_url=database_url,
        analytics_path=analytics_path,
        artifact_root=artifact_root,
    )

@app.command()
def init(database_url: str | None = DATABASE_URL_OPTION) -> None:
    """Initialize a local Goodomics database."""
    resolved_url = database_url or os.environ.get(
        "GOODOMICS_DATABASE_URL",
        DEFAULT_DATABASE_URL,
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
