# pyright: reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncEngine
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
from goodomics.schemas.models import (
    DataImport,
    DataProfile,
    DataProfileField,
    FileAsset,
    FileLink,
    Project,
    Run,
    RunSample,
    Sample,
    SampleSet,
    SampleSetMember,
    Subject,
)
from goodomics.storage.database import create_async_database_engine

RecordT = TypeVar("RecordT", bound=SQLModel)


@dataclass(frozen=True)
class CatalogWriteResult:
    project: ProjectRecord
    data_import: DataImportRecord | None
    runs: list[RunRecord]
    subjects: list[SubjectRecord]
    samples: list[SampleRecord]
    run_samples: list[RunSampleRecord]
    data_profiles: list[DataProfileRecord]
    data_profile_fields: list[DataProfileFieldRecord]
    files: list[FileRecord]
    file_links: list[FileLinkRecord]
    sample_sets: list[SampleSetRecord]
    sample_set_members: list[SampleSetMemberRecord]


# These SQLModel classes are persistence records, not the public Goodomics
# schemas. Keep database-only concerns here: table names, primary keys, indexes,
# foreign keys, JSON column storage, and nullable columns used by SQL backends.
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

    id: int | None = Field(default=None, primary_key=True)
    project_id: str = Field(max_length=255, unique=True, index=True)
    slug: str | None = Field(default=None, max_length=255, index=True)
    name: str = Field(max_length=255)
    description: str | None = None
    default_report_id: str | None = Field(default=None, max_length=255)
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

    id: int | None = Field(default=None, primary_key=True)
    run_sample_id: str = Field(max_length=512, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    run_id: int = Field(foreign_key="runs.id", index=True)
    sample_id: int | None = Field(default=None, foreign_key="samples.id", index=True)
    assay: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=64)
    status: str = Field(default="unknown", max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataProfileRecord(SQLModel, table=True):
    __tablename__ = "data_profiles"

    id: int | None = Field(default=None, primary_key=True)
    data_profile_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
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
    entity_grain: str | None = Field(default=None, max_length=128)
    value_semantics: str | None = Field(default=None, max_length=128)
    primary_table: str | None = Field(default=None, max_length=128)
    physical_tables_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    summary_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    last_profiled_at: datetime | None = None
    source_fingerprint: str | None = Field(default=None, max_length=255)
    query_modes_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    mcp_description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class DataProfileFieldRecord(SQLModel, table=True):
    __tablename__ = "data_profile_fields"

    id: int | None = Field(default=None, primary_key=True)
    data_profile_id: int = Field(foreign_key="data_profiles.id", index=True)
    field_id: str = Field(max_length=255, index=True)
    field_role: str = Field(default="metric", max_length=64, index=True)
    entity_scope: str | None = Field(default=None, max_length=128)
    display_name: str = Field(max_length=255)
    value_type: str = Field(default="numeric", max_length=64, index=True)
    unit: str | None = Field(default=None, max_length=64)
    direction: str | None = Field(default=None, max_length=64)
    description: str | None = None
    priority: str | None = Field(default=None, max_length=64)
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
    file_role: str = Field(max_length=255)
    format: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = None
    sha256: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class FileLinkRecord(SQLModel, table=True):
    __tablename__ = "file_links"

    # A file can be linked to a run, run sample, sample, or data profile without
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
    data_profile_id: int | None = Field(
        default=None, foreign_key="data_profiles.id", index=True
    )
    link_role: str = Field(max_length=255)


class SampleSetRecord(SQLModel, table=True):
    __tablename__ = "sample_sets"

    id: int | None = Field(default=None, primary_key=True)
    sample_set_id: str = Field(max_length=255, unique=True, index=True)
    project_id: int | None = Field(default=None, foreign_key="projects.id", index=True)
    name: str = Field(max_length=255)
    kind: str = Field(default="cohort", max_length=64)
    description: str | None = None
    definition_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleSetMemberRecord(SQLModel, table=True):
    __tablename__ = "sample_set_members"

    id: int | None = Field(default=None, primary_key=True)
    sample_set_id: int = Field(foreign_key="sample_sets.id", index=True)
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


class SQLModelGoodomicsStore:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self.database_url = database_url
        self.engine = engine

    def _get_engine(self) -> AsyncEngine:
        # Engine creation is centralized so every caller gets the same SQLite
        # parent-directory handling and future connection options.
        if self.engine is None:
            self.engine = create_async_database_engine(self.database_url)
        return self.engine

    async def ensure_schema(self) -> None:
        async with self._get_engine().begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def ensure_default_project(self) -> Project:
        return await self.ensure_project(DEFAULT_PROJECT_SLUG)

    async def ensure_project(self, reference: str | None = None) -> Project:
        await self.ensure_schema()
        raw_reference = (reference or DEFAULT_PROJECT_SLUG).strip()
        # Project callers may pass a project id, slug, display-ish name, or no
        # value. Resolve existing ids/slugs first, then create by normalized slug.
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
                    DEFAULT_PROJECT_ID
                    if slug == DEFAULT_PROJECT_SLUG
                    else new_project_id()
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
            row = await get_record_by_field(
                session, ProjectRecord, ProjectRecord.project_id, project_id
            )
        return _project_from_row(row) if row is not None else None

    async def save_run(self, run: Run) -> None:
        # Lightweight save path for callers that provide a Run with embedded
        # samples. Rich ingest paths use replace_run_catalog().
        await self.ensure_schema()
        project = await self.ensure_project(run.project_id or run.project)
        async with AsyncSession(self._get_engine()) as session:
            project_row = await _require_project_record(session, project.project_id)
            project_pk = _record_id(project_row)
            existing_run = await get_record_by_field(
                session, RunRecord, RunRecord.run_id, run.run_id
            )
            existing_run_pk = _record_id(existing_run) if existing_run else None
            await session.exec(
                delete(QCDecisionRecord).where(
                    QCDecisionRecord.run_id == existing_run_pk
                )
            )
            await session.exec(
                delete(RunSampleRecord).where(RunSampleRecord.run_id == existing_run_pk)
            )

            if existing_run is not None:
                await session.delete(existing_run)

            run_row = _run_record(
                run,
                project,
                project_pk=project_pk,
                data_import_pk=None,
            )
            session.add(run_row)
            await session.flush()
            run_pk = _record_id(run_row)
            if run.samples:
                sample_pk_by_label: dict[str, int] = {}
                for sample in run.samples:
                    sample_row = await _upsert_sample(session, sample, project_pk)
                    await session.flush()
                    sample_pk_by_label[sample.sample_id] = _record_id(sample_row)
                session.add_all(
                    [
                        RunSampleRecord(
                            run_sample_id=f"{run.run_id}:{sample.sample_id}",
                            project_id=project_pk,
                            run_id=run_pk,
                            sample_id=sample_pk_by_label.get(sample.sample_id),
                            assay=run.assay,
                            status="unknown",
                        )
                        for sample in run.samples
                    ]
                )
            await session.commit()

    async def replace_run_catalog(
        self,
        run: Run,
        *,
        data_import: DataImport | None = None,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        data_profiles: list[DataProfile] | None = None,
        data_profile_fields: list[DataProfileField] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_sets: list[SampleSet] | None = None,
        sample_set_members: list[SampleSetMember] | None = None,
    ) -> CatalogWriteResult:
        # Replace the SQL catalog rows for one run. Analytical metric
        # observations are intentionally not stored here; they live in DuckDB.
        normalized_links = [
            link.model_copy(update={"run_id": link.run_id or run.run_id})
            for link in file_links or []
        ]
        return await self.replace_runs_catalog(
            [run],
            data_import=data_import,
            subjects=subjects,
            samples=samples or run.samples,
            run_samples=run_samples,
            data_profiles=data_profiles,
            data_profile_fields=data_profile_fields,
            files=files,
            file_links=normalized_links,
            sample_sets=sample_sets,
            sample_set_members=sample_set_members,
        )

    async def replace_runs_catalog(
        self,
        runs: list[Run],
        *,
        data_import: DataImport | None = None,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        data_profiles: list[DataProfile] | None = None,
        data_profile_fields: list[DataProfileField] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_sets: list[SampleSet] | None = None,
        sample_set_members: list[SampleSetMember] | None = None,
    ) -> CatalogWriteResult:
        # Bulk variant used by imports that produce multiple logical runs from
        # one parsed dataset, such as sample-scoped cBioPortal ingests.
        if not runs:
            raise ValueError("replace_runs_catalog requires at least one run")
        await self.ensure_schema()
        project = await self.ensure_project(runs[0].project_id or runs[0].project)
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

        async with AsyncSession(self._get_engine()) as session:
            project_row = await _require_project_record(session, project.project_id)
            project_pk = _record_id(project_row)
            if data_import is not None:
                await _delete_data_import_scoped_catalog(
                    session, data_import.data_import_id
                )
            for run_id in sorted(run_ids):
                await _delete_run_scoped_catalog(session, run_id)
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

            run_rows = [
                _run_record(
                    run,
                    project,
                    project_pk=project_pk,
                    data_import_pk=data_import_pk,
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
                    project_id=project_pk,
                    run_id=run_pk_by_label[run_sample.run_id],
                    sample_id=_optional_map_lookup(
                        sample_pk_by_label, run_sample.sample_id
                    ),
                    assay=run_sample.assay,
                    role=run_sample.role,
                    status=run_sample.status,
                    metadata_json=dict(run_sample.metadata_json),
                )
                for run_sample in run_samples or []
            ]
            session.add_all(run_sample_rows)
            await session.flush()
            run_sample_pk_by_label = _id_map(run_sample_rows, "run_sample_id")

            profile_rows = await _upsert_data_profiles(
                session, data_profiles or [], project_pk
            )
            profile_pk_by_label = _id_map(profile_rows, "data_profile_id")
            profile_field_rows = await _upsert_data_profile_fields(
                session,
                data_profile_fields or [],
                profile_pk_by_label,
            )

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
                    data_profile_id=_optional_map_lookup(
                        profile_pk_by_label, link.data_profile_id
                    ),
                    link_role=link.link_role,
                )
                for link in file_links or []
            ]
            session.add_all(file_link_rows)
            await session.flush()

            set_ids = [sample_set.sample_set_id for sample_set in sample_sets or []]
            if set_ids:
                set_pks = (
                    await session.exec(
                        select(SampleSetRecord.id).where(
                            cast(Any, SampleSetRecord.sample_set_id).in_(set_ids)
                        )
                    )
                ).all()
                await session.exec(
                    delete(SampleSetMemberRecord).where(
                        cast(Any, SampleSetMemberRecord.sample_set_id).in_(set_pks)
                    )
                )
                await session.exec(
                    delete(SampleSetRecord).where(
                        cast(Any, SampleSetRecord.sample_set_id).in_(set_ids)
                    )
                )

            sample_set_rows = [
                SampleSetRecord(
                    sample_set_id=sample_set.sample_set_id,
                    project_id=project_pk,
                    name=sample_set.name,
                    kind=sample_set.kind,
                    description=sample_set.description,
                    definition_json=dict(sample_set.definition_json),
                    created_at=sample_set.created_at,
                    metadata_json=dict(sample_set.metadata_json),
                )
                for sample_set in sample_sets or []
            ]
            session.add_all(sample_set_rows)
            await session.flush()
            sample_set_pk_by_label = _id_map(sample_set_rows, "sample_set_id")

            sample_set_member_rows = [
                SampleSetMemberRecord(
                    sample_set_id=sample_set_pk_by_label[member.sample_set_id],
                    run_sample_id=run_sample_pk_by_label[member.run_sample_id],
                )
                for member in sample_set_members or []
            ]
            session.add_all(sample_set_member_rows)
            await session.flush()

            result = CatalogWriteResult(
                project=_snapshot_record(project_row),
                data_import=(
                    _snapshot_record(data_import_row)
                    if data_import_row is not None
                    else None
                ),
                runs=_snapshot_records(run_rows),
                subjects=_snapshot_records(subject_rows),
                samples=_snapshot_records(sample_rows),
                run_samples=_snapshot_records(run_sample_rows),
                data_profiles=_snapshot_records(profile_rows),
                data_profile_fields=_snapshot_records(profile_field_rows),
                files=_snapshot_records(file_rows),
                file_links=_snapshot_records(file_link_rows),
                sample_sets=_snapshot_records(sample_set_rows),
                sample_set_members=_snapshot_records(sample_set_member_rows),
            )
            await session.commit()
        return result

    async def get_run(self, run_id: str) -> Run | None:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
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
            assay=run_row.assay,
            pipeline_name=run_row.pipeline_name,
            pipeline_version=run_row.pipeline_version,
            parameters_json=run_row.parameters_json,
            started_at=run_row.started_at,
            ended_at=run_row.ended_at,
            status=run_row.status,
            metadata_json=run_row.metadata_json,
            created_at=run_row.created_at,
            samples=samples,
        )

    async def replace_run_file_catalog(
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
        profile_rows = await _records_by_field(
            session,
            DataProfileRecord,
            DataProfileRecord.data_profile_id,
            [link.data_profile_id for link in file_links if link.data_profile_id],
        )
        data_import_map = _id_map(data_import_rows.values(), "data_import_id")
        run_map = _id_map(run_rows.values(), "run_id")
        run_sample_map = _id_map(run_sample_rows.values(), "run_sample_id")
        sample_map = _id_map(sample_rows.values(), "sample_id")
        profile_map = _id_map(profile_rows.values(), "data_profile_id")
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
                    data_profile_id=_optional_map_lookup(
                        profile_map, link.data_profile_id
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


def catalog_id_maps_from_records(
    result: CatalogWriteResult,
) -> dict[str, dict[str, int]]:
    """Build DuckDB integer-id lookup maps from persisted catalog records."""

    return {
        "project_id": _id_map([result.project], "project_id"),
        "data_profile_id": _id_map(result.data_profiles, "data_profile_id"),
        "field_id": _id_map(result.data_profile_fields, "field_id"),
        "run_id": _id_map(result.runs, "run_id"),
        "run_sample_id": _id_map(result.run_samples, "run_sample_id"),
        "sample_id": _id_map(result.samples, "sample_id"),
        "source_file_id": _id_map(result.files, "file_id"),
        "sample_set_id": _id_map(result.sample_sets, "sample_set_id"),
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


async def _upsert_data_profiles(
    session: AsyncSession,
    profiles: list[DataProfile],
    project_id: int,
) -> list[DataProfileRecord]:
    existing = await _records_by_field(
        session,
        DataProfileRecord,
        DataProfileRecord.data_profile_id,
        [profile.data_profile_id for profile in profiles],
    )
    rows: list[DataProfileRecord] = []
    for profile in profiles:
        row = existing.get(profile.data_profile_id)
        profile_project_id = project_id if profile.project_id is not None else None
        if row is None:
            row = DataProfileRecord(
                data_profile_id=profile.data_profile_id,
                project_id=profile_project_id,
                name=profile.name,
                data_type=profile.data_type,
                assay=profile.assay,
                producer_tool=profile.producer_tool,
                producer_tool_version=profile.producer_tool_version,
                producer_pipeline=profile.producer_pipeline,
                genome_build=profile.genome_build,
                feature_type=profile.feature_type,
                value_type=profile.value_type,
                unit=profile.unit,
                entity_grain=profile.entity_grain,
                value_semantics=profile.value_semantics,
                primary_table=profile.primary_table,
                physical_tables_json=dict(profile.physical_tables_json),
                summary_json=dict(profile.summary_json),
                last_profiled_at=profile.last_profiled_at,
                source_fingerprint=profile.source_fingerprint,
                query_modes_json=dict(profile.query_modes_json),
                mcp_description=profile.mcp_description,
                metadata_json=dict(profile.metadata_json),
            )
        else:
            row.project_id = profile_project_id
            row.name = profile.name
            row.data_type = profile.data_type
            row.assay = profile.assay
            row.producer_tool = profile.producer_tool
            row.producer_tool_version = profile.producer_tool_version
            row.producer_pipeline = profile.producer_pipeline
            row.genome_build = profile.genome_build
            row.feature_type = profile.feature_type
            row.value_type = profile.value_type
            row.unit = profile.unit
            row.entity_grain = profile.entity_grain
            row.value_semantics = profile.value_semantics
            row.primary_table = profile.primary_table
            row.physical_tables_json = dict(profile.physical_tables_json)
            row.summary_json = dict(profile.summary_json)
            row.last_profiled_at = profile.last_profiled_at
            row.source_fingerprint = profile.source_fingerprint
            row.query_modes_json = dict(profile.query_modes_json)
            row.mcp_description = profile.mcp_description
            row.metadata_json = dict(profile.metadata_json)
        rows.append(row)
    session.add_all(rows)
    await session.flush()
    return rows


async def _upsert_data_profile_fields(
    session: AsyncSession,
    fields: list[DataProfileField],
    profile_pk_by_label: dict[str, int],
) -> list[DataProfileFieldRecord]:
    if not fields:
        return []
    profile_pks = sorted(
        {
            profile_pk_by_label[field.data_profile_id]
            for field in fields
            if field.data_profile_id in profile_pk_by_label
        }
    )
    if profile_pks:
        await session.exec(
            delete(DataProfileFieldRecord).where(
                cast(Any, DataProfileFieldRecord.data_profile_id).in_(profile_pks)
            )
        )
    rows = [
        DataProfileFieldRecord(
            data_profile_id=profile_pk_by_label[field.data_profile_id],
            field_id=field.field_id,
            field_role=field.field_role,
            entity_scope=field.entity_scope,
            display_name=field.display_name,
            value_type=field.value_type,
            unit=field.unit,
            direction=field.direction,
            description=field.description,
            priority=field.priority,
            query_ref_json=dict(field.query_ref_json),
            summary_json=dict(field.summary_json),
            metadata_json=dict(field.metadata_json),
        )
        for field in fields
        if field.data_profile_id in profile_pk_by_label
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


def _run_record(
    run: Run,
    project: Project,
    *,
    project_pk: int,
    data_import_pk: int | None,
) -> RunRecord:
    return RunRecord(
        run_id=run.run_id,
        project_id=project_pk,
        data_import_id=data_import_pk,
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


async def _delete_data_import_scoped_catalog(
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


async def _delete_run_scoped_catalog(
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
    profile_ids = (
        await session.exec(
            select(DataProfileRecord.id).where(
                DataProfileRecord.data_profile_id.startswith(f"{run_id}:")
            )
        )
    ).all()
    file_ids = (
        await session.exec(
            select(FileLinkRecord.file_id).where(FileLinkRecord.run_id == run_pk)
        )
    ).all()
    sample_set_ids: list[int] = []
    if run_sample_ids:
        sample_set_ids = list(
            (
                await session.exec(
                    select(SampleSetMemberRecord.sample_set_id).where(
                        cast(Any, SampleSetMemberRecord.run_sample_id).in_(
                            list(run_sample_ids)
                        )
                    )
                )
            ).all()
        )
    await session.exec(delete(FileLinkRecord).where(FileLinkRecord.run_id == run_pk))
    await session.exec(delete(RunSampleRecord).where(RunSampleRecord.run_id == run_pk))
    if profile_ids:
        await session.exec(
            delete(DataProfileFieldRecord).where(
                cast(Any, DataProfileFieldRecord.data_profile_id).in_(list(profile_ids))
            )
        )
        await session.exec(
            delete(FileLinkRecord).where(
                cast(Any, FileLinkRecord.data_profile_id).in_(list(profile_ids))
            )
        )
    await session.exec(
        delete(DataProfileRecord).where(
            DataProfileRecord.data_profile_id.startswith(f"{run_id}:")
        )
    )
    if file_ids:
        await session.exec(
            delete(FileRecord).where(cast(Any, FileRecord.id).in_(file_ids))
        )
    if sample_set_ids:
        await session.exec(
            delete(SampleSetMemberRecord).where(
                SampleSetMemberRecord.sample_set_id.in_(list(sample_set_ids))
            )
        )
        await session.exec(
            delete(SampleSetRecord).where(
                cast(Any, SampleSetRecord.id).in_(list(sample_set_ids))
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
