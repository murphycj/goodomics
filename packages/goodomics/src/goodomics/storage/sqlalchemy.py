# pyright: reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

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
    DataProfile,
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


# These SQLModel classes are persistence records, not the public Goodomics
# schemas. Keep database-only concerns here: table names, primary keys, indexes,
# foreign keys, JSON column storage, and nullable columns used by SQL backends.
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
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class SampleRecord(SQLModel, table=True):
    __tablename__ = "samples"

    sample_id: str = Field(primary_key=True, max_length=255)
    project_id: str | None = Field(default=None, max_length=255, index=True)
    subject_id: str | None = Field(default=None, max_length=255, index=True)
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

    # A file can be linked to a run, run sample, sample, or data profile without
    # duplicating the file asset row itself.
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


class QCDecisionRecord(SQLModel, table=True):
    __tablename__ = "qc_decisions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
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
            await _ensure_compatible_schema(connection)

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
            row = await session.get(ProjectRecord, project_id)
        return _project_from_row(row) if row is not None else None

    async def save_run(self, run: Run) -> None:
        # Lightweight compatibility path for callers that only provide a Run
        # with embedded samples. Rich ingest paths use replace_run_catalog().
        await self.ensure_schema()
        project = await self.ensure_project(run.project_id or run.project)
        async with AsyncSession(self._get_engine()) as session:
            await session.exec(
                delete(QCDecisionRecord).where(QCDecisionRecord.run_id == run.run_id)
            )
            await session.exec(
                delete(RunSampleRecord).where(RunSampleRecord.run_id == run.run_id)
            )

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
            await session.commit()

    async def replace_run_catalog(
        self,
        run: Run,
        *,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        data_profiles: list[DataProfile] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_sets: list[SampleSet] | None = None,
        sample_set_members: list[SampleSetMember] | None = None,
    ) -> Project:
        # Replace the SQL catalog rows for one run. Analytical metric
        # observations are intentionally not stored here; they live in DuckDB.
        await self.ensure_schema()
        project = await self.ensure_project(run.project_id or run.project)
        resolved_run = run.model_copy(
            update={
                "project_id": project.project_id,
                "project": run.project or project.slug or project.name,
            }
        )
        subject_records = list(subjects or [])
        sample_records = list(samples or resolved_run.samples)
        run_sample_records = list(run_samples or [])
        profile_records = list(data_profiles or [])
        file_records = list(files or [])
        link_records = list(file_links or [])
        set_records = list(sample_sets or [])
        member_records = list(sample_set_members or [])

        async with AsyncSession(self._get_engine()) as session:
            await _delete_run_scoped_catalog(session, resolved_run.run_id)

            existing = await session.get(RunRecord, resolved_run.run_id)
            if existing is not None:
                await session.delete(existing)

            session.add(_run_record(resolved_run, project))
            for subject in subject_records:
                row = await session.get(SubjectRecord, subject.subject_id)
                if row is None:
                    row = SubjectRecord(
                        subject_id=subject.subject_id,
                        project_id=subject.project_id or project.project_id,
                        metadata_json=dict(subject.metadata_json),
                    )
                else:
                    row.project_id = subject.project_id or row.project_id
                    row.metadata_json = dict(subject.metadata_json)
                session.add(row)

            for sample in sample_records:
                row = await session.get(SampleRecord, sample.sample_id)
                if row is None:
                    row = SampleRecord(
                        sample_id=sample.sample_id,
                        project_id=sample.project_id or project.project_id,
                        subject_id=sample.subject_id,
                        sample_name=sample.sample_name,
                        metadata_json=dict(sample.metadata_json),
                    )
                else:
                    row.project_id = sample.project_id or row.project_id
                    row.subject_id = sample.subject_id
                    row.sample_name = sample.sample_name
                    row.metadata_json = dict(sample.metadata_json)
                session.add(row)

            session.add_all(
                [
                    RunSampleRecord(
                        run_sample_id=run_sample.run_sample_id,
                        project_id=run_sample.project_id or project.project_id,
                        run_id=resolved_run.run_id,
                        sample_id=run_sample.sample_id,
                        assay=run_sample.assay,
                        role=run_sample.role,
                        status=run_sample.status,
                        metadata_json=dict(run_sample.metadata_json),
                    )
                    for run_sample in run_sample_records
                ]
            )
            for profile in profile_records:
                await _upsert_data_profile(session, profile)
            session.add_all(
                [
                    FileRecord(
                        file_id=file.file_id,
                        project_id=file.project_id or project.project_id,
                        path=file.path,
                        uri=file.uri,
                        file_role=file.file_role,
                        format=file.format,
                        size_bytes=file.size_bytes,
                        sha256=file.sha256,
                        created_at=file.created_at,
                        metadata_json=dict(file.metadata_json),
                    )
                    for file in file_records
                ]
            )
            session.add_all(
                [
                    FileLinkRecord(
                        file_id=link.file_id,
                        project_id=link.project_id or project.project_id,
                        run_id=link.run_id or resolved_run.run_id,
                        run_sample_id=link.run_sample_id,
                        sample_id=link.sample_id,
                        data_profile_id=link.data_profile_id,
                        link_role=link.link_role,
                    )
                    for link in link_records
                ]
            )
            session.add_all(
                [
                    SampleSetRecord(
                        sample_set_id=sample_set.sample_set_id,
                        project_id=sample_set.project_id or project.project_id,
                        name=sample_set.name,
                        kind=sample_set.kind,
                        description=sample_set.description,
                        definition_json=dict(sample_set.definition_json),
                        created_at=sample_set.created_at,
                        metadata_json=dict(sample_set.metadata_json),
                    )
                    for sample_set in set_records
                ]
            )
            session.add_all(
                [
                    SampleSetMemberRecord(
                        sample_set_id=member.sample_set_id,
                        run_sample_id=member.run_sample_id,
                    )
                    for member in member_records
                ]
            )
            await session.commit()
        return project

    async def replace_runs_catalog(
        self,
        runs: list[Run],
        *,
        subjects: list[Subject] | None = None,
        samples: list[Sample] | None = None,
        run_samples: list[RunSample] | None = None,
        data_profiles: list[DataProfile] | None = None,
        files: list[FileAsset] | None = None,
        file_links: list[FileLink] | None = None,
        sample_sets: list[SampleSet] | None = None,
        sample_set_members: list[SampleSetMember] | None = None,
    ) -> Project:
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
            for run_id in sorted(run_ids):
                await _delete_run_scoped_catalog(session, run_id)
                existing = await session.get(RunRecord, run_id)
                if existing is not None:
                    await session.delete(existing)

            for run in resolved_runs:
                session.add(_run_record(run, project))

            for subject in subjects or []:
                await _upsert_subject(session, subject, project.project_id)

            for sample in samples or []:
                await _upsert_sample(session, sample, project.project_id)

            session.add_all(
                [
                    RunSampleRecord(
                        run_sample_id=run_sample.run_sample_id,
                        project_id=run_sample.project_id or project.project_id,
                        run_id=run_sample.run_id,
                        sample_id=run_sample.sample_id,
                        assay=run_sample.assay,
                        role=run_sample.role,
                        status=run_sample.status,
                        metadata_json=dict(run_sample.metadata_json),
                    )
                    for run_sample in run_samples or []
                ]
            )
            for profile in data_profiles or []:
                await _upsert_data_profile(session, profile)

            for file in files or []:
                await _upsert_file(session, file, project.project_id)

            session.add_all(
                [
                    FileLinkRecord(
                        file_id=link.file_id,
                        project_id=link.project_id or project.project_id,
                        run_id=link.run_id,
                        run_sample_id=link.run_sample_id,
                        sample_id=link.sample_id,
                        data_profile_id=link.data_profile_id,
                        link_role=link.link_role,
                    )
                    for link in file_links or []
                ]
            )

            set_ids = [sample_set.sample_set_id for sample_set in sample_sets or []]
            if set_ids:
                await session.exec(
                    delete(SampleSetMemberRecord).where(
                        cast(Any, SampleSetMemberRecord.sample_set_id).in_(set_ids)
                    )
                )
                await session.exec(
                    delete(SampleSetRecord).where(
                        cast(Any, SampleSetRecord.sample_set_id).in_(set_ids)
                    )
                )

            session.add_all(
                [
                    SampleSetRecord(
                        sample_set_id=sample_set.sample_set_id,
                        project_id=sample_set.project_id or project.project_id,
                        name=sample_set.name,
                        kind=sample_set.kind,
                        description=sample_set.description,
                        definition_json=dict(sample_set.definition_json),
                        created_at=sample_set.created_at,
                        metadata_json=dict(sample_set.metadata_json),
                    )
                    for sample_set in sample_sets or []
                ]
            )
            session.add_all(
                [
                    SampleSetMemberRecord(
                        sample_set_id=member.sample_set_id,
                        run_sample_id=member.run_sample_id,
                    )
                    for member in sample_set_members or []
                ]
            )
            await session.commit()
        return project

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
        file_ids = (
            await session.exec(
                select(FileLinkRecord.file_id).where(FileLinkRecord.run_id == run_id)
            )
        ).all()
        await session.exec(
            delete(FileLinkRecord).where(FileLinkRecord.run_id == run_id)
        )
        if file_ids:
            await session.exec(
                delete(FileRecord).where(cast(Any, FileRecord.file_id).in_(file_ids))
            )
        for file in files:
            await _upsert_file(session, file, project_id)
        session.add_all(
            [
                FileLinkRecord(
                    file_id=link.file_id,
                    project_id=link.project_id or project_id,
                    run_id=link.run_id or run_id,
                    run_sample_id=link.run_sample_id,
                    sample_id=link.sample_id,
                    data_profile_id=link.data_profile_id,
                    link_role=link.link_role,
                )
                for link in file_links
            ]
        )
        await session.commit()


