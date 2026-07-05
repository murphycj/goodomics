from __future__ import annotations

from goodomics.profiles.base import profile
from goodomics.schemas.models import DataProfile

MULTIQC_PAYLOADS = "multiqc:payloads"

# MultiQC-owned profiles describe report-level payloads. Tool metrics parsed
# from MultiQC exports use bare tool-owned profiles such as ``salmon:metrics``
# and ``fastqc:raw:metrics`` so direct parsers can reuse the same contracts.
STATIC_PROFILES: dict[str, DataProfile] = {
    MULTIQC_PAYLOADS: profile(
        MULTIQC_PAYLOADS,
        name="MultiQC report payload tables",
        data_type="profile_payload",
        producer_tool="multiqc",
        value_type="table",
        entity_grain="run",
        primary_table="profile_payloads",
        physical_tables=["profile_payloads"],
        query_modes=["payload"],
        description=(
            "Report-level source tables and plot payloads parsed from MultiQC outputs."
        ),
    ),
}


def profiles() -> list[DataProfile]:
    return sorted(STATIC_PROFILES.values(), key=lambda item: item.data_profile_id)
