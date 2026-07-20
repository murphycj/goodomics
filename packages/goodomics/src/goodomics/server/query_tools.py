"""Read-only query tool surface bridging SQL metadata and DuckDB analytics."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import quote

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.projects import DEFAULT_PROJECT_ID, analytics_path_for_project
from goodomics.server.auth import (
    Principal,
    authorized_project_pks,
    current_principal,
)
from goodomics.server.settings import Settings
from goodomics.storage.duckdb import AnalyticsStoreRegistry, DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    AnalysisMethodRecord,
    AnalysisTypeRecord,
    DataContractFieldRecord,
    DataContractRecord,
    DataImportRecord,
    FileLinkRecord,
    FileRecord,
    ProjectRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
    SQLModelGoodomicsStore,
    SubjectRecord,
    get_record_by_field,
)

# This module is the "friendly read API" for agents and query tools. It bridges
# the SQL metadata store, which tracks projects/runs/samples/files/contracts, and the
# DuckDB analytics store, which holds metric values and other analytical facts.
# The public methods intentionally return compact dictionaries with dashboard
# links and stable public IDs rather than raw SQLModel or DuckDB records.
JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
ToolResultT = TypeVar("ToolResultT")
_tool_session: ContextVar[AsyncSession | None] = ContextVar(
    "goodomics_query_tool_session", default=None
)


def _tool_invocation(
    method: Callable[..., Awaitable[ToolResultT]],
) -> Callable[..., Awaitable[ToolResultT]]:
    """Run one public query-tool call within one short-lived SQL session."""

    @wraps(method)
    async def wrapped(
        self: GoodomicsQueryTools, *args: Any, **kwargs: Any
    ) -> ToolResultT:
        """Reuse one SQL session across nested helpers for this invocation."""

        if _tool_session.get() is not None:
            return await method(self, *args, **kwargs)
        async with self.context.store.session() as session:
            token = _tool_session.set(session)
            try:
                return await method(self, *args, **kwargs)
            finally:
                _tool_session.reset(token)

    return wrapped


@dataclass(frozen=True)
class QueryToolContext:
    """Dependencies required by query-tool handlers."""

    settings: Settings
    """Server settings used to locate project analytics databases."""

    store: SQLModelGoodomicsStore
    """SQL metadata store used for short-lived query sessions."""

    analytics_stores: AnalyticsStoreRegistry = field(
        default_factory=AnalyticsStoreRegistry
    )
    """Shared registry of lazily initialized project analytics stores."""


class GoodomicsQueryTools:
    """Public query helpers used by AI and MCP tooling."""

    context: QueryToolContext
    """Immutable dependencies shared across query-tool operations."""

    # Read-only helper surface for AI/MCP-style calls. Methods return plain
    # dictionaries so tool responses stay compact and JSON-native.
    def __init__(self, context: QueryToolContext) -> None:
        self.context = context

    @_tool_invocation
    async def list_projects(
        self, query: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        """List projects with optional text filtering over IDs, slugs, and names."""

        # Start from the metadata project list, then apply lightweight in-memory
        # filtering. Counts and dashboard links are added by _project_summary().
        projects = await self._all_projects()
        term = _normalize(query or "")
        if term:
            projects = [
                project
                for project in projects
                if term in _normalize(project.name)
                or term in _normalize(project.slug or "")
                or term in _normalize(project.project_id)
            ]
        projects = projects[: _bounded_limit(limit)]
        return {
            "projects": [await self._project_summary(project) for project in projects]
        }

    @_tool_invocation
    async def list_data_contracts(
        self,
        project: str | None = None,
        query: str | None = None,
        limit: int = 20,
        field_limit: int = 25,
    ) -> dict[str, Any]:
        """List visible data contracts and a bounded set of field definitions."""

        # Project arguments may be IDs, slugs, or names. Resolve first so the
        # SQL query can filter by the integer project primary key.
        project_id, project_resolution = await self._optional_project_id(project)
        if project is not None and project_id is None:
            return project_resolution or {"contracts": []}

        term = _normalize(query or "")
        async with self._session() as session:
            project_pk: int | None = None
            if project_id is not None:
                project_row = await get_record_by_field(
                    session, ProjectRecord, ProjectRecord.project_id, project_id
                )
                if project_row is None:
                    return {"contracts": []}
                project_pk = project_row.id
            statement = select(DataContractRecord)
            if project_pk is not None:
                if project_id == DEFAULT_PROJECT_ID:
                    contract_project_id = cast(Any, DataContractRecord.project_id)
                    statement = statement.where(
                        or_(
                            contract_project_id == project_pk,
                            contract_project_id.is_(None),
                        )
                    )
                else:
                    statement = statement.where(
                        DataContractRecord.project_id == project_pk
                    )
            statement = statement.order_by(DataContractRecord.name).limit(
                _bounded_limit(limit)
            )
            contracts = list((await session.exec(statement)).all())
            if project_pk is not None:
                contracts = _prefer_project_contract_rows(contracts, project_pk)
            if term:
                # The SQL query has already handled project visibility. This
                # second pass keeps text search simple across a few contract
                # descriptors without exposing raw SQL search syntax.
                contracts = [
                    contract
                    for contract in contracts
                    if term in _normalize(contract.name)
                    or term in _normalize(contract.data_contract_id)
                    or term in _normalize(contract.data_type)
                ]
            contract_ids = [
                contract.id for contract in contracts if contract.id is not None
            ]
            fields_by_contract: dict[int | None, list[DataContractFieldRecord]] = {}
            if contract_ids:
                # Fetch fields in one query rather than one query per contract.
                # Responses are capped per contract so wide schemas do not swamp
                # an agent/tool response.
                rows = (
                    await session.exec(
                        select(DataContractFieldRecord)
                        .where(
                            cast(Any, DataContractFieldRecord.data_contract_id).in_(
                                contract_ids
                            )
                        )
                        .order_by(
                            DataContractFieldRecord.field_role,
                            DataContractFieldRecord.field_id,
                        )
                    )
                ).all()
                bounded_fields = _bounded_limit(field_limit, maximum=100)
                for row in rows:
                    bucket = fields_by_contract.setdefault(row.data_contract_id, [])
                    if len(bucket) < bounded_fields:
                        bucket.append(row)
            return {
                "contracts": [
                    _data_result_payload(
                        contract, fields_by_contract.get(contract.id, [])
                    )
                    for contract in contracts
                ]
            }

    @_tool_invocation
    async def resolve_project(self, reference: str, limit: int = 5) -> dict[str, Any]:
        """Resolve a project reference into a match, ambiguity payload, or not-found."""

        # Resolution returns status/candidates instead of raising. That lets
        # callers surface ambiguity to users or agents in a structured way.
        reference = reference.strip()
        if not reference:
            return {"status": "not_found", "project": None, "candidates": []}

        projects = await self._all_projects()
        # Exact stable IDs win first because project_id is the canonical public
        # identifier used by API routes and generated dashboard links.
        for project in projects:
            if reference == project.project_id:
                return {
                    "status": "matched",
                    "match_type": "project_id",
                    "project": await self._project_summary(project),
                    "candidates": [],
                }
        # Slugs are user-facing aliases, so they are tried after project_id but
        # before name and fuzzy matching.
        for project in projects:
            if reference == (project.slug or ""):
                return {
                    "status": "matched",
                    "match_type": "slug",
                    "project": await self._project_summary(project),
                    "candidates": [],
                }

        # Normalize names before exact comparison so punctuation/case differences
        # in a human-entered project name do not block a clear match.
        normalized_reference = _normalize(reference)
        normalized_name_matches = [
            project
            for project in projects
            if _normalize(project.name) == normalized_reference
        ]
        if len(normalized_name_matches) == 1:
            return {
                "status": "matched",
                "match_type": "name",
                "project": await self._project_summary(normalized_name_matches[0]),
                "candidates": [],
            }
        if len(normalized_name_matches) > 1:
            return {
                "status": "ambiguous",
                "project": None,
                "candidates": [
                    await self._project_candidate(project, normalized_reference)
                    for project in normalized_name_matches[: _bounded_limit(limit)]
                ],
            }

        # Fuzzy scoring is only used after exact ID, slug, and name matching
        # fail. This avoids choosing a "near" name when the user supplied a
        # precise but less human-readable identifier.
        candidates = sorted(
            (
                (
                    max(
                        _score(reference, project.name),
                        _score(reference, project.slug or ""),
                    ),
                    project,
                )
                for project in projects
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        # Fuzzy matching is intentionally conservative: a confident winner is
        # auto-selected only when it is both high scoring and clearly separated
        # from the next candidate.
        candidates = [item for item in candidates if item[0] >= 0.35][
            : _bounded_limit(limit)
        ]
        if not candidates:
            return {"status": "not_found", "project": None, "candidates": []}

        top_score, top_project = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        candidate_payloads = [
            await self._project_candidate(project, reference, score=score)
            for score, project in candidates
        ]
        if top_score >= 0.86 and top_score - second_score >= 0.12:
            return {
                "status": "matched",
                "match_type": "fuzzy",
                "project": await self._project_summary(top_project),
                "candidates": candidate_payloads,
            }
        return {
            "status": "ambiguous",
            "project": None,
            "candidates": candidate_payloads,
        }

    @_tool_invocation
    async def get_project_summary(self, project: str) -> dict[str, Any]:
        """Return a compact project overview with recent runs and sample examples."""

        # Compose a quick orientation payload: project counts plus a small set of
        # recent runs and sample examples. This is meant for "where am I?" agent
        # answers, not exhaustive browsing.
        resolution = await self.resolve_project(project)
        project_id = _matched_project_id(resolution)
        if project_id is None:
            return {"project_resolution": resolution}
        row = await self._get_project(project_id)
        if row is None:
            return {"project_resolution": resolution}
        summary = await self._project_summary(row)
        recent_runs = await self.list_recent_runs(project=row.project_id, limit=5)
        samples = await self.list_project_samples(row.project_id, limit=5)
        return {
            "project": summary,
            "recent_runs": recent_runs["runs"],
            "sample_examples": samples["samples"],
        }

    @_tool_invocation
    async def list_recent_runs(
        self, project: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """List recent runs globally or within one resolved project."""

        # Without a project argument this intentionally spans all projects. With
        # a project argument, failed resolution is returned alongside an empty
        # result so the caller can explain the issue.
        project_id, resolution = await self._optional_project_id(project)
        if resolution is not None and project_id is None:
            return {"project_resolution": resolution, "runs": []}
        return {
            "runs": await self._run_rows(
                project_id=project_id,
                limit=limit,
                order_recent=True,
            )
        }

    @_tool_invocation
    async def list_project_runs(
        self,
        project: str,
        status: str | None = None,
        analysis_type_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List runs for a project with optional analysis-type/status filters."""

        # Project-scoped run listing is stricter than list_recent_runs(): a
        # project reference is required and must resolve cleanly.
        project_id, resolution = await self._required_project_id(project)
        if project_id is None:
            return {"project_resolution": resolution, "runs": []}
        return {
            "project_resolution": resolution,
            "runs": await self._run_rows(
                project_id=project_id,
                status=status,
                analysis_type_id=analysis_type_id,
                limit=limit,
                order_recent=True,
            ),
        }

    @_tool_invocation
    async def list_project_samples(
        self,
        project: str,
        query: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List project samples with optional substring search."""

        # Samples live in the SQL metadata store. Analytical rows in DuckDB reference
        # them by integer ID, but tool callers work with stable sample_id labels.
        project_id, resolution = await self._required_project_id(project)
        if project_id is None:
            return {"project_resolution": resolution, "samples": []}
        project_row = await self._get_project(project_id)
        project_pk = project_row.id if project_row is not None else None
        statement = select(SampleRecord).where(SampleRecord.project_id == project_pk)
        term = (query or "").strip().lower()
        if term:
            # Sample browsing supports simple substring search over the stable
            # sample ID and optional display name.
            pattern = f"%{term}%"
            statement = statement.where(
                (func.lower(SampleRecord.sample_id).like(pattern))
                | (func.lower(SampleRecord.sample_name).like(pattern))
            )
        statement = statement.order_by(cast(Any, SampleRecord.sample_id)).limit(
            _bounded_limit(limit)
        )
        async with self._session() as session:
            rows = (await session.exec(statement)).all()
            samples = [await _sample_payload_public(session, row) for row in rows]
        return {
            "project_resolution": resolution,
            "samples": samples,
        }

    @_tool_invocation
    async def get_run(self, run_id: str, project: str | None = None) -> dict[str, Any]:
        """Fetch one run payload and optionally enforce project ownership."""

        # The store-level get_run returns the public Run schema, including
        # embedded samples. If a project is supplied, verify that the run belongs
        # to it before returning data.
        run = await self.context.store.get_run(run_id)
        if run is None:
            return {"status": "not_found", "run": None}
        if (
            run.project_id is not None
            and await self._get_project(run.project_id) is None
        ):
            return {"status": "not_found", "run": None}
        if project:
            project_id, resolution = await self._required_project_id(project)
            if project_id is None:
                return {"project_resolution": resolution, "run": None}
            if run.project_id != project_id:
                return {
                    "status": "not_found",
                    "project_resolution": resolution,
                    "run": None,
                }
        return {
            "status": "matched",
            "run": _run_payload(run),
        }

    @_tool_invocation
    async def list_run_samples(
        self, run_id: str, project: str | None = None
    ) -> dict[str, Any]:
        """List samples embedded in a run after optional project validation."""

        # Reuse get_run() for existence and optional project validation, then
        # fetch the full run model so we can expose its embedded sample list.
        run_result = await self.get_run(run_id, project=project)
        run = run_result.get("run")
        if not isinstance(run, dict):
            return run_result | {"samples": []}
        full_run = await self.context.store.get_run(run_id)
        return {
            "run": run,
            "samples": [
                _sample_model_payload(sample)
                for sample in (full_run.samples if full_run else [])
            ],
        }

    @_tool_invocation
    async def list_run_metrics(
        self,
        run_id: str,
        project: str | None = None,
        metric_query: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """List run metrics from DuckDB, optionally filtered by metric text."""

        # Metrics are stored in DuckDB, but run lookup starts in SQL so we can
        # convert the public run_id label to the internal integer run primary key.
        run_result = await self.get_run(run_id, project=project)
        run = run_result.get("run")
        if not isinstance(run, dict):
            return run_result | {"metrics": []}

        term = (metric_query or "").strip().lower()
        metrics: list[dict[str, Any]] = []
        try:
            async with self._session() as session:
                run_row = await get_record_by_field(
                    session, RunRecord, RunRecord.run_id, run_id
                )
            if run_row is None:
                return run_result | {"metrics": []}
            values = self._analytics_store(run.get("project_id")).list_metric_values(
                run_row.id
            )
            metrics = [_analytics_metric_payload(value) for value in values]
            if term:
                metrics = [
                    metric
                    for metric in metrics
                    if term in str(metric.get("field_id", "")).lower()
                    or term in str(metric.get("value", "")).lower()
                ]
        except Exception:
            # Tool calls should remain useful if the analytics store is missing
            # or stale. Metadata-backed run details can still be returned.
            metrics = []

        bounded = _bounded_limit(limit)
        return {
            "run": run,
            "metrics": metrics[:bounded],
        }

    @_tool_invocation
    async def list_run_files(
        self,
        run_id: str,
        project: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List run-linked and import-linked files with optional kind filtering."""

        # Files are metadata records with link rows that describe whether a file
        # belongs to a run, sample, import, or data contract.
        run_result = await self.get_run(run_id, project=project)
        run = run_result.get("run")
        if not isinstance(run, dict):
            return run_result | {"files": []}
        async with self._session() as session:
            run_row = await get_record_by_field(
                session, RunRecord, RunRecord.run_id, run_id
            )
        if run_row is None:
            return run_result | {"files": []}
        direct_statement = (
            select(FileRecord, FileLinkRecord)
            .join(
                FileLinkRecord,
                cast(Any, FileLinkRecord.file_id) == FileRecord.id,
            )
            .where(FileLinkRecord.run_id == run_row.id)
        )
        if kind:
            # kind maps to FileRecord.file_role, e.g. "multiqc_report" or
            # source-specific roles assigned by an ingest path.
            direct_statement = direct_statement.where(
                func.lower(FileRecord.file_role) == kind.lower()
            )
        direct_statement = direct_statement.order_by(cast(Any, FileRecord.file_id))
        data_import_id = run.get("data_import_id")
        async with self._session() as session:
            rows: list[dict[str, Any]] = []
            # Return direct run files first, then import-level source files that
            # explain where imported-result runs came from.
            for file, link in (await session.exec(direct_statement)).all():
                rows.append(
                    await _file_payload_public(
                        session,
                        file,
                        link,
                        association_scope="direct_run",
                        association_reason="File directly linked to this run.",
                    )
                )
            if isinstance(data_import_id, str):
                # Imported-result runs often inherit evidence from the import
                # event rather than owning every source file directly.
                data_import_row = await get_record_by_field(
                    session,
                    DataImportRecord,
                    DataImportRecord.data_import_id,
                    data_import_id,
                )
                data_import_pk = (
                    data_import_row.id if data_import_row is not None else None
                )
                import_statement = (
                    select(FileRecord, FileLinkRecord)
                    .join(
                        FileLinkRecord,
                        cast(Any, FileLinkRecord.file_id) == FileRecord.id,
                    )
                    .where(
                        FileLinkRecord.data_import_id == data_import_pk,
                        cast(Any, FileLinkRecord.run_id).is_(None),
                    )
                )
                if kind:
                    import_statement = import_statement.where(
                        func.lower(FileRecord.file_role) == kind.lower()
                    )
                import_statement = import_statement.order_by(
                    cast(Any, FileRecord.file_id)
                )
                for file, link in (await session.exec(import_statement)).all():
                    rows.append(
                        await _file_payload_public(
                            session,
                            file,
                            link,
                            association_scope="data_import",
                            association_reason=(
                                "Source file from the data import that produced "
                                "this run."
                            ),
                        )
                    )
        return {
            "run": run,
            "files": _dedupe_file_payloads(rows)[: _bounded_limit(limit)],
        }

    async def _all_projects(self) -> list[ProjectRecord]:
        # The default project is created lazily, so a project list call is safe
        # even against a fresh local database.
        await self.context.store.ensure_default_project()
        async with self._session() as session:
            statement = select(ProjectRecord).order_by(
                cast(Any, ProjectRecord.created_at),
                ProjectRecord.name,
            )
            visible = await self._visible_project_pks(session)
            if visible is not None:
                statement = statement.where(cast(Any, ProjectRecord.id).in_(visible))
            return list((await session.exec(statement)).all())

    async def _get_project(self, project_id: str) -> ProjectRecord | None:
        # Public methods pass stable project_id labels. Most SQL filters need
        # the integer primary key stored on the ProjectRecord.
        async with self._session() as session:
            row = await get_record_by_field(
                session, ProjectRecord, ProjectRecord.project_id, project_id
            )
            if row is None:
                return None
            visible = await self._visible_project_pks(session)
            if visible is not None and row.id not in visible:
                return None
            return row

    async def _visible_project_pks(self, session: AsyncSession) -> set[int] | None:
        if not self.context.settings.auth.enabled:
            return None
        principal = current_principal.get() or Principal(kind="anonymous")
        return await authorized_project_pks(session, principal, self.context.settings)

    async def _project_summary(self, project: ProjectRecord) -> dict[str, Any]:
        # Project summaries calculate small aggregate counts on demand. That
        # avoids keeping denormalized counters in sync during ingest/edit flows.
        async with self._session() as session:
            run_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(RunRecord)
                        .where(RunRecord.project_id == project.id)
                    )
                ).one()
            )
            sample_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(SampleRecord)
                        .where(SampleRecord.project_id == project.id)
                    )
                ).one()
            )
            latest_activity_at = (
                await session.exec(
                    select(func.max(RunRecord.created_at)).where(
                        RunRecord.project_id == project.id
                    )
                )
            ).one()
            file_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(FileRecord)
                        .join(
                            FileLinkRecord,
                            cast(Any, FileLinkRecord.file_id) == FileRecord.id,
                        )
                        .where(FileLinkRecord.project_id == project.id)
                    )
                ).one()
            )
        return {
            "project_id": project.project_id,
            "slug": project.slug,
            "name": project.name,
            "description": project.description,
            "app_path": _project_path(project.project_id),
            "markdown_link": f"[{project.name}]({_project_path(project.project_id)})",
            "created_at": project.created_at.isoformat(),
            "run_count": run_count,
            "sample_count": sample_count,
            "file_count": file_count,
            "latest_activity_at": (
                latest_activity_at.isoformat()
                if latest_activity_at is not None
                else None
            ),
        }

    async def _project_candidate(
        self, project: ProjectRecord, reference: str, *, score: float | None = None
    ) -> dict[str, Any]:
        # Ambiguous project matches still include full summaries so the caller
        # has enough context to choose the intended project.
        payload = await self._project_summary(project)
        candidate_score = score
        if candidate_score is None:
            candidate_score = max(
                _score(reference, project.name),
                _score(reference, project.slug or ""),
            )
        payload["score"] = round(
            candidate_score,
            3,
        )
        return payload

    async def _run_rows(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        analysis_type_id: str | None = None,
        limit: int = 20,
        order_recent: bool = False,
    ) -> list[dict[str, Any]]:
        # Shared run-list builder used by both global and project-scoped tools.
        # It accepts public project IDs but filters RunRecord.project_id by SQL
        # primary key.
        statement = select(RunRecord)
        if project_id is not None:
            project_row = await self._get_project(project_id)
            project_pk = project_row.id if project_row is not None else None
            statement = statement.where(RunRecord.project_id == project_pk)
        if status:
            statement = statement.where(func.lower(RunRecord.status) == status.lower())
        if analysis_type_id:
            statement = statement.join(
                AnalysisTypeRecord,
                cast(Any, AnalysisTypeRecord.id) == RunRecord.analysis_type_id,
            ).where(
                func.lower(AnalysisTypeRecord.analysis_type_id)
                == analysis_type_id.lower()
            )
        if order_recent:
            statement = statement.order_by(
                cast(Any, RunRecord.created_at).desc(),
                RunRecord.run_id,
            )
        else:
            statement = statement.order_by(RunRecord.run_id)
        statement = statement.limit(_bounded_limit(limit))
        async with self._session() as session:
            if project_id is None:
                visible = await self._visible_project_pks(session)
                if visible is not None:
                    statement = statement.where(
                        cast(Any, RunRecord.project_id).in_(visible)
                    )
            rows = (await session.exec(statement)).all()
            return [await _run_record_payload_public(session, row) for row in rows]

    async def _optional_project_id(
        self, project: str | None
    ) -> tuple[str | None, dict[str, Any] | None]:
        # Optional project filters should not force the default project. Returning
        # (None, None) means "query globally".
        if not project:
            return None, None
        return await self._required_project_id(project)

    async def _required_project_id(
        self, project: str
    ) -> tuple[str | None, dict[str, Any]]:
        # Required project references preserve the full resolution payload so
        # public methods can report ambiguous/not-found lookups.
        resolution = await self.resolve_project(project)
        return _matched_project_id(resolution), resolution

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """Yield the invocation session, owning one only for internal direct calls."""

        session = _tool_session.get()
        if session is not None:
            yield session
            return
        async with self.context.store.session() as owned_session:
            yield owned_session

    def _analytics_store(self, project_id: str | None) -> DuckDBAnalyticsStore:
        settings = self.context.settings
        if settings.analytics_path:
            return self.context.analytics_stores.get(settings.analytics_path)
        # In project mode each workspace has an isolated DuckDB file; callers
        # without a project fall back to the default project analytics store.
        return self.context.analytics_stores.get(
            analytics_path_for_project(
                settings.analytics_root, project_id or DEFAULT_PROJECT_ID
            )
        )


