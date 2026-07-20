from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from goodomics import run
from goodomics.contracts.base import CONTRACT_NAMESPACE_PREFIXES
from goodomics.contracts.cbioportal import (
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
    CBIOPORTAL_COPY_NUMBER_SEGMENTS,
    CBIOPORTAL_GENE_PANEL_MATRIX,
    CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
    CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    CBIOPORTAL_MUTATIONS_MAF,
    CBIOPORTAL_STRUCTURAL_VARIANTS,
)
from goodomics.contracts.cbioportal import (
    contract_for_meta as cbioportal_data_contract_for_meta,
)
from goodomics.contracts.registry import (
    built_in_contracts,
    built_in_data_contract_fields_by_contract,
)
from goodomics.contracts.specs import (
    data_contract_fields_from_specs,
    data_contracts_from_specs,
    load_data_contract_spec_file,
    load_package_data_contract_specs,
)
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import DataImport, QCDecision, Run, Sample
from goodomics.storage.database import DEFAULT_DATABASE_URL
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataContractFieldRecord,
    RunRecord,
    SampleRecord,
    initialized_store,
)
from pytest import MonkeyPatch
from sqlmodel import select


def _scalar(row: tuple[Any, ...] | None) -> Any:
    assert row is not None
    return row[0]


def _run_pk(run_id: str) -> int:
    async def load() -> int:
        async with (
            initialized_store(DEFAULT_DATABASE_URL) as metadata_store,
            metadata_store.session() as session,
        ):
            row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == run_id))
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _field_pk(field_id: str) -> int:
    async def load() -> int:
        async with (
            initialized_store(DEFAULT_DATABASE_URL) as metadata_store,
            metadata_store.session() as session,
        ):
            row = (
                await session.exec(
                    select(DataContractFieldRecord).where(
                        DataContractFieldRecord.field_id == field_id
                    )
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _sample_pk(sample_id: str) -> int:
    async def load() -> int:
        async with (
            initialized_store(DEFAULT_DATABASE_URL) as metadata_store,
            metadata_store.session() as session,
        ):
            row = (
                await session.exec(
                    select(SampleRecord).where(SampleRecord.sample_id == sample_id)
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def test_sdk_run_collects_metrics_and_files() -> None:
    qc_run = run("demo", analysis_type_id="rna_sequencing")
    qc_run.log_metric("sample-1", "reads", 42, unit="count")
    qc_run.metric("status", "ok")
    qc_run.log_file(Path("results") / "multiqc.html")

    assert qc_run.name == "demo"
    assert qc_run.analysis_type_id == "rna_sequencing"
    assert qc_run.metrics[0].name == "reads"
    assert qc_run.files == [Path("results") / "multiqc.html"]


def test_sdk_context_persists_metrics_to_project_duckdb(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with run(
        "rnaseq-batch-042", project="rnaseq-core", analysis_type_id="rna_sequencing"
    ) as ctx:
        ctx.log_metric("S1", "pct_mapped", 91.2, unit="percent")
        ctx.log_metric("S1", "status", "pass")

    async def load_run():
        async with initialized_store(DEFAULT_DATABASE_URL) as store:
            return await store.get_run("rnaseq-batch-042")

    saved_run = asyncio.run(load_run())

    assert saved_run is not None
    assert saved_run.project == "rnaseq-core"
    assert saved_run.analysis_type_id == "rna_sequencing"
    assert saved_run.project_id is not None
    assert [sample.sample_id for sample in saved_run.samples] == ["S1"]

    analytics_path = analytics_path_for_project(".goodomics", saved_run.project_id)
    analytics = DuckDBAnalyticsStore(analytics_path)
    values = analytics.list_metric_values(_run_pk("rnaseq-batch-042"))
    pct_mapped_field_id = _field_pk("goodomics:sdk_metrics:pct_mapped")
    status_field_id = _field_pk("goodomics:sdk_metrics:status")
    s1_sample_id = _sample_pk("S1")

    assert any(
        value.field_id == pct_mapped_field_id
        and value.sample_id == s1_sample_id
        and value.value_numeric == 91.2
        for value in values
    )
    assert any(
        value.field_id == status_field_id
        and value.sample_id == s1_sample_id
        and value.value_string == "pass"
        for value in values
    )


def test_schema_models_have_expected_defaults() -> None:
    model = Run(
        run_id="run-1",
        project="project-1",
        analysis_type_id="rna_sequencing",
        method_id="test/workflow",
        samples=[Sample(sample_id="sample-1")],
    )

    assert model.created_at.tzinfo is not None
    assert model.samples[0].metadata == {}


def test_data_import_model_has_expected_defaults() -> None:
    model = DataImport(
        data_import_id="import-1",
        source_type="cbioportal",
        importer_name="cbioportal",
    )

    assert model.status == "complete"
    assert model.created_at.tzinfo is not None
    assert model.parameters_json == {}
    assert model.summary_json == {}


def test_qc_decision_status_values() -> None:
    decision = QCDecision(status="warn", reasons=["low depth"], cohort="study-a")

    assert decision.status == "warn"
    assert decision.reasons == ["low depth"]


def test_builtin_data_contract_registry_has_stable_namespaces() -> None:
    built_in_data_contracts = built_in_contracts()
    assert len(built_in_data_contracts) == len(set(built_in_data_contracts))
    assert all(
        contract_id.startswith(CONTRACT_NAMESPACE_PREFIXES)
        for contract_id in built_in_data_contracts
    )


def test_package_data_contract_specs_load_from_resources() -> None:
    spec_files = load_package_data_contract_specs()
    contract_ids = {
        contract.data_contract_id for contract in data_contracts_from_specs(spec_files)
    }

    assert "salmon:results" in contract_ids
    assert "fastqc:results" in contract_ids
    assert "multiqc:payloads" in contract_ids
    assert "cbioportal:mutations:maf" in contract_ids
    assert "goodomics:sdk_metrics" in contract_ids


def test_cbioportal_feature_matrix_contracts_have_semantic_fields() -> None:
    fields_by_contract = built_in_data_contract_fields_by_contract()

    assert {
        contract_id: [field.field_id for field in fields_by_contract[contract_id]]
        for contract_id in (
            "cbioportal:copy_number:continuous",
            "cbioportal:copy_number:log2",
            "cbioportal:mrna_expression:continuous",
            "cbioportal:mrna_expression:z_score",
            "cbioportal:methylation:continuous_beta",
            "cbioportal:protein_level:log2",
            "cbioportal:protein_level:z_score",
            "cbioportal:generic_assay:limit_value",
        )
    } == {
        "cbioportal:copy_number:continuous": ["copy_number"],
        "cbioportal:copy_number:log2": ["log2_copy_number"],
        "cbioportal:mrna_expression:continuous": ["expression"],
        "cbioportal:mrna_expression:z_score": ["expression_z_score"],
        "cbioportal:methylation:continuous_beta": ["methylation_beta"],
        "cbioportal:protein_level:log2": ["protein_abundance"],
        "cbioportal:protein_level:z_score": ["protein_abundance_z_score"],
        "cbioportal:generic_assay:limit_value": ["assay_measurement"],
    }


def test_data_contract_specs_reject_duplicate_contract_ids() -> None:
    first = load_data_contract_spec_file(
        {
            "contracts": [
                {
                    "data_contract_id": "demo:metrics",
                    "name": "Demo metrics",
                    "data_type": "generic_metrics",
                }
            ]
        }
    )
    second = load_data_contract_spec_file(
        {
            "contracts": [
                {
                    "data_contract_id": "demo:metrics",
                    "name": "Demo metrics again",
                    "data_type": "generic_metrics",
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Duplicate data_contract_id"):
        data_contracts_from_specs([first, second])


def test_data_contract_specs_reject_duplicate_field_identities() -> None:
    spec = load_data_contract_spec_file(
        {
            "contracts": [
                {
                    "data_contract_id": "demo:metrics",
                    "name": "Demo metrics",
                    "data_type": "generic_metrics",
                    "fields": [
                        {"field_id": "demo.value", "display_name": "Demo value"},
                        {"field_id": "demo.value", "display_name": "Duplicate"},
                    ],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Duplicate data contract field"):
        data_contract_fields_from_specs([spec])


def test_data_contract_specs_materialize_contract_and_field_models() -> None:
    spec = load_data_contract_spec_file(
        {
            "contracts": [
                {
                    "data_contract_id": "demo:metrics",
                    "name": "Demo metrics",
                    "data_type": "generic_metrics",
                    "description": "Demo metric fields.",
                    "query_modes": ["sample", "metric"],
                    "fields": [
                        {
                            "field_id": "demo.value",
                            "display_name": "Demo value",
                            "unit": "count",
                            "primary_table": "sample_metrics",
                            "physical_tables": ["sample_metrics"],
                        }
                    ],
                }
            ]
        }
    )

    contract = data_contracts_from_specs([spec])[0]
    field = data_contract_fields_from_specs([spec])[0]

    assert contract.data_contract_id == "demo:metrics"
    assert contract.description == "Demo metric fields."
    assert contract.query_modes_json == {"modes": ["sample", "metric"]}
    assert field.data_contract_id == "demo:metrics"
    assert field.field_id == "demo.value"
    assert field.unit == "count"
    assert field.primary_table == "sample_metrics"
    assert field.physical_tables_json == {"tables": ["sample_metrics"]}


def test_cbioportal_contract_mapping_covers_fixture_formats() -> None:
    cases = [
        (
            {
                "genetic_alteration_type": "CLINICAL",
                "datatype": "PATIENT_ATTRIBUTES",
            },
            "cbioportal:clinical:patient_attributes",
        ),
        (
            {
                "genetic_alteration_type": "COPY_NUMBER_ALTERATION",
                "datatype": "DISCRETE",
            },
            CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
        ),
        (
            {
                "genetic_alteration_type": "COPY_NUMBER_ALTERATION",
                "datatype": "SEG",
            },
            CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        ),
        (
            {"genetic_alteration_type": "MUTATION_EXTENDED", "datatype": "MAF"},
            CBIOPORTAL_MUTATIONS_MAF,
        ),
        (
            {"genetic_alteration_type": "MRNA_EXPRESSION", "datatype": "CONTINUOUS"},
            CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        ),
        (
            {"genetic_alteration_type": "STRUCTURAL_VARIANT", "datatype": "SV"},
            CBIOPORTAL_STRUCTURAL_VARIANTS,
        ),
        (
            {"genetic_alteration_type": "GENERIC_ASSAY", "datatype": "LIMIT-VALUE"},
            CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
        ),
        (
            {
                "genetic_alteration_type": "GENE_PANEL_MATRIX",
                "datatype": "GENE_PANEL_MATRIX",
            },
            CBIOPORTAL_GENE_PANEL_MATRIX,
        ),
    ]

    for values, expected_contract_id in cases:
        contract = cbioportal_data_contract_for_meta(
            values,
            source_meta_file="meta_test.txt",
        )
        assert contract.data_contract_id == expected_contract_id
