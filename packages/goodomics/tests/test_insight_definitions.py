"""Values-only insight and report definition contract tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goodomics.schemas.field_references import parse_field_reference
from goodomics.schemas.insights import (
    InsightDocument,
    InsightSpec,
    ReportDocument,
    ReportSpec,
    normalize_insight_definition,
)
from goodomics.schemas.models import DataContract, DataContractField
from goodomics.server.app import create_app
from goodomics.server.insight_capabilities import metadata_fields
from pydantic import ValidationError


@pytest.fixture
def definition_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Yield an isolated API client with metadata and analytics storage."""

    monkeypatch.setenv(
        "GOODOMICS_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}",
    )
    monkeypatch.setenv(
        "GOODOMICS_ANALYTICS_PATH", str(tmp_path / "state" / "analytics.duckdb")
    )
    with TestClient(create_app()) as client:
        yield client


def test_insight_definition_expands_defaults_and_rejects_removed_keys() -> None:
    """Strict parsing expands defaults and rejects removed grammar keys."""

    definition = normalize_insight_definition(
        {
            "version": 1,
            "analysis": {
                "grain": "sample",
                "values": [{"field": "metadata/sample/sample_name"}],
            },
            "view": {"kind": "table"},
        }
    )

    assert definition.analysis.join == "outer"
    assert definition.analysis.match_by == "sample"
    assert definition.analysis.limit == 1000
    assert definition.analysis.random is False
    assert definition.analysis.values[0].aggregation == "raw"
    assert definition.compact_config() == {
        "version": 1,
        "analysis": {
            "grain": "sample",
            "values": [{"field": "metadata/sample/sample_name"}],
        },
        "view": {"kind": "table"},
    }
    inner_join = normalize_insight_definition(
        {
            "version": 1,
            "analysis": {
                "values": [{"field": "metadata/sample/sample_name"}],
                "join": "inner",
            },
            "view": {"kind": "table"},
        }
    )
    assert inner_join.analysis.join == "inner"
    assert inner_join.compact_config()["analysis"]["join"] == "inner"
    selected_rows = normalize_insight_definition(
        {
            "version": 1,
            "analysis": {
                "values": [{"field": "metadata/sample/sample_name"}],
                "limit": 250,
                "random": True,
            },
            "view": {"kind": "table"},
        }
    )
    selected_analysis = selected_rows.compact_config()["analysis"]
    assert selected_analysis["limit"] == 250
    assert selected_analysis["random"] is True
    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "values": [{"field": "metadata/sample/sample_name"}],
                    "alignment": "outer",
                },
                "view": {"kind": "table"},
                "output": {"mode": "preview", "limit": 1000},
            }
        )
    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "values": [{"field": "metadata/sample/sample_name"}],
                    "limit": 10001,
                },
                "view": {"kind": "table"},
            }
        )
    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 2,
                "analysis": {
                    "values": [
                        {
                            "field": "metadata/sample/sample_name",
                        }
                    ]
                },
                "view": {"kind": "table"},
            }
        )
    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "values": [
                        {
                            "field": "metadata/sample/sample_name",
                        }
                    ]
                },
                "view": {"kind": "table"},
                "query": {"sql": "select * from samples"},
            }
        )


def test_field_references_reserve_only_slashes_in_contract_machine_ids() -> None:
    """Canonical references stay unambiguous without restricting display labels."""

    reference = parse_field_reference("salmon:results/metrics.percent-mapped;v1")
    assert reference.kind == "contract"
    assert reference.contract_id == "salmon:results"
    assert reference.field_id == "metrics.percent-mapped;v1"

    with pytest.raises(ValidationError, match="cannot contain '/'"):
        DataContract(
            data_contract_id="custom/results",
            name="Custom / results",
            data_type="metrics",
        )
    with pytest.raises(ValidationError, match="cannot contain '/'"):
        DataContractField(
            data_contract_id="custom:results",
            field_id="quality/score",
            display_name="Quality / score",
        )


@pytest.mark.parametrize(
    "value",
    [
        {"field": "status"},
        {"field": "data/salmon:results/status"},
        {"field": "metadata/run/status/extra"},
        {"id": "old", "field": "metadata/run/status"},
        {
            "entity": "run",
            "contract": "salmon:results",
            "field": "salmon:results/status",
        },
        {
            "field": "metadata/run/status",
            "scope": {"selection": "all_eligible"},
        },
    ],
)
def test_insight_definition_requires_canonical_field_reference(
    value: dict[str, object],
) -> None:
    """Values accept only one source-bearing canonical field reference."""

    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {"values": [value]},
                "view": {"kind": "table"},
            }
        )


