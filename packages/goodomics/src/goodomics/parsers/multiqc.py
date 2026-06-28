from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from goodomics.data_profiles import MULTIQC_METRICS, MULTIQC_PAYLOADS
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    MetricDefinition,
    UnresolvedAnalyticalRecord,
)

MULTIQC_METRICS_PROFILE = MULTIQC_METRICS
MULTIQC_PAYLOAD_PROFILE = MULTIQC_PAYLOADS


@dataclass(frozen=True)
class MultiQCOutput:
    root_dir: Path
    data_dir: Path
    report_html: Path | None


@dataclass
class MultiQCParseResult:
    sample_metric_numeric: list[Any] = field(default_factory=list)
    sample_metric_string: list[Any] = field(default_factory=list)
    definitions: list[MetricDefinition] = field(default_factory=list)
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
            metric_definitions=_dedupe_definitions(self.definitions),
            sample_metric_numeric=self.sample_metric_numeric,
            sample_metric_string=self.sample_metric_string,
            profile_payloads=self.payloads,
            tool_versions=self.tool_versions,
            data_sources=self.data_sources,
        )


def parse_multiqc_bundle(path: Path, *, run_id: str) -> MultiQCParseResult:
    return parse_multiqc_outputs(discover_multiqc_outputs(path), run_id=run_id)


def parse_multiqc_outputs(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
) -> MultiQCParseResult:
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
                        metric_id=metric_id,
                        value=value_num,
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
                        metric_id=metric_id,
                        value=value_text or "",
                        source_file_id=str(path),
                    )
                )
            result.definitions.append(
                MetricDefinition(
                    metric_id=metric_id,
                    namespace=tool,
                    metric_name=metric_id,
                    display_name=display_name,
                    value_type="numeric" if value_num is not None else "string",
                    unit=None,
                    producer_tool=tool,
                    producer_module=module,
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


def _dedupe_definitions(
    definitions: list[MetricDefinition],
) -> list[MetricDefinition]:
    by_id: dict[tuple[str, str], MetricDefinition] = {}
    for definition in definitions:
        by_id[(definition.metric_id, definition.value_type)] = definition
    return list(by_id.values())
