from __future__ import annotations

import re

from goodomics.contracts.base import CONTRACT_NAMESPACE_PREFIXES, contract
from goodomics.schemas.models import DataContract


def tool_contract_id(
    tool: str,
    context: str | None = None,
    *,
    kind: str = "metrics",
) -> str:
    """Return a stable bare contract ID for one tool output contract."""

    parts = [_normalize_part(tool)]
    if context:
        parts.append(_normalize_part(context))
    parts.append(_normalize_part(kind))
    return ":".join(parts)


def tool_metrics_contract(
    tool: str,
    context: str | None = None,
    *,
    name: str | None = None,
) -> DataContract:
    """Build a reusable metric contract for a bioinformatics tool output."""

    normalized_tool = _normalize_part(tool)
    normalized_context = _normalize_part(context) if context else None
    display_base = _display_name(normalized_tool, normalized_context)
    display_name = name or f"{display_base} metrics"
    data_contract = contract(
        tool_contract_id(normalized_tool, normalized_context, kind="metrics"),
        name=display_name,
        data_type="generic_metrics",
        producer_tool=normalized_tool,
        feature_type="metric",
        value_type="mixed",
        entity_grain="run_sample",
        primary_table="sample_metrics",
        physical_tables=["sample_metrics"],
        query_modes=["sample", "metric", "cohort"],
        description=f"Sample-level metrics from {display_base} outputs.",
    )
    return _with_tool_metadata(data_contract, normalized_tool, normalized_context)


def tool_payload_contract(
    tool: str,
    context: str | None = None,
    *,
    name: str | None = None,
) -> DataContract:
    """Build a reusable payload-table contract for a bioinformatics tool output."""

    normalized_tool = _normalize_part(tool)
    normalized_context = _normalize_part(context) if context else None
    display_base = _display_name(normalized_tool, normalized_context)
    display_name = name or f"{display_base} payload tables"
    data_contract = contract(
        tool_contract_id(normalized_tool, normalized_context, kind="payloads"),
        name=display_name,
        data_type="contract_payload",
        producer_tool=normalized_tool,
        value_type="table",
        entity_grain="run",
        primary_table="contract_payloads",
        physical_tables=["contract_payloads"],
        query_modes=["payload"],
        description=f"Source tables and plot payloads from {display_base} outputs.",
    )
    return _with_tool_metadata(data_contract, normalized_tool, normalized_context)


def tool_contract_from_id(data_contract_id: str) -> DataContract | None:
    """Return a tool contract for a bare tool contract ID, if it matches one."""

    if data_contract_id.startswith(CONTRACT_NAMESPACE_PREFIXES):
        return None
    parts = data_contract_id.split(":")
    if len(parts) < 2:
        return None
    kind = parts[-1]
    if kind not in {"metrics", "payloads"}:
        return None
    tool = parts[0]
    context = ":".join(parts[1:-1]) or None
    expected = tool_contract_id(tool, context, kind=kind)
    if expected != data_contract_id:
        return None
    if kind == "metrics":
        return tool_metrics_contract(tool, context)
    return tool_payload_contract(tool, context)


def _normalize_part(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "unknown"


def _display_name(tool: str, context: str | None) -> str:
    words = [_title_word(part) for part in tool.split("_")]
    if context:
        words.extend(_title_word(part) for part in context.split("_"))
    return " ".join(words)


def _title_word(value: str) -> str:
    known = {
        "bbtools": "BBTools",
        "fastqc": "FastQC",
        "gc": "GC",
        "qc": "QC",
    }
    return known.get(value, value.title())


def _with_tool_metadata(
    data_contract: DataContract,
    tool: str,
    context: str | None,
) -> DataContract:
    metadata = dict(data_contract.metadata_json)
    metadata.update(
        {
            "contract_family": "tool_output",
            "tool": tool,
            "tool_context": context,
        }
    )
    return data_contract.model_copy(update={"metadata_json": metadata})