def test_insight_definition_rejects_alias_collisions_and_unknown_bindings() -> None:
    """Aliases are safe, unique, non-identity names referenced by the view."""

    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "grain": "sample",
                    "values": [
                        {"as": "sample_id", "field": "metadata/sample/sample_name"}
                    ],
                },
                "view": {"kind": "metric", "value": "sample_id"},
            }
        )
    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {"values": [{"field": "metadata/sample/sample_name"}]},
                "view": {"kind": "metric", "value": "missing"},
            }
        )


def test_repeated_fields_require_aliases_only_for_distinct_references() -> None:
    """A field is its default reference and `as` disambiguates repeated uses."""

    with pytest.raises(ValidationError, match="add 'as' to repeated fields"):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "values": [
                        {"field": "metadata/run/run_kind"},
                        {
                            "field": "metadata/run/run_kind",
                            "aggregation": "count",
                        },
                    ]
                },
                "view": {"kind": "table"},
            }
        )

    definition = InsightSpec.model_validate(
        {
            "version": 1,
            "analysis": {
                "grain": "run",
                "values": [
                    {"field": "metadata/run/run_kind"},
                    {
                        "field": "metadata/run/run_kind",
                        "as": "run_count",
                        "aggregation": "count",
                    },
                ],
            },
            "view": {"kind": "bar", "category": "metadata/run/run_kind"},
        }
    )

    assert [value.reference for value in definition.analysis.values] == [
        "metadata/run/run_kind",
        "run_count",
    ]
    assert definition.compact_config()["analysis"]["values"][1]["as"] == "run_count"


def test_view_uses_one_hidden_list_and_rejects_removed_selection_lists() -> None:
    """Value order comes from analysis and visibility comes only from the view."""

    values = [
        {"as": "a", "field": "metadata/sample/sample_name"},
        {"as": "b", "field": "metadata/sample/subject_id"},
    ]
    definition = InsightSpec.model_validate(
        {
            "version": 1,
            "analysis": {"values": values},
            "view": {"kind": "pie", "hidden_values": ["b"]},
        }
    )

    assert [value.reference for value in definition.analysis.values] == ["a", "b"]
    assert definition.view.hidden_values == ["b"]
    for view in (
        {"kind": "table", "columns": ["sample_id", "a"]},
        {"kind": "pie", "values": ["a"]},
    ):
        with pytest.raises(ValidationError):
            InsightSpec.model_validate(
                {"version": 1, "analysis": {"values": values}, "view": view}
            )


@pytest.mark.parametrize(
    "view",
    [
        {"kind": "table", "hidden_values": ["missing"]},
        {"kind": "table", "hidden_values": ["a", "a"]},
        {"kind": "metric", "value": "a", "hidden_values": ["a"]},
        {"kind": "scatter", "x": "a", "y": "b", "hidden_values": ["a"]},
    ],
)
def test_hidden_values_must_be_unique_values_and_not_required_bindings(
    view: dict[str, object],
) -> None:
    """Visibility cannot remove identities or fields that define the view."""

    with pytest.raises(ValidationError):
        InsightSpec.model_validate(
            {
                "version": 1,
                "analysis": {
                    "values": [
                        {"as": "a", "field": "metadata/sample/sample_name"},
                        {"as": "b", "field": "metadata/sample/subject_id"},
                    ]
                },
                "view": view,
            }
        )


def test_metadata_fields_are_allow_list_without_sensitive_columns() -> None:
    """Capabilities expose only documented public metadata fields."""

    fields = metadata_fields()
    sources = {(item["entity"], item["field"]) for item in fields}
    assert ("run", "metadata/run/status") in sources
    assert ("file", "metadata/file/storage_location") in sources
    assert not any(
        item["field"].rsplit("/", 1)[-1]
        in {
            "id",
            "project_id",
            "metadata_json",
            "parameters_json",
            "path",
            "uri",
            "object_key",
            "sha256",
        }
        for item in fields
    )
    status = next(
        item
        for item in fields
        if item["entity"] == "run" and item["field"] == "metadata/run/status"
    )
    assert status["allowed_aggregations"] == ["raw", "count", "count_distinct"]


