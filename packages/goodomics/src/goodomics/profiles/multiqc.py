from __future__ import annotations

from goodomics.profiles.base import profile
from goodomics.schemas.models import DataProfile

MULTIQC_METRICS = "multiqc:qc_metrics"
MULTIQC_PAYLOADS = "multiqc:payloads"

# MultiQC emits both normalized metric observations and raw payload tables, so
# the provider exposes separate contracts for those query modes.
STATIC_PROFILES: dict[str, DataProfile] = {
    MULTIQC_METRICS: profile(
        MULTIQC_METRICS,
        name="MultiQC quality-control metrics",
        data_type="generic_metrics",
        producer_tool="multiqc",
        feature_type="metric",
        value_type="mixed",
        query_modes=["sample", "metric", "cohort"],
        description="Sample-level quality-control metrics parsed from MultiQC outputs.",
    ),
    MULTIQC_PAYLOADS: profile(
        MULTIQC_PAYLOADS,
        name="MultiQC payload tables",
        data_type="profile_payload",
        producer_tool="multiqc",
        value_type="table",
        query_modes=["payload"],
        description="Source tables and plot payloads parsed from MultiQC outputs.",
    ),
}


def profiles() -> list[DataProfile]:
    return sorted(STATIC_PROFILES.values(), key=lambda item: item.data_profile_id)
