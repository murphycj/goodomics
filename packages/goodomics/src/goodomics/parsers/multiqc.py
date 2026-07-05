"""Parsing utilities for turning MultiQC exports into Goodomics ingest records."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goodomics.profiles.multiqc import MULTIQC_METRICS, MULTIQC_PAYLOADS
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataProfileField,
    UnresolvedAnalyticalRecord,
)

MULTIQC_METRICS_PROFILE = MULTIQC_METRICS
MULTIQC_PAYLOAD_PROFILE = MULTIQC_PAYLOADS


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
        _parse_general_stats(output, run_id, result)
        _parse_module_summary_tables(output, run_id, result)
        _parse_sources(output, run_id, result)
        _parse_versions(output, run_id, result)
        _parse_payloads(output, run_id, result)
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
) -> None:
    path = output.data_dir / "multiqc_general_stats.txt"
    if path.exists():
        _parse_metric_table(path, run_id, result, module_hint="general_stats")


def _parse_module_summary_tables(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
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
            _parse_metric_table(path, run_id, result, module_hint=path.stem)


def _parse_metric_table(
    path: Path,
    run_id: str,
    result: MultiQCParseResult,
    *,
    module_hint: str,
) -> None:
    rows = _read_tsv(path)
    source_hash = sha256_file(path)
    fields: dict[str, DataProfileField] = {}
    field_values: dict[str, list[Any]] = {}
    for row in rows:
        sample_id = _clean_text(row.get("Sample"))
        for column, raw_value in row.items():
            if column == "Sample":
                continue
            value = _clean_text(raw_value)
            if value is None:
                continue
            metric_id = _metric_id(module_hint, column)
            tool, module, _, display_name = _metric_parts(module_hint, column)
            value_num, value_text = _coerce_metric_value(value)
            if value_num is not None:
                result.sample_metric_numeric.append(
                    UnresolvedAnalyticalRecord(
                        data_profile_id=MULTIQC_METRICS_PROFILE,
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
                        data_profile_id=MULTIQC_METRICS_PROFILE,
                        run_id=run_id,
                        run_sample_id=_run_sample_id(run_id, sample_id),
                        sample_id=sample_id,
                        field_id=metric_id,
                        value_type="string",
                        value_string=value_text or "",
                        source_file_id=str(path),
                    )
                )
            field_values.setdefault(metric_id, []).append(
                value_num if value_num is not None else value_text
            )
            if metric_id not in fields:
                value_type = "numeric" if value_num is not None else "string"
                fields[metric_id] = DataProfileField(
                    data_profile_id=MULTIQC_METRICS_PROFILE,
                    field_id=metric_id,
                    field_role="metric",
                    entity_scope="run_sample",
                    display_name=display_name,
                    value_type=value_type,
                    unit=None,
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
                    metadata_json={"producer_tool": tool, "producer_module": module},
                )
    for metric_id, profile_field in fields.items():
        result.fields.append(
            profile_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        profile_field.value_type,
                        field_values.get(metric_id, []),
                    )
                }
            )
        )
    if rows:
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}",
                data_profile_id=MULTIQC_PAYLOAD_PROFILE,
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
        tool, module, _, _ = _metric_parts(path.stem, "")
        sample_id = next(iter(samples)) if len(samples) == 1 else None
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}:{sample_id or 'all'}",
                data_profile_id=MULTIQC_PAYLOAD_PROFILE,
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
                    "tool": tool,
                    "module": module,
                },
            )
        )


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