def _matched_project_id(resolution: dict[str, Any]) -> str | None:
    # Extract the stable project_id only from successful resolution payloads.
    project = resolution.get("project")
    if isinstance(project, dict):
        project_id = project.get("project_id")
        return str(project_id) if project_id else None
    return None


def _normalize(value: str) -> str:
    # Normalize user-facing identifiers for forgiving matching. This deliberately
    # removes punctuation so names, slugs, and typed phrases compare similarly.
    return "".join(character.lower() for character in value if character.isalnum())


def _score(reference: str, candidate: str) -> float:
    # Score is a blend of substring friendliness and SequenceMatcher similarity.
    # It is used only for project disambiguation, not as a database filter.
    left = _normalize(reference)
    right = _normalize(candidate)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return min(
            1.0, max(len(left), len(right)) / max(min(len(left), len(right)), 1) * 0.72
        )
    return SequenceMatcher(a=left, b=right).ratio()


def _bounded_limit(limit: int, *, maximum: int = 50) -> int:
    # Keep tool responses compact and prevent accidental huge metadata/analytics
    # reads from being returned to an agent.
    return max(1, min(limit, maximum))


def _prefer_project_contract_rows(
    contracts: list[DataContractRecord],
    project_pk: int,
) -> list[DataContractRecord]:
    by_label: dict[str, DataContractRecord] = {}
    for contract in contracts:
        existing = by_label.get(contract.data_contract_id)
        if existing is None or contract.project_id == project_pk:
            by_label[contract.data_contract_id] = contract
    return list(by_label.values())


