from __future__ import annotations

from pathlib import Path

from goodomics.profiles.base import profile
from goodomics.schemas.models import DataProfile

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

# cBioPortal profiles are broad semantic contracts reused across studies. Study
# IDs, filenames, and source stable IDs stay as provenance metadata elsewhere.

STATIC_PROFILES: dict[str, DataProfile] = {
    CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES: profile(
        CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
        name="cBioPortal patient clinical attributes",
        data_type="entity_attributes",
        producer_tool="cbioportal",
        value_type="mixed",
        query_modes=["subject", "attribute"],
        description="Patient-level clinical attributes imported from cBioPortal.",
    ),
    CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES: profile(
        CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES,
        name="cBioPortal sample clinical attributes",
        data_type="entity_attributes",
        producer_tool="cbioportal",
        value_type="mixed",
        query_modes=["sample", "attribute"],
        description="Sample-level clinical attributes imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_SEGMENTS: profile(
        CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        name="cBioPortal copy-number segments",
        data_type="copy_number_segments",
        producer_tool="cbioportal",
        feature_type="interval",
        value_type="numeric",
        query_modes=["sample", "region"],
        description="Segment-level copy-number values imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS: profile(
        CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
        name="cBioPortal discrete copy-number calls",
        data_type="feature_calls",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "feature", "call", "cohort"],
        description="Gene-level discrete copy-number calls imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_CONTINUOUS: profile(
        CBIOPORTAL_COPY_NUMBER_CONTINUOUS,
        name="cBioPortal continuous copy-number values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description=(
            "Gene-level continuous copy-number values imported from cBioPortal."
        ),
    ),
    CBIOPORTAL_COPY_NUMBER_LOG2: profile(
        CBIOPORTAL_COPY_NUMBER_LOG2,
        name="cBioPortal log2 copy-number values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Gene-level log2 copy-number values imported from cBioPortal.",
    ),
    CBIOPORTAL_MUTATIONS_MAF: profile(
        CBIOPORTAL_MUTATIONS_MAF,
        name="cBioPortal mutation calls",
        data_type="small_variants",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "variant", "gene", "region"],
        description="Small-variant calls imported from cBioPortal MAF files.",
    ),
    CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS: profile(
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        name="cBioPortal mRNA expression values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous mRNA expression values imported from cBioPortal.",
    ),
    CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE: profile(
        CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE,
        name="cBioPortal mRNA expression z-scores",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="mRNA expression z-scores imported from cBioPortal.",
    ),
    CBIOPORTAL_METHYLATION_CONTINUOUS_BETA: profile(
        CBIOPORTAL_METHYLATION_CONTINUOUS_BETA,
        name="cBioPortal methylation beta values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous methylation beta values imported from cBioPortal.",
    ),
    CBIOPORTAL_PROTEIN_LEVEL_LOG2: profile(
        CBIOPORTAL_PROTEIN_LEVEL_LOG2,
        name="cBioPortal protein abundance values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="protein",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous protein abundance values imported from cBioPortal.",
    ),
    CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE: profile(
        CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE,
        name="cBioPortal protein abundance z-scores",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="protein",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Protein abundance z-scores imported from cBioPortal.",
    ),
    CBIOPORTAL_STRUCTURAL_VARIANTS: profile(
        CBIOPORTAL_STRUCTURAL_VARIANTS,
        name="cBioPortal structural variants",
        data_type="structural_variants",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "feature", "region"],
        description="Structural-variant calls imported from cBioPortal.",
    ),
    CBIOPORTAL_GENE_PANEL_MATRIX: profile(
        CBIOPORTAL_GENE_PANEL_MATRIX,
        name="cBioPortal gene panel matrix",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="matrix",
        query_modes=["payload", "sample", "profile"],
        description="cBioPortal gene panel coverage matrix payload.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE: profile(
        CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
        name="cBioPortal generic assay limit values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="generic_entity",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Numeric limit-value generic assay data imported from cBioPortal.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL: profile(
        CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL,
        name="cBioPortal generic assay categorical values",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="categorical",
        query_modes=["payload", "sample", "feature"],
        description="Categorical generic assay data imported from cBioPortal.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_BINARY: profile(
        CBIOPORTAL_GENERIC_ASSAY_BINARY,
        name="cBioPortal generic assay binary values",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="boolean",
        query_modes=["payload", "sample", "feature"],
        description="Binary generic assay data imported from cBioPortal.",
    ),
}


def profiles() -> list[DataProfile]:
    return sorted(STATIC_PROFILES.values(), key=lambda item: item.data_profile_id)


def profile_for_meta(values: dict[str, str], *, source_meta_file: str) -> DataProfile:
    # Prefer cBioPortal's formal alteration/datatype pair, then conservative
    # stable_id/filename fallbacks for common underspecified source files.
    alteration = values.get("genetic_alteration_type", "").upper()
    datatype = values.get("datatype", "").upper()
    stable_id = values.get("stable_id", "")
    filename = values.get("data_filename", "")

    profile_id = _profile_id(
        alteration=alteration,
        datatype=datatype,
        stable_id=stable_id,
        filename=filename,
    )
    if profile_id is None:
        custom_profile_id = _custom_profile_id(values, source_meta_file)
        return _custom_profile(values, custom_profile_id, source_meta_file)
    return STATIC_PROFILES[profile_id]


def _profile_id(
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


def _custom_profile(
    values: dict[str, str],
    data_profile_id: str,
    source_meta_file: str,
) -> DataProfile:
    # Unknown cBioPortal shapes get source-specific profiles so Goodomics avoids
    # merging incompatible data under a reusable built-in contract.
    alteration = values.get("genetic_alteration_type")
    datatype = values.get("datatype")
    name = (
        values.get("profile_name")
        or values.get("description")
        or values.get("stable_id")
        or Path(values.get("data_filename", source_meta_file)).stem
    )
    return DataProfile(
        data_profile_id=data_profile_id,
        name=name,
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="mixed",
        query_modes_json={"modes": ["payload"]},
        mcp_description=values.get("profile_description") or values.get("description"),
        metadata_json={
            "profile_scope": "source_specific_contract",
            "source_format": "cbioportal",
            "source_meta_file": source_meta_file,
            "source_profile_metadata": {
                "genetic_alteration_type": alteration,
                "datatype": datatype,
                "stable_id": values.get("stable_id"),
            },
        },
    )


def _custom_profile_id(values: dict[str, str], source_meta_file: str) -> str:
    study = _normalize_profile_part(values.get("cancer_study_identifier") or "unknown")
    stable = values.get("stable_id") or Path(values.get("data_filename", "")).stem
    if not stable:
        stable = Path(source_meta_file).stem
    return f"cbioportal:custom:{study}:{_normalize_profile_part(stable)}"


def _normalize_profile_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    return "_".join(part for part in cleaned.strip("_").lower().split("_") if part)