async def _upsert_subject(
    session: AsyncSession,
    subject: Subject,
    project_id: str,
) -> None:
    # Subjects and samples are project-level entities, so run replacement should
    # update them in place rather than deleting shared rows owned by other runs.
    row = await session.get(SubjectRecord, subject.subject_id)
    if row is None:
        row = SubjectRecord(
            subject_id=subject.subject_id,
            project_id=subject.project_id or project_id,
            metadata_json=dict(subject.metadata_json),
        )
    else:
        row.project_id = subject.project_id or row.project_id
        row.metadata_json = dict(subject.metadata_json)
    session.add(row)


async def _upsert_sample(
    session: AsyncSession,
    sample: Sample,
    project_id: str,
) -> None:
    row = await session.get(SampleRecord, sample.sample_id)
    if row is None:
        row = SampleRecord(
            sample_id=sample.sample_id,
            project_id=sample.project_id or project_id,
            subject_id=sample.subject_id,
            sample_name=sample.sample_name,
            metadata_json=dict(sample.metadata_json),
        )
    else:
        row.project_id = sample.project_id or row.project_id
        row.subject_id = sample.subject_id
        row.sample_name = sample.sample_name
        row.metadata_json = dict(sample.metadata_json)
    session.add(row)


async def _upsert_file(
    session: AsyncSession,
    file: FileAsset,
    project_id: str,
) -> None:
    # File assets are content/location records; links carry the run/sample/profile
    # relationship. Updating the asset keeps checksum and path metadata current.
    row = await session.get(FileRecord, file.file_id)
    if row is None:
        row = FileRecord(
            file_id=file.file_id,
            project_id=file.project_id or project_id,
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
        row.project_id = file.project_id or row.project_id
        row.path = file.path
        row.uri = file.uri
        row.file_role = file.file_role
        row.format = file.format
        row.size_bytes = file.size_bytes
        row.sha256 = file.sha256
        row.created_at = file.created_at
        row.metadata_json = dict(file.metadata_json)
    session.add(row)


async def _upsert_data_profile(
    session: AsyncSession,
    profile: DataProfile,
) -> None:
    # Data profiles are semantic contracts and may be reused across many runs.
    row = await session.get(DataProfileRecord, profile.data_profile_id)
    if row is None:
        row = DataProfileRecord(
            data_profile_id=profile.data_profile_id,
            project_id=profile.project_id,
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
            query_modes_json=dict(profile.query_modes_json),
            mcp_description=profile.mcp_description,
            metadata_json=dict(profile.metadata_json),
        )
    else:
        row.project_id = profile.project_id
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
        row.query_modes_json = dict(profile.query_modes_json)
        row.mcp_description = profile.mcp_description
        row.metadata_json = dict(profile.metadata_json)
    session.add(row)


def _sample_from_row(row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(
        sample_id=row.sample_id,
        project_id=row.project_id,
        subject_id=row.subject_id,
        sample_name=row.sample_name,
        metadata_json=metadata_dict,
    )


def _run_record(run: Run, project: Project) -> RunRecord:
    return RunRecord(
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


async def _delete_run_scoped_catalog(
    session: AsyncSession,
    run_id: str,
) -> None:
    # Delete rows owned by this run before replacement, while leaving shared
    # project-level subjects/samples intact.
    profile_ids = (
        await session.exec(
            select(DataProfileRecord.data_profile_id).where(
                DataProfileRecord.data_profile_id.startswith(f"{run_id}:")
            )
        )
    ).all()
    file_ids = (
        await session.exec(
            select(FileLinkRecord.file_id).where(FileLinkRecord.run_id == run_id)
        )
    ).all()
    sample_set_ids = (
        await session.exec(
            select(SampleSetRecord.sample_set_id).where(
                SampleSetRecord.sample_set_id.in_(
                    select(SampleSetMemberRecord.sample_set_id).where(
                        SampleSetMemberRecord.run_sample_id.startswith(f"{run_id}:")
                    )
                )
            )
        )
    ).all()
    await session.exec(delete(FileLinkRecord).where(FileLinkRecord.run_id == run_id))
    await session.exec(delete(RunSampleRecord).where(RunSampleRecord.run_id == run_id))
    await session.exec(
        delete(DataProfileRecord).where(
            DataProfileRecord.data_profile_id.startswith(f"{run_id}:")
        )
    )
    if profile_ids:
        await session.exec(
            delete(FileLinkRecord).where(
                cast(Any, FileLinkRecord.data_profile_id).in_(list(profile_ids))
            )
        )
    if file_ids:
        await session.exec(delete(FileRecord).where(FileRecord.file_id.in_(file_ids)))
    if sample_set_ids:
        await session.exec(
            delete(SampleSetMemberRecord).where(
                SampleSetMemberRecord.sample_set_id.in_(list(sample_set_ids))
            )
        )
        await session.exec(
            delete(SampleSetRecord).where(
                SampleSetRecord.sample_set_id.in_(list(sample_set_ids))
            )
        )


async def _resolve_project_row(
    session: AsyncSession, reference: str | None
) -> ProjectRecord | None:
    # Prefer primary-key lookup, then fall back to slug lookup for user-facing
    # project references passed through CLI, API, and SDK entry points.
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


async def _ensure_compatible_schema(connection: Any) -> None:
    # There are no shipped migrations yet, but this keeps local scratch
    # databases usable across recent development changes.
    dialect_name = connection.dialect.name
    if dialect_name != "sqlite":
        return
    result = await connection.exec_driver_sql("PRAGMA table_info(projects)")
    columns = {str(row[1]) for row in result.fetchall()}
    if "slug" not in columns:
        await connection.exec_driver_sql(
            "ALTER TABLE projects ADD COLUMN slug VARCHAR(255)"
        )
        await connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_projects_slug ON projects (slug)"
        )
