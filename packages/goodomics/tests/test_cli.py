from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fixtures import write_cbioportal_fixture, write_multiqc_fixture
from goodomics.cli import app
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.server.db.models import InstallationStateRecord
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import RunRecord, SQLModelGoodomicsStore
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from typer.testing import CliRunner

runner = CliRunner()
AUTH_SECRET = "a-secure-test-secret-of-adequate-length"


@pytest.fixture(autouse=True)
def _run_cli_in_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)


def _run_pk(database_path: Path, run_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(f"sqlite+aiosqlite:///{database_path}")
        async with AsyncSession(catalog_store._get_engine()) as session:
            row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == run_id))
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _write_auth_config(tmp_path: Path, database_path: Path) -> Path:
    """Write an authentication-enabled CLI test configuration."""

    config_path = tmp_path / "goodomics.toml"
    config_path.write_text(
        f"""
[database]
url = "sqlite+aiosqlite:///{database_path}"

[auth]
enabled = true
""".strip(),
        encoding="utf-8",
    )
    return config_path


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
    config_path = tmp_path / "goodomics.toml"
    assert config_path.is_file()
    assert "Created Goodomics configuration" in result.stdout
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
            "--analysis-type",
            "rna_sequencing",
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
    assert (tmp_path / "goodomics.toml").is_file()
    assert "Ingested run" in result.stdout
    assert "run-1" in result.stdout
    assert database_path.exists()
    assert analytics_path.exists()
    assert (file_root / "run-1" / "multiqc").exists()
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_path, "run-1:S1:analysis")
    )


