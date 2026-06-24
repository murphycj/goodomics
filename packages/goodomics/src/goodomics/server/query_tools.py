from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.projects import DEFAULT_PROJECT_ID, analytics_path_for_project
from goodomics.server.settings import Settings
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    ProjectRecord,
    RunRecord,
    SampleRecord,
    SQLModelGoodomicsStore,
    StoredFileRecord,
)

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(frozen=True)
class QueryToolContext:
    settings: Settings
    store: SQLModelGoodomicsStore


class GoodomicsQueryTools:
    def __init__(self, context: QueryToolContext) -> None:
        self.context = context

    async def list_projects(
        self, query: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
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

    async def resolve_project(self, reference: str, limit: int = 5) -> dict[str, Any]:
        reference = reference.strip()
        if not reference:
            return {"status": "not_found", "project": None, "candidates": []}

        projects = await self._all_projects()
        for project in projects:
            if reference == project.project_id:
                return {
                    "status": "matched",
                    "match_type": "project_id",
                    "project": await self._project_summary(project),
                    "candidates": [],
                }
        for project in projects:
            if reference == (project.slug or ""):
                return {
                    "status": "matched",
                    "match_type": "slug",
                    "project": await self._project_summary(project),
                    "candidates": [],
                }

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

    async def get_project_summary(self, project: str) -> dict[str, Any]:
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

    async def list_recent_runs(
        self, project: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
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

    async def list_project_runs(
        self,
        project: str,
        status: str | None = None,
        assay: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        project_id, resolution = await self._required_project_id(project)
        if project_id is None:
            return {"project_resolution": resolution, "runs": []}
        return {
            "project_resolution": resolution,
            "runs": await self._run_rows(
                project_id=project_id,
                status=status,
                assay=assay,
                limit=limit,
                order_recent=True,
            ),
        }

    async def list_project_samples(
        self,
        project: str,
        query: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        project_id, resolution = await self._required_project_id(project)
        if project_id is None:
            return {"project_resolution": resolution, "samples": []}
        await self.context.store.ensure_schema()
        statement = select(SampleRecord).where(SampleRecord.project_id == project_id)
        term = (query or "").strip().lower()
        if term:
            pattern = f"%{term}%"
            statement = statement.where(
                (func.lower(SampleRecord.sample_id).like(pattern))
                | (func.lower(SampleRecord.sample_name).like(pattern))
                | (func.lower(SampleRecord.external_id).like(pattern))
            )
        statement = statement.order_by(cast(Any, SampleRecord.sample_id)).limit(
            _bounded_limit(limit)
        )
        async with self._session() as session:
            rows = (await session.exec(statement)).all()
        return {
            "project_resolution": resolution,
            "samples": [_sample_payload(row) for row in rows],
        }

    async def get_run(self, run_id: str, project: str | None = None) -> dict[str, Any]:
        run = await self.context.store.get_run(run_id)
        if run is None:
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

    async def list_run_samples(
        self, run_id: str, project: str | None = None
    ) -> dict[str, Any]:
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

    async def list_run_metrics(
        self,
        run_id: str,
        project: str | None = None,
        metric_query: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        run_result = await self.get_run(run_id, project=project)
        run = run_result.get("run")
        if not isinstance(run, dict):
            return run_result | {"metrics": [], "analytics_metrics": []}

        term = (metric_query or "").strip().lower()
        scalar_metrics = await self.context.store.list_metrics(run_id)
        if term:
            scalar_metrics = [
                metric
                for metric in scalar_metrics
                if term in metric.name.lower()
                or term in str(metric.value).lower()
                or term in (metric.unit or "").lower()
            ]

        analytics_metrics: list[dict[str, Any]] = []
        try:
            values = self._analytics_store(run.get("project_id")).list_metric_values(
                run_id
            )
            analytics_metrics = [_analytics_metric_payload(value) for value in values]
            if term:
                analytics_metrics = [
                    metric
                    for metric in analytics_metrics
                    if term in str(metric.get("metric_key", "")).lower()
                    or term in str(metric.get("value", "")).lower()
                ]
        except Exception:
            analytics_metrics = []

        bounded = _bounded_limit(limit)
        return {
            "run": run,
            "metrics": [
                metric.model_dump(mode="json") for metric in scalar_metrics[:bounded]
            ],
            "analytics_metrics": analytics_metrics[:bounded],
        }

    async def list_run_files(
        self,
        run_id: str,
        project: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        run_result = await self.get_run(run_id, project=project)
        run = run_result.get("run")
        if not isinstance(run, dict):
            return run_result | {"files": []}
        await self.context.store.ensure_schema()
        statement = select(StoredFileRecord).where(StoredFileRecord.run_id == run_id)
        if kind:
            statement = statement.where(
                func.lower(StoredFileRecord.kind) == kind.lower()
            )
        statement = statement.order_by(cast(Any, StoredFileRecord.id)).limit(
            _bounded_limit(limit)
        )
        async with self._session() as session:
            rows = (await session.exec(statement)).all()
        return {"run": run, "files": [_file_payload(row) for row in rows]}

    async def _all_projects(self) -> list[ProjectRecord]:
        await self.context.store.ensure_default_project()
        async with self._session() as session:
            return list(
                (
                    await session.exec(
                        select(ProjectRecord).order_by(
                            cast(Any, ProjectRecord.created_at),
                            ProjectRecord.name,
                        )
                    )
                ).all()
            )

    async def _get_project(self, project_id: str) -> ProjectRecord | None:
        await self.context.store.ensure_schema()
        async with self._session() as session:
            return await session.get(ProjectRecord, project_id)

    async def _project_summary(self, project: ProjectRecord) -> dict[str, Any]:
        async with self._session() as session:
            run_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(RunRecord)
                        .where(RunRecord.project_id == project.project_id)
                    )
                ).one()
            )
            sample_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(SampleRecord)
                        .where(SampleRecord.project_id == project.project_id)
                    )
                ).one()
            )
            latest_activity_at = (
                await session.exec(
                    select(func.max(RunRecord.created_at)).where(
                        RunRecord.project_id == project.project_id
                    )
                )
            ).one()
            file_count = int(
                (
                    await session.exec(
                        select(func.count())
                        .select_from(StoredFileRecord)
                        .join(
                            RunRecord,
                            cast(Any, StoredFileRecord.run_id) == RunRecord.run_id,
                        )
                        .where(RunRecord.project_id == project.project_id)
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
            "latest_activity_at": latest_activity_at.isoformat()
            if latest_activity_at is not None
            else None,
        }

    async def _project_candidate(
        self, project: ProjectRecord, reference: str, *, score: float | None = None
    ) -> dict[str, Any]:
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
        assay: str | None = None,
        limit: int = 20,
        order_recent: bool = False,
    ) -> list[dict[str, Any]]:
        await self.context.store.ensure_schema()
        statement = select(RunRecord)
        if project_id is not None:
            statement = statement.where(RunRecord.project_id == project_id)
        if status:
            statement = statement.where(func.lower(RunRecord.status) == status.lower())
        if assay:
            statement = statement.where(func.lower(RunRecord.assay) == assay.lower())
        if order_recent:
            statement = statement.order_by(
                cast(Any, RunRecord.created_at).desc(),
                RunRecord.run_id,
            )
        else:
            statement = statement.order_by(RunRecord.run_id)
        statement = statement.limit(_bounded_limit(limit))
        async with self._session() as session:
            rows = (await session.exec(statement)).all()
        return [_run_record_payload(row) for row in rows]

    async def _optional_project_id(
        self, project: str | None
    ) -> tuple[str | None, dict[str, Any] | None]:
        if not project:
            return None, None
        return await self._required_project_id(project)

    async def _required_project_id(
        self, project: str
    ) -> tuple[str | None, dict[str, Any]]:
        resolution = await self.resolve_project(project)
        return _matched_project_id(resolution), resolution

    def _session(self) -> AsyncSession:
        return AsyncSession(self.context.store._get_engine())

    def _analytics_store(self, project_id: str | None) -> DuckDBAnalyticsStore:
        settings = self.context.settings
        if settings.analytics_path:
            return DuckDBAnalyticsStore(settings.analytics_path)
        return DuckDBAnalyticsStore(
            analytics_path_for_project(
                settings.analytics_root, project_id or DEFAULT_PROJECT_ID
            )
        )


def _matched_project_id(resolution: dict[str, Any]) -> str | None:
    project = resolution.get("project")
    if isinstance(project, dict):
        project_id = project.get("project_id")
        return str(project_id) if project_id else None
    return None


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _score(reference: str, candidate: str) -> float:
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
    return max(1, min(limit, maximum))


def _run_record_payload(row: RunRecord) -> dict[str, Any]:
    app_path = _run_path(row.project_id, row.run_id)
    return {
        "run_id": row.run_id,
        "project_id": row.project_id,
        "project": row.project,
        "name": row.name,
        "app_path": app_path,
        "markdown_link": f"[{row.name or row.run_id}]({app_path})"
        if app_path
        else row.run_id,
        "run_kind": row.run_kind,
        "assay": row.assay,
        "pipeline_name": row.pipeline_name,
        "pipeline_version": row.pipeline_version,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat()
        if row.started_at is not None
        else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at is not None else None,
    }


def _run_payload(run: Any) -> dict[str, Any]:
    payload = run.model_dump(mode="json", exclude={"samples", "metrics"})
    app_path = _run_path(run.project_id, run.run_id)
    payload["app_path"] = app_path
    payload["markdown_link"] = (
        f"[{run.name or run.run_id}]({app_path})" if app_path else run.run_id
    )
    payload["sample_count"] = len(run.samples)
    payload["metric_count"] = len(run.metrics)
    return payload


def _sample_payload(row: SampleRecord) -> dict[str, Any]:
    payload = _sample_link_fields(
        project_id=row.project_id,
        sample_id=row.sample_id,
        sample_name=row.sample_name,
    )
    payload.update(
        {
            "subject_id": row.subject_id,
            "external_id": row.external_id,
        }
    )
    return payload


def _sample_model_payload(sample: Any) -> dict[str, Any]:
    payload = _sample_link_fields(
        project_id=sample.project_id,
        sample_id=sample.sample_id,
        sample_name=sample.sample_name,
    )
    payload.update(
        {
            "subject_id": sample.subject_id,
            "external_id": sample.external_id,
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
    return f"/project/{quote(project_id, safe='')}"


def _run_path(project_id: str | None, run_id: str) -> str | None:
    if project_id is None:
        return None
    return f"{_project_path(project_id)}/runs/{quote(run_id, safe='')}"


def _sample_path(project_id: str | None, sample_id: str) -> str | None:
    if project_id is None:
        return None
    return f"{_project_path(project_id)}/samples/{quote(sample_id, safe='')}"


def _file_payload(row: StoredFileRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "file_id": row.file_id,
        "run_id": row.run_id,
        "kind": row.kind,
        "path": row.path,
        "name": Path(row.path).name,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "source_path": row.source_path,
        "created_at": row.created_at.isoformat()
        if row.created_at is not None
        else None,
    }


def _analytics_metric_payload(value: Any) -> dict[str, Any]:
    return {
        "run_id": value.run_id,
        "data_profile_key": value.data_profile_key,
        "run_sample_key": value.run_sample_key,
        "sample_key": value.sample_key,
        "metric_key": value.metric_key,
        "value": value.value,
        "source_file_id": value.source_file_id,
    }
