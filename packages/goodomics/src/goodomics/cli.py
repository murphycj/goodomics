from __future__ import annotations

import asyncio
import logging
import os
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typer.core import TyperGroup

from goodomics.ingest.runner import print_ingest_result, run_ingest
from goodomics.projects import DEFAULT_PROJECT_ID, analytics_path_for_project
from goodomics.report.html import (
    load_report_template,
    render_report_result,
    write_report,
)
from goodomics.server.db.models import InsightRecord, ReportRecord
from goodomics.server.insights import execute_report
from goodomics.server.logging import build_uvicorn_log_config
from goodomics.server.settings import Settings, ensure_config_file, load_settings
from goodomics.storage.database import resolve_database_url
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore, initialized_store


class LogLevel(StrEnum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    debug = "debug"
    trace = "trace"


class ProjectVisibility(StrEnum):
    """Supported project access levels for CLI project management."""

    private = "private"
    public = "public"


class GoodomicsTyperGroup(TyperGroup):
    def resolve_command(
        self,
        ctx: typer.Context,
        args: list[str],
    ) -> tuple[str | None, object | None, list[str]]:
        """Treat an existing leading path as the hidden default ingest command."""

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
    help="Sample context, QC, and storage for omics pipelines.",
)
console = Console()
RESULTS_ARGUMENT = typer.Argument(..., help="Pipeline results directory.")
REPORT_OUT_OPTION = typer.Option(Path("goodomics_report.html"), "--out", "-o")
TEMPLATE_OPTION = typer.Option(
    None, "--template", "-T", help="YAML or JSON report template config."
)
PROJECT_OPTION = typer.Option(None, "--project", "-p")
ANALYSIS_TYPE_OPTION = typer.Option(
    None,
    "--analysis-type",
    "-a",
    help="Controlled analysis type ID, such as rna_sequencing.",
)
INGEST_TYPE_OPTION = typer.Option(
    "multiqc",
    "--type",
    "-t",
    # Registry validation keeps this option open to package-provided sources.
    help="Input type to ingest.",
)
REPORT_OPTION = typer.Option(None, "--report", "-r")
GROUP_OPTION = typer.Option(None, "--group", "-g")
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
    None,
    "--file-root",
    "-f",
    help="Local file storage root. Defaults to the selected configuration.",
)
LOG_LEVEL_OPTION = typer.Option(
    LogLevel.info,
    "--log-level",
    "-l",
    help="Log level: critical, error, warning, info, debug, or trace.",
)
CONFIG_OPTION = typer.Option(None, "--config", help="TOML configuration file.")
MUST_CHANGE_PASSWORD_OPTION = typer.Option(False, "--must-change-password")
ADMIN_EMAIL_OPTION = typer.Option(
    None,
    "--admin-email",
    envvar="GOODOMICS_ADMIN_EMAIL",
    help="Email of the installation administrator authorizing this operation.",
)


def _is_existing_path_arg(value: str) -> bool:
    """Return whether a CLI argument names an existing non-option path."""

    if value.startswith("-"):
        return False
    return Path(value).exists()


