from __future__ import annotations

from goodomics.profiles.base import profile
from goodomics.schemas.models import DataProfile

GOODOMICS_SDK_METRICS = "goodomics:sdk_metrics"

# SDK metrics are intentionally generic because users define metric names at
# logging time rather than through a parser-specific schema.
STATIC_PROFILES: dict[str, DataProfile] = {
    GOODOMICS_SDK_METRICS: profile(
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


def profiles() -> list[DataProfile]:
    return sorted(STATIC_PROFILES.values(), key=lambda item: item.data_profile_id)