async def _run_record_payload_public(
    session: AsyncSession, row: RunRecord
) -> dict[str, Any]:
    # RunRecord stores project/import as integer foreign keys. Convert them to
    # public labels before building the tool payload.
    project_id = await _public_label(
        session, ProjectRecord, "project_id", row.project_id
    )
    data_import_id = await _public_label(
        session, DataImportRecord, "data_import_id", row.data_import_id
    )
    analysis_type_id = await _public_label(
        session, AnalysisTypeRecord, "analysis_type_id", row.analysis_type_id
    )
    method_id = await _public_label(
        session, AnalysisMethodRecord, "method_id", row.method_id
    )
    app_path = _run_path(project_id, row.run_id)
    return {
        "run_id": row.run_id,
        "project_id": project_id,
        "data_import_id": data_import_id,
        "project": row.project,
        "name": row.name,
        "app_path": app_path,
        "markdown_link": (
            f"[{row.name or row.run_id}]({app_path})" if app_path else row.run_id
        ),
        "run_kind": row.run_kind,
        "analysis_type_id": analysis_type_id,
        "method_id": method_id,
        "method_version": row.method_version,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "started_at": (
            row.started_at.isoformat() if row.started_at is not None else None
        ),
        "ended_at": row.ended_at.isoformat() if row.ended_at is not None else None,
    }


