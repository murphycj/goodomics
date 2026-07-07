"""Parsing utilities for turning MultiQC exports into Goodomics ingest records."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from goodomics.contracts.multiqc import MULTIQC_PAYLOADS
from goodomics.contracts.registry import (
    built_in_data_contract,
    built_in_data_contract_field,
)
from goodomics.contracts.tool import tool_metrics_contract, tool_payload_contract
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    DataContract,
    DataContractField,
    UnresolvedAnalyticalRecord,
)

MULTIQC_PAYLOAD_CONTRACT = MULTIQC_PAYLOADS


@dataclass(frozen=True)
class ToolContractIdentity:
    tool: str
    context: str | None = None
    label: str | None = None
    module: str | None = None

    @property
    def metrics_contract_id(self) -> str:
        return tool_metrics_contract(self.tool, self.context).data_contract_id

    @property
    def payload_contract_id(self) -> str:
        return tool_payload_contract(self.tool, self.context).data_contract_id


@dataclass(frozen=True)
class MultiQCOutput:
    """One discovered MultiQC output directory with optional HTML report."""

    root_dir: Path
    data_dir: Path
    parquet_path: Path
    report_html: Path | None


@dataclass
class MultiQCParseResult:
    """Accumulated analytical records and discovered outputs from MultiQC parsing."""

    sample_metric_numeric: list[Any] = field(default_factory=list)
    sample_metric_string: list[Any] = field(default_factory=list)
    data_contracts: dict[str, DataContract] = field(default_factory=dict)
    fields: list[DataContractField] = field(default_factory=list)
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
            sample_id = _record_value(payload, "sample_id")
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
            result_payloads=self.payloads,
            tool_versions=self.tool_versions,
            data_sources=self.data_sources,
        )

    @property
    def contract_fields(self) -> list[DataContractField]:
        return _dedupe_fields(self.fields)

    @property
    def contracts(self) -> list[DataContract]:
        return [self.data_contracts[key] for key in sorted(self.data_contracts)]


def parse_multiqc_bundle(path: Path, *, run_id: str) -> MultiQCParseResult:
    """Parse all MultiQC outputs discoverable beneath the given path."""

    outputs = discover_multiqc_outputs(path)
    if not outputs:
        raise ValueError(f"No MultiQC parquet file found under {path}")
    return parse_multiqc_outputs(outputs, run_id=run_id)


def parse_multiqc_outputs(
    outputs: list[MultiQCOutput],
    *,
    run_id: str,
) -> MultiQCParseResult:
    """Parse a specific set of MultiQC outputs into a normalized ingest payload."""

    if not outputs:
        raise ValueError("No MultiQC parquet file found")
    result = MultiQCParseResult()
    for output in outputs:
        result.outputs.append(output)
        _parse_parquet_output(output, run_id, result)
    return result


def discover_multiqc_outputs(path: Path) -> list[MultiQCOutput]:
    """Discover parquet-backed MultiQC output folders."""

    if not path.exists():
        return []

    parquet_paths: set[Path] = set()
    if path.is_file() and path.name == "multiqc.parquet":
        parquet_paths.add(path)
    elif path.is_dir() and (path / "multiqc.parquet").exists():
        parquet_paths.add(path / "multiqc.parquet")
    elif path.is_dir() and (path / "multiqc_data" / "multiqc.parquet").exists():
        parquet_paths.add(path / "multiqc_data" / "multiqc.parquet")
    elif path.is_dir():
        parquet_paths.update(path.rglob("multiqc.parquet"))

    return [
        MultiQCOutput(
            root_dir=parquet_path.parent.parent,
            data_dir=parquet_path.parent,
            parquet_path=parquet_path,
            report_html=_find_report_html(parquet_path.parent),
        )
        for parquet_path in sorted(parquet_paths)
    ]


def multiqc_upstream_run_id(report_run_id: str, sample_id: str) -> str:
    """Return the provisional upstream analysis run id inferred for a sample."""

    return f"{report_run_id}:{sample_id}:analysis"


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


def _parse_parquet_output(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
) -> None:
    rows_by_type = _read_multiqc_parquet(output.parquet_path)
    metadata_rows = rows_by_type.get("run_metadata", [])
    plot_input_rows = rows_by_type.get("plot_input", [])
    plot_row_rows = rows_by_type.get("plot_input_row", [])
    metadata = _metadata_from_parquet_rows(metadata_rows)
    _parse_parquet_general_stats(
        output,
        run_id,
        result,
        plot_row_rows,
        metadata,
    )
    _parse_parquet_plot_input_rows(output, run_id, result, plot_row_rows)
    _parse_parquet_versions(output, run_id, result, metadata_rows)
    _parse_parquet_data_sources(output, run_id, result, plot_input_rows)
    _parse_parquet_plot_payloads(output, run_id, result, plot_input_rows)


def _read_multiqc_parquet(path: Path) -> dict[str, list[dict[str, Any]]]:
    with duckdb.connect() as connection:
        cursor = connection.execute(
            """
            SELECT *
            FROM read_parquet(?)
            ORDER BY type, anchor, sample, row_sample, metric
            """,
            [str(path)],
        )
        columns = [description[0] for description in cursor.description or []]
        rows = [
            {
                column: _jsonable(value)
                for column, value in zip(columns, row, strict=True)
            }
            for row in cursor.fetchall()
        ]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_type = _clean_text(row.get("type")) or "unknown"
        by_type.setdefault(row_type, []).append(row)
    return by_type


def _metadata_from_parquet_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    row = rows[0]
    metadata: dict[str, Any] = {}
    for key in ("modules", "software_versions", "config"):
        value = row.get(key)
        if isinstance(value, str):
            metadata[key] = _json_loads(value)
    if row.get("multiqc_version") is not None:
        metadata["multiqc_version"] = row.get("multiqc_version")
    if row.get("creation_date") is not None:
        metadata["creation_date"] = row.get("creation_date")
    return metadata


def _parse_parquet_general_stats(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    general_rows = [
        row
        for row in rows
        if row.get("type") == "plot_input_row"
        and row.get("anchor") == "general_stats_table"
        and _clean_text(row.get("sample")) is not None
    ]
    source_hash = sha256_file(output.parquet_path)
    fields: dict[tuple[str, str], DataContractField] = {}
    field_values: dict[tuple[str, str], list[Any]] = {}
    for row in general_rows:
        sample_id = _clean_text(row.get("sample"))
        if sample_id is None:
            continue
        row_sample = _clean_text(row.get("row_sample")) or sample_id
        metric = _clean_text(row.get("metric")) or "unknown"
        header = _column_meta(row.get("column_meta"))
        rid = _clean_text(header.get("rid")) or _clean_text(header.get("clean_rid"))
        metric_source = rid or metric
        metric_id = _metric_id("general_stats", metric_source)
        identity = _metric_identity("general_stats", metric_source, header)
        data_contract_id = _metrics_contract_id(result, identity)
        display_name = _metric_display_name("general_stats", metric_source, header)
        field_key = (data_contract_id, metric_id)
        raw_value = row.get("val_raw")
        formatted_value = _clean_text(row.get("val_fmt"))
        upstream_run_id = multiqc_upstream_run_id(run_id, sample_id)
        source_observation_id, source_observation_label = _source_observation(
            sample_id, row_sample
        )
        source_metadata = {
            "source": "multiqc.parquet",
            "sample": sample_id,
            "row_sample": row_sample,
            "anchor": row.get("anchor"),
            "metric": metric,
            "column_meta": header,
            "val_mod": row.get("val_mod"),
            "val_fmt": formatted_value,
            "source_hash": source_hash,
        }
        if isinstance(raw_value, int | float):
            value_num = float(raw_value)
            result.sample_metric_numeric.append(
                UnresolvedAnalyticalRecord(
                    data_contract_id=data_contract_id,
                    run_id=upstream_run_id,
                    run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                    sample_id=sample_id,
                    field_id=metric_id,
                    source_file_id=str(output.parquet_path),
                    source_observation_id=source_observation_id,
                    source_observation_label=source_observation_label,
                    source_observation_metadata_json=source_metadata,
                    value_type="numeric",
                    value_numeric=value_num,
                )
            )
            field_values.setdefault(field_key, []).append(value_num)
            value_type = "numeric"
        else:
            value_text = formatted_value or ""
            result.sample_metric_string.append(
                UnresolvedAnalyticalRecord(
                    data_contract_id=data_contract_id,
                    run_id=upstream_run_id,
                    run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                    sample_id=sample_id,
                    field_id=metric_id,
                    source_file_id=str(output.parquet_path),
                    source_observation_id=source_observation_id,
                    source_observation_label=source_observation_label,
                    source_observation_metadata_json=source_metadata,
                    value_type="string",
                    value_string=value_text,
                )
            )
            field_values.setdefault(field_key, []).append(value_text)
            value_type = "string"
        if field_key not in fields:
            fields[field_key] = _metric_field(
                data_contract_id=data_contract_id,
                field_id=metric_id,
                display_name=display_name,
                value_type=value_type,
                unit=_metric_unit(header),
                identity=identity,
                module_hint="general_stats",
            )
    for field_key, contract_field in fields.items():
        result.fields.append(
            contract_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        contract_field.value_type,
                        field_values.get(field_key, []),
                    )
                }
            )
        )


def _parse_parquet_versions(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        software_versions = _json_loads(row.get("software_versions"))
        if not isinstance(software_versions, dict):
            continue
        for namespace, tools in software_versions.items():
            if not isinstance(tools, dict):
                continue
            for tool, versions in tools.items():
                version_values = versions if isinstance(versions, list) else [versions]
                for version in version_values:
                    value = _clean_text(version)
                    if value is None:
                        continue
                    result.tool_versions.append(
                        UnresolvedAnalyticalRecord(
                            run_id=run_id,
                            tool=_normalize_key(str(tool or namespace)),
                            version=value,
                            source_file_id=str(output.parquet_path),
                        )
                    )


def _parse_parquet_plot_input_rows(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows: list[dict[str, Any]],
) -> None:
    scalar_rows = [
        row
        for row in rows
        if row.get("type") == "plot_input_row"
        and row.get("anchor") != "general_stats_table"
        and "overrepresented_sequences" not in str(row.get("anchor") or "")
        and _clean_text(row.get("sample")) is not None
    ]
    source_hash = sha256_file(output.parquet_path)
    fields: dict[tuple[str, str], DataContractField] = {}
    field_values: dict[tuple[str, str], list[Any]] = {}
    for row in scalar_rows:
        source_sample = _clean_text(row.get("sample"))
        if source_sample is None:
            continue
        sample_id = _canonical_multiqc_sample(source_sample)
        row_sample = _clean_text(row.get("row_sample")) or source_sample
        row_sample = _clean_plot_series_name(row_sample)
        metric = _clean_text(row.get("metric")) or "unknown"
        anchor = _clean_text(row.get("anchor")) or "plot_input"
        header = _column_meta(row.get("column_meta"))
        rid = _clean_text(header.get("rid")) or _clean_text(header.get("clean_rid"))
        metric_source = rid or metric
        metric_id = _metric_id(anchor, metric_source)
        identity = _metric_identity(anchor, metric_source, header)
        data_contract_id = _metrics_contract_id(result, identity)
        display_name = _metric_display_name(anchor, metric_source, header)
        field_key = (data_contract_id, metric_id)
        raw_value = row.get("val_raw")
        formatted_value = _clean_text(row.get("val_fmt"))
        upstream_run_id = multiqc_upstream_run_id(run_id, sample_id)
        source_observation_id, source_observation_label = _source_observation(
            sample_id, row_sample
        )
        source_metadata = {
            "source": "multiqc.parquet",
            "sample": sample_id,
            "row_sample": row_sample,
            "anchor": anchor,
            "metric": metric,
            "column_meta": header,
            "val_mod": row.get("val_mod"),
            "val_fmt": formatted_value,
            "source_hash": source_hash,
        }
        if isinstance(raw_value, int | float):
            value_num = float(raw_value)
            result.sample_metric_numeric.append(
                UnresolvedAnalyticalRecord(
                    data_contract_id=data_contract_id,
                    run_id=upstream_run_id,
                    run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                    sample_id=sample_id,
                    field_id=metric_id,
                    source_file_id=str(output.parquet_path),
                    source_observation_id=source_observation_id,
                    source_observation_label=source_observation_label,
                    source_observation_metadata_json=source_metadata,
                    value_type="numeric",
                    value_numeric=value_num,
                )
            )
            field_values.setdefault(field_key, []).append(value_num)
            value_type = "numeric"
        else:
            value_text = formatted_value or ""
            result.sample_metric_string.append(
                UnresolvedAnalyticalRecord(
                    data_contract_id=data_contract_id,
                    run_id=upstream_run_id,
                    run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                    sample_id=sample_id,
                    field_id=metric_id,
                    source_file_id=str(output.parquet_path),
                    source_observation_id=source_observation_id,
                    source_observation_label=source_observation_label,
                    source_observation_metadata_json=source_metadata,
                    value_type="string",
                    value_string=value_text,
                )
            )
            field_values.setdefault(field_key, []).append(value_text)
            value_type = "string"
        if field_key not in fields:
            fields[field_key] = _metric_field(
                data_contract_id=data_contract_id,
                field_id=metric_id,
                display_name=display_name,
                value_type=value_type,
                unit=_metric_unit(header),
                identity=identity,
                module_hint=anchor,
            )
    for field_key, contract_field in fields.items():
        result.fields.append(
            contract_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        contract_field.value_type,
                        field_values.get(field_key, []),
                    )
                }
            )
        )


def _parse_parquet_data_sources(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        data_sources = _json_loads(row.get("data_sources"))
        if not isinstance(data_sources, dict):
            continue
        anchor = _clean_text(row.get("anchor"))
        for sample_id, sources in data_sources.items():
            if not isinstance(sample_id, str):
                continue
            source_values = sources if isinstance(sources, list) else [sources]
            for source in source_values:
                source_path = _clean_text(source)
                if source_path is None:
                    continue
                upstream_run_id = multiqc_upstream_run_id(run_id, sample_id)
                result.data_sources.append(
                    UnresolvedAnalyticalRecord(
                        run_id=upstream_run_id,
                        run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                        sample_id=sample_id,
                        tool="multiqc",
                        module=anchor,
                        source_path=source_path,
                    )
                )


def _parse_parquet_plot_payloads(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows: list[dict[str, Any]],
) -> None:
    source_hash = sha256_file(output.parquet_path)
    canonical_sample_ids = {
        _record_value(metric, "sample_id")
        for metric in result.metrics
        if isinstance(_record_value(metric, "sample_id"), str)
    }
    for row in rows:
        anchor = _clean_text(row.get("anchor"))
        plot_input = _json_loads(row.get("plot_input_data"))
        if anchor is None or not isinstance(plot_input, dict):
            continue
        flat_rows = _flatten_plot_input_rows(anchor, plot_input)
        if not flat_rows:
            continue
        _parse_flat_plot_result_payloads(
            output,
            run_id,
            result,
            anchor,
            flat_rows,
            source_hash,
            plot_input,
            canonical_sample_ids,
        )
        _parse_flat_plot_scalar_metrics(
            output,
            run_id,
            result,
            anchor,
            flat_rows,
            source_hash,
            plot_input,
        )


def _parse_flat_plot_result_payloads(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    anchor: str,
    rows: list[dict[str, Any]],
    source_hash: str,
    plot_input: dict[str, Any],
    canonical_sample_ids: set[str],
) -> None:
    series_rows = [row for row in rows if "x" in row and "y" in row]
    if not series_rows:
        return
    identity = _payload_identity_from_anchor(anchor)
    data_contract_id = (
        _payload_contract_id(result, identity)
        if identity is not None
        else _multiqc_payload_contract_id(result)
    )
    groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    for row in series_rows:
        sample_id = _clean_text(row.get("sample_id"))
        source_observation_id = _clean_text(row.get("source_observation_id"))
        if (
            sample_id is None
            or source_observation_id is None
            or sample_id not in canonical_sample_ids
        ):
            continue
        data_label = _clean_text(row.get("data_label"))
        groups.setdefault((sample_id, source_observation_id, data_label), []).append(
            row
        )

    for (sample_id, source_observation_id, data_label), group_rows in groups.items():
        upstream_run_id = multiqc_upstream_run_id(run_id, sample_id)
        source_observation_label = _clean_text(
            group_rows[0].get("source_observation_label")
        )
        x_field = _xy_series_x_field(anchor)
        y_field = _xy_series_y_field(anchor, data_label)
        field_id = _result_payload_field_id(anchor, data_label)
        schema_json = _xy_series_schema(anchor, data_label, x_field, y_field)
        result.fields.append(
            _result_payload_field(
                data_contract_id=data_contract_id,
                field_id=field_id,
                anchor=anchor,
                data_label=data_label,
                payload_kind="xy_series",
                schema_json=schema_json,
            )
        )
        data_json = [
            [row.get("x"), row.get("y")]
            for row in sorted(group_rows, key=lambda item: _sort_value(item.get("x")))
        ]
        data_label_key = _normalize_key(data_label or "value")
        source_key = source_observation_id.removeprefix("multiqc:")
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=(
                    f"{upstream_run_id}:{anchor}:{source_key}:{data_label_key}"
                ),
                data_contract_id=data_contract_id,
                run_id=upstream_run_id,
                run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                sample_id=sample_id,
                field_id=field_id,
                payload_name=field_id,
                payload_kind="xy_series",
                storage_format="inline_json",
                schema_json=schema_json,
                row_count=len(data_json),
                source_file_id=str(output.parquet_path),
                source_observation_id=source_observation_id,
                source_observation_label=source_observation_label,
                source_observation_metadata_json={
                    "source": "multiqc.parquet",
                    "sample": sample_id,
                    "row_sample": group_rows[0].get("row_sample"),
                    "anchor": anchor,
                    "plot_type": plot_input.get("plot_type"),
                    "data_label": data_label,
                    "source_hash": source_hash,
                },
                data_json=data_json,
                metadata_json={
                    "source": "multiqc.parquet",
                    "anchor": anchor,
                    "plot_type": plot_input.get("plot_type"),
                    "data_label": data_label,
                    "source_hash": source_hash,
                },
            )
        )


def _flatten_plot_input_rows(
    anchor: str,
    plot_input: dict[str, Any],
) -> list[dict[str, Any]]:
    plot_type = _clean_text(plot_input.get("plot_type")) or "plot"
    pconfig = plot_input.get("pconfig")
    data_labels = _plot_data_labels(pconfig)
    rows: list[dict[str, Any]] = []
    for dataset_index, dataset in enumerate(_plot_datasets(plot_input.get("data"))):
        data_label = (
            data_labels[dataset_index]
            if dataset_index < len(data_labels)
            else None
        )
        if isinstance(dataset, dict):
            rows.extend(_flatten_mapping_plot(anchor, plot_type, dataset, data_label))
        elif isinstance(dataset, list):
            rows.extend(_flatten_series_plot(anchor, plot_type, dataset, data_label))
    return rows


def _plot_data_labels(pconfig: Any) -> list[str | None]:
    if not isinstance(pconfig, dict):
        return []
    labels = pconfig.get("data_labels")
    if not isinstance(labels, list):
        return []
    values: list[str | None] = []
    for label in labels:
        if isinstance(label, dict):
            values.append(_clean_text(label.get("name")))
        else:
            values.append(_clean_text(label))
    return values


def _plot_datasets(data: Any) -> list[Any]:
    if not isinstance(data, list):
        return [data] if data is not None else []
    return data


def _flatten_mapping_plot(
    anchor: str,
    plot_type: str,
    dataset: dict[str, Any],
    data_label: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_sample, values in dataset.items():
        if not isinstance(values, dict):
            continue
        sample_id = _canonical_multiqc_sample(str(raw_sample))
        row_sample = _clean_plot_series_name(str(raw_sample))
        source_observation_id, source_observation_label = _source_observation(
            sample_id, row_sample
        )
        for metric, value in values.items():
            rows.append(
                {
                    "anchor": anchor,
                    "plot_type": plot_type,
                    "sample_id": sample_id,
                    "row_sample": row_sample,
                    "source_observation_id": source_observation_id,
                    "source_observation_label": source_observation_label,
                    "series_name": row_sample,
                    "data_label": data_label,
                    "metric": str(metric),
                    "value": value,
                }
            )
    return rows


def _flatten_series_plot(
    anchor: str,
    plot_type: str,
    dataset: list[Any],
    data_label: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for series in dataset:
        if not isinstance(series, dict):
            continue
        series_name = _clean_text(series.get("name"))
        if series_name is None:
            continue
        sample_id = _canonical_multiqc_sample(series_name)
        row_sample = _clean_plot_series_name(series_name)
        source_observation_id, source_observation_label = _source_observation(
            sample_id, row_sample
        )
        for pair in series.get("pairs") or []:
            if not isinstance(pair, list | tuple) or len(pair) < 2:
                continue
            rows.append(
                {
                    "anchor": anchor,
                    "plot_type": plot_type,
                    "sample_id": sample_id,
                    "row_sample": row_sample,
                    "source_observation_id": source_observation_id,
                    "source_observation_label": source_observation_label,
                    "series_name": series_name,
                    "data_label": data_label,
                    "x": pair[0],
                    "y": pair[1],
                }
            )
    return rows


def _payload_identity_from_anchor(anchor: str) -> ToolContractIdentity | None:
    tool = _tool_from_anchor(anchor)
    if tool is None:
        return None
    normalized = _normalize_key(anchor)
    context: str | None = None
    if tool == "fastqc":
        if normalized.startswith(("fqc_raw", "fastqc_raw")):
            context = "raw"
        elif normalized.startswith(("fqc_trimmed", "fastqc_trimmed")):
            context = "trimmed"
    return ToolContractIdentity(tool=tool, context=context, module=normalized)


def _result_payload_field_id(anchor: str, data_label: str | None) -> str:
    field_id = _normalize_key(anchor)
    field_id = re.sub(r"(^|_)plot($|_)", "_", field_id)
    field_id = re.sub(r"_+", "_", field_id).strip("_")
    if data_label is not None:
        field_id = f"{field_id}_{_normalize_key(data_label)}"
    return field_id


def _result_payload_field(
    *,
    data_contract_id: str,
    field_id: str,
    anchor: str,
    data_label: str | None,
    payload_kind: str,
    schema_json: dict[str, Any] | None,
) -> DataContractField:
    return DataContractField(
        data_contract_id=data_contract_id,
        field_id=field_id,
        field_role="payload",
        entity_scope="run_sample",
        display_name=_result_payload_display_name(anchor, data_label),
        value_type="json",
        query_ref_json={
            "table": "result_payloads",
            "field_column": "field_id",
            "field_value": field_id,
            "value_column": "data_json",
        },
        metadata_json={
            "producer_module": _normalize_key(anchor),
            "payload_kind": payload_kind,
            "schema_json": schema_json or {},
            "contract_field_source": "inferred_multiqc_plot_input",
        },
    )


def _result_payload_display_name(anchor: str, data_label: str | None) -> str:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        label = "Per-base sequence quality"
    elif "per_sequence_gc_content" in normalized:
        label = "Per-sequence GC content"
    elif "trimmed_sequences" in normalized:
        label = "Trimmed sequence lengths (3')"
    else:
        label = _payload_label_from_anchor(anchor)
    if data_label is None:
        return label
    return f"{label} - {data_label}"


def _payload_label_from_anchor(anchor: str) -> str:
    text = _result_payload_field_id(anchor, data_label=None)
    for prefix in ("fqc_raw_", "fqc_trimmed_", "fastqc_raw_", "fastqc_trimmed_"):
        text = text.removeprefix(prefix)
    text = text.replace("_", " ").strip()
    return text.capitalize() if text else anchor


def _xy_series_x_field(anchor: str) -> str:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "position"
    if "trimmed_sequences" in normalized:
        return "length"
    return "x"


def _xy_series_y_field(anchor: str, data_label: str | None) -> str:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "mean_quality"
    if data_label:
        return _normalize_key(data_label)
    return "value"


def _xy_series_schema(
    anchor: str,
    data_label: str | None,
    x_field: str,
    y_field: str,
) -> dict[str, Any]:
    return {
        "shape": "xy_pairs",
        "columns": [x_field, y_field],
        "x": {
            "field": x_field,
            "type": "number",
            "label": _xy_series_x_label(anchor, x_field),
            "unit": _xy_series_x_unit(anchor),
        },
        "y": {
            "field": y_field,
            "type": "number",
            "label": _xy_series_y_label(anchor, data_label),
            "unit": _xy_series_y_unit(anchor),
        },
    }


def _xy_series_x_label(anchor: str, fallback: str) -> str:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "Position in read"
    if "trimmed_sequences" in normalized:
        return "Trimmed sequence length"
    return fallback.replace("_", " ").title()


def _xy_series_x_unit(anchor: str) -> str | None:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "bp"
    return None


def _xy_series_y_label(anchor: str, data_label: str | None) -> str:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "Mean Phred quality"
    return data_label or "Value"


def _xy_series_y_unit(anchor: str) -> str | None:
    normalized = _normalize_key(anchor)
    if "per_base_sequence_quality" in normalized:
        return "phred"
    return None


def _sort_value(value: Any) -> tuple[str, Any]:
    if isinstance(value, int | float):
        return ("number", value)
    return ("string", str(value))


def _parse_flat_plot_scalar_metrics(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    anchor: str,
    rows: list[dict[str, Any]],
    source_hash: str,
    plot_input: dict[str, Any],
) -> None:
    if not rows or any("x" in row for row in rows):
        return
    tool = _tool_from_anchor(anchor)
    if tool is None:
        return
    identity = ToolContractIdentity(tool=tool, module=_normalize_key(anchor))
    data_contract_id = _metrics_contract_id(result, identity)
    fields: dict[str, DataContractField] = {}
    values_by_field: dict[str, list[Any]] = {}
    for row in rows:
        sample_id = _clean_text(row.get("sample_id"))
        metric = _clean_text(row.get("metric"))
        value = row.get("value")
        if sample_id is None or metric is None or not isinstance(value, int | float):
            continue
        metric_id = _metric_id(anchor, metric)
        display_name = _plot_metric_display_name(tool, metric)
        upstream_run_id = multiqc_upstream_run_id(run_id, sample_id)
        result.sample_metric_numeric.append(
            UnresolvedAnalyticalRecord(
                data_contract_id=data_contract_id,
                run_id=upstream_run_id,
                run_sample_id=_run_sample_id(upstream_run_id, sample_id),
                sample_id=sample_id,
                field_id=metric_id,
                source_file_id=str(output.parquet_path),
                source_observation_id=row.get("source_observation_id"),
                source_observation_label=row.get("source_observation_label"),
                source_observation_metadata_json={
                    "source": "multiqc.parquet",
                    "sample": sample_id,
                    "row_sample": row.get("row_sample"),
                    "anchor": anchor,
                    "metric": metric,
                    "plot_type": plot_input.get("plot_type"),
                    "source_hash": source_hash,
                },
                value_type="numeric",
                value_numeric=float(value),
            )
        )
        values_by_field.setdefault(metric_id, []).append(value)
        fields.setdefault(
            metric_id,
            DataContractField(
                data_contract_id=data_contract_id,
                field_id=metric_id,
                field_role="metric",
                entity_scope="run_sample",
                display_name=display_name,
                value_type="numeric",
                query_ref_json={
                    "table": "sample_metrics",
                    "field_column": "field_id",
                    "field_value": metric_id,
                    "value_column": "value_numeric",
                },
                metadata_json={
                    "producer_tool": tool,
                    "producer_module": _normalize_key(anchor),
                    "multiqc_module": anchor,
                    "contract_field_source": "inferred_plot_input",
                },
            ),
        )
    for field_id, contract_field in fields.items():
        result.fields.append(
            contract_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        contract_field.value_type,
                        values_by_field.get(field_id, []),
                    )
                }
            )
        )


def _parse_parquet_payloads(
    output: MultiQCOutput,
    run_id: str,
    result: MultiQCParseResult,
    rows_by_type: dict[str, list[dict[str, Any]]],
) -> None:
    payload_contract_id = _multiqc_payload_contract_id(result)
    source_hash = sha256_file(output.parquet_path)
    for row_type, rows in sorted(rows_by_type.items()):
        if not rows:
            continue
        columns = list(rows[0].keys())
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:multiqc_parquet:{row_type}",
                data_contract_id=payload_contract_id,
                run_id=run_id,
                run_sample_id=None,
                field_id=f"multiqc_parquet_{row_type}",
                payload_name=f"multiqc_parquet_{row_type}",
                payload_kind=f"multiqc_parquet_{row_type}",
                storage_format="json",
                schema_json={
                    "shape": "records",
                    "columns": columns,
                },
                row_count=len(rows),
                source_file_id=str(output.parquet_path),
                data_json=rows,
                metadata_json={
                    "source_hash": source_hash,
                    "source_path": str(output.parquet_path),
                    "row_type": row_type,
                },
            )
        )


def _source_observation(sample_id: str, row_sample: str) -> tuple[str, str]:
    if row_sample == sample_id:
        return "multiqc:summary", sample_id
    suffix = row_sample.removeprefix(sample_id)
    suffix = re.sub(r"^[\s_-]+", "", suffix).lower()
    suffix = re.sub(r"^val[_\s-]*", "", suffix)
    if suffix in {"1", "r1", "read1", "read_1"} or re.fullmatch(
        r"(1|r1|read1|read_1)[_\s-]*val[_\s-]*1",
        suffix,
    ):
        return "multiqc:r1", row_sample
    if suffix in {"2", "r2", "read2", "read_2"} or re.fullmatch(
        r"(2|r2|read2|read_2)[_\s-]*val[_\s-]*2",
        suffix,
    ):
        return "multiqc:r2", row_sample
    return f"multiqc:{_normalize_key(row_sample)}", row_sample


def _canonical_multiqc_sample(value: str) -> str:
    text = _clean_plot_series_name(value)
    text = re.sub(r"\s+[Rr]([12])$", "", text)
    text = re.sub(r"_val_[12]$", "", text)
    text = re.sub(r"_[12]$", "", text)
    return text


def _clean_plot_series_name(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\s+-\s+.+$", "", text)
    return text


def _tool_from_anchor(anchor: str) -> str | None:
    normalized = _normalize_key(anchor)
    if normalized.startswith("featurecounts"):
        return "featurecounts"
    if normalized.startswith("star"):
        return "star"
    if normalized.startswith("cutadapt"):
        return "cutadapt"
    if normalized.startswith("fqc") or normalized.startswith("fastqc"):
        return "fastqc"
    return None


def _plot_metric_display_name(tool: str, metric: str) -> str:
    return metric.replace("_", " ").replace("-", " ").strip()


def _column_meta(value: Any) -> dict[str, Any]:
    loaded = _json_loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _json_loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


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
    fields: dict[tuple[str, str], DataContractField] = {}
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
            data_contract_id = _metrics_contract_id(result, identity)
            display_name = _metric_display_name(module_hint, column, header)
            field_key = (data_contract_id, metric_id)
            value_num, value_text = _coerce_metric_value(value)
            if value_num is not None:
                result.sample_metric_numeric.append(
                    UnresolvedAnalyticalRecord(
                        data_contract_id=data_contract_id,
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
                        data_contract_id=data_contract_id,
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
                fields[field_key] = _metric_field(
                    data_contract_id=data_contract_id,
                    field_id=metric_id,
                    display_name=display_name,
                    value_type=value_type,
                    unit=_metric_unit(header),
                    identity=identity,
                    module_hint=module_hint,
                )
    for field_key, contract_field in fields.items():
        result.fields.append(
            contract_field.model_copy(
                update={
                    "summary_json": _field_summary(
                        contract_field.value_type,
                        field_values.get(field_key, []),
                    )
                }
            )
        )
    if rows:
        payload_contract_id = _summary_table_payload_contract_id(
            result, metadata, module_hint
        )
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}",
                data_contract_id=payload_contract_id,
                run_id=run_id,
                field_id=path.stem,
                payload_name=path.stem,
                payload_kind="multiqc_summary_table",
                storage_format="json",
                schema_json={
                    "shape": "records",
                    "columns": list(rows[0].keys()),
                },
                row_count=len(rows),
                source_file_id=str(path),
                data_json=rows,
                metadata_json={
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
        data_contract_id = _payload_contract_id(result, identity)
        sample_id = next(iter(samples)) if len(samples) == 1 else None
        result.payloads.append(
            UnresolvedAnalyticalRecord(
                payload_id=f"{run_id}:{path.stem}:{sample_id or 'all'}",
                data_contract_id=data_contract_id,
                run_id=run_id,
                run_sample_id=(
                    _run_sample_id(run_id, sample_id)
                    if sample_id is not None
                    else None
                ),
                sample_id=sample_id,
                field_id=path.stem,
                payload_name=path.stem,
                payload_kind="multiqc_plot_table",
                storage_format="json",
                schema_json={
                    "shape": "records",
                    "columns": list(rows[0].keys()),
                },
                row_count=len(rows),
                source_file_id=str(path),
                data_json=rows,
                metadata_json={
                    "source_hash": sha256_file(path),
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
) -> ToolContractIdentity:
    namespace = (
        _clean_text(header.get("namespace")) if isinstance(header, dict) else None
    )
    if namespace:
        return _identity_from_namespace(namespace, module_hint=module_hint)
    return _identity_from_metric_prefix(module_hint, column)


def _payload_identity(
    payload_name: str,
    metadata: dict[str, Any],
) -> ToolContractIdentity:
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


def _summary_table_payload_contract_id(
    result: MultiQCParseResult,
    metadata: dict[str, Any],
    module_hint: str,
) -> str:
    if module_hint == "general_stats":
        return _multiqc_payload_contract_id(result)
    raw_data = metadata.get("report_saved_raw_data")
    module_data = raw_data.get(module_hint) if isinstance(raw_data, dict) else None
    if isinstance(module_data, dict):
        return _payload_contract_id(
            result, _identity_from_metric_prefix(module_hint, "")
        )
    return _payload_contract_id(result, _identity_from_metric_prefix(module_hint, ""))


def _metrics_contract_id(
    result: MultiQCParseResult,
    identity: ToolContractIdentity,
) -> str:
    fallback = tool_metrics_contract(identity.tool, identity.context)
    data_contract = _known_contract_or_fallback(fallback)
    _register_contract(result, data_contract)
    return data_contract.data_contract_id


def _payload_contract_id(
    result: MultiQCParseResult,
    identity: ToolContractIdentity,
) -> str:
    fallback = tool_payload_contract(identity.tool, identity.context)
    data_contract = _known_contract_or_fallback(fallback)
    _register_contract(result, data_contract)
    return data_contract.data_contract_id


def _multiqc_payload_contract_id(result: MultiQCParseResult) -> str:
    _register_contract(result, built_in_data_contract(MULTIQC_PAYLOAD_CONTRACT))
    return MULTIQC_PAYLOAD_CONTRACT


def _known_contract_or_fallback(fallback: DataContract) -> DataContract:
    try:
        return built_in_data_contract(fallback.data_contract_id)
    except KeyError:
        return fallback


def _metric_field(
    *,
    data_contract_id: str,
    field_id: str,
    display_name: str,
    value_type: str,
    unit: str | None,
    identity: ToolContractIdentity,
    module_hint: str,
) -> DataContractField:
    authored = built_in_data_contract_field(data_contract_id, field_id)
    metadata = {
        "producer_tool": identity.tool,
        "producer_module": identity.module,
        "tool_context": identity.context,
        "multiqc_module": module_hint,
        "multiqc_namespace": identity.label,
    }
    if authored is not None:
        return authored.model_copy(
            update={
                "summary_json": {},
                "metadata_json": dict(authored.metadata_json) | metadata,
            }
        )
    return DataContractField(
        data_contract_id=data_contract_id,
        field_id=field_id,
        field_role="metric",
        entity_scope="run_sample",
        display_name=display_name,
        value_type="numeric" if value_type == "numeric" else "string",
        unit=unit,
        query_ref_json={
            "table": "sample_metrics",
            "field_column": "field_id",
            "field_value": field_id,
            "value_column": "value_numeric"
            if value_type == "numeric"
            else "value_string",
        },
        metadata_json=metadata | {"contract_field_source": "inferred"},
    )


def _register_contract(
    result: MultiQCParseResult,
    data_contract: DataContract,
) -> None:
    result.data_contracts.setdefault(data_contract.data_contract_id, data_contract)


def _identity_from_namespace(
    namespace: str,
    *,
    module_hint: str,
) -> ToolContractIdentity:
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
    return ToolContractIdentity(
        tool=tool,
        context=context,
        label=namespace,
        module=_normalize_key(module_hint),
    )


def _identity_from_metric_prefix(
    module_hint: str,
    column: str,
) -> ToolContractIdentity:
    source = module_hint.removeprefix("multiqc_")
    if (module_hint == "general_stats" or source == "general_stats") and "-" in column:
        source = column.split("-", 1)[0]
    prefix = _normalize_key(source)
    parts = [part for part in prefix.split("_") if part]
    if not parts:
        return ToolContractIdentity(tool="unknown", module=_normalize_key(module_hint))

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

    return ToolContractIdentity(
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
    namespace = (
        _clean_text(header.get("namespace")) if isinstance(header, dict) else None
    )
    namespace = namespace or _display_namespace_from_metric_source(column)
    if title:
        label = title
        qualifier = _metric_display_qualifier(column, title, namespace, header)
        if qualifier is not None:
            label = f"{label} ({qualifier})"
        return label
    _, _, _, display_name = _metric_parts(module_hint, column)
    return display_name


def _metric_display_qualifier(
    column: str,
    title: str,
    namespace: str | None,
    header: dict[str, Any] | None,
) -> str | None:
    if not isinstance(header, dict):
        return None
    raw = (
        _clean_text(header.get("clean_rid"))
        or _clean_text(header.get("rid"))
        or _clean_text(column)
    )
    if raw is None:
        return None
    normalized = _normalize_key(raw)
    namespace_key = _normalize_key(namespace) if namespace else None
    if namespace_key and normalized.startswith(f"{namespace_key}_"):
        normalized = normalized.removeprefix(f"{namespace_key}_")
    qualifier = normalized.replace("_", " ")
    if _normalize_key(qualifier) == _normalize_key(title):
        return None
    return qualifier or None


def _display_namespace_from_metric_source(value: str) -> str | None:
    prefix = _normalize_key(value).split("_", 1)[0]
    return {
        "star": "STAR",
        "fastqc": "FastQC",
        "featurecounts": "featureCounts",
        "cutadapt": "Cutadapt",
        "salmon": "Salmon",
    }.get(prefix)


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


def _dedupe_fields(fields: list[DataContractField]) -> list[DataContractField]:
    by_id: dict[tuple[str, str], DataContractField] = {}
    for contract_field in fields:
        by_id[(contract_field.data_contract_id, contract_field.field_id)] = (
            contract_field
        )
    return list(by_id.values())
