"""Built-in semantic shapes and the trusted storage-adapter registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from goodomics.schemas.models import (
    DataContract,
    DataContractField,
    DataShape,
    DataShapeVersion,
)


@dataclass(frozen=True)
class LogicalRelation:
    """Private adapter-owned analytical relation description."""

    table: str
    identity_columns: tuple[str, ...]
    value_column: str | None = None
    field_column: str | None = None


class ShapeAdapter(Protocol):
    """Trusted implementation of storage behavior for a semantic shape."""

    @property
    def key(self) -> str:
        """Return the stable registered adapter key."""

        raise NotImplementedError

    def validate_definition(self, definition: Mapping[str, Any]) -> list[str]:
        """Return validation errors for a declarative shape definition."""

        raise NotImplementedError

    def validate_contract(self, contract: DataContract) -> list[str]:
        """Return validation errors for contract bindings."""

        raise NotImplementedError

    def capabilities(self, contract: DataContract) -> frozenset[str]:
        """Return logical operations supported by this contract."""

        raise NotImplementedError

    def relation(
        self, contract: DataContract, field: DataContractField | None = None
    ) -> LogicalRelation:
        """Return the private canonical relation used by query runners."""

        raise NotImplementedError


@dataclass(frozen=True)
class CanonicalShapeAdapter:
    """Adapter for an existing canonical DuckDB analytical table."""

    key: str
    table: str
    identities: tuple[str, ...]
    operations: frozenset[str]
    value_column: str | None = None
    field_column: str | None = None
    required_bindings: tuple[str, ...] = ()

    def validate_definition(self, definition: Mapping[str, Any]) -> list[str]:
        """Validate required logical keys without accepting physical routing."""

        forbidden = {"table", "column", "sql", "python_path", "primary_table"}
        present = forbidden.intersection(definition)
        return [
            f"Shape definitions cannot contain physical key {key!r}."
            for key in sorted(present)
        ]

    def validate_contract(self, contract: DataContract) -> list[str]:
        """Validate adapter-required semantic bindings."""

        return [
            f"Missing required shape binding {binding!r}."
            for binding in self.required_bindings
            if not contract.shape_bindings_json.get(binding)
        ]

    def capabilities(self, contract: DataContract) -> frozenset[str]:
        """Return the adapter's stable operation set."""

        del contract
        return self.operations

    def relation(
        self, contract: DataContract, field: DataContractField | None = None
    ) -> LogicalRelation:
        """Resolve the private relation while keeping routing out of metadata."""

        del contract, field
        return LogicalRelation(
            table=self.table,
            identity_columns=self.identities,
            value_column=self.value_column,
            field_column=self.field_column,
        )


@dataclass(frozen=True)
class RoutedShapeAdapter:
    """Trusted adapter dispatching canonical relations by semantic observation kind."""

    key: str
    relations: Mapping[str, LogicalRelation]
    operations: frozenset[str]
    required_bindings: tuple[str, ...] = ()

    def validate_definition(self, definition: Mapping[str, Any]) -> list[str]:
        """Reject physical routing in declarative shape definitions."""

        forbidden = {"table", "column", "sql", "python_path", "primary_table"}
        return [
            f"Shape definitions cannot contain physical key {key!r}."
            for key in sorted(forbidden.intersection(definition))
        ]

    def validate_contract(self, contract: DataContract) -> list[str]:
        """Require semantic bindings and a trusted supported observation kind."""

        errors = [
            f"Missing required shape binding {binding!r}."
            for binding in self.required_bindings
            if not contract.shape_bindings_json.get(binding)
        ]
        observation_kind = str(
            contract.shape_bindings_json.get("observation_kind") or ""
        )
        if observation_kind not in self.relations:
            errors.append(f"Unsupported observation kind {observation_kind!r}.")
        return errors

    def capabilities(self, contract: DataContract) -> frozenset[str]:
        """Return operations when the contract resolves to a trusted relation."""

        return frozenset() if self.validate_contract(contract) else self.operations

    def relation(
        self, contract: DataContract, field: DataContractField | None = None
    ) -> LogicalRelation:
        """Resolve a private canonical relation from semantic bindings."""

        del field
        observation_kind = str(
            contract.shape_bindings_json.get("observation_kind") or ""
        )
        try:
            return self.relations[observation_kind]
        except KeyError as error:
            raise ValueError(
                f"Unsupported {self.key} observation kind: {observation_kind!r}"
            ) from error


class ShapeAdapterRegistry:
    """Registry of trusted code adapters keyed by published shape versions."""

    def __init__(self, adapters: Iterable[ShapeAdapter] = ()) -> None:
        """Create a registry and reject duplicate keys."""

        self._adapters: dict[str, ShapeAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ShapeAdapter) -> None:
        """Register one trusted adapter under a unique key."""

        if adapter.key in self._adapters:
            raise ValueError(f"Shape adapter already registered: {adapter.key}")
        self._adapters[adapter.key] = adapter

    def get(self, key: str) -> ShapeAdapter:
        """Return a registered adapter or raise a precise lookup error."""

        try:
            return self._adapters[key]
        except KeyError as error:
            raise KeyError(f"Unknown shape adapter: {key}") from error

    def keys(self) -> tuple[str, ...]:
        """Return registered keys in deterministic order."""

        return tuple(sorted(self._adapters))