def _run_payload(run: Any) -> dict[str, Any]:
    # Public Run models already carry labels, so this helper only adds links and
    # a lightweight sample count.
    payload = run.model_dump(mode="json", exclude={"samples"})
    app_path = _run_path(run.project_id, run.run_id)
    payload["app_path"] = app_path
    payload["markdown_link"] = (
        f"[{run.name or run.run_id}]({app_path})" if app_path else run.run_id
    )
    payload["sample_count"] = len(run.samples)
    return payload


async def _sample_payload_public(
    session: AsyncSession, row: SampleRecord
) -> dict[str, Any]:
    # SampleRecord uses integer foreign keys for project/subject; expose public
    # labels in tool output.
    project_id = await _public_label(
        session, ProjectRecord, "project_id", row.project_id
    )
    payload = _sample_link_fields(
        project_id=project_id,
        sample_id=row.sample_id,
        sample_name=row.sample_name,
    )
    payload.update(
        {
            "subject_id": await _public_label(
                session, SubjectRecord, "subject_id", row.subject_id
            ),
        }
    )
    return payload


def _sample_model_payload(sample: Any) -> dict[str, Any]:
    # Samples embedded in public Run models are already label-based, unlike raw
    # SampleRecord rows from SQL.
    payload = _sample_link_fields(
        project_id=sample.project_id,
        sample_id=sample.sample_id,
        sample_name=sample.sample_name,
    )
    payload.update(
        {
            "subject_id": sample.subject_id,
            "metadata_json": sample.metadata_json,
        }
    )
    return payload


