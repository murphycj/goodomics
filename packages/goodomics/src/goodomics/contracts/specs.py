from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import resources
from typing import Any, Literal, cast

import yaml
from pydantic import Field

from goodomics.schemas.field_references import FieldReferenceSegment
from goodomics.schemas.models import (
    DataContract,
    DataContractField,
    GoodomicsModel,
    JsonObject,
)


class DataContractFieldSpec(GoodomicsModel):
    """Declarative field definition nested under a data contract spec."""

    field_id: FieldReferenceSegment
    field_role: str = "metric"
    entity_scope: str | None = None
    display_name: str
    value_type: Literal["numeric", "string", "boolean", "date", "json"] = "numeric"
    unit: str | None = None
    direction: str | None = None
    description: str | None = None
    priority: str | None = None
    primary_table: str | None = None
    physical_tables: list[str] = Field(default_factory=list)
    query_ref_json: JsonObject = Field(default_factory=dict)
    summary_json: JsonObject = Field(default_factory=dict)
    metadata_json: JsonObject = Field(default_factory=dict)

    def to_model(self, data_contract_id: str) -> DataContractField:
        """Convert a trusted built-in spec into public field semantics."""

        purpose = {
            "identifier": "key",
            "key": "key",
            "coordinate": "coordinate",
            "annotation": "annotation",
        }.get(self.field_role, "value")
        scalar_type = {
            "call": "categorical",
            "matrix": "json",
        }.get(self.value_type, self.value_type)
        return DataContractField(
            data_contract_id=data_contract_id,
            field_id=self.field_id,
            display_name=self.display_name,
            purpose=cast(Any, purpose),
            scalar_type=cast(Any, scalar_type),
            semantic_type=str(
                self.metadata_json.get("semantic_type") or self.field_role
            ),
            unit=self.unit,
            direction=self.direction,
            description=self.description,
            priority=_priority_value(self.priority),
            domain_tags=[
                str(value)
                for value in self.metadata_json.get("domain_tags", [])
                if isinstance(value, str)
            ],
            metadata_json={
                key: value
                for key, value in self.metadata_json.items()
                if key not in {"primary_table", "physical_tables", "query_ref"}
            },
        )


class DataContractSpec(GoodomicsModel):
    """Declarative form of one built-in data contract."""

    data_contract_id: FieldReferenceSegment
    name: str
    data_type: str
    producer_tool: str | None = None
    producer_pipeline: str | None = None
    feature_type: str | None = None
    value_type: str | None = None
    unit: str | None = None
    entity_grain: str | None = None
    value_semantics: str | None = None
    summary_json: JsonObject = Field(default_factory=dict)
    source_fingerprint: str | None = None
    query_modes: list[str] = Field(default_factory=list)
    description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)
    fields: list[DataContractFieldSpec] = Field(default_factory=list)

    def to_model(self) -> DataContract:
        """Convert a trusted source spec into dataset-level v2 semantics."""

        shape_id = _shape_id_for_data_type(self.data_type)
        bindings: JsonObject = {
            "entity_type": _public_entity_grain(self.entity_grain),
            "observation_kind": self.data_type,
        }
        if self.feature_type:
            bindings["feature_domain"] = self.feature_type
        if shape_id == "region":
            bindings["coordinate_system"] = str(
                self.metadata_json.get("coordinate_system") or "genomic"
            )
        if shape_id == "series":
            bindings["position_domain"] = str(
                self.metadata_json.get("position_domain") or "ordered"
            )
        if shape_id == "timeline":
            bindings["time_origin"] = str(
                self.metadata_json.get("time_origin") or "absolute_or_relative"
            )
        if shape_id == "records":
            bindings["row_identity"] = str(
                self.metadata_json.get("row_identity") or "row_id"
            )
        return DataContract(
            data_contract_id=self.data_contract_id,
            name=self.name,
            data_shape_id=shape_id,
            data_shape_version=1,
            shape_bindings_json={
                key: value for key, value in bindings.items() if value
            },
            search_tags=list(
                dict.fromkeys(
                    [
                        self.data_type,
                        *self.query_modes,
                        *([self.feature_type] if self.feature_type is not None else []),
                    ]
                )
            ),
            description=self.description,
            metadata_json={
                **self.metadata_json,
                "producer_families": [
                    value
                    for value in (self.producer_tool, self.producer_pipeline)
                    if value
                ],
            },
        )

    def field_models(self) -> list[DataContractField]:
        return [field.to_model(self.data_contract_id) for field in self.fields]


