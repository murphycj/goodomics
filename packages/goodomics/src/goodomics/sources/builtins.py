from __future__ import annotations

from goodomics.sources.registry import SourceSpec

# Built-ins use dotted refs so listing sources does not import parser or
# ingestor modules until a source is selected.
BUILT_IN_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="cbioportal",
        label="cBioPortal study",
        ingest="goodomics.ingest.cbioportal:ingest_cbioportal_study",
        parser="goodomics.parsers.cbioportal:parse_cbioportal_study",
        data_contract_provider="goodomics.contracts.cbioportal:contracts",
        result_printer="goodomics.ingest.runner:print_cbioportal_ingest_result",
        ingest_parameters=(
            "project",
            "analysis_type_id",
            "data_import_id",
            "database_url",
            "analytics_path",
            "show_progress",
            "console",
        ),
        run_id_parameter="data_import_id",
    ),
    SourceSpec(
        key="multiqc",
        label="MultiQC output",
        ingest="goodomics.ingest.multiqc:ingest_multiqc_runs",
        parser="goodomics.parsers.multiqc:parse_multiqc_bundle",
        data_contract_provider="goodomics.contracts.multiqc:contracts",
        result_printer="goodomics.ingest.runner:print_multiqc_ingest_results",
        ingest_parameters=(
            "project",
            "analysis_type_id",
            "run_id",
            "database_url",
            "analytics_path",
            "file_root",
        ),
        run_id_parameter="run_id",
    ),
)