def _sample_link_fields(
    *,
    project_id: str | None,
    sample_id: str,
    sample_name: str | None,
) -> dict[str, Any]:
    # Keep dashboard link fields consistent across sample-list and run-sample
    # payloads.
    label = sample_name or sample_id
    app_path = _sample_path(project_id, sample_id)
    return {
        "sample_id": sample_id,
        "project_id": project_id,
        "sample_name": sample_name,
        "app_path": app_path,
        "markdown_link": f"[{label}]({app_path})" if app_path else label,
    }


def _project_path(project_id: str) -> str:
    # quote(..., safe="") prevents slashes or spaces in source IDs from being
    # interpreted as route separators.
    return f"/project/{quote(project_id, safe='')}"


def _run_path(project_id: str | None, run_id: str) -> str | None:
    # Some legacy/global run payloads may not have a project label; without it,
    # the dashboard cannot build a project-scoped route.
    if project_id is None:
        return None
    return f"{_project_path(project_id)}/runs/{quote(run_id, safe='')}"


def _sample_path(project_id: str | None, sample_id: str) -> str | None:
    # Sample pages are project-scoped, so a missing project means no safe link.
    if project_id is None:
        return None
    return f"{_project_path(project_id)}/samples/{quote(sample_id, safe='')}"


def _file_payload(
    file: FileRecord,
    link: FileLinkRecord,
    *,
    association_scope: str = "direct_run",
    association_reason: str | None = None,
) -> dict[str, Any]:
    # This first pass preserves the raw link IDs. _file_payload_public() upgrades
    # them to stable labels when a session is available.
    metadata_value = file.metadata_json
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    source_path = metadata.get("source_path")
    return {
        "file_id": file.file_id,
        "project_id": file.project_id,
        "data_import_id": link.data_import_id,
        "run_id": link.run_id,
        "run_sample_id": link.run_sample_id,
        "sample_id": link.sample_id,
        "data_contract_id": link.data_contract_id,
        "association_scope": association_scope,
        "association_reason": association_reason,
        "kind": file.file_role,
        "path": file.path,
        "name": Path(file.path).name if file.path is not None else file.file_id,
        "size_bytes": file.size_bytes,
        "sha256": file.sha256,
        "source_path": source_path if isinstance(source_path, str) else None,
        "created_at": (
            file.created_at.isoformat() if file.created_at is not None else None
        ),
    }