class DataContractSpecFile(GoodomicsModel):
    """One YAML file containing metadata plus one or more data contracts."""

    source: JsonObject = Field(default_factory=dict)
    contracts: list[DataContractSpec]


def data_contracts_from_specs(
    spec_files: Iterable[DataContractSpecFile],
) -> list[DataContract]:
    contracts: list[DataContract] = []
    seen: set[str] = set()
    for spec_file in spec_files:
        for spec in spec_file.contracts:
            if spec.data_contract_id in seen:
                raise ValueError(f"Duplicate data_contract_id: {spec.data_contract_id}")
            seen.add(spec.data_contract_id)
            contracts.append(spec.to_model())
    return contracts


def data_contract_fields_from_specs(
    spec_files: Iterable[DataContractSpecFile],
) -> list[DataContractField]:
    fields: list[DataContractField] = []
    seen: set[tuple[str, str]] = set()
    for spec_file in spec_files:
        for contract_spec in spec_file.contracts:
            for field_spec in contract_spec.fields:
                field_key = (contract_spec.data_contract_id, field_spec.field_id)
                if field_key in seen:
                    contract_id, field_id = field_key
                    raise ValueError(
                        "Duplicate data contract field: "
                        f"data_contract_id={contract_id!r}, field_id={field_id!r}"
                    )
                seen.add(field_key)
                fields.append(field_spec.to_model(contract_spec.data_contract_id))
    return fields


def load_data_contract_spec_file(data: Mapping[str, Any]) -> DataContractSpecFile:
    return DataContractSpecFile.model_validate(data)


def load_package_data_contract_specs() -> list[DataContractSpecFile]:
    base = resources.files("goodomics.contracts")
    spec_files: list[DataContractSpecFile] = []
    for subdir in ("tools", "sources"):
        root = base.joinpath(subdir)
        if not root.is_dir():
            continue
        for resource in sorted(root.iterdir(), key=lambda item: item.name):
            if resource.name.endswith((".yaml", ".yml")):
                with resource.open("r", encoding="utf-8") as handle:
                    loaded = yaml.safe_load(handle) or {}
                if not isinstance(loaded, Mapping):
                    raise ValueError(f"Contract spec must be a mapping: {resource}")
                spec_files.append(load_data_contract_spec_file(loaded))

    data_contracts_from_specs(spec_files)
    data_contract_fields_from_specs(spec_files)
    return spec_files


def _shape_id_for_data_type(data_type: str) -> str:
    """Map trusted legacy source descriptors onto one built-in semantic shape."""

    if data_type in {"feature_matrix", "feature_calls"}:
        return "feature"
    if data_type in {"small_variants", "structural_variants"}:
        return "variant"
    if data_type in {"copy_number_segments", "interval_values"}:
        return "region"
    if data_type in {"series", "ordered_series"}:
        return "series"
    if data_type in {"timeline", "timeline_events"}:
        return "timeline"
    if data_type in {"records", "record_table"}:
        return "records"
    if data_type in {"result_payload", "structured_result"}:
        return "structured"
    return "entity"


def _public_entity_grain(value: str | None) -> str:
    """Normalize internal run-sample storage grain to the public sample identity."""

    return "sample" if value in {None, "run_sample"} else str(value)


def _priority_value(value: str | None) -> int | None:
    """Convert trusted textual priorities into a stable numeric ordering hint."""

    if value is None:
        return None
    if value.isdigit():
        return int(value)
    return {"high": 100, "medium": 50, "low": 10}.get(value.lower())
