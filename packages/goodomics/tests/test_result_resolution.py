from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from goodomics.analysis import (
    RNA_SEQUENCING,
    WHOLE_GENOME_SEQUENCING,
    analysis_method,
    resolve_analysis_type,
)
from goodomics.schemas.models import (
    DataContract,
    DataContractAnalysisType,
    Run,
    RunContract,
    RunContractSample,
    RunSample,
    Sample,
)
from goodomics.server.result_resolution import resolve_contract_results
from goodomics.storage.sqlalchemy import (
    DataContractRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select


def test_result_resolver_is_contract_compatible_and_ranks_per_sample(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}"
    store = SQLModelGoodomicsStore(database_url)
    asyncio.run(store.ensure_schema())
    project = asyncio.run(store.ensure_project("resolver"))
    now = datetime.now(UTC)
    runs = [
        _run("rna-old", project.project_id, "rna/workflow", "1", now),
        _run(
            "rna-new", project.project_id, "rna/workflow", "2", now + timedelta(days=1)
        ),
        _run(
            "rna-failed",
            project.project_id,
            "rna/workflow",
            "3",
            now + timedelta(days=2),
            status="failed",
        ),
        Run(
            run_id="wgs-new",
            project_id=project.project_id,
            analysis_type_id=WHOLE_GENOME_SEQUENCING,
            method_id="wgs/workflow",
            method_version="1",
            status="complete",
            ended_at=now + timedelta(days=3),
        ),
    ]
    samples = [
        Sample(sample_id="S1", project_id=project.project_id),
        Sample(sample_id="S2", project_id=project.project_id),
    ]
    run_samples = [
        RunSample(
            run_sample_id=f"{run.run_id}:{sample.sample_id}",
            run_id=run.run_id,
            sample_id=sample.sample_id,
        )
        for run in runs
        for sample in samples
    ]
    contract = DataContract(
        data_contract_id="rna:expression",
        project_id=project.project_id,
        name="RNA expression",
        data_type="feature_matrix",
        entity_grain="sample",
    )
    occurrences = [_occurrence(run, contract.data_contract_id) for run in runs]
    availability = [
        RunContractSample(
            run_contract_id=f"rna-old:{contract.data_contract_id}",
            run_sample_id="rna-old:S1",
            availability="observed",
        ),
        RunContractSample(
            run_contract_id=f"rna-old:{contract.data_contract_id}",
            run_sample_id="rna-old:S2",
            availability="observed",
        ),
        RunContractSample(
            run_contract_id=f"rna-new:{contract.data_contract_id}",
            run_sample_id="rna-new:S1",
            availability="profiled_empty",
        ),
        RunContractSample(
            run_contract_id=f"rna-failed:{contract.data_contract_id}",
            run_sample_id="rna-failed:S2",
            availability="observed",
        ),
        RunContractSample(
            run_contract_id=f"wgs-new:{contract.data_contract_id}",
            run_sample_id="wgs-new:S1",
            availability="observed",
        ),
    ]
    asyncio.run(
        store.replace_runs_catalog(
            runs,
            analysis_types=[
                resolve_analysis_type(RNA_SEQUENCING),
                resolve_analysis_type(WHOLE_GENOME_SEQUENCING),
            ],
            analysis_methods=[
                analysis_method("rna/workflow", method_kind="workflow"),
                analysis_method("wgs/workflow", method_kind="workflow"),
            ],
            samples=samples,
            run_samples=run_samples,
            data_contracts=[contract],
            data_contract_analysis_types=[
                DataContractAnalysisType(
                    data_contract_id=contract.data_contract_id,
                    analysis_type_id=RNA_SEQUENCING,
                )
            ],
            run_contracts=occurrences,
            run_contract_samples=availability,
        )
    )

    async def resolve(scope: dict[str, object] | None = None):
        async with store.session() as session:
            row = (
                await session.exec(
                    select(DataContractRecord).where(
                        DataContractRecord.data_contract_id == contract.data_contract_id
                    )
                )
            ).one()
            return await resolve_contract_results(
                session=session,
                project_id=project.project_id,
                contract=row,
                analysis_grain="sample",
                result_scope=scope,
            )

    latest = asyncio.run(resolve())
    assert latest.diagnostics["resolved_run_contract_ids"] == [
        "rna-old:rna:expression",
        "rna-new:rna:expression",
    ]
    assert latest.diagnostics["excluded_failures"] == 1
    assert latest.diagnostics["excluded_incompatible_analysis_types"] == 1
    assert latest.diagnostics["availability_counts"]["profiled_empty"] == 1
    assert latest.diagnostics["warnings"]

    fixed = asyncio.run(
        resolve(
            {
                "selection": "specific_versions",
                "method_versions": ["2"],
            }
        )
    )
    assert fixed.diagnostics["resolved_run_contract_ids"] == ["rna-new:rna:expression"]
    assert fixed.diagnostics["missing_samples"] == ["S2"]


def _run(
    run_id: str,
    project_id: str,
    method_id: str,
    version: str,
    ended_at: datetime,
    *,
    status: str = "complete",
) -> Run:
    return Run(
        run_id=run_id,
        project_id=project_id,
        analysis_type_id=RNA_SEQUENCING,
        method_id=method_id,
        method_version=version,
        status=status,
        ended_at=ended_at,
    )


def _occurrence(run: Run, contract_id: str) -> RunContract:
    return RunContract(
        run_contract_id=f"{run.run_id}:{contract_id}",
        run_id=run.run_id,
        data_contract_id=contract_id,
        producer_method_id=run.method_id,
        producer_version=run.method_version,
        status="available",
        ended_at=run.ended_at,
    )
