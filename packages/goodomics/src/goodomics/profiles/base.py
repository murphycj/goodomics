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
    entity_grain: str | None = None,
    value_semantics: str | None = None,
    primary_table: str | None = None,
    physical_tables: Iterable[str] | None = None,
    description: str | None = None,
) -> DataProfile:
    """Create a reusable semantic data profile contract."""
    # Profile records are contracts, not source/run instances; provenance stays
    # on imports, runs, files, and analytical records.
    resolved_primary_table = primary_table or _default_primary_table(data_type)
    resolved_physical_tables = list(physical_tables or [])
    if resolved_primary_table and not resolved_physical_tables:
        resolved_physical_tables = [resolved_primary_table]
    return DataProfile(
        data_profile_id=data_profile_id,
        name=name,
        data_type=data_type,
        assay=assay,
        producer_tool=producer_tool,
        genome_build=genome_build,
        feature_type=feature_type,
        value_type=value_type,
        entity_grain=entity_grain,
        value_semantics=value_semantics,
        primary_table=resolved_primary_table,
        physical_tables_json={"tables": resolved_physical_tables},
        query_modes_json={"modes": list(query_modes)},
        mcp_description=description,
        metadata_json={"profile_scope": "semantic_contract"},
    )


def _default_primary_table(data_type: str) -> str | None:
    return {
        "generic_metrics": "sample_metrics",
        "entity_attributes": "entity_attributes",
        "feature_matrix": "feature_value_numeric",
        "feature_calls": "feature_call",
        "copy_number_segments": "copy_number_segments",
        "small_variants": "sample_variant_calls",
        "structural_variants": "sample_structural_variant_calls",
        "profile_payload": "profile_payloads",
    }.get(data_type)
