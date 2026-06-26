from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fixtures import write_cbioportal_fixture
from goodomics.data_profiles import (
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
    EntityAttributeNumeric,
    FeatureCall,
    FeatureValueNumeric,
    ProfilePayload,
    SampleStructuralVariantCall,
    SampleVariantCall,
)
from goodomics.server.app import create_app
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataImportRecord,
    DataProfileRecord,
    FileLinkRecord,
    FileRecord,
    RunRecord,
    SampleSetRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


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
    assert {profile.data_type for profile in parsed.data_profiles} >= {
        "entity_attributes",
        "feature_matrix",
        "feature_calls",
        "small_variants",
        "copy_number_segments",
        "structural_variants",
        "profile_payload",
    }
    profile_ids = {profile.data_profile_id for profile in parsed.data_profiles}
    assert CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS in profile_ids
    assert CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS in profile_ids
    assert CBIOPORTAL_COPY_NUMBER_SEGMENTS in profile_ids
    assert CBIOPORTAL_MUTATIONS_MAF in profile_ids
    assert CBIOPORTAL_STRUCTURAL_VARIANTS in profile_ids
    assert CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE in profile_ids
    assert CBIOPORTAL_GENE_PANEL_MATRIX in profile_ids
    assert all("run-cbio" not in profile_id for profile_id in profile_ids)
    assert all("S1" not in profile_id for profile_id in profile_ids)
    assert parsed.files
    assert any(
        link.data_profile_id == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
        and link.data_import_id == "run-cbio"
        and link.run_id is None
        for link in parsed.file_links
    )
    assert parsed.sample_sets[0].name == "All samples"
    assert len(parsed.bulk_loads) == 6


def test_parse_cbioportal_study_creates_sample_runs(
    tmp_path: Path,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")

    parsed = parse_cbioportal_study(study, project_id="project-1")

    assert {run.run_id for run in parsed.all_runs} == {
        "demo_cbio:S1",
        "demo_cbio:S2",
    }
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        "demo_cbio:S1",
        "demo_cbio:S2",
    }
    assert {profile.data_profile_id for profile in parsed.data_profiles} >= {
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        CBIOPORTAL_MUTATIONS_MAF,
    }
    assert any(
        link.data_import_id == "demo_cbio"
        and link.run_id is None
        and link.run_sample_id is None
        and link.data_profile_id == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
        for link in parsed.file_links
    )


def test_parse_cbioportal_studies_reuse_semantic_profiles(tmp_path: Path) -> None:
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

    assert {profile.data_profile_id for profile in first.data_profiles} == {
        profile.data_profile_id for profile in second.data_profiles
    }


