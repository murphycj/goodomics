from __future__ import annotations

import asyncio
import logging
import os
from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from typer.core import TyperGroup

from goodomics.ingest.runner import (
    DEFAULT_DATABASE_URL,
    IngestType,
    print_ingest_result,
    run_ingest,
)
from goodomics.report.html import load_report_template, write_report
from goodomics.server.logging import build_uvicorn_log_config


class LogLevel(StrEnum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


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


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
app = typer.Typer(
    cls=GoodomicsTyperGroup,
    context_settings=CONTEXT_SETTINGS,
    help="Cohort-aware QC for omics pipelines.",
)
console = Console()
RESULTS_ARGUMENT = typer.Argument(..., help="Pipeline results directory.")
REPORT_OUT_OPTION = typer.Option(Path("goodomics_report.html"), "--out", "-o")
TEMPLATE_OPTION = typer.Option(
    None, "--template", "-T", help="YAML or JSON report template config."
)
PROJECT_OPTION = typer.Option(None, "--project", "-p")
ASSAY_OPTION = typer.Option(None, "--assay", "-a")
INGEST_TYPE_OPTION = typer.Option(
    IngestType.multiqc,
    "--type",
    "-t",
    help="Input type to ingest.",
)
REPORT_OPTION = typer.Option(None, "--report", "-r")
COHORT_OPTION = typer.Option(None, "--cohort", "-c")
RUN_ID_OPTION = typer.Option(None, "--run-id", "-R")
DATABASE_URL_OPTION = typer.Option(
    None,
    "--database-url",
    "-d",
    help="Database URL for local Goodomics state.",
)
ANALYTICS_PATH_OPTION = typer.Option(
    None,
    "--analytics-path",
    "-A",
    help=(
        "DuckDB analytics database path. Defaults to the selected project's "
        "analytics store."
    ),
)
FILE_ROOT_OPTION = typer.Option(
    Path(".goodomics/files"),
    "--file-root",
    "-f",
    help="Local file storage root.",
)
LOG_LEVEL_OPTION = typer.Option(
    LogLevel.info,
    "--log-level",
    "-l",
    help="Log level: critical, error, warning, info, debug, or trace.",
)


def _is_existing_path_arg(value: str) -> bool:
    if value.startswith("-"):
        return False
    return Path(value).exists()


def _configure_cli_logging(log_level: LogLevel | str) -> None:
    normalized = str(log_level).upper()
    if normalized == "TRACE":
        normalized = "DEBUG"
    level = getattr(logging, normalized, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("goodomics").setLevel(level)


@app.command(name="__default__", hidden=True)
def default_ingest(
    results: Path = RESULTS_ARGUMENT,
    ingest_type: IngestType = INGEST_TYPE_OPTION,
    project: str | None = PROJECT_OPTION,
    assay: str | None = ASSAY_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path | None = ANALYTICS_PATH_OPTION,
    file_root: Path = FILE_ROOT_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Search a results directory and ingest it."""
    _configure_cli_logging(log_level)
    try:
        result = run_ingest(
            results,
            ingest_type=ingest_type,
            project=project,
            assay=assay,
            run_id=run_id,
            database_url=database_url,
            analytics_path=analytics_path,
            file_root=file_root,
            console=console,
            show_progress=True,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print_ingest_result(result, console)


@app.command()
def report(
    results: Path = RESULTS_ARGUMENT,
    out: Path = REPORT_OUT_OPTION,
    template: Path | None = TEMPLATE_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Generate a standalone Goodomics HTML report."""
    _configure_cli_logging(log_level)
    console.print(f"Scanning [bold]{results}[/bold]")
    write_report(results, out, template=load_report_template(template))
    console.print(f"Writing report to [bold]{out}[/bold]")


@app.command()
def ingest(
    results: Path = RESULTS_ARGUMENT,
    ingest_type: IngestType = INGEST_TYPE_OPTION,
    project: str | None = PROJECT_OPTION,
    assay: str | None = ASSAY_OPTION,
    report_name: str | None = REPORT_OPTION,
    cohort: str | None = COHORT_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path | None = ANALYTICS_PATH_OPTION,
    file_root: Path = FILE_ROOT_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Ingest a run into a local or remote Goodomics store."""
    _configure_cli_logging(log_level)
    if report_name:
        console.print("[yellow]Ignoring --report during ingestion.[/yellow]")
    if cohort:
        console.print("[yellow]Ignoring --cohort during ingestion.[/yellow]")
    try:
        result = run_ingest(
            results,
            ingest_type=ingest_type,
            project=project,
            assay=assay,
            run_id=run_id,
            database_url=database_url,
            analytics_path=analytics_path,
            file_root=file_root,
            console=console,
            show_progress=True,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print_ingest_result(result, console)


@app.command()
def init(
    database_url: str | None = DATABASE_URL_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Initialize a local Goodomics database."""
    _configure_cli_logging(log_level)
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
        store = SQLModelGoodomicsStore(resolved_url)
        asyncio.run(store.ensure_schema())
        asyncio.run(store.ensure_default_project())
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            f"Missing database driver `{exc.name}`. Install `goodomics` for the full "
            "distribution or add the matching `goodomics-core` database extra."
        ) from exc
    console.print(f"Initialized Goodomics database at [bold]{resolved_url}[/bold]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-H"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Run the Goodomics API, MCP server, AI chat, and dashboard."""
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
        log_level=log_level.value,
        log_config=build_uvicorn_log_config(log_level.value),
        factory=True,
    )


if __name__ == "__main__":
    app()
