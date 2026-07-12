from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from goodomics.schemas.models import DataContract

# Built-in and custom namespaces share the same contract ID space so query tools
# can reason about both without special casing user-provided data.
CONTRACT_NAMESPACE_PREFIXES = (
    "bbtools:",
    "cbioportal:",
    "cutadapt:",
    "fastqc:",
    "goodomics:",
    "multiqc:",
    "salmon:",
    "user:",
)


class DataContractProvider(Protocol):
    """Provider for source-owned reusable data contracts."""

    def contracts(self) -> list[DataContract]:
        """Return the contracts this provider can emit."""
        ...


def contract(
    data_contract_id: str,
    *,
    name: str,
    data_type: str,
    producer_tool: str | None = None,
    feature_type: str | None = None,
    value_type: str | None = None,
    query_modes: Iterable[str],
    entity_grain: str | None = None,
    value_semantics: str | None = None,
    description: str | None = None,
) -> DataContract:
    """Create a reusable semantic data contract."""
    # Contract records are contracts, not source/run instances; provenance stays
    # on imports, runs, files, and analytical records.
    return DataContract(
        data_contract_id=data_contract_id,
        name=name,
        data_type=data_type,
        feature_type=feature_type,
        value_type=value_type,
        entity_grain=entity_grain,
        value_semantics=value_semantics,
        query_modes_json={"modes": list(query_modes)},
        intrinsic_producer_families_json=(
            {"families": [producer_tool]} if producer_tool else {}
        ),
        description=description,
        metadata_json={"contract_scope": "semantic_contract"},
    )