def test_ingest_cbioportal_writes_control_and_analytics(tmp_path: Path) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = ingest_cbioportal_study(
        study,
        data_import_id="run-cbio",
        project="demo",
        assay="cell_line_panel",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.profiles_ingested > 0
    assert result.files_registered > 0
    assert result.bulk_loads == 6

    catalog_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(catalog_store.get_run("run-cbio:S1"))
    assert run is not None
    assert run.run_kind == "imported_result"
    assert run.data_import_id == "run-cbio"

    async def load_catalog_counts() -> tuple[
        int, int, int, int, int, list[str], set[str | None]
    ]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            imports = (await session.exec(select(DataImportRecord))).all()
            runs = (
                await session.exec(select(RunRecord).order_by(RunRecord.run_id))
            ).all()
            files = (await session.exec(select(FileRecord))).all()
            links = (await session.exec(select(FileLinkRecord))).all()
            profiles = (await session.exec(select(DataProfileRecord))).all()
            sample_sets = (await session.exec(select(SampleSetRecord))).all()
        return (
            len(imports),
            len(files),
            len(links),
            len(profiles),
            len(sample_sets),
            [row.run_id for row in runs],
            {link.data_import_id for link in links},
        )

    (
        imports_count,
        files_count,
        links_count,
        profiles_count,
        sample_sets_count,
        run_ids,
        linked_import_ids,
    ) = asyncio.run(load_catalog_counts())
    assert imports_count == 1
    assert run_ids == ["run-cbio:S1", "run-cbio:S2"]
    assert linked_import_ids == {"run-cbio"}
    assert files_count > 0
    assert links_count >= files_count
    assert profiles_count == result.profiles_ingested
    assert sample_sets_count == 1

    analytics = DuckDBAnalyticsStore(analytics_path)
    counts = analytics.row_counts()
    assert counts["entity_attribute_numeric"] >= 2
    assert counts["feature_value_numeric"] >= 6
    assert counts["feature_call"] == 4
    assert counts["copy_number_segments"] == 1
    assert counts["sample_variant_calls"] == 1
    assert counts["sample_structural_variant_calls"] == 1
    assert counts["profile_payloads"] == 1

    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id="run-cbio:S1",
    )
    assert any(
        value.feature_key == "gene:TP53" and value.sample_key == "S1"
        for value in expression_values
    )
    cna_calls = analytics.fetch_records(
        "feature_call", FeatureCall, run_id="run-cbio:S1"
    )
    assert any(
        call.call_code == "AMP" and call.feature_key == "gene:EGFR"
        for call in cna_calls
    )
    segments = analytics.fetch_records(
        "copy_number_segments",
        CopyNumberSegment,
        run_id="run-cbio:S1",
    )
    assert segments[0].genome_build == "hg19"
    variant_calls = analytics.fetch_records(
        "sample_variant_calls",
        SampleVariantCall,
        run_id="run-cbio:S1",
    )
    assert variant_calls[0].allele_fraction == 8 / 28
    sv_calls = analytics.fetch_records(
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        run_id="run-cbio:S1",
    )
    assert sv_calls[0].split_read_count == 4
    payloads = analytics.fetch_records(
        "profile_payloads", ProfilePayload, run_id="run-cbio"
    )
    assert payloads[0].payload_kind == "gene_panel_matrix"
    numeric_attributes = analytics.fetch_records(
        "entity_attribute_numeric",
        EntityAttributeNumeric,
    )
    assert any(
        attribute.attribute_key == "sample:tmb" for attribute in numeric_attributes
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
        file["data_profile_id"] == CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
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
        assay="cell_line_panel",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.runs_ingested == 2
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
        f"{result.data_import_id}:S1",
        f"{result.data_import_id}:S2",
    ]

    analytics = DuckDBAnalyticsStore(analytics_path)
    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id=f"{result.data_import_id}:S1",
    )
    assert expression_values
    assert {value.sample_key for value in expression_values} == {"S1"}
    assert {value.data_profile_key for value in expression_values} == {
        CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    }


def test_cbioportal_ccle_fixture_discovers_profiles_without_loading_large_files() -> (
    None
):
    study = _external_cbioportal_fixture("ccle_broad_2019")

    parsed = parse_cbioportal_study(study, data_import_id="ccle-test")

    assert len(parsed.data_profiles) >= 10
    assert parsed.summary["files_registered"] >= 30
    assert any(
        profile.data_profile_id == CBIOPORTAL_MUTATIONS_MAF
        for profile in parsed.data_profiles
    )
    assert len(parsed.bulk_loads) >= 10


def test_cbioportal_brca_fixture_creates_sample_runs() -> None:
    study = _external_cbioportal_fixture("brca_tcga_pub2015")

    parsed = parse_cbioportal_study(study)

    assert len(parsed.samples) == 818
    assert len(parsed.all_runs) == len(parsed.samples)
    assert len(parsed.run_samples) == len(parsed.samples)
    assert all(run.run_id.startswith("brca_tcga_pub2015:") for run in parsed.all_runs)
    assert "brca_tcga_pub2015" not in {
        run_sample.run_id for run_sample in parsed.run_samples
    }
    assert {
        CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        CBIOPORTAL_MUTATIONS_MAF,
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
    }.issubset({profile.data_profile_id for profile in parsed.data_profiles})


def test_cbioportal_chol_fixture_uses_sample_runs_and_stable_profiles() -> None:
    study = _external_cbioportal_fixture("chol_tcga_pan_can_atlas_2018")

    parsed = parse_cbioportal_study(study)

    assert len(parsed.samples) == 36
    assert len(parsed.all_runs) == 36
    assert len(parsed.run_samples) == 36
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        f"chol_tcga_pan_can_atlas_2018:{run_sample.sample_id}"
        for run_sample in parsed.run_samples
    }
    assert "cbioportal:copy_number:log2" in {
        profile.data_profile_id for profile in parsed.data_profiles
    }
