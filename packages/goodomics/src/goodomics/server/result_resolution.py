"""Shared contract-result resolver for insights, reports, API, MCP, and AI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.storage.sqlalchemy import (
    AnalysisMethodRecord,
    AnalysisTypeRecord,
    DataContractAnalysisTypeRecord,
    DataContractRecord,
    ProjectRecord,
    RunContractRecord,
    RunContractSampleRecord,
    RunRecord,
    RunSampleRecord,
    SampleRecord,
)

SUCCESSFUL_RUN_STATUSES = {"complete", "completed", "success", "successful", "passed"}
ELIGIBLE_AVAILABILITY = {"observed", "profiled_empty"}


@dataclass(frozen=True)
class ResultResolution:
    """Resolved occurrence IDs plus user-visible selection diagnostics."""

    run_contract_pks: list[int]
    run_sample_pks: list[int]
    diagnostics: dict[str, Any]


async def resolve_contract_results(
    *,
    session: AsyncSession,
    project_id: str | None,
    contract: DataContractRecord,
    analysis_grain: str,
    result_scope: Mapping[str, Any] | None,
) -> ResultResolution:
    """Resolve compatible produced results according to one series scope."""

    scope = dict(result_scope or {})
    selection = str(
        scope.get("selection")
        or (
            "all_eligible_runs"
            if analysis_grain == "run"
            else "latest_successful_per_sample"
        )
    )
    project_pk = await _project_pk(session, project_id)
    statement = (
        select(
            RunContractRecord,
            RunRecord,
            AnalysisTypeRecord,
            AnalysisMethodRecord,
        )
        .join(RunRecord, cast(Any, RunRecord.id) == RunContractRecord.run_id)
        .join(
            AnalysisTypeRecord,
            cast(Any, AnalysisTypeRecord.id) == RunRecord.analysis_type_id,
        )
        .join(
            AnalysisMethodRecord,
            cast(Any, AnalysisMethodRecord.id) == RunRecord.method_id,
        )
        .where(RunContractRecord.data_contract_id == contract.id)
    )
    if project_pk is not None:
        statement = statement.where(RunRecord.project_id == project_pk)
    compatible_type_ids = set(await _compatible_analysis_types(session, contract))
    rows = list((await session.exec(statement)).all())
    incompatible = [
        row
        for row in rows
        if compatible_type_ids and row[2].id not in compatible_type_ids
    ]
    rows = [
        row
        for row in rows
        if not compatible_type_ids or row[2].id in compatible_type_ids
    ]
    all_compatible_rows = list(rows)

    rows = _apply_scope_filters(rows, scope, selection)
    excluded_failures = sum(
        1
        for occurrence, run, _, _ in all_compatible_rows
        if run.status.lower() not in SUCCESSFUL_RUN_STATUSES
        or occurrence.status.lower() not in {"available", "complete", "observed"}
    )
    if selection == "latest_successful_per_sample":
        rows = [
            row
            for row in rows
            if row[1].status.lower() in SUCCESSFUL_RUN_STATUSES
            and row[0].status.lower() in {"available", "complete", "observed"}
        ]

    occurrence_pks = [int(row[0].id) for row in rows if row[0].id is not None]
    availability_rows = await _availability_rows(session, occurrence_pks)
    eligible_availability = [
        row for row in availability_rows if row[0].availability in ELIGIBLE_AVAILABILITY
    ]
    by_occurrence = {int(row[0].id): row for row in rows if row[0].id is not None}
    selected_availability = eligible_availability
    superseded: list[dict[str, Any]] = []
    if analysis_grain != "run" and selection == "latest_successful_per_sample":
        ranked: dict[
            int, list[tuple[RunContractSampleRecord, RunSampleRecord, SampleRecord]]
        ] = {}
        for availability, run_sample, sample in eligible_availability:
            ranked.setdefault(int(sample.id), []).append(
                (availability, run_sample, sample)
            )
        selected_availability = []
        for candidates in ranked.values():
            candidates.sort(
                key=lambda item: _rank_key(by_occurrence[int(item[0].run_contract_id)]),
                reverse=True,
            )
            selected_availability.append(candidates[0])
            superseded.extend(
                {
                    "run_contract_id": by_occurrence[int(item[0].run_contract_id)][
                        0
                    ].run_contract_id,
                    "run_sample_id": item[1].run_sample_id,
                    "sample_id": item[2].sample_id,
                }
                for item in candidates[1:]
            )

    selected_occurrence_pks = (
        sorted({int(row[0].run_contract_id) for row in selected_availability})
        if analysis_grain != "run"
        else occurrence_pks
    )
    selected_run_sample_pks = sorted(
        {int(row[1].id) for row in selected_availability if row[1].id is not None}
    )
    represented = [by_occurrence[pk] for pk in selected_occurrence_pks]
    versions: dict[str, int] = {}
    methods: dict[str, int] = {}
    for occurrence, _, _, method in represented:
        version = occurrence.producer_version or "unversioned"
        versions[version] = versions.get(version, 0) + 1
        methods[method.method_id] = methods.get(method.method_id, 0) + 1

    candidate_sample_ids = {
        row[2].sample_id
        for row in await _availability_rows(
            session,
            [int(row[0].id) for row in all_compatible_rows if row[0].id is not None],
        )
        if row[0].availability in ELIGIBLE_AVAILABILITY
    }
    selected_sample_ids = {row[2].sample_id for row in selected_availability}
    warnings: list[str] = []
    if len(versions) > 1 and selection == "latest_successful_per_sample":
        warnings.append(
            "Latest compatible results use multiple analysis method versions."
        )
    diagnostics = {
        "selection": selection,
        "resolved_run_contract_ids": [row[0].run_contract_id for row in represented],
        "resolved_run_sample_ids": [
            row[1].run_sample_id for row in selected_availability
        ],
        "excluded_failures": excluded_failures,
        "excluded_incompatible_analysis_types": len(incompatible),
        "missing_samples": sorted(candidate_sample_ids - selected_sample_ids),
        "methods": methods,
        "versions": versions,
        "superseded_results": superseded,
        "availability_counts": _availability_counts(availability_rows),
        "warnings": warnings,
    }
    return ResultResolution(
        run_contract_pks=selected_occurrence_pks,
        run_sample_pks=selected_run_sample_pks,
        diagnostics=diagnostics,
    )


def _apply_scope_filters(
    rows: list[Any], scope: Mapping[str, Any], selection: str
) -> list[Any]:
    analysis_types = _string_set(scope, "analysis_type_ids", "analysis_type_id")
    methods = _string_set(scope, "method_ids", "method_id")
    versions = _string_set(scope, "method_versions", "method_version", "versions")
    run_ids = _string_set(scope, "run_ids", "run_id")
    statuses = _string_set(scope, "statuses", "status")
    pinned = _string_set(scope, "run_contract_ids", "run_contract_id", "pinned_results")
    started_after = _datetime_value(scope.get("started_after"))
    ended_before = _datetime_value(scope.get("ended_before"))
    result = []
    for occurrence, run, analysis_type, method in rows:
        if analysis_types and analysis_type.analysis_type_id not in analysis_types:
            continue
        if methods and method.method_id not in methods:
            continue
        if (
            versions
            and (occurrence.producer_version or run.method_version or "")
            not in versions
        ):
            continue
        if run_ids and run.run_id not in run_ids:
            continue
        if (
            statuses
            and run.status not in statuses
            and occurrence.status not in statuses
        ):
            continue
        started_at = occurrence.started_at or run.started_at
        ended_at = occurrence.ended_at or run.ended_at
        if started_after and (started_at is None or started_at < started_after):
            continue
        if ended_before and (ended_at is None or ended_at > ended_before):
            continue
        if (
            selection == "pinned_results"
            and pinned
            and occurrence.run_contract_id not in pinned
        ):
            continue
        result.append((occurrence, run, analysis_type, method))
    return result


async def _availability_rows(
    session: AsyncSession, occurrence_pks: list[int]
) -> list[Any]:
    if not occurrence_pks:
        return []
    return list(
        (
            await session.exec(
                select(RunContractSampleRecord, RunSampleRecord, SampleRecord)
                .join(
                    RunSampleRecord,
                    cast(Any, RunSampleRecord.id)
                    == RunContractSampleRecord.run_sample_id,
                )
                .join(
                    SampleRecord,
                    cast(Any, SampleRecord.id) == RunSampleRecord.sample_id,
                )
                .where(
                    cast(Any, RunContractSampleRecord.run_contract_id).in_(
                        occurrence_pks
                    )
                )
            )
        ).all()
    )


async def _compatible_analysis_types(
    session: AsyncSession, contract: DataContractRecord
) -> list[int]:
    return [
        int(value)
        for value in (
            await session.exec(
                select(DataContractAnalysisTypeRecord.analysis_type_id).where(
                    DataContractAnalysisTypeRecord.data_contract_id == contract.id
                )
            )
        ).all()
    ]


async def _project_pk(session: AsyncSession, project_id: str | None) -> int | None:
    if project_id is None:
        return None
    row = (
        await session.exec(
            select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        )
    ).first()
    return int(row.id) if row is not None and row.id is not None else None


def _rank_key(row: Any) -> tuple[datetime, datetime, datetime, str]:
    occurrence, run, _, _ = row
    minimum = datetime.min.replace(tzinfo=run.created_at.tzinfo)
    return (
        occurrence.ended_at or run.ended_at or minimum,
        occurrence.started_at or run.started_at or minimum,
        run.created_at or minimum,
        run.run_id,
    )


def _string_set(scope: Mapping[str, Any], *keys: str) -> set[str]:
    values: set[str] = set()
    for key in keys:
        raw = scope.get(key)
        if isinstance(raw, str) and raw:
            values.add(raw)
        elif isinstance(raw, list):
            values.update(str(item) for item in raw if isinstance(item, str | int))
    return values


def _availability_counts(rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for availability, _, _ in rows:
        counts[availability.availability] = counts.get(availability.availability, 0) + 1
    return counts


def _datetime_value(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
