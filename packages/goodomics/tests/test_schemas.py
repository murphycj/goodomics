from __future__ import annotations

import asyncio
from pathlib import Path

from goodomics import run
from goodomics.data_profiles import (
    BUILT_IN_DATA_PROFILES,
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
    CBIOPORTAL_COPY_NUMBER_SEGMENTS,
    CBIOPORTAL_GENE_PANEL_MATRIX,
    CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
    CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    CBIOPORTAL_MUTATIONS_MAF,
    CBIOPORTAL_STRUCTURAL_VARIANTS,
    PROFILE_NAMESPACE_PREFIXES,
    cbioportal_data_profile_for_meta,
)
from goodomics.projects import analytics_path_for_project
from goodomics.schemas.models import DataImport, QCDecision, Run, Sample
from goodomics.storage.database import DEFAULT_DATABASE_URL
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import SQLModelGoodomicsStore
from pytest import MonkeyPatch


def test_sdk_run_collects_metrics_and_files() -> None:
    qc_run = run("demo", assay="rnaseq")
    qc_run.log_metric("sample-1", "reads", 42, unit="count")
    qc_run.metric("status", "ok")
    qc_run.log_file(Path("results") / "multiqc.html")

    assert qc_run.name == "demo"
    assert qc_run.assay == "rnaseq"
    assert qc_run.metrics[0].name == "reads"
    assert qc_run.files == [Path("results") / "multiqc.html"]


def test_sdk_context_persists_metrics_to_project_duckdb(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with run("rnaseq-batch-042", project="rnaseq-core", assay="bulk_rnaseq") as ctx:
        ctx.log_metric("S1", "pct_mapped", 91.2, unit="percent")
        ctx.log_metric("S1", "status", "pass")

    store = SQLModelGoodomicsStore(DEFAULT_DATABASE_URL)
    saved_run = asyncio.run(store.get_run("rnaseq-batch-042"))

    assert saved_run is not None
    assert saved_run.project == "rnaseq-core"
    assert saved_run.assay == "bulk_rnaseq"
    assert saved_run.project_id is not None
    assert [sample.sample_id for sample in saved_run.samples] == ["S1"]

    analytics_path = analytics_path_for_project(".goodomics", saved_run.project_id)
    values = DuckDBAnalyticsStore(analytics_path).list_metric_values("rnaseq-batch-042")

    assert any(
        value.metric_key == "goodomics:sdk_metrics:pct_mapped"
        and value.sample_key == "S1"
        and value.value == 91.2
        for value in values
    )
    assert any(
        value.metric_key == "goodomics:sdk_metrics:status"
        and value.sample_key == "S1"
        and value.value == "pass"
        for value in values
    )


def test_schema_models_have_expected_defaults() -> None:
    model = Run(
        run_id="run-1",
        project="project-1",
        assay="rnaseq",
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


def test_builtin_data_profile_registry_has_stable_namespaces() -> None:
    assert len(BUILT_IN_DATA_PROFILES) == len(set(BUILT_IN_DATA_PROFILES))
    assert all(
        profile_id.startswith(PROFILE_NAMESPACE_PREFIXES)
        for profile_id in BUILT_IN_DATA_PROFILES
    )


def test_cbioportal_profile_mapping_covers_fixture_formats() -> None:
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

    for values, expected_profile_id in cases:
        profile = cbioportal_data_profile_for_meta(
            values,
            source_meta_file="meta_test.txt",
        )
        assert profile.data_profile_id == expected_profile_id
