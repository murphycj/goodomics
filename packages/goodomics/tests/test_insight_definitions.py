"""Version 2 typed insight-definition and capability tests."""

from __future__ import annotations

import pytest
from goodomics.schemas.insights import (
    MATRIX_CELL_LIMIT_DEFAULT,
    RESULT_LIMIT_DEFAULT,
    InsightSpec,
    SavedReportCreate,
    normalize_insight_definition,
    referenced_fields,
)
from goodomics.server.analysis_providers import provider_requirement
from goodomics.server.insight_capabilities import explain_query
from pydantic import ValidationError


def _field(name: str) -> dict[str, str]:
    """Return one canonical metadata selection for compact fixtures."""

    return {"field": f"metadata/sample/{name}"}


QUERY_FIXTURES = {
    "rows": {
        "grain": "sample",
        "columns": [_field("sample_name")],
        "view": "table",
    },
    "summary": {
        "grain": "sample",
        "group_by": [_field("sample_name")],
        "aggregations": [
            {**_field("sample_id"), "aggregation": "count_distinct", "as": "count"}
        ],
        "view": "bar",
    },
    "relationship": {
        "x": _field("sample_id"),
        "y": _field("sample_name"),
        "match_by": "sample",
        "view": "scatter",
    },
    "distribution": {"value": _field("sample_name"), "view": "histogram"},
    "series": {
        "position": _field("sample_id"),
        "measurements": [_field("sample_name")],
        "view": "line",
    },
    "matrix": {
        "rows": _field("sample_id"),
        "columns": _field("sample_name"),
        "value": _field("subject_id"),
        "view": "heatmap",
    },
    "alteration_matrix": {
        "features": ["TP53"],
        "alterations": [_field("sample_name")],
        "view": "oncoprint",
    },
    "variant_position": {
        "position": _field("sample_id"),
        "frequency": _field("sample_name"),
        "view": "lollipop",
    },
    "genome_profile": {
        "coordinate": _field("sample_id"),
        "value": _field("sample_name"),
        "view": "genome_profile",
    },
    "survival": {
        "duration": _field("sample_id"),
        "event": _field("sample_name"),
        "provider": {"method": "kaplan_meier"},
        "view": "survival",
    },
    "timeline": {
        "subject": _field("subject_id"),
        "start": _field("sample_id"),
        "view": "timeline",
    },
    "association": {
        "features": ["TP53", "KRAS"],
        "state": [_field("sample_name")],
        "view": "association_matrix",
    },
}


@pytest.mark.parametrize("kind", QUERY_FIXTURES)
def test_every_query_family_is_discriminated_and_explainable(kind: str) -> None:
    """Every documented family parses, preserves references, and explains itself."""

    fixture = QUERY_FIXTURES[kind]
    query = {key: value for key, value in fixture.items() if key != "view"}
    definition = InsightSpec.model_validate(
        {
            "version": 2,
            "name": f"Example {kind}",
            "query": {"kind": kind, **query},
            "view": {"kind": fixture["view"]},
        }
    )

    assert definition.query.kind == kind
    assert referenced_fields(definition.query)
    assert explain_query(definition.query)
    assert definition.executable_config()["version"] == 2


def test_v1_and_unknown_properties_are_rejected() -> None:
    """The undeployed product performs a clean replacement without v1 readers."""

    with pytest.raises(ValidationError):
        normalize_insight_definition(
            {
                "version": 1,
                "analysis": {"values": [_field("sample_name")]},
                "view": {"kind": "table"},
            }
        )
    with pytest.raises(ValidationError):
        normalize_insight_definition(
            {
                "version": 2,
                "name": "Unsafe",
                "query": {
                    "kind": "rows",
                    "grain": "sample",
                    "columns": [_field("sample_name")],
                    "sql": "select *",
                },
                "view": {"kind": "table"},
            }
        )


def test_defaults_and_matrix_limits_are_explicit() -> None:
    """Inline and matrix limits retain the v2 acceptance-plan guardrails."""

    rows = InsightSpec.model_validate(
        {
            "version": 2,
            "name": "Rows",
            "query": {
                "kind": "rows",
                "grain": "sample",
                "columns": [_field("sample_id")],
            },
            "view": {"kind": "table"},
        }
    )
    matrix_fixture = QUERY_FIXTURES["matrix"]
    matrix = InsightSpec.model_validate(
        {
            "version": 2,
            "name": "Matrix",
            "query": {
                "kind": "matrix",
                **{
                    key: value for key, value in matrix_fixture.items() if key != "view"
                },
            },
            "view": {"kind": "heatmap"},
        }
    )

    assert rows.query.limit == RESULT_LIMIT_DEFAULT
    assert matrix.query.cell_limit == MATRIX_CELL_LIMIT_DEFAULT  # type: ignore[union-attr]


def test_query_view_compatibility_and_alias_uniqueness() -> None:
    """Typed results reject incompatible views and duplicate output aliases."""

    with pytest.raises(ValidationError, match="not compatible"):
        InsightSpec.model_validate(
            {
                "version": 2,
                "name": "Bad view",
                "query": {
                    "kind": "rows",
                    "grain": "sample",
                    "columns": [_field("sample_id")],
                },
                "view": {"kind": "survival"},
            }
        )
    with pytest.raises(ValidationError, match="must be unique"):
        InsightSpec.model_validate(
            {
                "version": 2,
                "name": "Duplicate",
                "query": {
                    "kind": "rows",
                    "grain": "sample",
                    "columns": [_field("sample_id"), _field("sample_id")],
                },
                "view": {"kind": "table"},
            }
        )


def test_survival_reports_an_explicit_provider_requirement() -> None:
    """Core represents survival inputs without silently implementing statistics."""

    fixture = QUERY_FIXTURES["survival"]
    definition = InsightSpec.model_validate(
        {
            "version": 2,
            "name": "Survival",
            "query": {
                "kind": "survival",
                **{key: value for key, value in fixture.items() if key != "view"},
            },
            "view": {"kind": "survival"},
        }
    )
    requirement = provider_requirement(definition.query)

    assert requirement is not None
    assert requirement.required is True
    assert requirement.available is False
    assert "required" in (requirement.message or "")


def test_report_v2_references_saved_insights() -> None:
    """Reports remain strict v2 grids of saved insight IDs."""

    report = SavedReportCreate.model_validate(
        {
            "version": 2,
            "name": "QC report",
            "insights": [
                {
                    "id": "mapping-rate",
                    "layout": {"x": 0, "y": 0, "width": 12, "height": 4},
                }
            ],
        }
    )
    assert report.version == 2
    assert report.insights[0].id == "mapping-rate"
