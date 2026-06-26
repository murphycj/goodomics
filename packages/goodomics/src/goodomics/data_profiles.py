"""Built-in semantic data profile registry.

A data profile is a stable query contract: it tells Goodomics, MCP tools, and
agents what kind of data exists under a profile ID, what shape that data has,
and which query patterns are natural for it. It is not an observation table, a
source file, a run, a sample, or a cBioPortal `stable_id`.

For example, `cbioportal:clinical:sample_attributes` means:

- `data_profile_id`: the stable semantic ID reused across cBioPortal studies.
- `name`: the human-readable label shown in UI and catalogs.
- `data_type`: the broad physical/logical fact shape, such as
  `entity_attributes`, `feature_matrix`, `small_variants`, or
  `copy_number_segments`.
- `producer_tool`: the parser/tool family that emits the profile. This is
  provenance for the contract, not a source run ID.
- `feature_type`: the feature axis when one exists, such as `gene`, `protein`,
  `metric`, or `interval`.
- `value_type`: the expected value semantics for the profile. `numeric` means
  the profile is numeric, `call` means categorical biological calls, and
  `mixed` means rows may contain different concrete value types. Clinical
  attributes are `mixed` because one profile can contain strings, numbers,
  dates, booleans, or JSON-like values.
- `genome_build`: only set when the semantic contract is tied to a reference
  build. Source-specific genome metadata can also live on files/facts.
- `query_modes`: the natural access patterns for agents and query builders.
  `["sample", "attribute"]` means users should expect questions like "show
  attributes for this sample" or "find samples by this attribute"; it does not
  imply gene or region lookup. Today this is descriptive metadata, but it is the
  right place for MCP/UI tooling to decide which query affordances to expose.
- `description`: concise agent-readable text stored as `mcp_description`.

Keep registry entries stable and reusable. If a source cannot be confidently
mapped to one of these contracts, create a source-specific custom profile rather
than forcing incompatible data into a built-in ID.
"""

from __future__ import annotations

from pathlib import Path

from goodomics.schemas.models import DataProfile

# Built-in profile IDs use Goodomics-owned namespaces so agents and MCP tools can
# query by stable semantic contracts instead of source file, study, run, or
# sample-specific identifiers.
PROFILE_NAMESPACE_PREFIXES = ("cbioportal:", "multiqc:", "goodomics:", "user:")


def _profile(
    data_profile_id: str,
    *,
    name: str,
    data_type: str,
    producer_tool: str,
    feature_type: str | None = None,
    value_type: str | None = None,
    genome_build: str | None = None,
    query_modes: list[str],
    description: str,
) -> DataProfile:
    # Registry profiles describe reusable query contracts. Source-specific
    # provenance belongs in runs, file links, payload metadata, and facts.
    return DataProfile(
        data_profile_id=data_profile_id,
        name=name,
        data_type=data_type,
        producer_tool=producer_tool,
        genome_build=genome_build,
        feature_type=feature_type,
        value_type=value_type,
        query_modes_json={"modes": query_modes},
        mcp_description=description,
        metadata_json={"profile_scope": "semantic_contract"},
    )


# cBioPortal contracts are intentionally broad enough to be reused across
# studies. Keep study IDs, cBioPortal stable IDs, filenames, platform labels, and
# descriptions out of these constants unless they change the actual data shape.
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

MULTIQC_METRICS = "multiqc:qc_metrics"
MULTIQC_PAYLOADS = "multiqc:payloads"
GOODOMICS_SDK_METRICS = "goodomics:sdk_metrics"


