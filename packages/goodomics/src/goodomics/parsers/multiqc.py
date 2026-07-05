"""Parsing utilities for turning MultiQC exports into Goodomics ingest records."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goodomics.profiles.multiqc import MULTIQC_PAYLOADS
from goodomics.profiles.registry import built_in_data_profile
from goodomics.profiles.tool import tool_metrics_profile, tool_payload_profile
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataProfile,
    DataProfileField,
    UnresolvedAnalyticalRecord,
)

MULTIQC_PAYLOAD_PROFILE = MULTIQC_PAYLOADS


@dataclass(frozen=True)
class ToolProfileIdentity:
    tool: str
    context: str | None = None
    label: str | None = None
    module: str | None = None

    @property
    def metrics_profile_id(self) -> str:
        return tool_metrics_profile(self.tool, self.context).data_profile_id

    @property
    def payload_profile_id(self) -> str:
        return tool_payload_profile(self.tool, self.context).data_profile_id


@dataclass(frozen=True)
class MultiQCOutput:
    """One discovered MultiQC output directory with optional HTML report."""

    root_dir: Path
    data_dir: Path
    report_html: Path | None


@dataclass
class MultiQCParseResult:
    """Accumulated analytical records and discovered outputs from MultiQC parsing."""

    sample_metric_numeric: list[Any] = field(default_factory=list)
    sample_metric_string: list[Any] = field(default_factory=list)
    data_profiles: dict[str, DataProfile] = field(default_factory=dict)
    fields: list[DataProfileField] = field(default_factory=list)
    payloads: list[Any] = field(default_factory=list)
    tool_versions: list[Any] = field(default_factory=list)
    data_sources: list[Any] = field(default_factory=list)
    outputs: list[MultiQCOutput] = field(default_factory=list)

    @property
    def metrics(self) -> list[Any]:
        return [*self.sample_metric_numeric, *self.sample_metric_string]

    @property
    def sample_ids(self) -> set[str]:
        values: set[str] = set()
        for metric in self.metrics:
            sample_id = _record_value(metric, "sample_id")
            if isinstance(sample_id, str):
                values.add(sample_id)
        for payload in self.payloads:
            metadata_json = _record_value(payload, "metadata_json")
            sample_id = (
                metadata_json.get("sample_id")
                if isinstance(metadata_json, dict)
                else None
            )
            if isinstance(sample_id, str):
                values.add(sample_id)
        for source in self.data_sources:
            sample_id = _record_value(source, "sample_id")
            if isinstance(sample_id, str):
                values.add(sample_id)
        return values

    def to_batch(self, *, run_id: str) -> AnalyticsIngestBatch:
        return AnalyticsIngestBatch(
            sample_metrics=[*self.sample_metric_numeric, *self.sample_metric_string],
            profile_payloads=self.payloads,
            tool_versions=self.tool_versions,
            data_sources=self.data_sources,
        )

    @property
    def profile_fields(self) -> list[DataProfileField]:
        return _dedupe_fields(self.fields)

    @property
    def profiles(self) -> list[DataProfile]:
        return [self.data_profiles[key] for key in sorted(self.data_profiles)]


def parse_multiqc_bundle(path: Path, *, run_id: str) -> MultiQCParseResult:
    """Parse all MultiQC outputs discoverable beneath the given path."""

    return parse_multiqc_outputs(discover_multiqc_outputs(path), run_id=run_id)


def parse_multiqc_outputs(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
) -> MultiQCParseResult:
    """Parse a specific set of MultiQC outputs into a normalized ingest payload."""

    result = MultiQCParseResult()
    for output in outputs:
        result.outputs.append(output)
        metadata = _read_multiqc_metadata(output)
        _parse_general_stats(output, run_id, result, metadata)
        _parse_module_summary_tables(output, run_id, result, metadata)
        _parse_sources(output, run_id, result)
        _parse_versions(output, run_id, result)
        _parse_payloads(output, run_id, result, metadata)
    return result


def discover_multiqc_outputs(path: Path) -> list[MultiQCOutput]:
    """Discover MultiQC output folders from a file, run folder, or directory tree."""

    if not path.exists():
        return []

    data_dirs: set[Path] = set()
    if path.is_dir() and (path / "multiqc_general_stats.txt").exists():
        data_dirs.add(path)
    if path.is_dir():
        for candidate in path.rglob("*_multiqc_report_data"):
            if candidate.is_dir():
                data_dirs.add(candidate)
        for candidate in path.rglob("multiqc_data"):
            if (
                candidate.is_dir()
                and (candidate / "multiqc_general_stats.txt").exists()
            ):
                data_dirs.add(candidate)

    return [
        MultiQCOutput(
            root_dir=data_dir.parent,
            data_dir=data_dir,
            report_html=_find_report_html(data_dir),
        )
        for data_dir in sorted(data_dirs)
    ]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file using streaming reads."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_report_html(data_dir: Path) -> Path | None:
    parent = data_dir.parent
    stem = data_dir.name.removesuffix("_data")
    preferred = parent / f"{stem}.html"
    if preferred.exists():
        return preferred
    matches = sorted(parent.glob("*_multiqc_report.html")) + sorted(
        parent.glob("multiqc_report.html")
    )
    return matches[0] if matches else None


def _parse_general_stats(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    metadata: dict[str, Any],
) -> None:
    path = output.data_dir / "multiqc_general_stats.txt"
    if path.exists():
        _parse_metric_table(
            path,
            run_id,
            result,
            metadata,
            module_hint="general_stats",
        )


def _parse_module_summary_tables(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    metadata: dict[str, Any],
) -> None:
    for path in sorted(output.data_dir.glob("multiqc_*.txt")):
        if path.name in {
            "multiqc_general_stats.txt",
            "multiqc_sources.txt",
            "multiqc_software_versions.txt",
            "multiqc_citations.txt",
        }:
            continue
        if path.name.startswith("multiqc_") and _has_sample_column(path):
            _parse_metric_table(path, run_id, result, metadata, module_hint=path.stem)


def _parse_metric_table(
    path: Path,
    run_id: str,
    result: MultiQCParseResult,
    metadata: dict[str, Any],
    *,
    module_hint: str,
) -> None:
    rows = _read_tsv(path)
    source_hash = sha256_file(path)
    fields: dict[tuple[str, str], DataProfileField] = {}
    field_values: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        sample_id = _clean_text(row.get("Sample"))
        for column, raw_value in row.items():
            if column == "Sample":
                continue
            value = _clean_text(raw_value)
            if value is None:
                continue
            metric_id = _metric_id(module_hint, column)
            header = _general_stats_header(metadata, column)
            identity = _metric_identity(module_hint, column, header)
            data_profile_id = _metrics_profile_id(result, identity)
            display_name = _metric_display_name(module_hint, column, header)
            field_key = (data_profile_id, metric_id)
            value_num, value_text = _coerce_metric_value(value)
            if value_num is not None:
                result.sample_metric_numeric.append(
                    UnresolvedAnalyticalRecord(
                        data_profile_id=data_profile_id,
                        run_id=run_id,
                        run_sample_id=_run_sample_id(run_id, sample_id),
                        sample_id=sample_id,
                        field_id=metric_id,
                        value_type="numeric",
                        value_numeric=value_num,
                        source_file_id=str(path),
                    )
                )
            else:
                result.sample_metric_string.append(
                    UnresolvedAnalyticalRecord(
                        data_profile_id=data_profile_id,
                        run_id=run_id,
                        run_sample_id=_run_sample_id(run_id, sample_id),
                        sample_id=sample_id,
                        field_id=metric_id,
                        value_type="string",
                        value_string=value_text or "",
                        source_file_id=str(path),
                    )
                )
            field_values.setdefault(field_key, []).append(
                value_num if value_num is not None else value_text
            )
            if field_key not in fields:
                value_type = "numeric" if value_num is not None else "string"
                fields[field_key] = DataProfileField(
                    data_profile_id=data_profile_id,
                    field_id=metric_id,
                    field_role="metric",
                    entity_scope="run_sample",
                    display_name=display_name,
                    value_type=value_type,
                    unit=_metric_unit(header),
                    query_ref_json={
                        "table": "sample_metrics",
                        "field_column": "field_id",
                        "field_value": metric_id,
                        "value_column": (
                            "value_numeric"
                            if value_type == "numeric"
                            else "value_string"
                        ),
                    },
                    metadata_json={
                        "producer_tool": identity.tool,
                        "producer_module": identity.module,
                        "tool_context": identity.context,
                        "multiqc_module": module_hint,
                        "multiqc_namespace": identity.label,
                    },
                )
    for field_key, profile_field in fields.items():
        result.fields.append(
            profile_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        profile_field.value_type,
                        field_values.get(field_key, []),
                    )
                }
            )
        )
    if rows:
        payload_profile_id = _summary_table_payload_profile_id(
            result, metadata, module_hint
        )
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}",
                data_profile_id=payload_profile_id,
                run_id=run_id,
                payload_name=path.stem,
                payload_kind="multiqc_summary_table",
                storage_format="json",
                row_count=len(rows),
                source_file_id=str(path),
                metadata_json={
                    "columns": list(rows[0].keys()),
                    "rows": rows,
                    "source_hash": source_hash,
                    "module": module_hint,
                },
            )
        )


def _parse_sources(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
) -> None:
    path = output.data_dir / "multiqc_sources.txt"
    if not path.exists():
        return
    for row in _read_tsv(path):
        sample_id = _clean_text(row.get("Sample Name"))
        result.data_sources.append(
            UnresolvedAnalyticalRecord(
                run_id=run_id,
                run_sample_id=_run_sample_id(run_id, sample_id),
                sample_id=sample_id,
                tool=_clean_text(row.get("Module")),
                module=_clean_text(row.get("Section")),
                source_path=_clean_text(row.get("Source")) or "",
            )
        )


def _parse_versions(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
) -> None:
    path = output.data_dir / "multiqc_software_versions.txt"
    if not path.exists():
        return
    for row in _read_tsv(path):
        for tool, version in row.items():
            value = _clean_text(version)
            if tool == "Sample" or value is None:
                continue
            result.tool_versions.append(
                UnresolvedAnalyticalRecord(
                    run_id=run_id,
                    tool=_normalize_key(tool),
                    version=value,
                    source_file_id=str(path),
                )
            )


def _parse_payloads(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    metadata: dict[str, Any],
) -> None:
    for path in sorted(output.data_dir.glob("*.txt")):
        if not _is_payload_file(path):
            continue
        rows = _read_tsv(path)
        if not rows:
            continue
        samples = {
            value
            for row in rows
            if (value := _clean_text(row.get("Sample"))) is not None
        }
        identity = _payload_identity(path.stem, metadata)
        data_profile_id = _payload_profile_id(result, identity)
        sample_id = next(iter(samples)) if len(samples) == 1 else None
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}:{sample_id or 'all'}",
                data_profile_id=data_profile_id,
                run_id=run_id,
                run_sample_id=_run_sample_id(run_id, sample_id),
                payload_name=path.stem,
                payload_kind="multiqc_plot_table",
                storage_format="json",
                row_count=len(rows),
                source_file_id=str(path),
                metadata_json={
                    "columns": list(rows[0].keys()),
                    "rows": rows,
                    "source_hash": sha256_file(path),
                    "sample_id": sample_id,
                    "tool": identity.tool,
                    "module": identity.module,
                    "tool_context": identity.context,
                    "multiqc_namespace": identity.label,
                },
            )
        )


def _read_multiqc_metadata(output: MultiQCOutput) -> dict[str, Any]:
    path = output.data_dir / "multiqc_data.json"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _general_stats_header(
    metadata: dict[str, Any],
    column: str,
) -> dict[str, Any] | None:
    headers = metadata.get("report_general_stats_headers")
    if not isinstance(headers, dict):
        return None
    for module_headers in headers.values():
        if not isinstance(module_headers, dict):
            continue
        for metric_header in module_headers.values():
            if not isinstance(metric_header, dict):
                continue
            if column in {
                _clean_text(metric_header.get("rid")),
                _clean_text(metric_header.get("clean_rid")),
            }:
                return metric_header
    return None


def _metric_identity(
    module_hint: str,
    column: str,
    header: dict[str, Any] | None,
) -> ToolProfileIdentity:
    namespace = (
        _clean_text(header.get("namespace")) if isinstance(header, dict) else None
    )
    if namespace:
        return _identity_from_namespace(namespace, module_hint=module_hint)
    return _identity_from_metric_prefix(module_hint, column)


def _payload_identity(
    payload_name: str,
    metadata: dict[str, Any],
) -> ToolProfileIdentity:
    identity = _identity_from_metric_prefix(payload_name, "")
    if identity.tool != "unknown":
        return identity
    plot_data = metadata.get("report_plot_data")
    plot = plot_data.get(payload_name) if isinstance(plot_data, dict) else None
    if isinstance(plot, dict):
        pconfig = plot.get("pconfig")
        title = pconfig.get("title") if isinstance(pconfig, dict) else None
        if isinstance(title, str):
            return _identity_from_metric_prefix(title, "")
    return identity


def _summary_table_payload_profile_id(
    result: MultiQCParseResult,
    metadata: dict[str, Any],
    module_hint: str,
) -> str:
    if module_hint == "general_stats":
        return _multiqc_payload_profile_id(result)
    raw_data = metadata.get("report_saved_raw_data")
    module_data = raw_data.get(module_hint) if isinstance(raw_data, dict) else None
    if isinstance(module_data, dict):
        return _payload_profile_id(
            result, _identity_from_metric_prefix(module_hint, "")
        )
    return _payload_profile_id(result, _identity_from_metric_prefix(module_hint, ""))


def _metrics_profile_id(
    result: MultiQCParseResult,
    identity: ToolProfileIdentity,
) -> str:
    data_profile = tool_metrics_profile(identity.tool, identity.context)
    _register_profile(result, data_profile)
    return data_profile.data_profile_id


def _payload_profile_id(
    result: MultiQCParseResult,
    identity: ToolProfileIdentity,
) -> str:
    data_profile = tool_payload_profile(identity.tool, identity.context)
    _register_profile(result, data_profile)
    return data_profile.data_profile_id


def _multiqc_payload_profile_id(result: MultiQCParseResult) -> str:
    _register_profile(result, built_in_data_profile(MULTIQC_PAYLOAD_PROFILE))
    return MULTIQC_PAYLOAD_PROFILE


def _register_profile(
    result: MultiQCParseResult,
    data_profile: DataProfile,
) -> None:
    result.data_profiles.setdefault(data_profile.data_profile_id, data_profile)


def _identity_from_namespace(
    namespace: str,
    *,
    module_hint: str,
) -> ToolProfileIdentity:
    tool_text = namespace.strip()
    context: str | None = None
    paren = re.search(r"\(([^)]+)\)\s*$", tool_text)
    if paren:
        context = _normalize_key(paren.group(1))
        tool_text = tool_text[: paren.start()].strip()
    if ":" in tool_text:
        tool_text, context_text = tool_text.split(":", 1)
        context = _normalize_key(context_text)
    tool = _normalize_key(tool_text)
    if tool == "bbmap" and context == "bbsplit":
        tool = "bbtools"
    return ToolProfileIdentity(
        tool=tool,
        context=context,
        label=namespace,
        module=_normalize_key(module_hint),
    )


def _identity_from_metric_prefix(
    module_hint: str,
    column: str,
) -> ToolProfileIdentity:
    source = module_hint.removeprefix("multiqc_")
    if (module_hint == "general_stats" or source == "general_stats") and "-" in column:
        source = column.split("-", 1)[0]
    prefix = _normalize_key(source)
    parts = [part for part in prefix.split("_") if part]
    if not parts:
        return ToolProfileIdentity(tool="unknown", module=_normalize_key(module_hint))

    tool = parts[0]
    context: str | None = None
    if tool == "fastqc":
        context = _fastqc_context(parts[1:])
    elif tool == "bbtools" and len(parts) > 1:
        context = parts[1]
    elif tool == "bbsplit" or (
        tool == "bbmap" and len(parts) > 1 and parts[1] == "bbsplit"
    ):
        tool = "bbtools"
        context = "bbsplit"
    elif tool == "picard" and len(parts) > 1:
        context = _picard_context(parts[1:])

    return ToolProfileIdentity(
        tool=tool,
        context=context,
        label=source,
        module=_normalize_key(source),
    )


def _fastqc_context(parts: list[str]) -> str | None:
    known_contexts = {"raw", "trimmed", "filtered"}
    if len(parts) >= 2 and parts[0] == "fastqc" and parts[1] in known_contexts:
        return parts[1]
    if parts and parts[0] in known_contexts:
        return parts[0]
    return None


def _picard_context(parts: list[str]) -> str | None:
    trimmed = list(parts)
    if trimmed and trimmed[-1] == "metrics":
        trimmed.pop()
    return "_".join(trimmed) if trimmed else None


def _metric_display_name(
    module_hint: str,
    column: str,
    header: dict[str, Any] | None,
) -> str:
    title = _clean_text(header.get("title")) if isinstance(header, dict) else None
    if title:
        return title
    _, _, _, display_name = _metric_parts(module_hint, column)
    return display_name


def _metric_unit(header: dict[str, Any] | None) -> str | None:
    suffix = _clean_text(header.get("suffix")) if isinstance(header, dict) else None
    if suffix is None:
        return None
    if suffix == "M":
        return suffix
    return suffix.strip()


def _read_tsv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [
            {key: _typed_cell(value) for key, value in row.items() if key is not None}
            for row in reader
        ]


def _typed_cell(value: str | None) -> Any:
    clean = _clean_text(value)
    if clean is None:
        return None
    numeric, text = _coerce_metric_value(clean)
    return numeric if numeric is not None and text is None else clean


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _coerce_metric_value(value: str) -> tuple[float | None, str | None]:
    try:
        return float(value), None
    except ValueError:
        return None, value


def _has_sample_column(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n").split("\t")
    except OSError:
        return False
    return "Sample" in header


def _is_payload_file(path: Path) -> bool:
    name = path.name
    if name in {
        "multiqc_citations.txt",
        "multiqc_general_stats.txt",
        "multiqc_sources.txt",
        "multiqc_software_versions.txt",
    }:
        return False
    if name.startswith("multiqc_") or name == "llms-full.txt":
        return False
    stem = path.stem
    return "plot" in stem or stem.endswith("_table") or "heatmap" in stem


def _metric_id(module_hint: str, column: str) -> str:
    return f"{_normalize_key(module_hint)}.{_normalize_key(column)}"


def _metric_parts(
    module_hint: str,
    column: str,
) -> tuple[str | None, str | None, str | None, str]:
    source = module_hint.removeprefix("multiqc_")
    if "-" in column:
        prefix, display_name = column.split("-", 1)
    else:
        prefix, display_name = source, column
    prefix = prefix.removeprefix("multiqc_")
    parts = prefix.split("_")
    tool = parts[0] if parts else None
    stage = parts[1] if tool == "fastqc" and len(parts) > 1 else None
    module = prefix if prefix else source
    return (
        _normalize_key(tool) if tool else None,
        _normalize_key(module) if module else None,
        _normalize_key(stage) if stage else None,
        display_name.replace("_", " ").replace("-", " "),
    )


def _normalize_key(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "unknown"


def _run_sample_id(run_id: str, sample_id: str | None) -> str | None:
    return f"{run_id}:{sample_id}" if sample_id else None


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _field_summary(
    value_type: str, values: list[Any], *, cap: int = 100
) -> dict[str, Any]:
    present = [value for value in values if value is not None]
    summary: dict[str, Any] = {
        "count": len(values),
        "non_null_count": len(present),
        "null_count": len(values) - len(present),
    }
    if value_type == "numeric":
        numeric = sorted(
            float(value)
            for value in present
            if isinstance(value, int | float) and not isinstance(value, bool)
        )
        if numeric:
            summary.update(
                {
                    "min": numeric[0],
                    "max": numeric[-1],
                    "mean": sum(numeric) / len(numeric),
                    "median": _quantile(numeric, 0.5),
                    "q05": _quantile(numeric, 0.05),
                    "q95": _quantile(numeric, 0.95),
                }
            )
        return summary
    counts: dict[str, int] = {}
    for value in present:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    summary["distinct_count"] = len(counts)
    summary["top_values"] = [
        {"value": value, "count": count}
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[:cap]
    ]
    summary["examples"] = list(dict.fromkeys(str(value) for value in present))[:cap]
    return summary


def _quantile(values: list[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _dedupe_fields(fields: list[DataProfileField]) -> list[DataProfileField]:
    by_id: dict[tuple[str, str], DataProfileField] = {}
    for profile_field in fields:
        by_id[(profile_field.field_id, profile_field.value_type)] = profile_field
    return list(by_id.values())
