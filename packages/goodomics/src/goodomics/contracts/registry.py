from __future__ import annotations

from functools import lru_cache

from goodomics.contracts.specs import (
    data_contract_fields_from_specs,
    data_contracts_from_specs,
    load_package_data_contract_specs,
)
from goodomics.schemas.models import DataContract, DataContractField


@lru_cache
def built_in_contracts() -> dict[str, DataContract]:
    contracts = data_contracts_from_specs(load_package_data_contract_specs())
    return {contract.data_contract_id: contract for contract in contracts}


def built_in_data_contract(data_contract_id: str) -> DataContract:
    return built_in_contracts()[data_contract_id]


def all_built_in_data_contracts() -> list[DataContract]:
    return sorted(
        built_in_contracts().values(), key=lambda contract: contract.data_contract_id
    )


@lru_cache
def built_in_data_contract_fields() -> tuple[DataContractField, ...]:
    return tuple(data_contract_fields_from_specs(load_package_data_contract_specs()))


@lru_cache
def built_in_data_contract_fields_by_contract() -> dict[
    str, tuple[DataContractField, ...]
]:
    grouped: dict[str, list[DataContractField]] = {}
    for field in built_in_data_contract_fields():
        grouped.setdefault(field.data_contract_id, []).append(field)
    return {
        contract_id: tuple(sorted(fields, key=lambda field: field.field_id))
        for contract_id, fields in grouped.items()
    }


def built_in_data_contract_field(
    data_contract_id: str,
    field_id: str,
) -> DataContractField | None:
    for field in built_in_data_contract_fields_by_contract().get(data_contract_id, ()):
        if field.field_id == field_id:
            return field
    return None
