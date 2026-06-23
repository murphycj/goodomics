# pyright: reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DEFAULT_PROJECT_SLUG,
    display_name_from_slug,
    new_project_id,
    validate_project_slug,
)
from goodomics.schemas.models import Metric, Project, Run, Sample


@dataclass(frozen=True)
class StoredFileMetadata:
    file_id: str
    run_id: str
    kind: str
    path: str
    size_bytes: int
    sha256: str
    source_path: str
    created_at: datetime


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    project: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    run_kind: str = Field(default="pipeline_run", max_length=64)
    assay: str | None = Field(default=None, max_length=255)
    pipeline_name: str | None = Field(default=None, max_length=255)
    pipeline_version: str | None = Field(default=None, max_length=255)
    parameters_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str = Field(default="unknown", max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class ProjectRecord(SQLModel, table=True):
    __tablename__ = "projects"

    project_id: str = Field(primary_key=True, max_length=255)
    slug: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class SubjectRecord(SQLModel, table=True):
    __tablename__ = "subjects"

    subject_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    external_id: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleRecord(SQLModel, table=True):
    __tablename__ = "samples"

    sample_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    subject_id: str | None = Field(default=None, max_length=255, index=True)
    external_id: str | None = Field(default=None, max_length=255)
    sample_name: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class RunSampleRecord(SQLModel, table=True):
    __tablename__ = "run_samples"

    run_sample_id: str = Field(primary_key=True, max_length=512)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    sample_id: str | None = Field(default=None, max_length=255, index=True)
    assay: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=64)
    status: str = Field(default="unknown", max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataProfileRecord(SQLModel, table=True):
    __tablename__ = "data_profiles"

    data_profile_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    run_id: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    data_type: str = Field(max_length=128, index=True)
    assay: str | None = Field(default=None, max_length=255)
    producer_tool: str | None = Field(default=None, max_length=255)
    producer_tool_version: str | None = Field(default=None, max_length=255)
    producer_pipeline: str | None = Field(default=None, max_length=255)
    genome_build: str | None = Field(default=None, max_length=64)
    feature_type: str | None = Field(default=None, max_length=128)
    value_type: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=64)
    query_modes_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    mcp_description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class FileRecord(SQLModel, table=True):
    __tablename__ = "files"

    file_id: str = Field(primary_key=True, max_length=512)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    path: str | None = Field(default=None, max_length=2048)
    uri: str | None = Field(default=None, max_length=2048)
    file_role: str = Field(max_length=255)
    format: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = None
    sha256: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class FileLinkRecord(SQLModel, table=True):
    __tablename__ = "file_links"

    id: int | None = Field(default=None, primary_key=True)
    file_id: str = Field(max_length=512, index=True)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    run_id: str | None = Field(default=None, max_length=255, index=True)
    run_sample_id: str | None = Field(default=None, max_length=512, index=True)
    sample_id: str | None = Field(default=None, max_length=255, index=True)
    data_profile_id: str | None = Field(default=None, max_length=255, index=True)
    link_role: str = Field(max_length=255)


class SampleSetRecord(SQLModel, table=True):
    __tablename__ = "sample_sets"

    sample_set_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    kind: str = Field(default="cohort", max_length=64)
    description: str | None = None
    definition_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleSetMemberRecord(SQLModel, table=True):
    __tablename__ = "sample_set_members"

    id: int | None = Field(default=None, primary_key=True)
    sample_set_id: str = Field(max_length=255, index=True)
    run_sample_id: str = Field(max_length=512, index=True)


class MetricRecord(SQLModel, table=True):
    __tablename__ = "metrics"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    sample_id: str | None = Field(default=None, max_length=255)
    name: str = Field(max_length=255)
    value: Any = Field(sa_type=JSON)
    unit: str | None = Field(default=None, max_length=255)


