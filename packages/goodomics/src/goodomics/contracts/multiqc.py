from __future__ import annotations

from goodomics.contracts.registry import built_in_data_contract
from goodomics.schemas.models import DataContract

MULTIQC_PAYLOADS = "multiqc:payloads"


def contracts() -> list[DataContract]:
    return [built_in_data_contract(MULTIQC_PAYLOADS)]
