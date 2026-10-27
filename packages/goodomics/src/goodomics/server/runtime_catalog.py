"""Request-scoped semantic catalog shared by REST, MCP, AI, and the builder."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.schemas.field_references import contract_field_reference
from goodomics.schemas.models import DataContract
from goodomics.semantic import BUILT_IN_ADAPTERS
from goodomics.server.insight_capabilities import metadata_fields
from goodomics.storage.sqlalchemy import (
    DataContractFieldProfileRecord,
    DataContractFieldRecord,
    DataContractProfileRecord,
    DataContractRecord,
    DataShapeRecord,
    DataShapeVersionRecord,
    ProjectRecord,
    RunContractRecord,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class CatalogDataset:
    """Resolved project-visible dataset and its published shape version."""

    contract: DataContractRecord
    shape: DataShapeRecord
    shape_version: DataShapeVersionRecord
    fields: tuple[DataContractFieldRecord, ...]


class RuntimeCatalog:
    """Permission-filtered request-local semantic discovery service."""

    def __init__(
        self,
        session: AsyncSession,
        project_id: str,
        *,
        visible_contract_ids: Iterable[str] | None = None,
    ) -> None:
        """Create a catalog with request-level memoization only."""

        self._session = session
        self.project_id = project_id
        self._visible_contract_ids = (
            frozenset(visible_contract_ids)
            if visible_contract_ids is not None
            else None
        )
        self._memo: dict[str, Any] = {}

    async def list_datasets(
        self, *, search: str | None = None, limit: int = 50, offset: int = 0
    ) -> JsonObject:
        """List bounded project-visible datasets without physical routing metadata."""

        datasets = await self._datasets()
        term = (search or "").strip().casefold()
        if term:
            datasets = [
                item
                for item in datasets
                if term in item.contract.data_contract_id.casefold()
                or term in item.contract.name.casefold()
                or term in (item.contract.description or "").casefold()
                or any(
                    term in value.casefold() for value in item.contract.search_tags_json
                )
            ]
        bounded = max(1, min(limit, 100))
        page = datasets[max(offset, 0) : max(offset, 0) + bounded]
        return {
            "items": [
                self._dataset_payload(item, include_fields=False) for item in page
            ],
            "total": len(datasets),
            "limit": bounded,
            "offset": max(offset, 0),
            "source_fingerprint": await self.source_fingerprint(),
        }

    async def describe_dataset(self, data_contract_id: str) -> JsonObject | None:
        """Describe one dataset, its fields, operations, profile, and occurrences."""

        dataset = await self._dataset(data_contract_id)
        if dataset is None:
            return None
        payload = self._dataset_payload(dataset, include_fields=True)
        payload["profile"] = await self.dataset_profile(data_contract_id)
        payload["occurrences"] = await self._occurrences(dataset.contract)
        payload["joins"] = await self.find_joins(data_contract_id)
        return payload

    async def search_fields(
        self,
        *,
        search: str | None = None,
        scalar_types: Iterable[str] = (),
        purposes: Iterable[str] = (),
        query_kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> JsonObject:
        """Search contract and approved metadata fields by semantic capability."""

        term = (search or "").strip().casefold()
        scalar_filter = frozenset(scalar_types)
        purpose_filter = frozenset(purposes)
        items: list[JsonObject] = []
        for dataset in await self._datasets():
            operations = self._operations(dataset)
            if query_kind is not None and query_kind not in operations:
                continue
            for field in dataset.fields:
                canonical = contract_field_reference(
                    dataset.contract.data_contract_id, field.field_id
                )
                haystack = " ".join(
                    [
                        canonical,
                        field.display_name,
                        field.semantic_type or "",
                        *field.domain_tags_json,
                    ]
                ).casefold()
                if term and term not in haystack:
                    continue
                if scalar_filter and field.scalar_type not in scalar_filter:
                    continue
                if purpose_filter and field.purpose not in purpose_filter:
                    continue
                items.append(self._field_payload(dataset, field))
        for field in metadata_fields():
            if query_kind is not None and query_kind not in {
                "rows",
                "summary",
                "relationship",
                "distribution",
                "series",
            }:
                continue
            if scalar_filter and str(field["value_type"]) not in scalar_filter:
                continue
            if purpose_filter and "annotation" not in purpose_filter:
                continue
            haystack = f"{field['field']} {field['label']}".casefold()
            if term and term not in haystack:
                continue
            items.append(
                {
                    "field": field["field"],
                    "display_name": field["label"],
                    "purpose": "annotation",
                    "scalar_type": field["value_type"],
                    "semantic_type": "metadata",
                    "unit": None,
                    "direction": None,
                    "domain_tags": [str(field["entity"])],
                    "query_families": [
                        "rows",
                        "summary",
                        "relationship",
                        "distribution",
                        "series",
                    ],
                    "source": "metadata",
                }
            )
        items.sort(
            key=lambda item: (str(item["display_name"]).casefold(), str(item["field"]))
        )
        bounded = max(1, min(limit, 200))
        start = max(offset, 0)
        return {
            "items": items[start : start + bounded],
            "total": len(items),
            "limit": bounded,
            "offset": start,
            "source_fingerprint": await self.source_fingerprint(),
        }

    async def sampled_values(
        self, field_reference: str, *, limit: int = 20
    ) -> JsonObject:
        """Return bounded categorical values from an optional disposable profile."""

        contract_id, separator, field_id = field_reference.partition("/")
        if not separator:
            return {"field": field_reference, "values": [], "profiled": False}
        dataset = await self._dataset(contract_id)
        if dataset is None:
            return {"field": field_reference, "values": [], "profiled": False}
        field = next(
            (item for item in dataset.fields if item.field_id == field_id), None
        )
        if field is None or field.id is None:
            return {"field": field_reference, "values": [], "profiled": False}
        project = await self._project()
        rows = (
            await self._session.exec(
                select(DataContractFieldProfileRecord).where(
                    DataContractFieldProfileRecord.project_id == project.id,
                    DataContractFieldProfileRecord.data_contract_field_id == field.id,
                )
            )
        ).all()
        profile = rows[0] if rows else None
        raw_values = (
            profile.top_values_json.get("values", []) if profile is not None else []
        )
        return {
            "field": field_reference,
            "values": list(raw_values)[: max(1, min(limit, 100))],
            "profiled": profile is not None,
            "source_fingerprint": (
                profile.source_fingerprint if profile is not None else None
            ),
        }

    async def field_profile(self, field_reference: str) -> JsonObject | None:
        """Return one minimal field profile without reading authoritative rows."""

        values = await self.sampled_values(field_reference, limit=20)
        contract_id, separator, field_id = field_reference.partition("/")
        if not separator:
            return None
        dataset = await self._dataset(contract_id)
        if dataset is None:
            return None
        field = next(
            (item for item in dataset.fields if item.field_id == field_id), None
        )
        if field is None or field.id is None:
            return None
        project = await self._project()
        profile = (
            await self._session.exec(
                select(DataContractFieldProfileRecord).where(
                    DataContractFieldProfileRecord.project_id == project.id,
                    DataContractFieldProfileRecord.data_contract_field_id == field.id,
                )
            )
        ).first()
        if profile is None:
            return None
        return {
            "field": field_reference,
            "source_fingerprint": profile.source_fingerprint,
            "profiled_at": profile.profiled_at.isoformat(),
            "missing_value_count": profile.missing_value_count,
            "numeric_minimum": profile.numeric_minimum,
            "numeric_maximum": profile.numeric_maximum,
            "categorical_distinct_count": profile.categorical_distinct_count,
            "top_values": values["values"],
        }

    async def dataset_profile(self, data_contract_id: str) -> JsonObject | None:
        """Return a current minimal dataset profile when one is available."""

        dataset = await self._dataset(data_contract_id)
        if dataset is None or dataset.contract.id is None:
            return None
        project = await self._project()
        rows = (
            await self._session.exec(
                select(DataContractProfileRecord).where(
                    DataContractProfileRecord.project_id == project.id,
                    DataContractProfileRecord.data_contract_id == dataset.contract.id,
                )
            )
        ).all()
        if not rows:
            return None
        profile = rows[0]
        return {
            "source_fingerprint": profile.source_fingerprint,
            "profiled_at": profile.profiled_at.isoformat(),
            "row_count": profile.row_count,
            "distinct_entity_count": profile.distinct_entity_count,
            "feature_set_coverage": profile.feature_set_coverage_json,
        }

    async def find_joins(self, data_contract_id: str | None = None) -> list[JsonObject]:
        """Return permission-filtered joins by logical identity only."""

        datasets = await self._datasets()
        source = await self._dataset(data_contract_id) if data_contract_id else None
        joins: list[JsonObject] = []
        for left_index, left in enumerate(datasets):
            if source is not None and left.contract.id != source.contract.id:
                continue
            left_identities = self._identities(left)
            for right in datasets[left_index + 1 :] if source is None else datasets:
                if left.contract.id == right.contract.id:
                    continue
                shared = sorted(left_identities.intersection(self._identities(right)))
                if not shared:
                    continue
                joins.append(
                    {
                        "left_contract_id": left.contract.data_contract_id,
                        "right_contract_id": right.contract.data_contract_id,
                        "identities": shared,
                    }
                )
        return joins

    async def supported_query_families(self) -> JsonObject:
        """Return query families, compatible views, and provider requirements."""

        families = sorted(
            {
                operation
                for dataset in await self._datasets()
                for operation in self._operations(dataset)
            }
            | {"survival"}
        )
        from goodomics.schemas.insights import VIEWS_BY_QUERY_KIND

        return {
            "query_families": [
                {
                    "kind": family,
                    "views": sorted(VIEWS_BY_QUERY_KIND[family]),
                    "provider_required": family == "survival",
                }
                for family in families
            ],
            "source_fingerprint": await self.source_fingerprint(),
        }

    async def source_fingerprint(self) -> str:
        """Return a stable fingerprint for this request's catalog sources."""

        cached = self._memo.get("fingerprint")
        if isinstance(cached, str):
            return cached
        payload = [
            {
                "contract": item.contract.data_contract_id,
                "shape": item.shape.data_shape_id,
                "version": item.shape_version.version,
                "fields": [
                    (field.field_id, field.scalar_type, field.semantic_type)
                    for field in item.fields
                ],
            }
            for item in await self._datasets()
        ]
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(body.encode()).hexdigest()
        self._memo["fingerprint"] = fingerprint
        return fingerprint

    async def _datasets(self) -> list[CatalogDataset]:
        """Load and memoize all project-visible semantic datasets in bounded queries."""

        cached = self._memo.get("datasets")
        if isinstance(cached, list):
            return cast(list[CatalogDataset], cached)
        project = await self._project()
        contracts = (
            await self._session.exec(
                select(DataContractRecord).where(
                    DataContractRecord.project_id == project.id
                )
            )
        ).all()
        if self._visible_contract_ids is not None:
            contracts = [
                item
                for item in contracts
                if item.data_contract_id in self._visible_contract_ids
            ]
        contract_pks = [item.id for item in contracts if item.id is not None]
        fields = (
            (
                await self._session.exec(
                    select(DataContractFieldRecord).where(
                        cast(Any, DataContractFieldRecord.data_contract_id).in_(
                            contract_pks
                        )
                    )
                )
            ).all()
            if contract_pks
            else []
        )
        fields_by_contract: dict[int, list[DataContractFieldRecord]] = {}
        for field in fields:
            fields_by_contract.setdefault(field.data_contract_id, []).append(field)
        versions = (await self._session.exec(select(DataShapeVersionRecord))).all()
        version_by_pk = {item.id: item for item in versions}
        shapes = (await self._session.exec(select(DataShapeRecord))).all()
        shape_by_pk = {item.id: item for item in shapes}
        datasets = [
            CatalogDataset(
                contract=contract,
                shape=shape_by_pk[
                    version_by_pk[contract.data_shape_version_id].data_shape_id
                ],
                shape_version=version_by_pk[contract.data_shape_version_id],
                fields=tuple(
                    sorted(
                        fields_by_contract.get(cast(int, contract.id), []),
                        key=lambda item: item.field_id,
                    )
                ),
            )
            for contract in contracts
            if contract.data_shape_version_id in version_by_pk
            and version_by_pk[contract.data_shape_version_id].data_shape_id
            in shape_by_pk
        ]
        datasets.sort(key=lambda item: item.contract.data_contract_id)
        self._memo["datasets"] = datasets
        return datasets

    async def _dataset(self, data_contract_id: str | None) -> CatalogDataset | None:
        """Return one memoized dataset by stable contract ID."""

        if data_contract_id is None:
            return None
        return next(
            (
                item
                for item in await self._datasets()
                if item.contract.data_contract_id == data_contract_id
            ),
            None,
        )

    async def _project(self) -> ProjectRecord:
        """Resolve and memoize the catalog's project boundary."""

        cached = self._memo.get("project")
        if isinstance(cached, ProjectRecord):
            return cached
        rows = (
            await self._session.exec(
                select(ProjectRecord).where(ProjectRecord.project_id == self.project_id)
            )
        ).all()
        if not rows:
            raise ValueError(f"Project not found: {self.project_id}")
        self._memo["project"] = rows[0]
        return rows[0]

    def _dataset_payload(
        self, dataset: CatalogDataset, *, include_fields: bool
    ) -> JsonObject:
        """Serialize logical semantics without table, column, SQL, or adapter keys."""

        payload: JsonObject = {
            "data_contract_id": dataset.contract.data_contract_id,
            "name": dataset.contract.name,
            "description": dataset.contract.description,
            "shape": {
                "data_shape_id": dataset.shape.data_shape_id,
                "name": dataset.shape.name,
                "version": dataset.shape_version.version,
            },
            "bindings": dataset.contract.shape_bindings_json,
            "search_tags": dataset.contract.search_tags_json,
            "query_families": sorted(self._operations(dataset)),
            "views": sorted(
                {
                    view
                    for family in self._operations(dataset)
                    for view in __import__(
                        "goodomics.schemas.insights", fromlist=["VIEWS_BY_QUERY_KIND"]
                    ).VIEWS_BY_QUERY_KIND[family]
                }
            ),
        }
        if include_fields:
            payload["fields"] = [
                self._field_payload(dataset, field) for field in dataset.fields
            ]
        return payload

    def _field_payload(
        self, dataset: CatalogDataset, field: DataContractFieldRecord
    ) -> JsonObject:
        """Serialize one field with its canonical reference and semantic metadata."""

        return {
            "field": contract_field_reference(
                dataset.contract.data_contract_id, field.field_id
            ),
            "field_id": field.field_id,
            "display_name": field.display_name,
            "purpose": field.purpose,
            "scalar_type": field.scalar_type,
            "semantic_type": field.semantic_type,
            "unit": field.unit,
            "direction": field.direction,
            "description": field.description,
            "priority": field.priority,
            "domain_tags": field.domain_tags_json,
            "query_families": sorted(self._operations(dataset)),
            "source": "contract",
            "data_contract_id": dataset.contract.data_contract_id,
        }

    def _operations(self, dataset: CatalogDataset) -> frozenset[str]:
        """Return trusted adapter capabilities for a resolved dataset."""

        contract = DataContract(
            data_contract_id=dataset.contract.data_contract_id,
            name=dataset.contract.name,
            data_shape_id=dataset.shape.data_shape_id,
            data_shape_version=dataset.shape_version.version,
            shape_bindings_json=dataset.contract.shape_bindings_json,
            search_tags=dataset.contract.search_tags_json,
            description=dataset.contract.description,
            metadata_json=dataset.contract.metadata_json,
        )
        return BUILT_IN_ADAPTERS.get(dataset.shape_version.adapter_key).capabilities(
            contract
        )

    def _identities(self, dataset: CatalogDataset) -> set[str]:
        """Return public logical identities declared by shape keys and bindings."""

        identities = {
            str(value)
            for value in dataset.shape_version.definition_json.get("logical_keys", [])
        }
        entity_type = dataset.contract.shape_bindings_json.get("entity_type")
        if isinstance(entity_type, str):
            identities.add(entity_type)
        return identities

    async def _occurrences(self, contract: DataContractRecord) -> list[JsonObject]:
        """Return bounded occurrence provenance for one dataset."""

        if contract.id is None:
            return []
        rows = (
            await self._session.exec(
                select(RunContractRecord)
                .where(RunContractRecord.data_contract_id == contract.id)
                .order_by(cast(Any, RunContractRecord.created_at).desc())
                .limit(100)
            )
        ).all()
        return [
            {
                "run_contract_id": row.run_contract_id,
                "status": row.status,
                "producer_version": row.producer_version,
                "reference_context": row.reference_context_json,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
