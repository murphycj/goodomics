# pyright: reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar, cast

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel import Field, SQLModel, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.analysis import analysis_method, resolve_analysis_type
from goodomics.projects import (
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DEFAULT_PROJECT_SLUG,
    display_name_from_slug,
    new_project_id,
    validate_project_slug,
)
from goodomics.schemas.models import (
    AnalysisMethod,
    AnalysisType,
    DataContract,
    DataContractAnalysisType,
    DataContractField,
    DataImport,
    FileAsset,
    FileLink,
    Project,
    Run,
    RunContract,
    RunContractSample,
    RunRelationship,
    RunSample,
    Sample,
    SampleGroup,
    SampleGroupMember,
    Subject,
)
from goodomics.storage.database import create_async_database_engine

RecordT = TypeVar("RecordT", bound=SQLModel)


@dataclass(frozen=True)
class MetadataWriteResult:
    project: ProjectRecord
    analysis_types: list[AnalysisTypeRecord]
    analysis_methods: list[AnalysisMethodRecord]
    data_import: DataImportRecord | None
    runs: list[RunRecord]
    subjects: list[SubjectRecord]
    samples: list[SampleRecord]
    run_samples: list[RunSampleRecord]
    run_relationships: list[RunRelationshipRecord]
    data_contracts: list[DataContractRecord]
    data_contract_analysis_types: list[DataContractAnalysisTypeRecord]
    run_contracts: list[RunContractRecord]
    run_contract_samples: list[RunContractSampleRecord]
    data_contract_fields: list[DataContractFieldRecord]
    files: list[FileRecord]
    file_links: list[FileLinkRecord]
    sample_groups: list[SampleGroupRecord]
    sample_group_members: list[SampleGroupMemberRecord]


