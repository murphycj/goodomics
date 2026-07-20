from __future__ import annotations

import re

from goodomics.contracts.base import CONTRACT_NAMESPACE_PREFIXES, contract
from goodomics.schemas.models import DataContract


def tool_contract_id(
    tool: str,
    context: str | None = None,
    *,
    kind: str = "results",
) -> str:
    """Return a stable bare contract ID for one tool output contract."""

    del context, kind
    return f"{_normalize_part(tool)}:results"


def tool_results_contract(
    tool: str,
    context: str | None = None,
    *,
    name: str | None = None,
) -> DataContract:
    """Build a reusable semantic contract for one bioinformatics tool."""

    normalized_tool = _normalize_part(tool)
    normalized_context = _normalize_part(context) if context else None
    display_base = _display_name(normalized_tool, None)
    data_contract = contract(
        tool_contract_id(normalized_tool),
        name=name or display_base,
        data_type="tool_results",
        producer_tool=normalized_tool,
        feature_type="tool_output",
        value_type="mixed",
        entity_grain="sample",
        query_modes=["sample", "metric", "payload", "sample_group"],
        description=f"Metrics and result payloads from {display_base} outputs.",
    )
    return _with_tool_metadata(data_contract, normalized_tool, normalized_context)


def tool_metrics_contract(
    tool: str,
    context: str | None = None,
    *,
    name: str | None = None,
) -> DataContract:
    """Build a reusable metric contract for a bioinformatics tool output."""

    return tool_results_contract(tool, context, name=name)


def tool_payload_contract(
    tool: str,
    context: str | None = None,
    *,
    name: str | None = None,
) -> DataContract:
    """Build a reusable result-payload contract for a bioinformatics tool output."""

    return tool_results_contract(tool, context, name=name)


def tool_contract_from_id(data_contract_id: str) -> DataContract | None:
    """Return a tool contract for a bare tool contract ID, if it matches one."""

    if data_contract_id.startswith(CONTRACT_NAMESPACE_PREFIXES):
        return None
    parts = data_contract_id.split(":")
    if len(parts) != 2:
        return None
    tool, kind = parts
    if kind != "results":
        return None
    expected = tool_contract_id(tool)
    if expected != data_contract_id:
        return None
    return tool_results_contract(tool)


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
