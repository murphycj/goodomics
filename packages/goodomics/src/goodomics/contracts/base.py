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

        raise NotImplementedError


def contract(
    data_contract_id: str,
    *,
    name: str,
    data_shape_id: str,
    data_shape_version: int = 1,
    bindings: dict[str, object] | None = None,
    search_tags: Iterable[str] = (),
    description: str | None = None,
    metadata_json: dict[str, object] | None = None,
) -> DataContract:
    """Create a reusable contract pinned to a published semantic shape."""

    return DataContract(
        data_contract_id=data_contract_id,
        name=name,
        data_shape_id=data_shape_id,
        data_shape_version=data_shape_version,
        shape_bindings_json=bindings or {},
        search_tags=list(dict.fromkeys(search_tags)),
        description=description,
        metadata_json=metadata_json or {},
    )