async def _file_payload_public(
    session: AsyncSession,
    file: FileRecord,
    link: FileLinkRecord,
    *,
    association_scope: str = "direct_run",
    association_reason: str | None = None,
) -> dict[str, Any]:
    payload = _file_payload(
        file,
        link,
        association_scope=association_scope,
        association_reason=association_reason,
    )
    # File links store SQL primary keys internally, but query tools should expose
    # stable public labels because their output is read by users and agents.
    payload.update(
        {
            "project_id": await _public_label(
                session, ProjectRecord, "project_id", link.project_id
            ),
            "data_import_id": await _public_label(
                session, DataImportRecord, "data_import_id", link.data_import_id
            ),
            "run_id": await _public_label(session, RunRecord, "run_id", link.run_id),
            "run_sample_id": await _public_label(
                session, RunSampleRecord, "run_sample_id", link.run_sample_id
            ),
            "sample_id": await _public_label(
                session, SampleRecord, "sample_id", link.sample_id
            ),
            "data_contract_id": await _public_label(
                session, DataContractRecord, "data_contract_id", link.data_contract_id
            ),
        }
    )
    return payload


async def _public_label(
    session: AsyncSession,
    model: type[Any],
    label_name: str,
    identifier: int | None,
) -> str | None:
    # Generic FK-to-label lookup used when turning metadata rows into tool
    # payloads. Missing links are tolerated because older/local data may be
    # partially populated.
    if identifier is None:
        return None
    row = await get_record_by_field(session, model, cast(Any, model).id, identifier)
    if row is None:
        return None
    label = getattr(row, label_name)
    return str(label) if label is not None else None


