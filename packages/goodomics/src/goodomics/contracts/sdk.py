from __future__ import annotations

from goodomics.contracts.registry import built_in_data_contract
from goodomics.schemas.models import DataContract

GOODOMICS_SDK_METRICS = "goodomics:sdk_metrics"


def contracts() -> list[DataContract]:
    return [built_in_data_contract(GOODOMICS_SDK_METRICS)]
