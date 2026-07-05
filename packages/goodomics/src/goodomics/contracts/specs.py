from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import resources
from typing import Any, Literal

import yaml
from pydantic import Field

from goodomics.schemas.models import (
    DataContract,
    DataContractField,
    GoodomicsModel,
    JsonObject,
)


class DataContractFieldSpec(GoodomicsModel):
    """Declarative field definition nested under a data contract spec."""

    field_id: str
    field_role: str = "metric"
    entity_scope: str | None = None
    display_name: str
    value_type: Literal["numeric", "string", "boolean", "date", "json"] = "numeric"
    unit: str | None = None
    direction: str | None = None
    description: str | None = None
    priority: str | None = None
    query_ref_json: JsonObject = Field(default_factory=dict)
    summary_json: JsonObject = Field(default_factory=dict)
    metadata_json: JsonObject = Field(default_factory=dict)

    def to_model(self, data_contract_id: str) -> DataContractField:
        return DataContractField(
            data_contract_id=data_contract_id,
            field_id=self.field_id,
            field_role=self.field_role,
            entity_scope=self.entity_scope,
            display_name=self.display_name,
            value_type=self.value_type,
            unit=self.unit,
            direction=self.direction,
            description=self.description,
            priority=self.priority,
            query_ref_json=dict(self.query_ref_json),
            summary_json=dict(self.summary_json),
            metadata_json=dict(self.metadata_json),
        )


class DataContractSpec(GoodomicsModel):
    """Declarative form of one built-in data contract."""

    data_contract_id: str
    name: str
    data_type: str
    assay: str | None = None
    producer_tool: str | None = None
    producer_tool_version: str | None = None
    producer_pipeline: str | None = None
    genome_build: str | None = None
    feature_type: str | None = None
    value_type: str | None = None
    unit: str | None = None
    entity_grain: str | None = None
    value_semantics: str | None = None
    primary_table: str | None = None
    physical_tables: list[str] = Field(default_factory=list)
    summary_json: JsonObject = Field(default_factory=dict)
    source_fingerprint: str | None = None
    query_modes: list[str] = Field(default_factory=list)
    mcp_description: str | None = None
    metadata_json: JsonObject = Field(default_factory=dict)
    fields: list[DataContractFieldSpec] = Field(default_factory=list)

    def to_model(self) -> DataContract:
        return DataContract(
            data_contract_id=self.data_contract_id,
            name=self.name,
            data_type=self.data_type,
            assay=self.assay,
            producer_tool=self.producer_tool,
            producer_tool_version=self.producer_tool_version,
            producer_pipeline=self.producer_pipeline,
            genome_build=self.genome_build,
            feature_type=self.feature_type,
            value_type=self.value_type,
            unit=self.unit,
            entity_grain=self.entity_grain,
            value_semantics=self.value_semantics,
            primary_table=self.primary_table,
            physical_tables_json={"tables": list(self.physical_tables)},
            summary_json=dict(self.summary_json),
            source_fingerprint=self.source_fingerprint,
            query_modes_json={"modes": list(self.query_modes)},
            mcp_description=self.mcp_description,
            metadata_json=dict(self.metadata_json),
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
