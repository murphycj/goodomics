from __future__ import annotations

import asyncio
from pathlib import Path

from fixtures import write_cbioportal_fixture
from goodomics.ingest.cbioportal import ingest_cbioportal_study
from goodomics.parsers.cbioportal import parse_cbioportal_study
from goodomics.schemas.models import (
    CopyNumberSegment,
    EntityAttributeNumeric,
    FeatureCall,
    FeatureValueNumeric,
    ProfileObservationSet,
    ProfilePayload,
    SampleStructuralVariantCall,
    SampleVariantCall,
)
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataProfileRecord,
    FileLinkRecord,
    FileRecord,
    RunRecord,
    SampleSetRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


def test_parse_cbioportal_study_derives_control_objects(tmp_path: Path) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")

    parsed = parse_cbioportal_study(study, run_id="run-cbio", project_id="project-1")

    assert parsed.run.run_kind == "import_run"
    assert {sample.sample_id for sample in parsed.samples} == {"S1", "S2"}
    assert {subject.subject_id for subject in parsed.subjects} == {"S1", "S2"}
    assert {profile.data_type for profile in parsed.data_profiles} >= {
        "entity_attributes",
        "feature_matrix",
        "feature_calls",
        "small_variants",
        "copy_number_segments",
        "structural_variants",
        "profile_availability",
    }
    assert any(
        profile.data_profile_id == "run-cbio:rna_seq_mrna"
        for profile in parsed.data_profiles
    )
    assert parsed.files
    assert any(
        link.data_profile_id == "run-cbio:rna_seq_mrna" for link in parsed.file_links
    )
    assert parsed.sample_sets[0].name == "All samples"
    assert len(parsed.bulk_loads) == 6


def test_parse_cbioportal_study_defaults_to_sample_scoped_runs(
    tmp_path: Path,
) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")

    parsed = parse_cbioportal_study(study, project_id="project-1")

    assert {run.run_id for run in parsed.all_runs} == {"demo_cbio:S1", "demo_cbio:S2"}
    assert {run_sample.run_id for run_sample in parsed.run_samples} == {
        "demo_cbio:S1",
        "demo_cbio:S2",
    }
    assert "demo_cbio:rna_seq_mrna" in {
        profile.data_profile_id for profile in parsed.data_profiles
    }
    assert "demo_cbio:S1:rna_seq_mrna" in {
        profile.data_profile_id for profile in parsed.data_profiles
    }
    assert any(
        link.run_id == "demo_cbio:S1"
        and link.run_sample_id == "demo_cbio:S1:S1"
        and link.data_profile_id == "demo_cbio:S1:rna_seq_mrna"
        for link in parsed.file_links
    )


def test_ingest_cbioportal_writes_control_and_analytics(tmp_path: Path) -> None:
    study = write_cbioportal_fixture(tmp_path / "study")
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = ingest_cbioportal_study(
        study,
        run_id="run-cbio",
        project="demo",
        assay="cell_line_panel",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.profiles_ingested > 0
    assert result.files_registered > 0
    assert result.bulk_loads == 6

    catalog_store = SQLModelGoodomicsStore(database_url)
    run = asyncio.run(catalog_store.get_run("run-cbio"))
    assert run is not None
    assert run.run_kind == "import_run"

    async def load_catalog_counts() -> tuple[int, int, int, int]:
        async with AsyncSession(catalog_store._get_engine()) as session:
            files = (await session.exec(select(FileRecord))).all()
            links = (await session.exec(select(FileLinkRecord))).all()
            profiles = (await session.exec(select(DataProfileRecord))).all()
            sample_sets = (await session.exec(select(SampleSetRecord))).all()
        return len(files), len(links), len(profiles), len(sample_sets)

    files_count, links_count, profiles_count, sample_sets_count = asyncio.run(
        load_catalog_counts()
    )
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
    assert counts["profile_observation_sets"] >= 6
    assert counts["profile_payloads"] == 1

    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id="run-cbio",
    )
    assert any(
        value.feature_key == "gene:TP53" and value.sample_key == "S1"
        for value in expression_values
    )
    cna_calls = analytics.fetch_records("feature_call", FeatureCall, run_id="run-cbio")
    assert any(
        call.call_code == "AMP" and call.feature_key == "gene:EGFR"
        for call in cna_calls
    )
    segments = analytics.fetch_records(
        "copy_number_segments",
        CopyNumberSegment,
        run_id="run-cbio",
    )
    assert segments[0].genome_build == "hg19"
    variant_calls = analytics.fetch_records(
        "sample_variant_calls",
        SampleVariantCall,
        run_id="run-cbio",
    )
    assert variant_calls[0].allele_fraction == 8 / 28
    sv_calls = analytics.fetch_records(
        "sample_structural_variant_calls",
        SampleStructuralVariantCall,
        run_id="run-cbio",
    )
    assert sv_calls[0].split_read_count == 4
    availability = analytics.fetch_records(
        "profile_observation_sets",
        ProfileObservationSet,
        run_id="run-cbio",
    )
    assert {record.feature_set_key for record in availability} == {"gene_panel:WXS"}
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


def test_ingest_cbioportal_without_run_id_writes_sample_scoped_runs(
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
    assert result.run_id.startswith("demo_cbio:")
    import_group_id = result.run_id.rsplit(":", 1)[0]

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
        f"{import_group_id}:S1",
        f"{import_group_id}:S2",
    ]

    analytics = DuckDBAnalyticsStore(analytics_path)
    expression_values = analytics.fetch_records(
        "feature_value_numeric",
        FeatureValueNumeric,
        run_id=f"{import_group_id}:S1",
    )
    assert expression_values
    assert {value.sample_key for value in expression_values} == {"S1"}
    assert {value.data_profile_key for value in expression_values} == {
        f"{import_group_id}:S1:drug_auc",
        f"{import_group_id}:S1:rna_seq_mrna",
    }


def test_cbioportal_ccle_fixture_discovers_profiles_without_loading_large_files() -> (
    None
):
    study = Path(__file__).parent / "cbioportal" / "ccle_broad_2019"

    parsed = parse_cbioportal_study(study, run_id="ccle-test")

    assert len(parsed.data_profiles) == 15
    assert parsed.summary["files_registered"] >= 30
    assert any(
        profile.data_profile_id == "ccle-test:mutations"
        for profile in parsed.data_profiles
    )
    assert len(parsed.bulk_loads) >= 10


def test_cbioportal_brca_fixture_defaults_to_sample_scoped_runs() -> None:
    study = Path(__file__).parent / "cbioportal" / "brca_tcga_pub2015"

    parsed = parse_cbioportal_study(study)

    assert len(parsed.samples) == 818
    assert len(parsed.all_runs) == len(parsed.samples)
    assert len(parsed.run_samples) == len(parsed.samples)
    assert parsed.all_runs[0].run_id.startswith("brca_tcga_pub2015:")