def test_metadata_only_insight_is_project_scoped(
    definition_client: TestClient,
) -> None:
    """Metadata execution returns public run identities from only one project."""

    project = definition_client.post("/api/v1/projects", json={"name": "Alpha"}).json()
    other = definition_client.post("/api/v1/projects", json={"name": "Beta"}).json()
    for project_id, run_id in (
        (project["project_id"], "alpha-run"),
        (other["project_id"], "beta-run"),
    ):
        response = definition_client.post(
            "/api/v1/runs",
            json={"project_id": project_id, "run_id": run_id},
        )
        assert response.status_code == 201, response.text
    result = definition_client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project["project_id"],
            "version": 1,
            "analysis": {
                "grain": "run",
                "values": [
                    {"field": "metadata/run/name"},
                    {"field": "metadata/run/status"},
                ],
            },
            "view": {"kind": "table"},
        },
    )

    assert result.status_code == 200, result.text
    payload = result.json()["result"]
    assert payload["columns"] == [
        "run_id",
        "metadata/run/name",
        "metadata/run/status",
    ]
    assert payload["column_labels"] == {
        "run_id": "Run",
        "metadata/run/name": "Run name",
        "metadata/run/status": "Status",
    }
    assert {row["run_id"] for row in payload["rows"]} == {"alpha-run"}


def test_table_uses_analysis_order_and_hidden_values(
    definition_client: TestClient,
) -> None:
    """Table identity stays first while values follow canonical declaration order."""

    project = definition_client.post("/api/v1/projects", json={"name": "Alpha"}).json()
    assert (
        definition_client.post(
            "/api/v1/runs",
            json={"project_id": project["project_id"], "run_id": "alpha-run"},
        ).status_code
        == 201
    )
    response = definition_client.post(
        "/api/v1/insights/execute",
        json={
            "project_id": project["project_id"],
            "version": 1,
            "analysis": {
                "grain": "run",
                "values": [
                    {"as": "status", "field": "metadata/run/status"},
                    {"as": "name", "field": "metadata/run/name"},
                    {"as": "kind", "field": "metadata/run/run_kind"},
                ],
            },
            "view": {"kind": "table", "hidden_values": ["name"]},
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["columns"] == ["run_id", "status", "kind"]
    assert [value["as"] for value in result["analysis"]["values"]] == [
        "status",
        "name",
        "kind",
    ]


def test_report_requires_unique_insight_references() -> None:
    """Each saved insight may occur only once in a report."""

    report = ReportSpec.model_validate(
        {
            "version": 1,
            "limit": 250,
            "random": True,
            "insights": [
                {
                    "id": "insight-1",
                    "layout": {"x": 0, "y": 0, "width": 6, "height": 4},
                },
                {
                    "id": "insight-2",
                    "layout": {"x": 6, "y": 0, "width": 6, "height": 4},
                },
            ],
        }
    )

    assert [insight.id for insight in report.insights] == [
        "insight-1",
        "insight-2",
    ]
    assert report.limit == 250
    assert report.random is True

    with pytest.raises(ValidationError):
        ReportSpec.model_validate(
            {
                "version": 1,
                "insights": [
                    {
                        "id": "insight-1",
                        "layout": {"x": 0, "y": 0, "width": 6, "height": 4},
                    },
                    {
                        "id": "insight-1",
                        "layout": {"x": 6, "y": 0, "width": 6, "height": 4},
                    },
                ],
            }
        )

    with pytest.raises(ValidationError):
        ReportSpec.model_validate(
            {
                "version": 1,
                "layout": {"kind": "grid"},
                "insights": [
                    {
                        "id": "insight-1",
                        "layout": {"x": 0, "y": 0, "width": 6, "height": 4},
                    }
                ],
            }
        )

    with pytest.raises(ValidationError):
        ReportSpec.model_validate(
            {
                "version": 1,
                "items": [
                    {
                        "item" + "_id": "first",
                        "insight_id": "insight-1",
                        "layout": {"x": 0, "y": 0, "width": 6, "height": 4},
                    }
                ],
            }
        )


def test_report_requires_at_least_one_insight() -> None:
    """An empty report is incomplete builder state and cannot be persisted."""

    with pytest.raises(ValidationError):
        ReportSpec.model_validate({"version": 1, "insights": []})


def test_portable_documents_keep_names_separate_from_executable_specs() -> None:
    """Named portable documents serialize without changing executable specs."""

    insight = InsightDocument.model_validate(
        {
            "version": 1,
            "insight_id": "quality-table",
            "name": "Quality table",
            "description": "Portable definition",
            "analysis": {
                "values": [{"field": "metadata/sample/sample_name"}],
            },
            "view": {"kind": "table"},
        }
    )
    report = ReportDocument.model_validate(
        {
            "version": 1,
            "report_id": "quality-report",
            "name": "Quality report",
            "insights": [
                {
                    "id": "quality-table",
                    "layout": {"x": 0, "y": 0, "width": 12, "height": 4},
                }
            ],
        }
    )

    assert "name" not in insight.executable_config()
    assert insight.model_dump(mode="json", by_alias=True)["name"] == "Quality table"
    assert "name" not in report.executable_config()
    assert report.model_dump(mode="json")["report_id"] == "quality-report"