def test_ingest_uses_paths_relative_to_created_custom_config(tmp_path: Path) -> None:
    results_dir = write_multiqc_fixture(tmp_path / "results")
    setup_dir = tmp_path / "installation"
    config_path = setup_dir / "goodomics.toml"

    result = runner.invoke(
        app,
        [
            "ingest",
            str(results_dir),
            "--project",
            "demo",
            "--run-id",
            "configured-run",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert config_path.is_file()
    assert (setup_dir / ".goodomics" / "goodomics.db").is_file()
    analytics_files = list(
        (setup_dir / ".goodomics" / "projects").glob("*/analytics.duckdb")
    )
    assert len(analytics_files) == 1
    assert (setup_dir / ".goodomics" / "files" / "configured-run" / "multiqc").is_dir()


def test_serve_creates_config_before_starting_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def capture_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr("uvicorn.run", capture_run)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    config_path = tmp_path / "goodomics.toml"
    assert config_path.is_file()
    assert "Created Goodomics configuration" in result.stdout
    assert calls[0][1]["host"] == "127.0.0.1"
    assert calls[0][1]["port"] == 8000


def test_create_admin_closes_first_run_setup(tmp_path: Path) -> None:
    """Allow unauthenticated admin creation only for first-run setup."""

    database_path = tmp_path / "state" / "goodomics.db"
    config_path = _write_auth_config(tmp_path, database_path)

    result = runner.invoke(
        app,
        [
            "users",
            "create-admin",
            "--email",
            "owner@example.org",
            "--password",
            "correct horse battery staple",
            "--config",
            str(config_path),
        ],
        env={"GOODOMICS_AUTH_SECRET": AUTH_SECRET},
    )

    assert result.exit_code == 0

    async def load_setup_state() -> InstallationStateRecord | None:
        store = SQLModelGoodomicsStore(f"sqlite+aiosqlite:///{database_path}")
        async with AsyncSession(store._get_engine()) as session:
            state = await session.get(InstallationStateRecord, "installation")
        await store._get_engine().dispose()
        return state

    state = asyncio.run(load_setup_state())
    assert state is not None
    assert state.setup_completed_by_user_id.startswith("usr_")


def test_user_commands_fail_when_authentication_is_disabled() -> None:
    """Reject user management before opening a database when auth is disabled."""

    result = runner.invoke(
        app,
        [
            "users",
            "create-admin",
            "--email",
            "owner@example.org",
            "--password",
            "correct horse battery staple",
        ],
    )

    assert result.exit_code != 0
    assert "User management is disabled" in result.output
    assert not Path(".goodomics/goodomics.db").exists()


def test_user_creation_requires_valid_admin_credentials(tmp_path: Path) -> None:
    """Authenticate an existing administrator before creating a regular user."""

    database_path = tmp_path / "state" / "goodomics.db"
    config_path = _write_auth_config(tmp_path, database_path)
    environment = {"GOODOMICS_AUTH_SECRET": AUTH_SECRET}
    bootstrap = runner.invoke(
        app,
        [
            "users",
            "create-admin",
            "--email",
            "owner@example.org",
            "--password",
            "correct horse battery staple",
            "--config",
            str(config_path),
        ],
        env=environment,
    )
    assert bootstrap.exit_code == 0
    command = [
        "users",
        "create",
        "--email",
        "analyst@example.org",
        "--password",
        "temporary analyst password",
        "--admin-email",
        "owner@example.org",
        "--config",
        str(config_path),
    ]

    rejected = runner.invoke(app, command, input="wrong password\n", env=environment)
    created = runner.invoke(
        app,
        command,
        input="correct horse battery staple\n",
        env=environment,
    )

    assert rejected.exit_code != 0
    assert "Invalid installation administrator credentials" in rejected.output
    assert created.exit_code == 0
    assert "Created user analyst@example.org" in created.stdout


def test_user_command_offers_first_admin_setup(tmp_path: Path) -> None:
    """Offer interactive bootstrap before the first non-bootstrap user command."""

    database_path = tmp_path / "state" / "goodomics.db"
    config_path = _write_auth_config(tmp_path, database_path)

    result = runner.invoke(
        app,
        [
            "users",
            "create",
            "--email",
            "analyst@example.org",
            "--password",
            "temporary analyst password",
            "--config",
            str(config_path),
        ],
        input=(
            "y\n"
            "owner@example.org\n"
            "correct horse battery staple\n"
            "correct horse battery staple\n"
        ),
        env={"GOODOMICS_AUTH_SECRET": AUTH_SECRET},
    )

    assert result.exit_code == 0
    assert "No installation administrator has been configured" in result.stdout
    assert "Created installation administrator owner@example.org" in result.stdout
    assert "Created user analyst@example.org" in result.stdout


def test_cli_preserves_the_final_active_administrator(tmp_path: Path) -> None:
    """Reject disabling the final active administrator from the CLI."""

    database_path = tmp_path / "state" / "goodomics.db"
    config_path = _write_auth_config(tmp_path, database_path)
    environment = {"GOODOMICS_AUTH_SECRET": AUTH_SECRET}
    bootstrap = runner.invoke(
        app,
        [
            "users",
            "create-admin",
            "--email",
            "owner@example.org",
            "--password",
            "correct horse battery staple",
            "--config",
            str(config_path),
        ],
        env=environment,
    )
    assert bootstrap.exit_code == 0

    result = runner.invoke(
        app,
        [
            "users",
            "disable",
            "owner@example.org",
            "--admin-email",
            "owner@example.org",
            "--config",
            str(config_path),
        ],
        input="correct horse battery staple\n",
        env=environment,
    )

    assert result.exit_code != 0
    assert "must keep at least one active administrator" in result.output

    second_admin = runner.invoke(
        app,
        [
            "users",
            "create-admin",
            "--email",
            "backup-owner@example.org",
            "--password",
            "another correct horse battery staple",
            "--admin-email",
            "owner@example.org",
            "--config",
            str(config_path),
        ],
        input="correct horse battery staple\n",
        env=environment,
    )
    assert second_admin.exit_code == 0

    disabled = runner.invoke(
        app,
        [
            "users",
            "disable",
            "owner@example.org",
            "--admin-email",
            "backup-owner@example.org",
            "--config",
            str(config_path),
        ],
        input="another correct horse battery staple\n",
        env=environment,
    )

    assert disabled.exit_code == 0
    assert "Disabled user owner@example.org" in disabled.stdout


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
    assert "Ingested 3 cBioPortal sample runs" in result.stdout
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
            "rna_sequencing",
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
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_path, "short-run:S1:analysis")
    )


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
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_path, "run-default:S1:analysis")
    )


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
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_path, "WT_REP1:WT_REP1:analysis")
    )
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_path, "WT_REP2:WT_REP2:analysis")
    )
    assert (file_root / "WT_REP1" / "multiqc").exists()
    assert (file_root / "WT_REP2" / "multiqc").exists()