def _configure_cli_logging(log_level: LogLevel | str) -> None:
    """Configure process and Goodomics loggers for the requested CLI level."""

    normalized = str(log_level).upper()
    if normalized == "TRACE":
        normalized = "DEBUG"
    level = getattr(logging, normalized, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")
    logging.getLogger("goodomics").setLevel(level)


def _load_setup_settings(config: Path | None) -> Settings:
    """Create a missing configuration, report it, and load typed settings."""

    config_path, created = ensure_config_file(config)
    if created:
        console.print(f"Created Goodomics configuration at [bold]{config_path}[/bold]")
    return load_settings(config_path)


def _run_configured_ingest(
    *,
    results: Path,
    ingest_type: str,
    project: str | None,
    analysis_type_id: str | None,
    run_id: str | None,
    database_url: str | None,
    analytics_path: Path | None,
    file_root: Path | None,
    config: Path | None,
) -> None:
    """Resolve ingest settings, run the selected parser, and print its result."""

    settings = _load_setup_settings(config)
    try:
        resolved_database_url = database_url or settings.database_url
        resolved_analytics_path = analytics_path or (
            Path(settings.analytics_path) if settings.analytics_path else None
        )
        if resolved_analytics_path is None:
            resolved_analytics_path = _configured_project_analytics_path(
                database_url=resolved_database_url,
                analytics_root=settings.analytics_root,
                project=project,
            )
        result = run_ingest(
            results,
            ingest_type=ingest_type,
            project=project,
            analysis_type_id=analysis_type_id,
            run_id=run_id,
            database_url=resolved_database_url,
            analytics_path=resolved_analytics_path,
            file_root=file_root or Path(settings.file_root),
            console=console,
            show_progress=True,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print_ingest_result(result, console)


def _configured_project_analytics_path(
    *, database_url: str, analytics_root: str, project: str | None
) -> Path:
    """Return the configured analytics path for an ensured project."""

    async def resolve() -> Path:
        """Ensure the project and derive its analytics path asynchronously."""

        async with initialized_store(database_url) as store:
            project_record = await store.ensure_project(project)
            return analytics_path_for_project(analytics_root, project_record.project_id)

    return asyncio.run(resolve())


@app.command(name="__default__", hidden=True)
def default_ingest(
    results: Path = RESULTS_ARGUMENT,
    ingest_type: str = INGEST_TYPE_OPTION,
    project: str | None = PROJECT_OPTION,
    analysis_type_id: str | None = ANALYSIS_TYPE_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path | None = ANALYTICS_PATH_OPTION,
    file_root: Path | None = FILE_ROOT_OPTION,
    config: Path | None = CONFIG_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Search a results directory and ingest it."""
    _configure_cli_logging(log_level)
    _run_configured_ingest(
        results=results,
        ingest_type=ingest_type,
        project=project,
        analysis_type_id=analysis_type_id,
        run_id=run_id,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
        config=config,
    )


@app.command()
def report(
    results: Path = RESULTS_ARGUMENT,
    out: Path = REPORT_OUT_OPTION,
    template: Path | None = TEMPLATE_OPTION,
    project: str | None = PROJECT_OPTION,
    report_name: str | None = REPORT_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path | None = ANALYTICS_PATH_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Generate a standalone Goodomics HTML report."""
    _configure_cli_logging(log_level)
    if report_name:
        console.print(f"Rendering saved report [bold]{report_name}[/bold]")
        asyncio.run(
            _write_saved_report(
                report_name=report_name,
                out=out,
                project=project,
                database_url=database_url,
                analytics_path=analytics_path,
            )
        )
        console.print(f"Writing report to [bold]{out}[/bold]")
        return
    console.print(f"Scanning [bold]{results}[/bold]")
    write_report(results, out, template=load_report_template(template))
    console.print(f"Writing report to [bold]{out}[/bold]")


async def _write_saved_report_operation(
    *,
    store: SQLModelGoodomicsStore,
    report_name: str,
    out: Path,
    project: str | None,
    analytics_path: Path | None,
) -> None:
    """Execute a saved report with its ordered insights and write rendered HTML."""

    settings = load_settings()
    async with store.session() as session:
        saved_report = await session.get(ReportRecord, report_name)
        if saved_report is None:
            rows = (
                await session.exec(
                    select(ReportRecord).where(ReportRecord.name == report_name)
                )
            ).all()
            saved_report = rows[0] if rows else None
        if saved_report is None:
            raise typer.BadParameter(f"Saved report not found: {report_name}")
        project_id = project or saved_report.project_id or DEFAULT_PROJECT_ID
        insight_ids = [
            item["insight_id"]
            for item in saved_report.config.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("insight_id"), str)
        ]
        insights = (
            await session.exec(
                select(InsightRecord).where(
                    cast(Any, InsightRecord.insight_id).in_(insight_ids)
                )
            )
        ).all()
        by_id = {insight.insight_id: insight for insight in insights}
        ordered_insights = [
            by_id[insight_id] for insight_id in insight_ids if insight_id in by_id
        ]
        analytics_store = DuckDBAnalyticsStore(
            analytics_path
            or settings.analytics_path
            or analytics_path_for_project(settings.analytics_root, project_id)
        )
        result = await execute_report(
            session=session,
            analytics_store=analytics_store,
            project_id=project_id,
            report=saved_report,
            insights=ordered_insights,
            refresh=True,
        )
    out.write_text(render_report_result(result), encoding="utf-8")


async def _write_saved_report(
    *,
    report_name: str,
    out: Path,
    project: str | None,
    database_url: str | None,
    analytics_path: Path | None,
) -> None:
    """Render a saved report within one initialized SQL-store lifecycle."""

    async with initialized_store(resolve_database_url(database_url)) as store:
        await _write_saved_report_operation(
            store=store,
            report_name=report_name,
            out=out,
            project=project,
            analytics_path=analytics_path,
        )


@app.command()
def ingest(
    results: Path = RESULTS_ARGUMENT,
    ingest_type: str = INGEST_TYPE_OPTION,
    project: str | None = PROJECT_OPTION,
    analysis_type_id: str | None = ANALYSIS_TYPE_OPTION,
    report_name: str | None = REPORT_OPTION,
    group: str | None = GROUP_OPTION,
    run_id: str | None = RUN_ID_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    analytics_path: Path | None = ANALYTICS_PATH_OPTION,
    file_root: Path | None = FILE_ROOT_OPTION,
    config: Path | None = CONFIG_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Ingest a run into a local or remote Goodomics store."""
    _configure_cli_logging(log_level)
    if report_name:
        console.print("[yellow]Ignoring --report during ingestion.[/yellow]")
    if group:
        console.print("[yellow]Ignoring --group during ingestion.[/yellow]")
    _run_configured_ingest(
        results=results,
        ingest_type=ingest_type,
        project=project,
        analysis_type_id=analysis_type_id,
        run_id=run_id,
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=file_root,
        config=config,
    )


@app.command()
def init(
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    log_level: LogLevel = LOG_LEVEL_OPTION,
) -> None:
    """Initialize a local Goodomics database."""
    _configure_cli_logging(log_level)
    settings = _load_setup_settings(config)
    resolved_url = database_url or settings.database_url
    try:
        from goodomics.storage.sqlalchemy import initialized_store
    except ImportError as exc:
        raise typer.BadParameter(
            "Database support is not installed. Install `goodomics` for the full "
            "distribution or `goodomics-core[sqlite]` for local SQLite support."
        ) from exc

    async def initialize() -> None:
        """Create SQL tables and default application data in one lifecycle."""

        async with initialized_store(resolved_url) as store:
            await store.ensure_default_project()

    try:
        asyncio.run(initialize())
    except ModuleNotFoundError as exc:
        raise typer.BadParameter(
            f"Missing database driver `{exc.name}`. Install `goodomics` for the full "
            "distribution or add the matching `goodomics-core` database extra."
        ) from exc
    console.print(f"Initialized Goodomics database at [bold]{resolved_url}[/bold]")


@app.command()
def serve(
    host: str | None = typer.Option(None, "--host", "-H"),
    port: int | None = typer.Option(None, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
    log_level: LogLevel = LOG_LEVEL_OPTION,
    config: Path | None = CONFIG_OPTION,
) -> None:
    """Run the Goodomics API, MCP server, AI chat, and dashboard."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "Server support is not installed. Install `goodomics` for the full "
            "distribution or `goodomics-core[server]` for the server extra."
        ) from exc

    server_overrides = {
        key: value
        for key, value in {"host": host, "port": port}.items()
        if value is not None
    }
    config_path, created = ensure_config_file(config)
    if created:
        console.print(f"Created Goodomics configuration at [bold]{config_path}[/bold]")
    settings = load_settings(config_path, cli_overrides={"server": server_overrides})
    # Uvicorn cannot pass a settings object to an import-string factory, so the
    # selected path is exported for reload workers and read by load_settings().
    os.environ["GOODOMICS_CONFIG"] = str(config_path)
    uvicorn.run(
        "goodomics.server.app:create_app",
        host=settings.server.host,
        port=settings.server.port,
        reload=reload,
        log_level=log_level.value,
        log_config=build_uvicorn_log_config(log_level.value),
        factory=True,
    )


projects_app = typer.Typer(help="Manage Goodomics projects.")
app.add_typer(projects_app, name="projects")


@projects_app.command("set-visibility")
def projects_set_visibility(
    project: str,
    visibility: ProjectVisibility,
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    admin_email: str | None = ADMIN_EMAIL_OPTION,
) -> None:
    """Set an existing project to public or private visibility."""

    settings = _load_setup_settings(config)

    async def update_visibility() -> str:
        """Authorize the operation and persist project visibility."""

        async with initialized_store(database_url or settings.database_url) as store:
            if settings.auth.enabled:
                async with store.session() as session:
                    await _require_cli_admin(session, settings, admin_email)
            return await store.set_project_visibility(project, visibility.value)

    try:
        project_id = asyncio.run(update_visibility())
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        f"Set project [bold]{project_id}[/bold] visibility to "
        f"[bold]{visibility.value}[/bold]"
    )


users_app = typer.Typer(help="Manage Goodomics users.")
app.add_typer(users_app, name="users")


def _load_user_management_settings(config: Path | None) -> Settings:
    """Load settings and reject user management for unrestricted installations."""

    settings = load_settings(config)
    if not settings.auth.enabled:
        raise typer.BadParameter(
            "User management is disabled because authentication is not enabled"
        )
    return settings


async def _bootstrap_cli_admin(
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Offer interactive first-admin setup and persist the accepted account."""

    from goodomics.server.auth import complete_installation_setup, create_user

    console.print("No installation administrator has been configured.")
    if not typer.confirm("Create the installation administrator now?"):
        raise typer.Abort()
    email = typer.prompt("Administrator email")
    password = typer.prompt(
        "Administrator password",
        hide_input=True,
        confirmation_prompt=True,
    )
    try:
        user = await create_user(
            session,
            email=email,
            password=password,
            is_admin=True,
            password_settings=settings.auth.password,
        )
        await complete_installation_setup(session, user)
        created_email = user.email
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"Created installation administrator [bold]{created_email}[/bold]")


async def _require_cli_admin(
    session: AsyncSession,
    settings: Settings,
    admin_email: str | None,
) -> None:
    """Require an active administrator or bootstrap the first one interactively."""

    from goodomics.server.auth import authenticate_user, installation_setup_required

    if await installation_setup_required(session):
        await _bootstrap_cli_admin(session, settings)
        return
    email = admin_email or typer.prompt("Administrator email")
    password = os.environ.get("GOODOMICS_ADMIN_PASSWORD") or typer.prompt(
        "Administrator password", hide_input=True
    )
    administrator = await authenticate_user(session, email, password)
    if administrator is None or not administrator.is_admin:
        raise typer.BadParameter("Invalid installation administrator credentials")


def _users_create(
    *,
    email: str,
    display_name: str | None,
    password: str,
    is_admin: bool,
    must_change_password: bool,
    database_url: str | None,
    config: Path | None,
    admin_email: str | None,
) -> None:
    """Create a configured user and complete setup for an administrator."""

    from goodomics.server.auth import (
        complete_installation_setup,
        create_user,
        installation_setup_required,
    )

    settings = _load_user_management_settings(config)

    async def create() -> None:
        """Persist the user using an initialized metadata store."""

        async with initialized_store(database_url or settings.database_url) as store:
            async with store.session() as session:
                try:
                    setup_required = await installation_setup_required(session)
                    if not is_admin or not setup_required:
                        await _require_cli_admin(session, settings, admin_email)
                    user = await create_user(
                        session,
                        email=email,
                        password=password,
                        display_name=display_name,
                        is_admin=is_admin,
                        must_change_password=must_change_password,
                        password_settings=settings.auth.password,
                    )
                    if is_admin and setup_required:
                        await complete_installation_setup(session, user)
                    created_email = user.email
                    await session.commit()
                except ValueError as exc:
                    raise typer.BadParameter(str(exc)) from exc
            console.print(f"Created user [bold]{created_email}[/bold]")

    asyncio.run(create())


@users_app.command("create")
def users_create(
    email: str = typer.Option(..., prompt=True),
    display_name: str | None = typer.Option(None, "--display-name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, confirmation_prompt=True
    ),
    must_change_password: bool = MUST_CHANGE_PASSWORD_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    admin_email: str | None = ADMIN_EMAIL_OPTION,
) -> None:
    """Create a regular user using a hidden password prompt."""

    _users_create(
        email=email,
        display_name=display_name,
        password=password,
        is_admin=False,
        must_change_password=must_change_password,
        database_url=database_url,
        config=config,
        admin_email=admin_email,
    )


@users_app.command("create-admin")
def users_create_admin(
    email: str = typer.Option(..., prompt=True),
    display_name: str | None = typer.Option(None, "--display-name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, confirmation_prompt=True
    ),
    must_change_password: bool = MUST_CHANGE_PASSWORD_OPTION,
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    admin_email: str | None = ADMIN_EMAIL_OPTION,
) -> None:
    """Create an installation administrator."""

    _users_create(
        email=email,
        display_name=display_name,
        password=password,
        is_admin=True,
        must_change_password=must_change_password,
        database_url=database_url,
        config=config,
        admin_email=admin_email,
    )


async def _find_cli_user(session: AsyncSession, email: str):
    """Find a user by normalized email for a CLI account operation."""

    from goodomics.server.auth import normalize_email
    from goodomics.server.db.models import UserRecord

    normalized = normalize_email(email)
    return (
        await session.exec(select(UserRecord).where(UserRecord.email == normalized))
    ).first()


@users_app.command("reset-password")
def users_reset_password(
    email: str,
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, confirmation_prompt=True
    ),
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    admin_email: str | None = ADMIN_EMAIL_OPTION,
) -> None:
    """Set a temporary password and invalidate outstanding tokens."""

    from datetime import UTC, datetime

    from goodomics.server.auth import hash_password

    settings = _load_user_management_settings(config)

    async def reset() -> None:
        """Persist a temporary password in an initialized store lifecycle."""

        async with initialized_store(database_url or settings.database_url) as store:
            async with store.session() as session:
                await _require_cli_admin(session, settings, admin_email)
                user = await _find_cli_user(session, email)
                if user is None:
                    raise typer.BadParameter("User not found")
                user.password_hash = hash_password(password, settings.auth.password)
                user.auth_version += 1
                user.must_change_password = True
                user.updated_at = datetime.now(UTC)
                session.add(user)
                await session.commit()
            console.print(f"Reset password for [bold]{email}[/bold]")

    asyncio.run(reset())


@users_app.command("disable")
def users_disable(
    email: str,
    database_url: str | None = DATABASE_URL_OPTION,
    config: Path | None = CONFIG_OPTION,
    admin_email: str | None = ADMIN_EMAIL_OPTION,
) -> None:
    """Disable a user and invalidate outstanding tokens."""

    from datetime import UTC, datetime

    settings = _load_user_management_settings(config)

    async def disable() -> None:
        """Disable the user using an initialized metadata store."""

        async with initialized_store(database_url or settings.database_url) as store:
            async with store.session() as session:
                from goodomics.server.db.models import UserRecord

                await _require_cli_admin(session, settings, admin_email)
                user = await _find_cli_user(session, email)
                if user is None:
                    raise typer.BadParameter("User not found")
                if user.is_admin and user.is_active:
                    another_active_admin = (
                        await session.exec(
                            select(UserRecord.id).where(
                                UserRecord.id != user.id,
                                UserRecord.is_admin,
                                UserRecord.is_active,
                            )
                        )
                    ).first()
                    if another_active_admin is None:
                        raise typer.BadParameter(
                            "The installation must keep at least one active "
                            "administrator"
                        )
                user.is_active = False
                user.auth_version += 1
                user.updated_at = datetime.now(UTC)
                session.add(user)
                await session.commit()
            console.print(f"Disabled user [bold]{email}[/bold]")

    asyncio.run(disable())


if __name__ == "__main__":
    app()