class StoredFileRecord(SQLModel, table=True):
    __tablename__ = "stored_files"

    id: int | None = Field(default=None, primary_key=True)
    file_id: str | None = Field(default=None, max_length=512, index=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    kind: str = Field(default="file", max_length=255)
    path: str = Field(max_length=2048)
    size_bytes: int | None = None
    sha256: str | None = Field(default=None, max_length=64)
    source_path: str | None = Field(default=None, max_length=2048)
    created_at: datetime | None = None


class QCDecisionRecord(SQLModel, table=True):
    __tablename__ = "qc_decisions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    status: str = Field(max_length=32)
    reasons: list[str] = Field(default_factory=list, sa_type=JSON)
    cohort: str | None = Field(default=None, max_length=255)
    report_version: str | None = Field(default=None, max_length=255)
    policy_version: str | None = Field(default=None, max_length=255)


metadata = SQLModel.metadata
projects_table = ProjectRecord.__table__
subjects_table = SubjectRecord.__table__
runs_table = RunRecord.__table__
samples_table = SampleRecord.__table__
run_samples_table = RunSampleRecord.__table__
data_profiles_table = DataProfileRecord.__table__
files_table = FileRecord.__table__
file_links_table = FileLinkRecord.__table__
sample_sets_table = SampleSetRecord.__table__
sample_set_members_table = SampleSetMemberRecord.__table__
metrics_table = MetricRecord.__table__
stored_files_table = StoredFileRecord.__table__
qc_decisions_table = QCDecisionRecord.__table__


class SQLModelGoodomicsStore:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self.database_url = database_url
        self.engine = engine

    def _get_engine(self) -> AsyncEngine:
        if self.engine is None:
            _ensure_sqlite_parent(self.database_url)
            self.engine = create_async_engine(self.database_url)
        return self.engine

    async def ensure_schema(self) -> None:
        async with self._get_engine().begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
            await _ensure_compatible_schema(connection)

    async def ensure_default_project(self) -> Project:
        return await self.ensure_project(DEFAULT_PROJECT_SLUG)

    async def ensure_project(self, reference: str | None = None) -> Project:
        await self.ensure_schema()
        raw_reference = (reference or DEFAULT_PROJECT_SLUG).strip()
        slug = (
            DEFAULT_PROJECT_SLUG
            if raw_reference in {"", DEFAULT_PROJECT_ID, DEFAULT_PROJECT_SLUG}
            else validate_project_slug(raw_reference)
        )
        async with AsyncSession(self._get_engine()) as session:
            row = await _resolve_project_row(session, raw_reference)
            if row is None and slug != raw_reference:
                row = await _resolve_project_row(session, slug)
            if row is None:
                project_id = (
                    DEFAULT_PROJECT_ID if slug == DEFAULT_PROJECT_SLUG else new_project_id()
                )
                row = ProjectRecord(
                    project_id=project_id,
                    slug=slug,
                    name=(
                        DEFAULT_PROJECT_NAME
                        if slug == DEFAULT_PROJECT_SLUG
                        else display_name_from_slug(slug)
                    ),
                    created_at=datetime.now(UTC),
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
        return _project_from_row(row)

    async def get_project(self, project_id: str) -> Project | None:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            row = await session.get(ProjectRecord, project_id)
        return _project_from_row(row) if row is not None else None

    async def save_run(self, run: Run) -> None:
        await self.ensure_schema()
        project = await self.ensure_project(run.project_id or run.project)
        async with AsyncSession(self._get_engine()) as session:
            await session.exec(
                delete(QCDecisionRecord).where(QCDecisionRecord.run_id == run.run_id)
            )
            await session.exec(
                delete(StoredFileRecord).where(StoredFileRecord.run_id == run.run_id)
            )
            await session.exec(delete(MetricRecord).where(MetricRecord.run_id == run.run_id))
            await session.exec(delete(RunSampleRecord).where(RunSampleRecord.run_id == run.run_id))

            existing = await session.get(RunRecord, run.run_id)
            if existing is not None:
                await session.delete(existing)

            session.add(
                RunRecord(
                    run_id=run.run_id,
                    project_id=project.project_id,
                    project=run.project or project.slug or project.name,
                    name=run.name,
                    run_kind=run.run_kind,
                    assay=run.assay,
                    pipeline_name=run.pipeline_name,
                    pipeline_version=run.pipeline_version,
                    parameters_json=dict(run.parameters_json),
                    started_at=run.started_at,
                    ended_at=run.ended_at,
                    status=run.status,
                    metadata_json=dict(run.metadata_json),
                    created_at=run.created_at,
                )
            )
            if run.samples:
                for sample in run.samples:
                    sample_row = await session.get(SampleRecord, sample.sample_id)
                    if sample_row is None:
                        sample_row = SampleRecord(
                            sample_id=sample.sample_id,
                            project_id=sample.project_id or project.project_id,
                            subject_id=sample.subject_id,
                            external_id=sample.external_id,
                            sample_name=sample.sample_name,
                            metadata_json=dict(sample.metadata_json),
                        )
                    else:
                        sample_row.project_id = (
                            sample.project_id
                            or sample_row.project_id
                            or project.project_id
                        )
                        sample_row.subject_id = sample.subject_id
                        sample_row.external_id = sample.external_id
                        sample_row.sample_name = sample.sample_name
                        sample_row.metadata_json = dict(sample.metadata_json)
                    session.add(sample_row)
                session.add_all(
                    [
                        RunSampleRecord(
                            run_sample_id=f"{run.run_id}:{sample.sample_id}",
                            project_id=project.project_id,
                            run_id=run.run_id,
                            sample_id=sample.sample_id,
                            assay=run.assay,
                            status="unknown",
                        )
                        for sample in run.samples
                    ]
                )
            if run.metrics:
                session.add_all(
                    [
                        MetricRecord(
                            run_id=run.run_id,
                            sample_id=metric.sample_id,
                            name=metric.name,
                            value=metric.value,
                            unit=metric.unit,
                        )
                        for metric in run.metrics
                    ]
                )
            await session.commit()

    async def get_run(self, run_id: str) -> Run | None:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            run_row = await session.get(RunRecord, run_id)
            if run_row is None:
                return None
            sample_rows = (
                await session.exec(
                    select(SampleRecord)
                    .join(
                        RunSampleRecord,
                        RunSampleRecord.sample_id == SampleRecord.sample_id,
                    )
                    .where(RunSampleRecord.run_id == run_id)
                )
            ).all()
            metric_rows = (
                await session.exec(select(MetricRecord).where(MetricRecord.run_id == run_id))
            ).all()
        return Run(
            run_id=run_row.run_id,
            project=run_row.project,
            project_id=run_row.project_id,
            name=run_row.name,
            run_kind=run_row.run_kind,
            assay=run_row.assay,
            pipeline_name=run_row.pipeline_name,
            pipeline_version=run_row.pipeline_version,
            parameters_json=run_row.parameters_json,
            started_at=run_row.started_at,
            ended_at=run_row.ended_at,
            status=run_row.status,
            metadata_json=run_row.metadata_json,
            created_at=run_row.created_at,
            samples=[_sample_from_row(row) for row in sample_rows],
            metrics=[_metric_from_row(row) for row in metric_rows],
        )

    async def list_metrics(self, run_id: str) -> list[Metric]:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            metric_rows = (
                await session.exec(select(MetricRecord).where(MetricRecord.run_id == run_id))
            ).all()
        return [_metric_from_row(row) for row in metric_rows]

    async def replace_files(
        self,
        session: AsyncSession,
        run_id: str,
        files: list[StoredFileMetadata],
    ) -> None:
        await session.exec(delete(StoredFileRecord).where(StoredFileRecord.run_id == run_id))
        if files:
            session.add_all(
                [
                    StoredFileRecord(
                        file_id=file.file_id,
                        run_id=file.run_id,
                        kind=file.kind,
                        path=file.path,
                        size_bytes=file.size_bytes,
                        sha256=file.sha256,
                        source_path=file.source_path,
                        created_at=file.created_at,
                    )
                    for file in files
                ]
            )
        await session.commit()


def _sample_from_row(row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=row.project_id,
        subject_id=row.subject_id,
        external_id=row.external_id,
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


async def _resolve_project_row(
    session: AsyncSession, reference: str | None
) -> ProjectRecord | None:
    if reference is None or reference == "":
        reference = DEFAULT_PROJECT_SLUG
    row = await session.get(ProjectRecord, reference)
    if row is not None:
        return row
    return (
        await session.exec(select(ProjectRecord).where(ProjectRecord.slug == reference))
    ).first()


def _project_from_row(row: ProjectRecord) -> Project:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Project(
        project_id=row.project_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        metadata_json=metadata_dict,
        created_at=row.created_at,
    )


def _metric_from_row(row: MetricRecord) -> Metric:
    return Metric(
        sample_id=row.sample_id,
        name=row.name,
        value=row.value,
        unit=row.unit,
    )


# Backward-compatible alias for existing imports.
SQLAlchemyGoodomicsStore = SQLModelGoodomicsStore


async def _ensure_compatible_schema(connection: Any) -> None:
    dialect_name = connection.dialect.name
    if dialect_name != "sqlite":
        return
    result = await connection.exec_driver_sql("PRAGMA table_info(projects)")
    columns = {str(row[1]) for row in result.fetchall()}
    if "slug" not in columns:
        await connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN slug VARCHAR(255)")
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_projects_slug ON projects (slug)"
        )


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    db_path = Path(database_url.removeprefix(prefix))
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