def _dedupe_file_payloads(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # A file can appear via both a direct run link and an import-level link.
    # Keep the richest association for each file_id.
    by_file_id: dict[str, dict[str, Any]] = {}
    for file in files:
        file_id = file.get("file_id")
        if not isinstance(file_id, str):
            continue
        existing = by_file_id.get(file_id)
        if existing is None or _file_payload_rank(file) > _file_payload_rank(existing):
            by_file_id[file_id] = file
    return [by_file_id[file_id] for file_id in sorted(by_file_id)]


def _file_payload_rank(file: dict[str, Any]) -> tuple[int, int]:
    # Direct associations are more specific than import-level associations, and
    # contract-linked files are usually more informative than generic files.
    scope = file.get("association_scope")
    if not isinstance(scope, str):
        scope = ""
    scope_rank = {"direct_run": 3, "direct_sample": 3, "data_import": 2}.get(
        scope,
        1,
    )
    contract_rank = 1 if file.get("data_contract_id") is not None else 0
    return scope_rank, contract_rank


def _analytics_metric_payload(value: Any) -> dict[str, Any]:
    # DuckDB metric rows are typed value records. Collapse the active value
    # column into a single "value" key for simpler tool output.
    return {
        "run_id": value.run_id,
        "data_contract_id": value.data_contract_id,
        "run_sample_id": value.run_sample_id,
        "sample_id": value.sample_id,
        "field_id": value.field_id,
        "value_type": value.value_type,
        "value": _sample_metric_value(value),
        "source_file_id": value.source_file_id,
    }


def _sample_metric_value(value: Any) -> JsonValue:
    # SampleMetric stores exactly one typed value column depending on value_type.
    if getattr(value, "value_type", None) == "numeric":
        return value.value_numeric
    if getattr(value, "value_type", None) == "json":
        return value.value_json
    return value.value_string


def _data_result_payload(
    contract: DataContractRecord,
    fields: list[DataContractFieldRecord],
) -> dict[str, Any]:
    # Data contracts are semantic query contracts. Include a bounded field list so
    # agents can discover available measures without loading every raw row.
    return {
        "data_contract_id": contract.data_contract_id,
        "name": contract.name,
        "data_type": contract.data_type,
        "intrinsic_producer_families": contract.intrinsic_producer_families_json,
        "entity_grain": contract.entity_grain,
        "value_semantics": contract.value_semantics,
        "description": contract.description,
        "summary": contract.summary_json,
        "fields": [_data_contract_field_payload(field) for field in fields],
    }


def _data_contract_field_payload(field: DataContractFieldRecord) -> dict[str, Any]:
    # Field metadata explains how to query and display an individual metric or
    # attribute within a contract.
    return {
        "field_id": field.field_id,
        "field_role": field.field_role,
        "entity_scope": field.entity_scope,
        "display_name": field.display_name,
        "value_type": field.value_type,
        "unit": field.unit,
        "direction": field.direction,
        "description": field.description,
        "primary_table": field.primary_table,
        "physical_tables": field.physical_tables_json,
        "summary": field.summary_json,
        "query_ref": field.query_ref_json,
    }
