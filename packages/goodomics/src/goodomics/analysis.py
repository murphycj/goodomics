"""Controlled analysis-type and method identities used by ingest and the SDK."""

from __future__ import annotations

import re

from goodomics.schemas.models import AnalysisMethod, AnalysisType

RNA_SEQUENCING = "rna_sequencing"
WHOLE_GENOME_SEQUENCING = "whole_genome_sequencing"
EXTERNAL_ONCOLOGY = "external_oncology"
QUALITY_CONTROL = "quality_control"
GENERIC_ANALYSIS = "generic_analysis"

BUILT_IN_ANALYSIS_TYPES: dict[str, AnalysisType] = {
    RNA_SEQUENCING: AnalysisType(
        analysis_type_id=RNA_SEQUENCING,
        name="RNA sequencing",
        description="RNA sequencing and transcriptomic analysis.",
    ),
    WHOLE_GENOME_SEQUENCING: AnalysisType(
        analysis_type_id=WHOLE_GENOME_SEQUENCING,
        name="Whole-genome sequencing",
        description="Whole-genome sequencing analysis.",
    ),
    EXTERNAL_ONCOLOGY: AnalysisType(
        analysis_type_id=EXTERNAL_ONCOLOGY,
        name="External oncology dataset",
        description="Imported oncology analysis results.",
    ),
    QUALITY_CONTROL: AnalysisType(
        analysis_type_id=QUALITY_CONTROL,
        name="Quality control",
        description="General quality-control analysis without a more specific type.",
    ),
    GENERIC_ANALYSIS: AnalysisType(
        analysis_type_id=GENERIC_ANALYSIS,
        name="Generic analysis",
        description="Project analysis without a built-in biological category.",
    ),
}

_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._/-][a-z0-9]+)*$")


def resolve_analysis_type(analysis_type_id: str) -> AnalysisType:
    """Resolve a controlled built-in analysis type or reject ambiguous text."""

    value = analysis_type_id.strip()
    analysis_type = BUILT_IN_ANALYSIS_TYPES.get(value)
    if analysis_type is None:
        choices = ", ".join(sorted(BUILT_IN_ANALYSIS_TYPES))
        raise ValueError(
            f"Unknown analysis type {analysis_type_id!r}. Use one of: {choices}."
        )
    return analysis_type


def analysis_method(
    method_id: str,
    *,
    name: str | None = None,
    method_kind: str,
    description: str | None = None,
) -> AnalysisMethod:
    """Build a method metadata entry after validating its stable identifier."""

    value = method_id.strip()
    if not _STABLE_ID.fullmatch(value):
        raise ValueError(
            "Analysis method IDs must be lowercase stable IDs using letters, "
            "numbers, '.', '_', '/', or '-'."
        )
    return AnalysisMethod(
        method_id=value,
        name=name or value,
        method_kind=method_kind,  # type: ignore[arg-type]
        description=description,
    )
