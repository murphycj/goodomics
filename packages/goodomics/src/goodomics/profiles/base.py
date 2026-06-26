from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from goodomics.schemas.models import DataProfile

# Built-in and custom namespaces share the same profile ID space so query tools
# can reason about both without special casing user-provided data.
PROFILE_NAMESPACE_PREFIXES = ("cbioportal:", "multiqc:", "goodomics:", "user:")


class DataProfileProvider(Protocol):
    """Provider for source-owned reusable data profile contracts."""

    def profiles(self) -> list[DataProfile]:
        """Return the profiles this provider can emit."""
        ...


def profile(
    data_profile_id: str,
    *,
    name: str,
    data_type: str,
    producer_tool: str | None = None,
    feature_type: str | None = None,
    value_type: str | None = None,
    genome_build: str | None = None,
    assay: str | None = None,
    query_modes: Iterable[str],
    description: str | None = None,
) -> DataProfile:
    """Create a reusable semantic data profile contract."""
    # Profile records are contracts, not source/run instances; provenance stays
    # on imports, runs, files, and analytical facts.
    return DataProfile(
        data_profile_id=data_profile_id,
        name=name,
        data_type=data_type,
        assay=assay,
        producer_tool=producer_tool,
        genome_build=genome_build,
        feature_type=feature_type,
        value_type=value_type,
        query_modes_json={"modes": list(query_modes)},
        mcp_description=description,
        metadata_json={"profile_scope": "semantic_contract"},
    )
