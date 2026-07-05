from __future__ import annotations

from pathlib import Path

from goodomics.contracts.registry import built_in_contracts, built_in_data_contract
from goodomics.schemas.models import DataContract

CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES = "cbioportal:clinical:patient_attributes"
CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES = "cbioportal:clinical:sample_attributes"
CBIOPORTAL_COPY_NUMBER_SEGMENTS = "cbioportal:copy_number:segments"
CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS = "cbioportal:copy_number:discrete_calls"
CBIOPORTAL_COPY_NUMBER_CONTINUOUS = "cbioportal:copy_number:continuous"
CBIOPORTAL_COPY_NUMBER_LOG2 = "cbioportal:copy_number:log2"
CBIOPORTAL_MUTATIONS_MAF = "cbioportal:mutations:maf"
CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS = "cbioportal:mrna_expression:continuous"
CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE = "cbioportal:mrna_expression:z_score"
CBIOPORTAL_METHYLATION_CONTINUOUS_BETA = "cbioportal:methylation:continuous_beta"
CBIOPORTAL_PROTEIN_LEVEL_LOG2 = "cbioportal:protein_level:log2"
CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE = "cbioportal:protein_level:z_score"
CBIOPORTAL_STRUCTURAL_VARIANTS = "cbioportal:structural_variants"
CBIOPORTAL_GENE_PANEL_MATRIX = "cbioportal:gene_panel_matrix"
CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE = "cbioportal:generic_assay:limit_value"
CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL = "cbioportal:generic_assay:categorical"
CBIOPORTAL_GENERIC_ASSAY_BINARY = "cbioportal:generic_assay:binary"


def contracts() -> list[DataContract]:
    contract_ids = {
        CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
        CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES,
        CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
        CBIOPORTAL_COPY_NUMBER_CONTINUOUS,
        CBIOPORTAL_COPY_NUMBER_LOG2,
        CBIOPORTAL_MUTATIONS_MAF,
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE,
        CBIOPORTAL_METHYLATION_CONTINUOUS_BETA,
        CBIOPORTAL_PROTEIN_LEVEL_LOG2,
        CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE,
        CBIOPORTAL_STRUCTURAL_VARIANTS,
        CBIOPORTAL_GENE_PANEL_MATRIX,
        CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
        CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL,
        CBIOPORTAL_GENERIC_ASSAY_BINARY,
    }
    built_ins = built_in_contracts()
    return sorted(
        [built_ins[contract_id] for contract_id in contract_ids],
        key=lambda item: item.data_contract_id,
    )


def contract_for_meta(values: dict[str, str], *, source_meta_file: str) -> DataContract:
    # Prefer cBioPortal's formal alteration/datatype pair, then conservative
    # stable_id/filename fallbacks for common underspecified source files.
    alteration = values.get("genetic_alteration_type", "").upper()
    datatype = values.get("datatype", "").upper()
    stable_id = values.get("stable_id", "")
    filename = values.get("data_filename", "")

    contract_id = _contract_id(
        alteration=alteration,
        datatype=datatype,
        stable_id=stable_id,
        filename=filename,
    )
    if contract_id is None:
        custom_contract_id = _custom_contract_id(values, source_meta_file)
        return _custom_contract(values, custom_contract_id, source_meta_file)
    return built_in_data_contract(contract_id)


def _contract_id(
    *,
    alteration: str,
    datatype: str,
    stable_id: str,
    filename: str,
) -> str | None:
    stable_id_lower = stable_id.lower()
    filename_lower = filename.lower()
    if alteration == "CLINICAL" and datatype == "PATIENT_ATTRIBUTES":
        return CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES
    if alteration == "CLINICAL" and datatype == "SAMPLE_ATTRIBUTES":
        return CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "SEG":
        return CBIOPORTAL_COPY_NUMBER_SEGMENTS
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "DISCRETE":
        return CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "LOG2-VALUE":
        return CBIOPORTAL_COPY_NUMBER_LOG2
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "CONTINUOUS":
        return CBIOPORTAL_COPY_NUMBER_CONTINUOUS
    if alteration == "MUTATION_EXTENDED" and datatype == "MAF":
        return CBIOPORTAL_MUTATIONS_MAF
    if alteration == "MRNA_EXPRESSION" and datatype == "Z-SCORE":
        return CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE
    if alteration == "MRNA_EXPRESSION" and datatype == "CONTINUOUS":
        return CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS
    if alteration == "METHYLATION" and datatype == "CONTINUOUS":
        return CBIOPORTAL_METHYLATION_CONTINUOUS_BETA
    if alteration == "PROTEIN_LEVEL" and datatype == "Z-SCORE":
        return CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE
    if alteration == "PROTEIN_LEVEL" and datatype in {"LOG2-VALUE", "CONTINUOUS"}:
        return CBIOPORTAL_PROTEIN_LEVEL_LOG2
    if alteration == "STRUCTURAL_VARIANT":
        return CBIOPORTAL_STRUCTURAL_VARIANTS
    if alteration == "GENE_PANEL_MATRIX":
        return CBIOPORTAL_GENE_PANEL_MATRIX
    if alteration == "GENERIC_ASSAY" and datatype == "LIMIT-VALUE":
        return CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE
    if alteration == "GENERIC_ASSAY" and datatype == "CATEGORICAL":
        return CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL
    if alteration == "GENERIC_ASSAY" and datatype == "BINARY":
        return CBIOPORTAL_GENERIC_ASSAY_BINARY
    if alteration == "COPY_NUMBER_ALTERATION" and "linear_cna" in stable_id_lower:
        return CBIOPORTAL_COPY_NUMBER_CONTINUOUS
    if alteration == "COPY_NUMBER_ALTERATION" and "linear_cna" in filename_lower:
        return CBIOPORTAL_COPY_NUMBER_CONTINUOUS
    return None


def _custom_contract(
    values: dict[str, str],
    data_contract_id: str,
    source_meta_file: str,
) -> DataContract:
    # Unknown cBioPortal shapes get source-specific contracts so Goodomics avoids
    # merging incompatible data under a reusable built-in contract.
    alteration = values.get("genetic_alteration_type")
    datatype = values.get("datatype")
    name = (
        values.get("profile_name")
        or values.get("description")
        or values.get("stable_id")
        or Path(values.get("data_filename", source_meta_file)).stem
    )
    return DataContract(
        data_contract_id=data_contract_id,
        name=name,
        data_type="contract_payload",
        producer_tool="cbioportal",
        value_type="mixed",
        entity_grain="run_sample",
        primary_table="contract_payloads",
        physical_tables_json={"tables": ["contract_payloads"]},
        query_modes_json={"modes": ["payload"]},
        mcp_description=(
            values.get("contract_description")
            or values.get("profile_description")
            or values.get("description")
        ),
        metadata_json={
            "contract_scope": "source_specific_contract",
            "source_format": "cbioportal",
            "source_meta_file": source_meta_file,
            "source_contract_metadata": {
                "genetic_alteration_type": alteration,
                "datatype": datatype,
                "stable_id": values.get("stable_id"),
            },
        },
    )


def _custom_contract_id(values: dict[str, str], source_meta_file: str) -> str:
    study = _normalize_contract_part(values.get("cancer_study_identifier") or "unknown")
    stable = values.get("stable_id") or Path(values.get("data_filename", "")).stem
    if not stable:
        stable = Path(source_meta_file).stem
    return f"cbioportal:custom:{study}:{_normalize_contract_part(stable)}"


def _normalize_contract_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    return "_".join(part for part in cleaned.strip("_").lower().split("_") if part)
