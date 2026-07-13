from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fixtures import write_cbioportal_fixture
from goodomics.contracts.cbioportal import (
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
    CBIOPORTAL_COPY_NUMBER_SEGMENTS,
    CBIOPORTAL_GENE_PANEL_MATRIX,
    CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
    CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    CBIOPORTAL_MUTATIONS_MAF,
    CBIOPORTAL_STRUCTURAL_VARIANTS,
)
from goodomics.ingest.cbioportal import ingest_cbioportal_study
from goodomics.parsers.cbioportal import parse_cbioportal_study
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.schemas.models import (
    CopyNumberSegment,
    EntityAttribute,
    FeatureCall,
    FeatureValueNumeric,
    ResultPayload,
    SampleStructuralVariantCall,
    SampleVariantCall,
)
from goodomics.server.app import create_app
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataContractRecord,
    DataImportRecord,
    FileLinkRecord,
    FileRecord,
    RunRecord,
    SampleRecord,
    SampleSetMemberRecord,
    SampleSetRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


def _scalar(row: tuple[Any, ...] | None) -> Any:
    assert row is not None
    return row[0]


def _run_pk(database_url: str, run_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(catalog_store._get_engine()) as session:
            row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == run_id))
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _sample_pk(database_url: str, sample_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(catalog_store._get_engine()) as session:
            row = (
                await session.exec(
                    select(SampleRecord).where(SampleRecord.sample_id == sample_id)
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _data_contract_pk(database_url: str, data_contract_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with AsyncSession(catalog_store._get_engine()) as session:
            row = (
                await session.exec(
                    select(DataContractRecord).where(
                        DataContractRecord.data_contract_id == data_contract_id
                    )
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _external_cbioportal_fixture(name: str) -> Path:
    study = Path(__file__).parent / "cbioportal" / name
    if not study.is_dir():
        pytest.skip(f"External cBioPortal fixture is not checked in: {name}")
    return study


def test_parse_cbioportal_study_derives_control_objects(tmp_path: Path) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")

    parsed = parse_cbioportal_study(
        study, data_import_id="run-cbio", project_id="project-1"
    )

    assert parsed.data_import is not None
    assert parsed.data_import.data_import_id == "run-cbio"
    assert parsed.run.run_kind == "imported_result"
    assert {run.run_id for run in parsed.all_runs} == {
        "run-cbio",
        "run-cbio:S1",
        "run-cbio:S2",
    }
    assert {run.data_import_id for run in parsed.all_runs} == {"run-cbio"}
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        "run-cbio:S1",
        "run-cbio:S2",
    }
    assert {sample.sample_id for sample in parsed.samples} == {"S1", "S2"}
    assert {subject.subject_id for subject in parsed.subjects} == {"S1", "S2"}
    assert {contract.data_type for contract in parsed.data_contracts} >= {
        "entity_attributes",
        "feature_matrix",
        "feature_calls",
        "small_variants",
        "copy_number_segments",
        "structural_variants",
        "result_payload",
    }
    contract_ids = {contract.data_contract_id for contract in parsed.data_contracts}
    assert CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS in contract_ids
    assert CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS in contract_ids
    assert CBIOPORTAL_COPY_NUMBER_SEGMENTS in contract_ids
    assert CBIOPORTAL_MUTATIONS_MAF in contract_ids
    assert any(
        field.field_role == "attribute" and field.field_id == "sample:tmb"
        for field in parsed.data_contract_fields
    )
    assert CBIOPORTAL_STRUCTURAL_VARIANTS in contract_ids
    assert CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE in contract_ids
    assert CBIOPORTAL_GENE_PANEL_MATRIX in contract_ids
    assert all("run-cbio" not in contract_id for contract_id in contract_ids)
    assert all("S1" not in contract_id for contract_id in contract_ids)
    assert parsed.files
    assert any(
        link.data_contract_id == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
        and link.data_import_id == "run-cbio"
        and link.run_id is None
        for link in parsed.file_links
    )
    assert parsed.sample_sets[0].name == "All samples"
    assert {member.run_sample_id for member in parsed.sample_set_members} == {
        "run-cbio:S1:S1",
        "run-cbio:S2:S2",
    }
    assert len(parsed.bulk_loads) == 6


def test_parse_cbioportal_study_creates_sample_runs(
    tmp_path: Path,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")

    parsed = parse_cbioportal_study(study, project_id="project-1")

    assert {run.run_id for run in parsed.all_runs} == {
        "demo_cbio",
        "demo_cbio:S1",
        "demo_cbio:S2",
    }
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        "demo_cbio:S1",
        "demo_cbio:S2",
    }
    assert {contract.data_contract_id for contract in parsed.data_contracts} >= {
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        CBIOPORTAL_MUTATIONS_MAF,
    }
    assert any(
        link.data_import_id == "demo_cbio"
        and link.run_id is None
        and link.run_sample_id is None
        and link.data_contract_id == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
        for link in parsed.file_links
    )


def test_parse_cbioportal_tcga_sample_suffixes_share_subject_ids(
    tmp_path: Path,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    (study / "data_clinical_patient.txt").write_text(
        "\r\n".join(
            [
                "#Patient Identifier\tSex\tAge",
                "#Identifier\tSex\tAge at diagnosis",
                "#STRING\tSTRING\tNUMBER",
                "#1\t1\t1",
                "PATIENT_ID\tSEX\tAGE",
                "TCGA-3X-AAV9\tFemale\t45",
                "TCGA-4Y-BBC1\tMale\t52",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    (study / "data_clinical_sample.txt").write_text(
        "\n".join(
            [
                "#Sample Identifier\tPatient Identifier\tCancer Type\tTMB",
                "#Identifier\tPatient\tCancer type\tTumor mutation burden",
                "#STRING\tSTRING\tSTRING\tNUMBER",
                "#1\t1\t1\t1",
                "SAMPLE_ID\tPATIENT_ID\tCANCER_TYPE\tTMB",
                "TCGA-3X-AAV9-01\tTCGA-3X-AAV9\tLung Cancer\t12.5",
                "TCGA-3X-AAV9-02\tTCGA-3X-AAV9\tLung Cancer\t10.1",
                "TCGA-4Y-BBC1-TA\tTCGA-4Y-BBC1\tBreast Cancer\t3.2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (study / "data_gene_panel_matrix.txt").write_text(
        "\n".join(
            [
                "SAMPLE_ID\tmutations\tcna\tstructural_variants",
                "TCGA-3X-AAV9-01\tWXS\tWXS\tWXS",
                "TCGA-3X-AAV9-02\tWXS\tWXS\tWXS",
                "TCGA-4Y-BBC1-TA\tWXS\tWXS\tWXS",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (study / "case_lists" / "cases_all.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "stable_id: demo_all",
                "case_list_name: All samples",
                "case_list_category: all_cases_in_study",
                ("case_list_ids: TCGA-3X-AAV9-01\tTCGA-3X-AAV9-02\tTCGA-4Y-BBC1-TA"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parsed = parse_cbioportal_study(study, project_id="project-1")

    assert {subject.subject_id for subject in parsed.subjects} == {
        "TCGA-3X-AAV9",
        "TCGA-4Y-BBC1",
    }
    assert {sample.sample_id for sample in parsed.samples} == {
        "TCGA-3X-AAV9-01",
        "TCGA-3X-AAV9-02",
        "TCGA-4Y-BBC1-TA",
    }
    assert {sample.sample_id: sample.subject_id for sample in parsed.samples} == {
        "TCGA-3X-AAV9-01": "TCGA-3X-AAV9",
        "TCGA-3X-AAV9-02": "TCGA-3X-AAV9",
        "TCGA-4Y-BBC1-TA": "TCGA-4Y-BBC1",
    }


def test_parse_cbioportal_studies_reuse_semantic_contracts(tmp_path: Path) -> None:
    first = parse_cbioportal_study(
        write_cbioportal_fixture(tmp_path / "study-1"),
        data_import_id="run-one",
        project_id="project-1",
    )
    second = parse_cbioportal_study(
        write_cbioportal_fixture(tmp_path / "study-2"),
        data_import_id="run-two",
        project_id="project-1",
    )

    assert {contract.data_contract_id for contract in first.data_contracts} == {
        contract.data_contract_id for contract in second.data_contracts
    }


def test_ingest_cbioportal_writes_control_and_analytics(tmp_path: Path) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = ingest_cbioportal_study(
        study,
        data_import_id="run-cbio",
        project="demo",
        analysis_type_id="external_oncology",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.contracts_ingested > 0
    assert result.files_registered > 0
    assert result.bulk_loads == 6

    catalog_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(catalog_store.get_run("run-cbio:S1"))
    assert run is not None
    assert run.run_kind == "imported_result"
    assert run.data_import_id == "run-cbio"

    async def load_catalog_counts() -> tuple[
        int, int, int, int, int, int, list[str], set[int | None]
    ]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            imports = (await session.exec(select(DataImportRecord))).all()
            runs = (
                await session.exec(select(RunRecord).order_by(RunRecord.run_id))
            ).all()
            files = (await session.exec(select(FileRecord))).all()
            links = (await session.exec(select(FileLinkRecord))).all()
            contracts = (await session.exec(select(DataContractRecord))).all()
            sample_sets = (await session.exec(select(SampleSetRecord))).all()
            sample_set_members = (
                await session.exec(select(SampleSetMemberRecord))
            ).all()
        return (
            len(imports),
            len(files),
            len(links),
            len(contracts),
            len(sample_sets),
            len(sample_set_members),
            [row.run_id for row in runs],
            {link.data_import_id for link in links},
        )

    (
        imports_count,
        files_count,
        links_count,
        contracts_count,
        sample_sets_count,
        sample_set_members_count,
        run_ids,
        linked_import_ids,
    ) = asyncio.run(load_catalog_counts())
    assert imports_count == 1
    assert run_ids == ["run-cbio", "run-cbio:S1", "run-cbio:S2"]
    assert linked_import_ids == {1}
    assert files_count > 0
    assert links_count >= files_count
    assert contracts_count == result.contracts_ingested
    assert sample_sets_count == 1
    assert sample_set_members_count == 2

    analytics = DuckDBAnalyticsStore(analytics_path)
    counts = analytics.row_counts()
    assert counts["entity_attributes"] >= 2
    assert counts["feature_value_numeric"] >= 6
    assert counts["feature_call"] == 4
    assert counts["copy_number_segments"] == 1
    assert counts["sample_variant_calls"] == 1
    assert counts["sample_structural_variant_calls"] == 1
    assert counts["result_payloads"] == 1
    with analytics._connect() as connection:
        physical_columns_by_table = {
            table_name: {
                row[1]: row[2]
                for row in connection.execute(
                    f"PRAGMA table_info('{table_name}')"
                ).fetchall()
            }
            for table_name in (
                "entity_attributes",
                "feature_value_numeric",
                "feature_call",
                "copy_number_segments",
                "sample_variant_calls",
                "sample_structural_variant_calls",
                "result_payloads",
            )
        }
    for table_columns in physical_columns_by_table.values():
        assert table_columns["data_contract_id"] == "BIGINT"
        assert table_columns["source_file_id"] == "BIGINT"
    for table_name, table_columns in physical_columns_by_table.items():
        if table_name == "entity_attributes":
            assert table_columns["entity_id"] == "VARCHAR"
            assert table_columns["field_id"] == "BIGINT"
            continue
        assert table_columns["run_id"] == "BIGINT"
        assert table_columns["run_sample_id"] == "BIGINT"
    assert physical_columns_by_table["feature_value_numeric"]["sample_id"] == ("BIGINT")
    assert physical_columns_by_table["feature_value_numeric"]["feature_id"] == (
        "BIGINT"
    )

    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id=_run_pk(database_url, "run-cbio:S1"),
    )
    with analytics._connect() as connection:
        tp53_feature_id = connection.execute(
            "SELECT feature_id FROM dim_features WHERE feature_label = 'gene:TP53'"
        ).fetchone()
        tp53_feature_id = _scalar(tp53_feature_id)
        egfr_feature_id = connection.execute(
            "SELECT feature_id FROM dim_features WHERE feature_label = 'gene:EGFR'"
        ).fetchone()
        egfr_feature_id = _scalar(egfr_feature_id)
        s1_sample_id = _sample_pk(database_url, "S1")
    assert any(
        value.feature_id == tp53_feature_id and value.sample_id == s1_sample_id
        for value in expression_values
    )
    cna_calls = analytics.fetch_records(
        "feature_call", FeatureCall, run_id=_run_pk(database_url, "run-cbio:S1")
    )
    assert any(
        call.call_code == "AMP" and call.feature_id == egfr_feature_id
        for call in cna_calls
    )
    segments = analytics.fetch_records(
        "copy_number_segments",
        CopyNumberSegment,
        run_id=_run_pk(database_url, "run-cbio:S1"),
    )
    assert segments[0].genome_build == "hg19"
    variant_calls = analytics.fetch_records(
        "sample_variant_calls",
        SampleVariantCall,
        run_id=_run_pk(database_url, "run-cbio:S1"),
    )
    assert variant_calls[0].allele_fraction == 8 / 28
    sv_calls = analytics.fetch_records(
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        run_id=_run_pk(database_url, "run-cbio:S1"),
    )
    assert sv_calls[0].split_read_count == 4
    payloads = analytics.fetch_records(
        "result_payloads", ResultPayload, run_id=_run_pk(database_url, "run-cbio")
    )
    assert payloads[0].payload_kind == "gene_panel_matrix"
    numeric_attributes = analytics.fetch_records(
        "entity_attributes",
        EntityAttribute,
    )
    with analytics._connect() as connection:
        tmb_field_id = connection.execute(
            """
            SELECT field_id
            FROM dim_fields
            WHERE field_label = 'sample:tmb'
            """
        ).fetchone()
        tmb_field_id = _scalar(tmb_field_id)
    assert any(
        attribute.field_id == tmb_field_id and attribute.value_type == "numeric"
        for attribute in numeric_attributes
    )


def test_cbioportal_run_files_include_inherited_import_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    ingest_cbioportal_study(
        study,
        data_import_id="run-cbio",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    catalog_store = SQLModelGoodomicsStore(database_url)

    async def load_direct_run_links() -> list[FileLinkRecord]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            return list(
                (
                    await session.exec(
                        select(FileLinkRecord).where(
                            FileLinkRecord.run_id == "run-cbio:S1"
                        )
                    )
                ).all()
            )

    assert asyncio.run(load_direct_run_links()) == []

    monkeypatch.setenv("GOODOMICS_DATABASE_URL", database_url)
    monkeypatch.setenv("GOODOMICS_ANALYTICS_PATH", str(analytics_path))
    with TestClient(create_app()) as client:
        run_files = client.get("/api/v1/runs/run-cbio:S1/files")
        sample_files = client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/samples/S1/files"
        )
        sample_run_files = client.get(
            f"/api/v1/projects/{DEFAULT_PROJECT_ID}/samples/S1/runs/run-cbio:S1/files"
        )

    assert run_files.status_code == 200
    files = run_files.json()
    assert files
    assert sample_files.status_code == 200
    assert sample_files.json() == files
    assert sample_run_files.status_code == 200
    assert sample_run_files.json() == files
    assert {file["association_scope"] for file in files} == {"data_import"}
    assert {file["data_import_id"] for file in files} == {"run-cbio"}
    assert any(
        file["data_contract_id"] == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
        for file in files
    )


def test_ingest_cbioportal_without_run_id_writes_generated_sample_runs(
    tmp_path: Path,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = ingest_cbioportal_study(
        study,
        project="demo",
        analysis_type_id="external_oncology",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.runs_ingested == 3
    assert result.data_import_id.startswith("demo_cbio:")

    catalog_store = SQLModelGoodomicsStore(database_url)

    async def load_runs() -> list[str]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            return [
                row.run_id
                for row in (
                    await session.exec(select(RunRecord).order_by(RunRecord.run_id))
                ).all()
            ]

    assert asyncio.run(load_runs()) == [
        result.data_import_id,
        f"{result.data_import_id}:S1",
        f"{result.data_import_id}:S2",
    ]

    analytics = DuckDBAnalyticsStore(analytics_path)
    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id=_run_pk(database_url, f"{result.data_import_id}:S1"),
    )
    assert expression_values
    expected_contract_ids = {
        _data_contract_pk(database_url, CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE),
        _data_contract_pk(database_url, CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS),
    }
    s1_sample_id = _sample_pk(database_url, "S1")
    assert {value.sample_id for value in expression_values} == {s1_sample_id}
    assert {
        value.data_contract_id for value in expression_values
    } == expected_contract_ids


def test_cbioportal_ccle_fixture_discovers_contracts_without_loading_large_files() -> (
    None
):
    study = _external_cbioportal_fixture("ccle_broad_2019")

    parsed = parse_cbioportal_study(study, data_import_id="ccle-test")

    assert len(parsed.data_contracts) >= 10
    assert parsed.summary["files_registered"] >= 30
    assert any(
        contract.data_contract_id == CBIOPORTAL_MUTATIONS_MAF
        for contract in parsed.data_contracts
    )
    assert len(parsed.bulk_loads) >= 10


def test_cbioportal_brca_fixture_creates_sample_runs() -> None:
    study = _external_cbioportal_fixture("brca_tcga_pub2015")

    parsed = parse_cbioportal_study(study)

    assert len(parsed.samples) == 818
    assert len(parsed.all_runs) == len(parsed.samples) + 1
    assert len(parsed.run_samples) == len(parsed.samples)
    sample_runs = [run for run in parsed.all_runs if run.run_id != "brca_tcga_pub2015"]
    assert all(run.run_id.startswith("brca_tcga_pub2015:") for run in sample_runs)
    assert "brca_tcga_pub2015" not in {
        run_sample.run_id for run_sample in parsed.run_samples
    }
    assert {
        CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        CBIOPORTAL_MUTATIONS_MAF,
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    }.issubset({contract.data_contract_id for contract in parsed.data_contracts})


def test_cbioportal_chol_fixture_uses_sample_runs_and_stable_contracts() -> None:
    study = _external_cbioportal_fixture("chol_tcga_pan_can_atlas_2018")

    parsed = parse_cbioportal_study(study)

    assert len(parsed.samples) == 36
    assert len(parsed.all_runs) == 37
    assert len(parsed.run_samples) == 36
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        f"chol_tcga_pan_can_atlas_2018:{run_sample.sample_id}"
        for run_sample in parsed.run_samples
    }
    assert "cbioportal:copy_number:log2" in {
        contract.data_contract_id for contract in parsed.data_contracts
    }


@pytest.mark.skipif(
    os.getenv("GOODOMICS_RUN_CHOL_CBIOPORTAL") != "1",
    reason="set GOODOMICS_RUN_CHOL_CBIOPORTAL=1 to run the CHOL cBioPortal ingest",
)
def test_ingest_cbioportal_chol_fixture_handles_crlf_clinical_headers(
    tmp_path: Path,
) -> None:
    study = _external_cbioportal_fixture("chol_tcga_pan_can_atlas_2018")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    ingest_cbioportal_study(
        study,
        data_import_id="chol-test",
        project="chol-test",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    counts = DuckDBAnalyticsStore(analytics_path).row_counts()
    assert counts["entity_attributes"] > 0
    assert counts["feature_value_numeric"] > 0


@pytest.mark.skipif(
    os.getenv("GOODOMICS_RUN_LARGE_CBIOPORTAL") != "1",
    reason="set GOODOMICS_RUN_LARGE_CBIOPORTAL=1 to run the 50k cBioPortal ingest",
)
def test_ingest_cbioportal_msk_impact_50k_uses_staged_loads_idempotently(
    tmp_path: Path,
) -> None:
    study = _external_cbioportal_fixture("msk_impact_50k_2026")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    ingest_cbioportal_study(
        study,
        data_import_id="msk-50k",
        project="msk-50k",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    analytics = DuckDBAnalyticsStore(analytics_path)
    first_counts = analytics.row_counts()

    ingest_cbioportal_study(
        study,
        data_import_id="msk-50k",
        project="msk-50k",
        database_url=database_url,
        analytics_path=analytics_path,
    )
    second_counts = analytics.row_counts()

    assert second_counts == first_counts
    assert second_counts["entity_attributes"] > 0
    assert second_counts["features"] > 0
    assert second_counts["feature_call"] > 0
    assert second_counts["copy_number_segments"] > 0
    assert second_counts["sample_variant_calls"] > 0
    assert second_counts["sample_structural_variant_calls"] > 0
    assert second_counts["gene_alteration_state"] > 0
