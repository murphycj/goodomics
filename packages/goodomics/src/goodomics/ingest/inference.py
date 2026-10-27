"""Low-configuration scalar, key, and semantic-shape inference for tabular data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast

from pydantic import Field

from goodomics.schemas.models import GoodomicsModel

ScalarType = Literal[
    "numeric", "integer", "string", "boolean", "categorical", "date", "datetime", "json"
]


class InferredField(GoodomicsModel):
    """One inferred tabular field with bounded evidence."""

    field_id: str
    scalar_type: ScalarType
    nullable: bool
    distinct_count: int
    sample_values: list[Any] = Field(default_factory=list)


class InferredTabularShape(GoodomicsModel):
    """Candidate shape, scalar fields, and stable row-key suggestions."""

    data_shape_id: Literal[
        "entity", "feature", "variant", "region", "series", "timeline", "records"
    ]
    confidence: float = Field(ge=0, le=1)
    candidate_keys: list[list[str]] = Field(default_factory=list)
    suggested_bindings: dict[str, Any] = Field(default_factory=dict)
    fields: list[InferredField]


def infer_tabular_shape(rows: list[dict[str, Any]]) -> InferredTabularShape:
    """Infer approved scalar types, candidate keys, and a compatible built-in shape."""

    if not rows:
        raise ValueError("Shape inference requires at least one representative row.")
    field_ids = list(dict.fromkeys(key for row in rows for key in row))
    fields = [
        _infer_field(field_id, [row.get(field_id) for row in rows])
        for field_id in field_ids
    ]
    names = {field.field_id.casefold() for field in fields}
    shape_id, confidence, bindings = _shape_candidate(names)
    candidate_keys = [
        [field.field_id]
        for field in fields
        if not field.nullable and field.distinct_count == len(rows)
    ]
    return InferredTabularShape(
        data_shape_id=cast(Any, shape_id),
        confidence=confidence,
        candidate_keys=candidate_keys,
        suggested_bindings=bindings,
        fields=fields,
    )


def split_shape_consistent_rows(
    rows: list[dict[str, Any]], *, discriminator: str
) -> dict[str, InferredTabularShape]:
    """Infer separate shape-consistent contracts while retaining producer grouping."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row.get(discriminator)
        if value is None:
            raise ValueError(f"Mixed-output discriminator is missing: {discriminator}")
        grouped.setdefault(str(value), []).append(row)
    return {key: infer_tabular_shape(group) for key, group in sorted(grouped.items())}


def _infer_field(field_id: str, values: list[Any]) -> InferredField:
    """Infer one approved scalar type from bounded representative values."""

    present = [value for value in values if value is not None]
    scalar_type: ScalarType
    if present and all(isinstance(value, bool) for value in present):
        scalar_type = "boolean"
    elif present and all(
        isinstance(value, int) and not isinstance(value, bool) for value in present
    ):
        scalar_type = "integer"
    elif present and all(
        isinstance(value, int | float) and not isinstance(value, bool)
        for value in present
    ):
        scalar_type = "numeric"
    elif present and all(isinstance(value, datetime) for value in present):
        scalar_type = "datetime"
    elif present and all(isinstance(value, date) for value in present):
        scalar_type = "date"
    elif present and all(isinstance(value, str) for value in present):
        distinct = len({str(value) for value in present})
        scalar_type = (
            "categorical"
            if distinct <= min(50, max(2, len(present) // 2))
            else "string"
        )
    else:
        scalar_type = "json"
    distinct_values = {repr(value) for value in present}
    return InferredField(
        field_id=field_id,
        scalar_type=scalar_type,
        nullable=len(present) != len(values),
        distinct_count=len(distinct_values),
        sample_values=present[:20],
    )


def _shape_candidate(names: set[str]) -> tuple[str, float, dict[str, Any]]:
    """Choose a semantic shape from recognizable logical key families."""

    if {"contig", "start", "end"} <= names or {
        "chromosome",
        "start_pos",
        "end_pos",
    } <= names:
        return "region", 0.95, {"coordinate_system": "genomic"}
    if {"variant_id", "sample_id"} <= names or {"ref", "alt", "pos"} <= names:
        return "variant", 0.9, {"entity_type": "sample"}
    if "position" in names and ("series_id" in names or "measurement_id" in names):
        return "series", 0.9, {"position_domain": "ordered", "entity_type": "sample"}
    if "subject_id" in names and (
        {"start_time", "event_type"} <= names or "event_id" in names
    ):
        return "timeline", 0.9, {"time_origin": "absolute_or_relative"}
    if "feature_id" in names and ({"sample_id", "subject_id", "run_id"} & names):
        return "feature", 0.85, {"entity_type": "sample", "feature_domain": "generic"}
    if {"sample_id", "subject_id", "run_id", "file_id"} & names:
        return (
            "entity",
            0.75,
            {
                "entity_type": next(
                    iter(
                        sorted(
                            {"sample", "subject", "run", "file"}
                            & {name.removesuffix("_id") for name in names}
                        )
                    ),
                    "sample",
                )
            },
        )
    return "records", 0.6, {"row_identity": "row_id"}
