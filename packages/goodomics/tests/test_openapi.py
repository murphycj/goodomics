"""Tests for the generated public OpenAPI contract."""

from __future__ import annotations

import json
from pathlib import Path

from goodomics.openapi import build_openapi_document, export_openapi


def _operations(document: dict[str, object]) -> list[dict[str, object]]:
    """Return all HTTP operations from a generated OpenAPI document."""

    methods = {"get", "post", "put", "patch", "delete", "options", "head"}
    paths = document["paths"]
    assert isinstance(paths, dict)
    return [
        operation
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method, operation in path_item.items()
        if method in methods and isinstance(operation, dict)
    ]


def test_operation_ids_are_present_and_unique() -> None:
    """Every generated SDK method has one stable unique operation identifier."""

    operations = _operations(build_openapi_document())
    operation_ids = [operation.get("operationId") for operation in operations]

    assert all(isinstance(operation_id, str) for operation_id in operation_ids)
    assert len(operation_ids) == len(set(operation_ids))


def test_openapi_export_is_deterministic(tmp_path: Path) -> None:
    """Repeated exports produce byte-identical, sorted JSON output."""

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8")) == build_openapi_document()


def test_insight_contract_separates_requests_reads_and_nullable_fields() -> None:
    """Insight HTTP resources reuse the canonical grammar with distinct roles."""

    schemas = build_openapi_document()["components"]["schemas"]

    assert "SavedInsightCreate" in schemas
    assert "SavedInsightPatch" in schemas
    assert "SavedInsightRead" in schemas
    analysis_value = schemas["AnalysisValue"]["properties"]
    assert {"as", "label", "scope"} <= analysis_value.keys()
    assert any(
        variant.get("type") == "null" for variant in analysis_value["as"]["anyOf"]
    )
    insight_view = schemas["SavedInsightRead"]["properties"]["view"]
    assert insight_view["discriminator"]["propertyName"] == "kind"


def test_no_content_operations_have_no_success_body() -> None:
    """HTTP 204 operations do not advertise an impossible JSON response body."""

    document = build_openapi_document()
    delete_insight = document["paths"]["/api/v1/insights/{insight_ref}"]["delete"]

    assert "content" not in delete_insight["responses"]["204"]