# This registry is the authoritative list of built-in semantic profiles. Only
# add entries here when Goodomics can parse and query the data shape consistently
# across projects/runs.
BUILT_IN_DATA_PROFILES: dict[str, DataProfile] = {
    CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES: _profile(
        CBIOPORTAL_CLINICAL_PATIENT_ATTRIBUTES,
        name="cBioPortal patient clinical attributes",
        data_type="entity_attributes",
        producer_tool="cbioportal",
        value_type="mixed",
        query_modes=["subject", "attribute"],
        description="Patient-level clinical attributes imported from cBioPortal.",
    ),
    CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES: _profile(
        CBIOPORTAL_CLINICAL_SAMPLE_ATTRIBUTES,
        name="cBioPortal sample clinical attributes",
        data_type="entity_attributes",
        producer_tool="cbioportal",
        value_type="mixed",
        query_modes=["sample", "attribute"],
        description="Sample-level clinical attributes imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_SEGMENTS: _profile(
        CBIOPORTAL_COPY_NUMBER_SEGMENTS,
        name="cBioPortal copy-number segments",
        data_type="copy_number_segments",
        producer_tool="cbioportal",
        feature_type="interval",
        value_type="numeric",
        query_modes=["sample", "region"],
        description="Segment-level copy-number values imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS: _profile(
        CBIOPORTAL_COPY_NUMBER_DISCRETE_CALLS,
        name="cBioPortal discrete copy-number calls",
        data_type="feature_calls",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "feature", "call", "cohort"],
        description="Gene-level discrete copy-number calls imported from cBioPortal.",
    ),
    CBIOPORTAL_COPY_NUMBER_CONTINUOUS: _profile(
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
    CBIOPORTAL_COPY_NUMBER_LOG2: _profile(
        CBIOPORTAL_COPY_NUMBER_LOG2,
        name="cBioPortal log2 copy-number values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Gene-level log2 copy-number values imported from cBioPortal.",
    ),
    CBIOPORTAL_MUTATIONS_MAF: _profile(
        CBIOPORTAL_MUTATIONS_MAF,
        name="cBioPortal mutation calls",
        data_type="small_variants",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "variant", "gene", "region"],
        description="Small-variant calls imported from cBioPortal MAF files.",
    ),
    CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS: _profile(
        CBIOPORTAL_MRNA_EXPRESSION_CONTINUOUS,
        name="cBioPortal mRNA expression values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous mRNA expression values imported from cBioPortal.",
    ),
    CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE: _profile(
        CBIOPORTAL_MRNA_EXPRESSION_Z_SCORE,
        name="cBioPortal mRNA expression z-scores",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="mRNA expression z-scores imported from cBioPortal.",
    ),
    CBIOPORTAL_METHYLATION_CONTINUOUS_BETA: _profile(
        CBIOPORTAL_METHYLATION_CONTINUOUS_BETA,
        name="cBioPortal methylation beta values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous methylation beta values imported from cBioPortal.",
    ),
    CBIOPORTAL_PROTEIN_LEVEL_LOG2: _profile(
        CBIOPORTAL_PROTEIN_LEVEL_LOG2,
        name="cBioPortal protein abundance values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="protein",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Continuous protein abundance values imported from cBioPortal.",
    ),
    CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE: _profile(
        CBIOPORTAL_PROTEIN_LEVEL_Z_SCORE,
        name="cBioPortal protein abundance z-scores",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="protein",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Protein abundance z-scores imported from cBioPortal.",
    ),
    CBIOPORTAL_STRUCTURAL_VARIANTS: _profile(
        CBIOPORTAL_STRUCTURAL_VARIANTS,
        name="cBioPortal structural variants",
        data_type="structural_variants",
        producer_tool="cbioportal",
        feature_type="gene",
        value_type="call",
        query_modes=["sample", "feature", "region"],
        description="Structural-variant calls imported from cBioPortal.",
    ),
    CBIOPORTAL_GENE_PANEL_MATRIX: _profile(
        CBIOPORTAL_GENE_PANEL_MATRIX,
        name="cBioPortal gene panel matrix",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="matrix",
        query_modes=["payload", "sample", "profile"],
        description="cBioPortal gene panel coverage matrix payload.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE: _profile(
        CBIOPORTAL_GENERIC_ASSAY_LIMIT_VALUE,
        name="cBioPortal generic assay limit values",
        data_type="feature_matrix",
        producer_tool="cbioportal",
        feature_type="generic_entity",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
        description="Numeric limit-value generic assay data imported from cBioPortal.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL: _profile(
        CBIOPORTAL_GENERIC_ASSAY_CATEGORICAL,
        name="cBioPortal generic assay categorical values",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="categorical",
        query_modes=["payload", "sample", "feature"],
        description="Categorical generic assay data imported from cBioPortal.",
    ),
    CBIOPORTAL_GENERIC_ASSAY_BINARY: _profile(
        CBIOPORTAL_GENERIC_ASSAY_BINARY,
        name="cBioPortal generic assay binary values",
        data_type="profile_payload",
        producer_tool="cbioportal",
        value_type="boolean",
        query_modes=["payload", "sample", "feature"],
        description="Binary generic assay data imported from cBioPortal.",
    ),
    MULTIQC_METRICS: _profile(
        MULTIQC_METRICS,
        name="MultiQC quality-control metrics",
        data_type="generic_metrics",
        producer_tool="multiqc",
        feature_type="metric",
        value_type="mixed",
        query_modes=["sample", "metric", "cohort"],
        description="Sample-level quality-control metrics parsed from MultiQC outputs.",
    ),
    MULTIQC_PAYLOADS: _profile(
        MULTIQC_PAYLOADS,
        name="MultiQC payload tables",
        data_type="profile_payload",
        producer_tool="multiqc",
        value_type="table",
        query_modes=["payload"],
        description="Source tables and plot payloads parsed from MultiQC outputs.",
    ),
    GOODOMICS_SDK_METRICS: _profile(
        GOODOMICS_SDK_METRICS,
        name="Goodomics SDK metrics",
        data_type="generic_metrics",
        producer_tool="goodomics-sdk",
        feature_type="metric",
        value_type="mixed",
        query_modes=["sample", "metric", "cohort"],
        description="User-logged metrics captured through the Goodomics SDK.",
    ),
}