_SHAPE_ROWS = (
    (
        "entity",
        "Entity data",
        "Values attached to subjects, samples, runs, processed samples, or files.",
    ),
    (
        "feature",
        "Feature data",
        "Values or calls for an entity and a biological or analytical feature.",
    ),
    (
        "variant",
        "Variant data",
        "Variant identity, annotations, and entity-level calls.",
    ),
    ("region", "Region data", "Values or events over genomic coordinates."),
    ("series", "Series data", "Ordered points over position, cycle, depth, or time."),
    ("timeline", "Timeline data", "Dated or relative-time subject events."),
    (
        "records",
        "Record table",
        "Managed typed rows with stable application-owned identity.",
    ),
    (
        "structured",
        "Structured result",
        "Opaque or partially queryable result payloads.",
    ),
)


def built_in_data_shapes() -> tuple[DataShape, ...]:
    """Return the eight stable built-in shape identities."""

    return tuple(
        DataShape(
            data_shape_id=shape_id, built_in=True, name=name, description=description
        )
        for shape_id, name, description in _SHAPE_ROWS
    )


def built_in_data_shape_versions() -> tuple[DataShapeVersion, ...]:
    """Return immutable version-one definitions for all built-in shapes."""

    definitions: dict[str, dict[str, Any]] = {
        "entity": {
            "logical_keys": ["entity"],
            "cardinality": "one_or_many_values_per_entity",
            "required_bindings": ["entity_type"],
        },
        "feature": {
            "logical_keys": ["entity", "feature"],
            "cardinality": "one_value_or_call_per_entity_feature",
            "required_bindings": ["entity_type", "feature_domain"],
        },
        "variant": {
            "logical_keys": ["variant", "entity"],
            "cardinality": "one_or_many_calls_per_variant_entity",
            "required_bindings": ["entity_type"],
        },
        "region": {
            "logical_keys": ["entity", "coordinate"],
            "cardinality": "one_or_many_regions_per_entity",
            "required_bindings": ["coordinate_system"],
        },
        "series": {
            "logical_keys": ["entity", "series", "position"],
            "cardinality": "ordered_points",
            "required_bindings": ["position_domain"],
        },
        "timeline": {
            "logical_keys": ["subject", "event", "time"],
            "cardinality": "dated_events",
            "required_bindings": ["time_origin"],
        },
        "records": {
            "logical_keys": ["row"],
            "cardinality": "typed_rows",
            "required_bindings": ["row_identity"],
        },
        "structured": {
            "logical_keys": ["result"],
            "cardinality": "opaque_payload",
            "required_bindings": [],
        },
    }
    return tuple(
        DataShapeVersion(
            data_shape_id=shape_id,
            version=1,
            status="published",
            definition_json={
                **definitions[shape_id],
                "field_purposes": ["key", "value", "coordinate", "annotation"],
                "scalar_types": [
                    "numeric",
                    "integer",
                    "string",
                    "boolean",
                    "categorical",
                    "date",
                    "datetime",
                    "json",
                ],
            },
            adapter_key=shape_id,
        )
        for shape_id, _, _ in _SHAPE_ROWS
    )


BUILT_IN_ADAPTERS = ShapeAdapterRegistry(
    (
        RoutedShapeAdapter(
            "entity",
            {
                "entity_attributes": LogicalRelation(
                    "entity_attributes", ("entity_id",), "value_numeric", "field_id"
                ),
                "generic_metrics": LogicalRelation(
                    "sample_metrics",
                    ("sample_id", "run_id"),
                    "value_numeric",
                    "field_id",
                ),
                "tool_results": LogicalRelation(
                    "sample_metrics",
                    ("sample_id", "run_id"),
                    "value_numeric",
                    "field_id",
                ),
            },
            frozenset({"rows", "summary", "relationship", "distribution"}),
            ("entity_type",),
        ),
        CanonicalShapeAdapter(
            "feature",
            "feature_value_numeric",
            ("sample_id", "feature_id"),
            frozenset(
                {
                    "rows",
                    "summary",
                    "relationship",
                    "distribution",
                    "matrix",
                    "alteration_matrix",
                    "association",
                }
            ),
            "value",
            required_bindings=("entity_type", "feature_domain"),
        ),
        CanonicalShapeAdapter(
            "variant",
            "small_variants",
            ("sample_id", "variant_id"),
            frozenset(
                {
                    "rows",
                    "summary",
                    "alteration_matrix",
                    "variant_position",
                    "association",
                }
            ),
            required_bindings=("entity_type",),
        ),
        CanonicalShapeAdapter(
            "region",
            "copy_number_segments",
            ("sample_id", "chromosome", "start_pos", "end_pos"),
            frozenset({"rows", "summary", "genome_profile"}),
            "segment_mean",
            required_bindings=("coordinate_system",),
        ),
        CanonicalShapeAdapter(
            "series",
            "series_points",
            ("sample_id", "series_id", "position"),
            frozenset({"rows", "series"}),
            "value",
            required_bindings=("position_domain",),
        ),
        CanonicalShapeAdapter(
            "timeline",
            "timeline_events",
            ("subject_id", "event_id"),
            frozenset({"rows", "timeline"}),
            required_bindings=("time_origin",),
        ),
        CanonicalShapeAdapter(
            "records",
            "managed_record_values",
            ("row_id",),
            frozenset({"rows", "summary", "relationship", "distribution", "matrix"}),
        ),
        CanonicalShapeAdapter(
            "structured", "result_payloads", ("run_id",), frozenset({"rows"})
        ),
    )
)


def shape_version(shape_id: str, version: int = 1) -> DataShapeVersion:
    """Return one built-in published shape version."""

    for candidate in built_in_data_shape_versions():
        if candidate.data_shape_id == shape_id and candidate.version == version:
            return candidate
    raise KeyError(f"Unknown built-in shape version: {shape_id}@{version}")