# These SQLModel classes are persistence records, not the public Goodomics
# schemas. Keep database-only concerns here: table names, primary keys, indexes,
# foreign keys, JSON column storage, and nullable columns used by SQL backends.
class AnalysisTypeRecord(SQLModel, table=True):
    __tablename__ = "analysis_types"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "analysis_type_id", name="uq_analysis_types_project_id"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    analysis_type_id: str = Field(max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class AnalysisMethodRecord(SQLModel, table=True):
    __tablename__ = "analysis_methods"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "method_id", name="uq_analysis_methods_project_id"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    method_id: str = Field(max_length=255, index=True)
    name: str = Field(max_length=255)
    method_kind: str = Field(max_length=64, index=True)
    description: str | None = None
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    data_import_id: int | None = Field(
        default=None, foreign_key="data_imports.id", index=True
    )
    project: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    run_kind: str = Field(default="pipeline_run", max_length=64)
    analysis_type_id: int = Field(foreign_key="analysis_types.id", index=True)
    method_id: int = Field(foreign_key="analysis_methods.id", index=True)
    method_version: str | None = Field(default=None, max_length=255)
    parameters_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str = Field(default="unknown", max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class ProjectRecord(SQLModel, table=True):
    __tablename__ = "projects"

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(max_length=255, unique=True, index=True)
    slug: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    default_report_id: str | None = Field(default=None, max_length=255)
    visibility: str = Field(default="private", max_length=32, index=True)
    default_storage_location: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class SubjectRecord(SQLModel, table=True):
    __tablename__ = "subjects"

    id: int | None = Field(default=None, primary_key=True)
    subject_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleRecord(SQLModel, table=True):
    __tablename__ = "samples"

    id: int | None = Field(default=None, primary_key=True)
    sample_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    subject_id: int | None = Field(default=None, foreign_key="subjects.id", index=True)
    sample_name: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class RunSampleRecord(SQLModel, table=True):
    __tablename__ = "run_samples"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sample_id",
            "role",
            name="uq_run_samples_run_sample_role",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_sample_id: str = Field(max_length=512, unique=True, index=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    sample_id: int = Field(foreign_key="samples.id", index=True)
    role: str | None = Field(default=None, max_length=64)


class RunRelationshipRecord(SQLModel, table=True):
    __tablename__ = "run_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_run_id",
            "target_run_id",
            "relationship_type",
            name="uq_run_relationships_source_target_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    source_run_id: int = Field(foreign_key="runs.id", index=True)
    target_run_id: int = Field(foreign_key="runs.id", index=True)
    relationship_type: str = Field(max_length=128, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataContractRecord(SQLModel, table=True):
    __tablename__ = "data_contracts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "data_contract_id",
            name="uq_data_contracts_project_contract_id",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    data_contract_id: str = Field(max_length=255, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    data_type: str = Field(max_length=128, index=True)
    feature_type: str | None = Field(default=None, max_length=128)
    value_type: str | None = Field(default=None, max_length=128)
    unit: str | None = Field(default=None, max_length=64)
    entity_grain: str | None = Field(default=None, max_length=128)
    value_semantics: str | None = Field(default=None, max_length=128)
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    last_profiled_at: datetime | None = None
    source_fingerprint: str | None = Field(default=None, max_length=255)
    query_modes_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    intrinsic_producer_families_json: dict[str, Any] = Field(
        default_factory=dict, sa_type=JSON
    )
    description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataContractAnalysisTypeRecord(SQLModel, table=True):
    __tablename__ = "data_contract_analysis_types"
    __table_args__ = (
        UniqueConstraint(
            "data_contract_id",
            "analysis_type_id",
            name="uq_contract_analysis_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    data_contract_id: int = Field(foreign_key="data_contracts.id", index=True)
    analysis_type_id: int = Field(foreign_key="analysis_types.id", index=True)


class RunContractRecord(SQLModel, table=True):
    __tablename__ = "run_contracts"
    __table_args__ = (
        UniqueConstraint("run_id", "data_contract_id", name="uq_run_contract"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_contract_id: str = Field(max_length=512, unique=True, index=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    data_contract_id: int = Field(foreign_key="data_contracts.id", index=True)
    producer_method_id: int | None = Field(
        default=None, foreign_key="analysis_methods.id", index=True
    )
    producer_version: str | None = Field(default=None, max_length=255)
    reference_context_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    status: str = Field(default="available", max_length=64, index=True)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class RunContractSampleRecord(SQLModel, table=True):
    __tablename__ = "run_contract_samples"
    __table_args__ = (
        UniqueConstraint(
            "run_contract_id", "run_sample_id", name="uq_run_contract_sample"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_contract_id: int = Field(foreign_key="run_contracts.id", index=True)
    run_sample_id: int = Field(foreign_key="run_samples.id", index=True)
    availability: str = Field(max_length=64, index=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataContractFieldRecord(SQLModel, table=True):
    __tablename__ = "data_contract_fields"

    id: int | None = Field(default=None, primary_key=True)
    data_contract_id: int = Field(foreign_key="data_contracts.id", index=True)
    field_id: str = Field(max_length=255, index=True)
    field_role: str = Field(default="metric", max_length=64, index=True)
    entity_scope: str | None = Field(default=None, max_length=128)
    display_name: str = Field(max_length=255)
    value_type: str = Field(default="numeric", max_length=64, index=True)
    unit: str | None = Field(default=None, max_length=64)
    direction: str | None = Field(default=None, max_length=64)
    description: str | None = None
    priority: str | None = Field(default=None, max_length=64)
    primary_table: str | None = Field(default=None, max_length=128)
    physical_tables_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    query_ref_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataImportRecord(SQLModel, table=True):
    __tablename__ = "data_imports"

    id: int | None = Field(default=None, primary_key=True)
    data_import_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    source_type: str = Field(max_length=128, index=True)
    source_uri: str | None = Field(default=None, max_length=2048)
    source_path: str | None = Field(default=None, max_length=2048)
    importer_name: str = Field(max_length=255)
    importer_version: str | None = Field(default=None, max_length=255)
    status: str = Field(default="complete", max_length=64)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    parameters_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime


class FileRecord(SQLModel, table=True):
    __tablename__ = "files"

    id: int | None = Field(default=None, primary_key=True)
    file_id: str = Field(max_length=512, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    path: str | None = Field(default=None, max_length=2048)
    uri: str | None = Field(default=None, max_length=2048)
    storage_location: str | None = Field(default=None, max_length=255, index=True)
    object_key: str | None = Field(default=None, max_length=2048)
    file_role: str = Field(max_length=255)
    format: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = None
    sha256: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class FileLinkRecord(SQLModel, table=True):
    __tablename__ = "file_links"

    # A file can be linked to a run, run sample, sample, or data contract without
    # duplicating the file asset row itself.
    id: int | None = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="files.id", index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    data_import_id: int | None = Field(
        default=None, foreign_key="data_imports.id", index=True
    )
    run_id: int | None = Field(default=None, foreign_key="runs.id", index=True)
    run_sample_id: int | None = Field(
        default=None, foreign_key="run_samples.id", index=True
    )
    sample_id: int | None = Field(default=None, foreign_key="samples.id", index=True)
    data_contract_id: int | None = Field(
        default=None, foreign_key="data_contracts.id", index=True
    )
    link_role: str = Field(max_length=255)


class SampleGroupRecord(SQLModel, table=True):
    __tablename__ = "sample_groups"

    id: int | None = Field(default=None, primary_key=True)
    sample_group_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    kind: str = Field(default="cohort", max_length=64)
    description: str | None = None
    definition_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleGroupMemberRecord(SQLModel, table=True):
    __tablename__ = "sample_group_members"
    __table_args__ = (
        UniqueConstraint(
            "sample_group_id",
            "run_sample_id",
            name="uq_sample_group_members_sample_group_run_sample",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    sample_group_id: int = Field(foreign_key="sample_groups.id", index=True)
    run_sample_id: int = Field(foreign_key="run_samples.id", index=True)


class QCDecisionRecord(SQLModel, table=True):
    __tablename__ = "qc_decisions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    status: str = Field(max_length=32)
    reasons: list[str] = Field(default_factory=list, sa_type=JSON)
    cohort: str | None = Field(default=None, max_length=255)
    report_version: str | None = Field(default=None, max_length=255)
    policy_version: str | None = Field(default=None, max_length=255)


@asynccontextmanager
async def initialized_store(
    database_url: str,
    *,
    engine: AsyncEngine | None = None,
) -> AsyncIterator[SQLModelGoodomicsStore]:
    """Yield an initialized store and always dispose its engine afterward."""

    store = SQLModelGoodomicsStore(database_url, engine=engine)
    try:
        await store.ensure_schema()
        yield store
    finally:
        await store.dispose()


class SQLModelGoodomicsStore:
    """Application-owned SQL metadata engine and session factory."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        """Create one engine and typed session factory for this store."""

        self.database_url = database_url
        self._engine = engine or create_async_database_engine(database_url)
        self._sessionmaker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def session(self) -> AsyncSession:
        """Return a new session bound to the application-owned engine."""

        return self._sessionmaker()

    @asynccontextmanager
    async def _session_scope(
        self, session: AsyncSession | None = None
    ) -> AsyncIterator[AsyncSession]:
        """Reuse a caller session or own a standalone session boundary."""

        if session is not None:
            yield session
            return
        async with self.session() as owned_session:
            yield owned_session

    async def dispose(self) -> None:
        """Dispose the application-owned engine and its pooled connections."""

        await self._engine.dispose()

    async def ensure_schema(self) -> None:
        """Create any missing SQL metadata tables."""

        async with self._engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def ensure_default_project(self) -> Project:
        """Return the lazily created default project."""

        return await self.ensure_project(DEFAULT_PROJECT_SLUG)

    async def ensure_project(self, reference: str | None = None) -> Project:
        """Resolve or lazily create a project in a standalone transaction."""

        async with self.session() as session:
            project = await self.ensure_project_with_session(session, reference)
            await session.commit()
            return project

    async def ensure_project_with_session(
        self,
        session: AsyncSession,
        reference: str | None = None,
    ) -> Project:
        """Resolve or lazily create a project using the caller's session."""

        raw_reference = (reference or DEFAULT_PROJECT_SLUG).strip()
        # Project callers may pass a project id, slug, display-ish name, or no
        # value. Resolve existing ids/slugs first, then create by normalized slug.
        slug = (
            DEFAULT_PROJECT_SLUG
            if raw_reference in {"", DEFAULT_PROJECT_ID, DEFAULT_PROJECT_SLUG}
            else validate_project_slug(raw_reference)
        )
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
            await session.flush()
            await session.refresh(row)
        return _project_from_row(row)

    async def get_project(self, project_id: str) -> Project | None:
        """Return a project by public ID using a short-lived session."""

        async with self.session() as session:
            row = await get_record_by_field(
                session, ProjectRecord, ProjectRecord.project_id, project_id
            )
        return _project_from_row(row) if row is not None else None

    async def set_project_visibility(
        self,
        reference: str,
        visibility: Literal["private", "public"],
    ) -> str:
        """Set an existing project's visibility and return its stable ID."""

        async with self.session() as session:
            row = await _resolve_project_row(session, reference.strip())
            if row is None:
                raise ValueError(f"Project not found: {reference}")
            project_id = row.project_id
            row.visibility = visibility
            session.add(row)
            await session.commit()
            return project_id

    async def save_run(self, run: Run) -> None:
        # Lightweight save path for callers that provide a Run with embedded
        # samples. Rich ingest paths use replace_run_metadata().
        await self.replace_run_metadata(
            run,
            samples=run.samples,
            run_samples=[
                RunSample(
                    run_sample_id=f"{run.run_id}:{sample.sample_id}",
                    run_id=run.run_id,
                    sample_id=sample.sample_id,
                )
                for sample in run.samples
            ],
        )

    async def replace_run_metadata(
        self,
        run: Run,
        *,
        data_import: DataImport | None = None,
        analysis_types: list[AnalysisType] | None = None,
        analysis_methods: list[AnalysisMethod] | None = None,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        run_relationships: list[RunRelationship] | None = None,
        data_contracts: list[DataContract] | None = None,
        data_contract_analysis_types: list[DataContractAnalysisType] | None = None,
        run_contracts: list[RunContract] | None = None,
        run_contract_samples: list[RunContractSample] | None = None,
        data_contract_fields: list[DataContractField] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_groups: list[SampleGroup] | None = None,
        sample_group_members: list[SampleGroupMember] | None = None,
        session: AsyncSession | None = None,
    ) -> MetadataWriteResult:
        # Replace the SQL metadata rows for one run. Analytical metric
        # observations are intentionally not stored here; they live in DuckDB.
        normalized_links = [
            link.model_copy(update={"run_id": link.run_id or run.run_id})
            for link in file_links or []
        ]
        return await self.replace_runs_metadata(
            [run],
            data_import=data_import,
            analysis_types=analysis_types,
            analysis_methods=analysis_methods,
            subjects=subjects,
            samples=samples or run.samples,
            run_samples=run_samples,
            run_relationships=run_relationships,
            data_contracts=data_contracts,
            data_contract_analysis_types=data_contract_analysis_types,
            run_contracts=run_contracts,
            run_contract_samples=run_contract_samples,
            data_contract_fields=data_contract_fields,
            files=files,
            file_links=normalized_links,
            sample_groups=sample_groups,
            sample_group_members=sample_group_members,
            session=session,
        )

    async def replace_runs_metadata(
        self,
        runs: list[Run],
        *,
        data_import: DataImport | None = None,
        analysis_types: list[AnalysisType] | None = None,
        analysis_methods: list[AnalysisMethod] | None = None,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        run_relationships: list[RunRelationship] | None = None,
        data_contracts: list[DataContract] | None = None,
        data_contract_analysis_types: list[DataContractAnalysisType] | None = None,
        run_contracts: list[RunContract] | None = None,
        run_contract_samples: list[RunContractSample] | None = None,
        data_contract_fields: list[DataContractField] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_groups: list[SampleGroup] | None = None,
        sample_group_members: list[SampleGroupMember] | None = None,
        session: AsyncSession | None = None,
    ) -> MetadataWriteResult:
        # Bulk variant used by imports that produce multiple logical runs from
        # one parsed dataset, such as sample-scoped cBioPortal ingests.
        if not runs:
            raise ValueError("replace_runs_metadata requires at least one run")
        if analysis_types is None:
            analysis_types = [
                resolve_analysis_type(value)
                for value in sorted({run.analysis_type_id for run in runs})
            ]
        if analysis_methods is None:
            analysis_methods = [
                analysis_method(
                    method_id,
                    method_kind=_method_kind_from_runs(runs, method_id),
                )
                for method_id in sorted({run.method_id for run in runs})
            ]
        project_reference = runs[0].project_id or runs[0].project
        project = (
            await self.ensure_project_with_session(session, project_reference)
            if session is not None
            else await self.ensure_project(project_reference)
        )
        resolved_runs = [
            run.model_copy(
                update={
                    "project_id": project.project_id,
                    "project": run.project or project.slug or project.name,
                }
            )
            for run in runs
        ]
        run_ids = {run.run_id for run in resolved_runs}

        async with self._session_scope(session) as session:
            project_row = await _require_project_record(session, project.project_id)
            project_pk = _record_id(project_row)
            if data_import is not None:
                await _delete_data_import_scoped_metadata(
                    session, data_import.data_import_id
                )
            for run_id in sorted(run_ids):
                await _delete_run_scoped_metadata(session, run_id)
                existing = await get_record_by_field(
                    session, RunRecord, RunRecord.run_id, run_id
                )
                if existing is not None:
                    await session.delete(existing)

            data_import_row: DataImportRecord | None = None
            data_import_pk: int | None = None
            if data_import is not None:
                data_import_row = await _upsert_data_import(
                    session, data_import, project_pk
                )
                await session.flush()
                data_import_pk = _record_id(data_import_row)

            analysis_type_rows = await _upsert_analysis_types(
                session, analysis_types or [], project_pk
            )
            analysis_method_rows = await _upsert_analysis_methods(
                session, analysis_methods or [], project_pk
            )
            analysis_type_pk_by_label = _id_map(analysis_type_rows, "analysis_type_id")
            method_pk_by_label = _id_map(analysis_method_rows, "method_id")

            run_rows = [
                _run_record(
                    run,
                    project,
                    project_pk=project_pk,
                    data_import_pk=data_import_pk,
                    analysis_type_pk=analysis_type_pk_by_label[run.analysis_type_id],
                    method_pk=method_pk_by_label[run.method_id],
                )
                for run in resolved_runs
            ]
            session.add_all(run_rows)
            await session.flush()
            run_pk_by_label = _id_map(run_rows, "run_id")

            subject_rows = await _upsert_subjects(session, subjects or [], project_pk)
            subject_pk_by_label = _id_map(subject_rows, "subject_id")

            sample_rows = await _upsert_samples(
                session,
                samples or [],
                project_pk,
                subject_pk_by_label=subject_pk_by_label,
            )
            sample_pk_by_label = _id_map(sample_rows, "sample_id")

            run_sample_rows = [
                RunSampleRecord(
                    run_sample_id=run_sample.run_sample_id,
                    run_id=run_pk_by_label[run_sample.run_id],
                    sample_id=sample_pk_by_label[run_sample.sample_id],
                    role=run_sample.role,
                )
                for run_sample in run_samples or []
            ]
            session.add_all(run_sample_rows)
            await session.flush()
            run_sample_pk_by_label = _id_map(run_sample_rows, "run_sample_id")

            run_relationship_rows = [
                RunRelationshipRecord(
                    source_run_id=run_pk_by_label[relationship.source_run_id],
                    target_run_id=run_pk_by_label[relationship.target_run_id],
                    relationship_type=relationship.relationship_type,
                    metadata_json=dict(relationship.metadata_json),
                )
                for relationship in run_relationships or []
            ]
            session.add_all(run_relationship_rows)
            await session.flush()

            contract_rows = await _upsert_data_contracts(
                session, data_contracts or [], project_pk
            )
            contract_pk_by_label = _id_map(contract_rows, "data_contract_id")
            contract_field_rows = await _upsert_data_contract_fields(
                session,
                data_contract_fields or [],
                contract_pk_by_label,
            )
            contract_analysis_type_rows: list[DataContractAnalysisTypeRecord] = []
            for item in data_contract_analysis_types or []:
                contract_pk = contract_pk_by_label[item.data_contract_id]
                analysis_type_pk = analysis_type_pk_by_label[item.analysis_type_id]
                row = await get_record_where(
                    session,
                    DataContractAnalysisTypeRecord,
                    DataContractAnalysisTypeRecord.data_contract_id == contract_pk,
                    DataContractAnalysisTypeRecord.analysis_type_id == analysis_type_pk,
                )
                if row is None:
                    row = DataContractAnalysisTypeRecord(
                        data_contract_id=contract_pk,
                        analysis_type_id=analysis_type_pk,
                    )
                contract_analysis_type_rows.append(row)
            session.add_all(contract_analysis_type_rows)
            await session.flush()

            run_contract_rows = [
                RunContractRecord(
                    run_contract_id=item.run_contract_id,
                    run_id=run_pk_by_label[item.run_id],
                    data_contract_id=contract_pk_by_label[item.data_contract_id],
                    producer_method_id=_optional_map_lookup(
                        method_pk_by_label, item.producer_method_id
                    ),
                    producer_version=item.producer_version,
                    reference_context_json=dict(item.reference_context_json),
                    status=item.status,
                    started_at=item.started_at,
                    ended_at=item.ended_at,
                    metadata_json=dict(item.metadata_json),
                    created_at=item.created_at,
                )
                for item in run_contracts or []
            ]
            session.add_all(run_contract_rows)
            await session.flush()
            run_contract_pk_by_label = _id_map(run_contract_rows, "run_contract_id")
            run_contract_sample_rows = [
                RunContractSampleRecord(
                    run_contract_id=run_contract_pk_by_label[item.run_contract_id],
                    run_sample_id=run_sample_pk_by_label[item.run_sample_id],
                    availability=item.availability,
                    metadata_json=dict(item.metadata_json),
                )
                for item in run_contract_samples or []
            ]
            session.add_all(run_contract_sample_rows)
            await session.flush()

            file_rows = await _upsert_files(session, files or [], project_pk)
            file_pk_by_label = _id_map(file_rows, "file_id")

            file_link_rows = [
                FileLinkRecord(
                    file_id=file_pk_by_label[link.file_id],
                    project_id=project_pk,
                    data_import_id=(
                        data_import_pk if link.data_import_id is not None else None
                    ),
                    run_id=_optional_map_lookup(run_pk_by_label, link.run_id),
                    run_sample_id=_optional_map_lookup(
                        run_sample_pk_by_label, link.run_sample_id
                    ),
                    sample_id=_optional_map_lookup(sample_pk_by_label, link.sample_id),
                    data_contract_id=_optional_map_lookup(
                        contract_pk_by_label, link.data_contract_id
                    ),
                    link_role=link.link_role,
                )
                for link in file_links or []
            ]
            session.add_all(file_link_rows)
            await session.flush()

            group_ids = [
                sample_group.sample_group_id for sample_group in sample_groups or []
            ]
            if group_ids:
                group_pks = (
                    await session.exec(
                        select(SampleGroupRecord.id).where(
                            cast(Any, SampleGroupRecord.sample_group_id).in_(group_ids)
                        )
                    )
                ).all()
                await session.exec(
                    delete(SampleGroupMemberRecord).where(
                        cast(Any, SampleGroupMemberRecord.sample_group_id).in_(
                            group_pks
                        )
                    )
                )
                await session.exec(
                    delete(SampleGroupRecord).where(
                        cast(Any, SampleGroupRecord.sample_group_id).in_(group_ids)
                    )
                )

            sample_group_rows = [
                SampleGroupRecord(
                    sample_group_id=sample_group.sample_group_id,
                    project_id=project_pk,
                    name=sample_group.name,
                    kind=sample_group.kind,
                    description=sample_group.description,
                    definition_json=dict(sample_group.definition_json),
                    created_at=sample_group.created_at,
                    updated_at=sample_group.updated_at,
                    metadata_json=dict(sample_group.metadata_json),
                )
                for sample_group in sample_groups or []
            ]
            session.add_all(sample_group_rows)
            await session.flush()
            sample_group_pk_by_label = _id_map(sample_group_rows, "sample_group_id")

            sample_group_member_rows = [
                SampleGroupMemberRecord(
                    sample_group_id=sample_group_pk_by_label[member.sample_group_id],
                    run_sample_id=run_sample_pk_by_label[member.run_sample_id],
                )
                for member in sample_group_members or []
            ]
            session.add_all(sample_group_member_rows)
            await session.flush()

            result = MetadataWriteResult(
                project=_snapshot_record(project_row),
                analysis_types=_snapshot_records(analysis_type_rows),
                analysis_methods=_snapshot_records(analysis_method_rows),
                data_import=(
                    _snapshot_record(data_import_row)
                    if data_import_row is not None
                    else None
                ),
                runs=_snapshot_records(run_rows),
                subjects=_snapshot_records(subject_rows),
                samples=_snapshot_records(sample_rows),
                run_samples=_snapshot_records(run_sample_rows),
                run_relationships=_snapshot_records(run_relationship_rows),
                data_contracts=_snapshot_records(contract_rows),
                data_contract_analysis_types=_snapshot_records(
                    contract_analysis_type_rows
                ),
                run_contracts=_snapshot_records(run_contract_rows),
                run_contract_samples=_snapshot_records(run_contract_sample_rows),
                data_contract_fields=_snapshot_records(contract_field_rows),
                files=_snapshot_records(file_rows),
                file_links=_snapshot_records(file_link_rows),
                sample_groups=_snapshot_records(sample_group_rows),
                sample_group_members=_snapshot_records(sample_group_member_rows),
            )
            await session.commit()
        return result

    async def get_run(
        self, run_id: str, *, session: AsyncSession | None = None
    ) -> Run | None:
        """Return one run using a caller session or short-lived boundary."""

        async with self._session_scope(session) as session:
            run_row = await get_record_by_field(
                session, RunRecord, RunRecord.run_id, run_id
            )
            if run_row is None:
                return None
            sample_rows = (
                await session.exec(
                    select(SampleRecord)
                    .join(
                        RunSampleRecord,
                        RunSampleRecord.sample_id == SampleRecord.id,
                    )
                    .where(RunSampleRecord.run_id == run_row.id)
                )
            ).all()
            project_id = await _project_public_id(session, run_row.project_id)
            data_import_id = await _data_import_public_id(
                session, run_row.data_import_id
            )
            analysis_type_id = await _analysis_type_public_id(
                session, run_row.analysis_type_id
            )
            method_id = await _analysis_method_public_id(session, run_row.method_id)
            samples = [
                await _sample_from_row_public(session, row) for row in sample_rows
            ]
        return Run(
            run_id=run_row.run_id,
            project=run_row.project,
            project_id=project_id,
            data_import_id=data_import_id,
            name=run_row.name,
            run_kind=run_row.run_kind,
            analysis_type_id=analysis_type_id,
            method_id=method_id,
            method_version=run_row.method_version,
            parameters_json=run_row.parameters_json,
            started_at=run_row.started_at,
            ended_at=run_row.ended_at,
            status=run_row.status,
            metadata_json=run_row.metadata_json,
            created_at=run_row.created_at,
            samples=samples,
        )

    async def replace_run_file_metadata(
        self,
        session: AsyncSession,
        run_id: str,
        files: list[FileAsset],
        file_links: list[FileLink],
        project_id: str,
    ) -> None:
        # File replacement is scoped to links from this run. Linked assets are
        # removed with the links so re-ingesting a run does not leave stale files.
        project_row = await _require_project_record(session, project_id)
        project_pk = _record_id(project_row)
        run_row = await get_record_by_field(
            session, RunRecord, RunRecord.run_id, run_id
        )
        run_pk = _record_id(run_row) if run_row is not None else None
        file_ids = (
            await session.exec(
                select(FileLinkRecord.file_id).where(FileLinkRecord.run_id == run_pk)
            )
        ).all()
        await session.exec(
            delete(FileLinkRecord).where(FileLinkRecord.run_id == run_pk)
        )
        if file_ids:
            await session.exec(
                delete(FileRecord).where(cast(Any, FileRecord.id).in_(file_ids))
            )
        file_rows = await _upsert_files(session, files, project_pk)
        file_pk_by_label = _id_map(file_rows, "file_id")
        data_import_rows = await _records_by_field(
            session,
            DataImportRecord,
            DataImportRecord.data_import_id,
            [link.data_import_id for link in file_links if link.data_import_id],
        )
        run_rows = await _records_by_field(
            session,
            RunRecord,
            RunRecord.run_id,
            [link.run_id or run_id for link in file_links],
        )
        run_sample_rows = await _records_by_field(
            session,
            RunSampleRecord,
            RunSampleRecord.run_sample_id,
            [link.run_sample_id for link in file_links if link.run_sample_id],
        )
        sample_rows = await _records_by_field(
            session,
            SampleRecord,
            SampleRecord.sample_id,
            [link.sample_id for link in file_links if link.sample_id],
        )
        contract_rows = await _data_contract_records_by_label(
            session,
            [link.data_contract_id for link in file_links if link.data_contract_id],
            project_id=project_pk,
        )
        data_import_map = _id_map(data_import_rows.values(), "data_import_id")
        run_map = _id_map(run_rows.values(), "run_id")
        run_sample_map = _id_map(run_sample_rows.values(), "run_sample_id")
        sample_map = _id_map(sample_rows.values(), "sample_id")
        contract_map = _id_map(contract_rows.values(), "data_contract_id")
        session.add_all(
            [
                FileLinkRecord(
                    file_id=file_pk_by_label[link.file_id],
                    project_id=project_pk,
                    data_import_id=_optional_map_lookup(
                        data_import_map, link.data_import_id
                    ),
                    run_id=_optional_map_lookup(run_map, link.run_id or run_id),
                    run_sample_id=_optional_map_lookup(
                        run_sample_map, link.run_sample_id
                    ),
                    sample_id=_optional_map_lookup(sample_map, link.sample_id),
                    data_contract_id=_optional_map_lookup(
                        contract_map, link.data_contract_id
                    ),
                    link_role=link.link_role,
                )
                for link in file_links
            ]
        )
        await session.commit()


async def get_record_where(
    session: AsyncSession,
    model: type[RecordT],
    *conditions: Any,
) -> RecordT | None:
    return (await session.exec(select(model).where(*conditions))).first()


async def get_record_by_field(
    session: AsyncSession,
    model: type[RecordT],
    field: Any,
    value: Any,
) -> RecordT | None:
    return await get_record_where(session, model, field == value)


def metadata_id_maps_from_records(
    result: MetadataWriteResult,
) -> dict[str, dict[str, int]]:
    """Build DuckDB integer-id lookup maps from persisted metadata records."""

    return {
        "project_id": _id_map([result.project], "project_id"),
        "analysis_type_id": _id_map(result.analysis_types, "analysis_type_id"),
        "method_id": _id_map(result.analysis_methods, "method_id"),
        "data_contract_id": _id_map(result.data_contracts, "data_contract_id"),
        "run_contract_id": _id_map(result.run_contracts, "run_contract_id"),
        "field_id": _id_map(result.data_contract_fields, "field_id"),
        "run_id": _id_map(result.runs, "run_id"),
        "run_sample_id": _id_map(result.run_samples, "run_sample_id"),
        "sample_id": _id_map(result.samples, "sample_id"),
        "source_file_id": _id_map(result.files, "file_id"),
        "sample_group_id": _id_map(result.sample_groups, "sample_group_id"),
        "subject_id": _id_map(result.subjects, "subject_id"),
    }


def _id_map(records: Iterable[SQLModel], label_name: str) -> dict[str, int]:
    mapped: dict[str, int] = {}
    for record in records:
        label = getattr(record, label_name, None)
        identifier = getattr(record, "id", None)
        if label is not None and identifier is not None:
            mapped[str(label)] = int(identifier)
    return mapped


def _record_id(row: SQLModel | None) -> int:
    identifier = getattr(row, "id", None)
    if identifier is None:
        raise RuntimeError("Expected persisted SQL record to have an integer id")
    return int(identifier)


def _snapshot_record(record: RecordT) -> RecordT:
    return record.model_copy(deep=True)


def _snapshot_records(records: Iterable[RecordT]) -> list[RecordT]:
    return [_snapshot_record(record) for record in records]


def _optional_map_lookup(mapping: dict[str, int], label: str | None) -> int | None:
    return mapping[label] if label else None


async def _require_project_record(
    session: AsyncSession, project_id: str
) -> ProjectRecord:
    row = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.project_id, project_id
    )
    if row is None:
        raise RuntimeError(f"Project not found after ensure_project: {project_id}")
    return row


async def _records_by_field(
    session: AsyncSession,
    model: type[RecordT],
    field: Any,
    labels: Iterable[str],
) -> dict[str, RecordT]:
    unique_labels = sorted({label for label in labels if label})
    if not unique_labels:
        return {}
    rows = (
        await session.exec(select(model).where(cast(Any, field).in_(unique_labels)))
    ).all()
    return {str(getattr(row, field.key)): row for row in rows}


async def _data_contract_records_by_label(
    session: AsyncSession,
    labels: Iterable[str],
    *,
    project_id: int,
) -> dict[str, DataContractRecord]:
    unique_labels = sorted({label for label in labels if label})
    if not unique_labels:
        return {}
    rows = (
        await session.exec(
            select(DataContractRecord)
            .where(cast(Any, DataContractRecord.data_contract_id).in_(unique_labels))
            .where(DataContractRecord.project_id == project_id)
        )
    ).all()
    return {row.data_contract_id: row for row in rows}


async def _upsert_subjects(
    session: AsyncSession,
    subjects: list[Subject],
    project_id: int,
) -> list[SubjectRecord]:
    existing = await _records_by_field(
        session,
        SubjectRecord,
        SubjectRecord.subject_id,
        [subject.subject_id for subject in subjects],
    )
    rows: list[SubjectRecord] = []
    for subject in subjects:
        row = existing.get(subject.subject_id)
        if row is None:
            row = SubjectRecord(
                subject_id=subject.subject_id,
                project_id=project_id,
                metadata_json=dict(subject.metadata_json),
            )
        else:
            row.project_id = project_id
            row.metadata_json = dict(subject.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_analysis_types(
    session: AsyncSession,
    analysis_types: list[AnalysisType],
    project_id: int,
) -> list[AnalysisTypeRecord]:
    rows: list[AnalysisTypeRecord] = []
    for item in analysis_types:
        row = await get_record_where(
            session,
            AnalysisTypeRecord,
            AnalysisTypeRecord.analysis_type_id == item.analysis_type_id,
            AnalysisTypeRecord.project_id == project_id,
        )
        if row is None:
            row = AnalysisTypeRecord(
                analysis_type_id=item.analysis_type_id,
                project_id=project_id,
                name=item.name,
            )
        row.name = item.name
        row.description = item.description
        row.metadata_json = dict(item.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_analysis_methods(
    session: AsyncSession,
    methods: list[AnalysisMethod],
    project_id: int,
) -> list[AnalysisMethodRecord]:
    rows: list[AnalysisMethodRecord] = []
    for item in methods:
        row = await get_record_where(
            session,
            AnalysisMethodRecord,
            AnalysisMethodRecord.method_id == item.method_id,
            AnalysisMethodRecord.project_id == project_id,
        )
        if row is None:
            row = AnalysisMethodRecord(
                method_id=item.method_id,
                project_id=project_id,
                name=item.name,
                method_kind=item.method_kind,
            )
        row.name = item.name
        row.method_kind = item.method_kind
        row.description = item.description
        row.metadata_json = dict(item.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_samples(
    session: AsyncSession,
    samples: list[Sample],
    project_id: int,
    *,
    subject_pk_by_label: dict[str, int] | None = None,
) -> list[SampleRecord]:
    existing = await _records_by_field(
        session,
        SampleRecord,
        SampleRecord.sample_id,
        [sample.sample_id for sample in samples],
    )
    rows: list[SampleRecord] = []
    for sample in samples:
        subject_pk = (
            _optional_map_lookup(subject_pk_by_label or {}, sample.subject_id)
            if sample.subject_id
            else None
        )
        row = existing.get(sample.sample_id)
        if row is None:
            row = SampleRecord(
                sample_id=sample.sample_id,
                project_id=project_id,
                subject_id=subject_pk,
                sample_name=sample.sample_name,
                metadata_json=dict(sample.metadata_json),
            )
        else:
            row.project_id = project_id
            row.subject_id = subject_pk
            row.sample_name = sample.sample_name
            row.metadata_json = dict(sample.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_data_contracts(
    session: AsyncSession,
    contracts: list[DataContract],
    project_id: int,
) -> list[DataContractRecord]:
    existing = await _data_contract_records_by_label(
        session,
        [contract.data_contract_id for contract in contracts],
        project_id=project_id,
    )
    rows: list[DataContractRecord] = []
    for contract in contracts:
        row = existing.get(contract.data_contract_id)
        contract_project_id = project_id
        if row is None:
            row = DataContractRecord(
                data_contract_id=contract.data_contract_id,
                project_id=contract_project_id,
                name=contract.name,
                data_type=contract.data_type,
                feature_type=contract.feature_type,
                value_type=contract.value_type,
                unit=contract.unit,
                entity_grain=contract.entity_grain,
                value_semantics=contract.value_semantics,
                summary_json=dict(contract.summary_json),
                last_profiled_at=contract.last_profiled_at,
                source_fingerprint=contract.source_fingerprint,
                query_modes_json=dict(contract.query_modes_json),
                intrinsic_producer_families_json=dict(
                    contract.intrinsic_producer_families_json
                ),
                description=contract.description,
                metadata_json=dict(contract.metadata_json),
            )
        else:
            row.project_id = contract_project_id
            row.name = contract.name
            row.data_type = contract.data_type
            row.feature_type = contract.feature_type
            row.value_type = contract.value_type
            row.unit = contract.unit
            row.entity_grain = contract.entity_grain
            row.value_semantics = contract.value_semantics
            row.summary_json = dict(contract.summary_json)
            row.last_profiled_at = contract.last_profiled_at
            row.source_fingerprint = contract.source_fingerprint
            row.query_modes_json = dict(contract.query_modes_json)
            row.intrinsic_producer_families_json = dict(
                contract.intrinsic_producer_families_json
            )
            row.description = contract.description
            row.metadata_json = dict(contract.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_data_contract_fields(
    session: AsyncSession,
    fields: list[DataContractField],
    contract_pk_by_label: dict[str, int],
) -> list[DataContractFieldRecord]:
    if not fields:
        return []
    field_ids_by_contract_pk: dict[int, set[str]] = {}
    for field in fields:
        contract_pk = contract_pk_by_label.get(field.data_contract_id)
        if contract_pk is not None:
            field_ids_by_contract_pk.setdefault(contract_pk, set()).add(field.field_id)

    for contract_pk, field_ids in sorted(field_ids_by_contract_pk.items()):
        await session.exec(
            delete(DataContractFieldRecord)
            .where(DataContractFieldRecord.data_contract_id == contract_pk)
            .where(cast(Any, DataContractFieldRecord.field_id).in_(sorted(field_ids)))
        )
    rows = [
        DataContractFieldRecord(
            data_contract_id=contract_pk_by_label[field.data_contract_id],
            field_id=field.field_id,
            field_role=field.field_role,
            entity_scope=field.entity_scope,
            display_name=field.display_name,
            value_type=field.value_type,
            unit=field.unit,
            direction=field.direction,
            description=field.description,
            priority=field.priority,
            primary_table=field.primary_table,
            physical_tables_json=dict(field.physical_tables_json),
            query_ref_json=dict(field.query_ref_json),
            summary_json=dict(field.summary_json),
            metadata_json=dict(field.metadata_json),
        )
        for field in fields
        if field.data_contract_id in contract_pk_by_label
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_files(
    session: AsyncSession,
    files: list[FileAsset],
    project_id: int,
) -> list[FileRecord]:
    existing = await _records_by_field(
        session,
        FileRecord,
        FileRecord.file_id,
        [file.file_id for file in files],
    )
    rows: list[FileRecord] = []
    for file in files:
        row = existing.get(file.file_id)
        if row is None:
            row = FileRecord(
                file_id=file.file_id,
                project_id=project_id,
                path=file.path,
                uri=file.uri,
                storage_location=file.storage_location,
                object_key=file.object_key,
                file_role=file.file_role,
                format=file.format,
                size_bytes=file.size_bytes,
                sha256=file.sha256,
                created_at=file.created_at,
                metadata_json=dict(file.metadata_json),
            )
        else:
            row.project_id = project_id
            row.path = file.path
            row.uri = file.uri
            row.storage_location = file.storage_location
            row.object_key = file.object_key
            row.file_role = file.file_role
            row.format = file.format
            row.size_bytes = file.size_bytes
            row.sha256 = file.sha256
            row.created_at = file.created_at
            row.metadata_json = dict(file.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_sample(
    session: AsyncSession,
    sample: Sample,
    project_id: int,
    *,
    subject_pk_by_label: dict[str, int] | None = None,
) -> SampleRecord:
    subject_pk = (
        _optional_map_lookup(subject_pk_by_label or {}, sample.subject_id)
        if sample.subject_id
        else None
    )
    row = await get_record_by_field(
        session, SampleRecord, SampleRecord.sample_id, sample.sample_id
    )
    if row is None:
        row = SampleRecord(
            sample_id=sample.sample_id,
            project_id=project_id,
            subject_id=subject_pk,
            sample_name=sample.sample_name,
            metadata_json=dict(sample.metadata_json),
        )
    else:
        row.project_id = project_id
        row.subject_id = subject_pk
        row.sample_name = sample.sample_name
        row.metadata_json = dict(sample.metadata_json)
    session.add(row)
    return row


async def _upsert_data_import(
    session: AsyncSession,
    data_import: DataImport,
    project_id: int,
) -> DataImportRecord:
    row = await get_record_by_field(
        session,
        DataImportRecord,
        DataImportRecord.data_import_id,
        data_import.data_import_id,
    )
    if row is None:
        row = DataImportRecord(
            data_import_id=data_import.data_import_id,
            project_id=project_id,
            source_type=data_import.source_type,
            source_uri=data_import.source_uri,
            source_path=data_import.source_path,
            importer_name=data_import.importer_name,
            importer_version=data_import.importer_version,
            status=data_import.status,
            started_at=data_import.started_at,
            ended_at=data_import.ended_at,
            parameters_json=dict(data_import.parameters_json),
            summary_json=dict(data_import.summary_json),
            metadata_json=dict(data_import.metadata_json),
            created_at=data_import.created_at,
        )
    else:
        row.project_id = project_id
        row.source_type = data_import.source_type
        row.source_uri = data_import.source_uri
        row.source_path = data_import.source_path
        row.importer_name = data_import.importer_name
        row.importer_version = data_import.importer_version
        row.status = data_import.status
        row.started_at = data_import.started_at
        row.ended_at = data_import.ended_at
        row.parameters_json = dict(data_import.parameters_json)
        row.summary_json = dict(data_import.summary_json)
        row.metadata_json = dict(data_import.metadata_json)
        row.created_at = data_import.created_at
    session.add(row)
    return row


def _sample_from_row(row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=str(row.project_id) if row.project_id is not None else None,
        subject_id=str(row.subject_id) if row.subject_id is not None else None,
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


async def _sample_from_row_public(session: AsyncSession, row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=await _project_public_id(session, row.project_id),
        subject_id=await _subject_public_id(session, row.subject_id),
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


async def _project_public_id(
    session: AsyncSession, project_pk: int | None
) -> str | None:
    if project_pk is None:
        return None
    row = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.id, project_pk
    )
    return row.project_id if row is not None else None


async def _subject_public_id(
    session: AsyncSession, subject_pk: int | None
) -> str | None:
    if subject_pk is None:
        return None
    row = await get_record_by_field(
        session, SubjectRecord, SubjectRecord.id, subject_pk
    )
    return row.subject_id if row is not None else None


async def _data_import_public_id(
    session: AsyncSession, data_import_pk: int | None
) -> str | None:
    if data_import_pk is None:
        return None
    row = await get_record_by_field(
        session, DataImportRecord, DataImportRecord.id, data_import_pk
    )
    return row.data_import_id if row is not None else None


async def _analysis_type_public_id(session: AsyncSession, value: int) -> str:
    row = await get_record_by_field(
        session, AnalysisTypeRecord, AnalysisTypeRecord.id, value
    )
    if row is None:
        raise RuntimeError(f"Analysis type metadata row {value} was not found")
    return row.analysis_type_id


async def _analysis_method_public_id(session: AsyncSession, value: int) -> str:
    row = await get_record_by_field(
        session, AnalysisMethodRecord, AnalysisMethodRecord.id, value
    )
    if row is None:
        raise RuntimeError(f"Analysis method metadata row {value} was not found")
    return row.method_id


def _run_record(
    run: Run,
    project: Project,
    *,
    project_pk: int,
    data_import_pk: int | None,
    analysis_type_pk: int,
    method_pk: int,
) -> RunRecord:
    return RunRecord(
        run_id=run.run_id,
        project_id=project_pk,
        data_import_id=data_import_pk,
        project=run.project or project.slug or project.name,
        name=run.name,
        run_kind=run.run_kind,
        analysis_type_id=analysis_type_pk,
        method_id=method_pk,
        method_version=run.method_version,
        parameters_json=dict(run.parameters_json),
        started_at=run.started_at,
        ended_at=run.ended_at,
        status=run.status,
        metadata_json=dict(run.metadata_json),
        created_at=run.created_at,
    )


def _method_kind_from_runs(runs: list[Run], method_id: str) -> str:
    run_kind = next(run.run_kind for run in runs if run.method_id == method_id)
    if run_kind == "notebook_run":
        return "notebook"
    if run_kind == "benchmark_run":
        return "benchmark"
    if run_kind == "imported_result":
        return "importer"
    return "workflow"


async def _delete_data_import_scoped_metadata(
    session: AsyncSession,
    data_import_id: str,
) -> None:
    # Replacing an import should remove source files and imported result runs
    # previously owned by that import. Project-level samples/subjects remain.
    data_import_row = await get_record_by_field(
        session,
        DataImportRecord,
        DataImportRecord.data_import_id,
        data_import_id,
    )
    if data_import_row is None:
        return
    data_import_pk = _record_id(data_import_row)
    run_ids = (
        await session.exec(
            select(RunRecord.id).where(RunRecord.data_import_id == data_import_pk)
        )
    ).all()
    file_ids = (
        await session.exec(
            select(FileLinkRecord.file_id).where(
                FileLinkRecord.data_import_id == data_import_pk
            )
        )
    ).all()
    await session.exec(
        delete(FileLinkRecord).where(FileLinkRecord.data_import_id == data_import_pk)
    )
    if run_ids:
        run_contract_ids = (
            await session.exec(
                select(RunContractRecord.id).where(
                    cast(Any, RunContractRecord.run_id).in_(list(run_ids))
                )
            )
        ).all()
        if run_contract_ids:
            await session.exec(
                delete(RunContractSampleRecord).where(
                    cast(Any, RunContractSampleRecord.run_contract_id).in_(
                        list(run_contract_ids)
                    )
                )
            )
            await session.exec(
                delete(RunContractRecord).where(
                    cast(Any, RunContractRecord.id).in_(list(run_contract_ids))
                )
            )
        await session.exec(
            delete(RunRelationshipRecord).where(
                cast(Any, RunRelationshipRecord.source_run_id).in_(list(run_ids))
                | cast(Any, RunRelationshipRecord.target_run_id).in_(list(run_ids))
            )
        )
        await session.exec(
            delete(RunSampleRecord).where(
                cast(Any, RunSampleRecord.run_id).in_(list(run_ids))
            )
        )
        await session.exec(
            delete(RunRecord).where(cast(Any, RunRecord.id).in_(list(run_ids)))
        )
    if file_ids:
        await session.exec(
            delete(FileRecord).where(cast(Any, FileRecord.id).in_(list(file_ids)))
        )
    await session.delete(data_import_row)


async def _delete_run_scoped_metadata(
    session: AsyncSession,
    run_id: str,
) -> None:
    # Delete rows owned by this run before replacement, while leaving shared
    # project-level subjects/samples intact.
    run_row = await get_record_by_field(session, RunRecord, RunRecord.run_id, run_id)
    if run_row is None:
        return
    run_pk = _record_id(run_row)
    run_sample_ids = (
        await session.exec(
            select(RunSampleRecord.id).where(RunSampleRecord.run_id == run_pk)
        )
    ).all()
    run_contract_ids = (
        await session.exec(
            select(RunContractRecord.id).where(RunContractRecord.run_id == run_pk)
        )
    ).all()
    contract_ids = (
        await session.exec(
            select(DataContractRecord.id).where(
                DataContractRecord.data_contract_id.startswith(f"{run_id}:")
            )
        )
    ).all()
    file_ids = (
        await session.exec(
            select(FileLinkRecord.file_id).where(FileLinkRecord.run_id == run_pk)
        )
    ).all()
    sample_group_ids: list[int] = []
    if run_sample_ids:
        sample_group_ids = list(
            (
                await session.exec(
                    select(SampleGroupMemberRecord.sample_group_id).where(
                        cast(Any, SampleGroupMemberRecord.run_sample_id).in_(
                            list(run_sample_ids)
                        )
                    )
                )
            ).all()
        )
    await session.exec(
        delete(RunRelationshipRecord).where(
            (RunRelationshipRecord.source_run_id == run_pk)
            | (RunRelationshipRecord.target_run_id == run_pk)
        )
    )
    if run_contract_ids:
        await session.exec(
            delete(RunContractSampleRecord).where(
                cast(Any, RunContractSampleRecord.run_contract_id).in_(
                    list(run_contract_ids)
                )
            )
        )
        await session.exec(
            delete(RunContractRecord).where(
                cast(Any, RunContractRecord.id).in_(list(run_contract_ids))
            )
        )
    await session.exec(delete(FileLinkRecord).where(FileLinkRecord.run_id == run_pk))
    await session.exec(delete(RunSampleRecord).where(RunSampleRecord.run_id == run_pk))
    if contract_ids:
        await session.exec(
            delete(DataContractFieldRecord).where(
                cast(Any, DataContractFieldRecord.data_contract_id).in_(
                    list(contract_ids)
                )
            )
        )
        await session.exec(
            delete(FileLinkRecord).where(
                cast(Any, FileLinkRecord.data_contract_id).in_(list(contract_ids))
            )
        )
    await session.exec(
        delete(DataContractRecord).where(
            DataContractRecord.data_contract_id.startswith(f"{run_id}:")
        )
    )
    if file_ids:
        await session.exec(
            delete(FileRecord).where(cast(Any, FileRecord.id).in_(file_ids))
        )
    if sample_group_ids:
        await session.exec(
            delete(SampleGroupMemberRecord).where(
                SampleGroupMemberRecord.sample_group_id.in_(list(sample_group_ids))
            )
        )
        await session.exec(
            delete(SampleGroupRecord).where(
                cast(Any, SampleGroupRecord.id).in_(list(sample_group_ids))
            )
        )


async def _resolve_project_row(
    session: AsyncSession, reference: str | None
) -> ProjectRecord | None:
    # Prefer stable project-id lookup, then fall back to slug lookup for user-facing
    # project references passed through CLI, API, and SDK entry points.
    if reference is None or reference == "":
        reference = DEFAULT_PROJECT_SLUG
    row = await get_record_by_field(
        session, ProjectRecord, ProjectRecord.project_id, reference
    )
    if row is not None:
        return row
    return await get_record_by_field(
        session, ProjectRecord, ProjectRecord.slug, reference
    )


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