def built_in_data_profile(data_profile_id: str) -> DataProfile:
    return BUILT_IN_DATA_PROFILES[data_profile_id]


def all_built_in_data_profiles() -> list[DataProfile]:
    return sorted(
        BUILT_IN_DATA_PROFILES.values(), key=lambda item: item.data_profile_id
    )


def cbioportal_data_profile_for_meta(
    values: dict[str, str],
    *,
    source_meta_file: str,
) -> DataProfile:
    # cBioPortal meta files provide several identifiers. The reusable profile is
    # chosen from data-shape fields first; source IDs stay provenance metadata.
    alteration = values.get("genetic_alteration_type", "").upper()
    datatype = values.get("datatype", "").upper()
    stable_id = values.get("stable_id", "")
    filename = values.get("data_filename", "")

    profile_id = _cbioportal_profile_id(
        alteration=alteration,
        datatype=datatype,
        stable_id=stable_id,
        filename=filename,
    )
    if profile_id is None:
        # Unknown cBioPortal shapes get source-specific profiles so we avoid
        # falsely merging incompatible data under a built-in contract.
        profile_id = _custom_cbioportal_profile_id(values, source_meta_file)
        return _custom_cbioportal_profile(values, profile_id, source_meta_file)
    return built_in_data_profile(profile_id)


def _cbioportal_profile_id(
    *,
    alteration: str,
    datatype: str,
    stable_id: str,
    filename: str,
) -> str | None:
    stable_id_lower = stable_id.lower()
    filename_lower = filename.lower()
    # Prefer cBioPortal's formal alteration/datatype pair. stable_id and
    # filename checks are conservative compatibility shims for common families
    # whose meta files do not fully express the Goodomics contract.
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


def _custom_cbioportal_profile(
    values: dict[str, str],
    profile_id: str,
    source_meta_file: str,
) -> DataProfile:
    # Custom profiles are still valid data profiles, but their IDs include source
    # context because Goodomics has not proven that their shape is reusable.
    data_type = "profile_payload"
    feature_type = None
    value_type = "mixed"
    alteration = values.get("genetic_alteration_type")
    datatype = values.get("datatype")
    name = (
        values.get("profile_name")
        or values.get("description")
        or values.get("stable_id")
        or Path(values.get("data_filename", source_meta_file)).stem
    )
    return DataProfile(
        data_profile_id=profile_id,
        name=name,
        data_type=data_type,
        producer_tool="cbioportal",
        feature_type=feature_type,
        value_type=value_type,
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


def _custom_cbioportal_profile_id(
    values: dict[str, str],
    source_meta_file: str,
) -> str:
    # Use normalized cBioPortal source identifiers to make fallback IDs stable
    # across repeated imports of the same study metadata.
    study = _normalize_profile_part(values.get("cancer_study_identifier") or "unknown")
    stable = values.get("stable_id") or Path(values.get("data_filename", "")).stem
    if not stable:
        stable = Path(source_meta_file).stem
    return f"cbioportal:custom:{study}:{_normalize_profile_part(stable)}"


def _normalize_profile_part(value: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in value)
    return "_".join(part for part in cleaned.strip("_").lower().split("_") if part)
