# Use insights and reports from Python

Insight and report authoring is available through the server JSON API. Python
applications can use `httpx` with ordinary dictionaries.

For typed construction and local validation, import the canonical executable
and portable-document contracts from `goodomics.schemas.insights`:

```python
from goodomics.schemas.insights import (
    InsightDocument,
    InsightSpec,
    ReportDocument,
    ReportSpec,
)
```

`InsightSpec` and `ReportSpec` contain executable configuration.
`InsightDocument` and `ReportDocument` add the names and identifiers needed for
portable YAML or JSON files. The server's saved-resource request and response
models reuse the same contracts.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000/api/v1")
project_id = "rnaseq-core"
```

## Discover selectable values

Use `/insights/capabilities` for approved metadata fields and view constraints,
and `/contracts` plus `/contracts/{contract}` for contract fields. Do not guess
field IDs or send table and column names.

```python
capabilities = client.get("/insights/capabilities").raise_for_status().json()
run_fields = [
    item for item in capabilities["metadata_fields"]
    if item["entity"] == "run"
]
# Each item["field"] is ready to use, such as "metadata/run/status".

salmon = client.get(
    "/contracts/salmon:results",
    params={"project_id": project_id},
).raise_for_status().json()
```

## Validate and execute an ad hoc insight

```python
definition = {
    "version": 1,
    "analysis": {
        "grain": "sample",
        "values": [
            {"field": "metadata/sample/sample_name"},
            {
                "field": "salmon:results/general_stats.salmon_percent_mapped",
            },
        ],
    },
    "view": {"kind": "table"},
}

validation = client.post(
    "/insights/validate",
    json={**definition, "project_id": project_id},
).raise_for_status().json()
if not validation["valid"]:
    raise ValueError(validation["messages"])

result = client.post(
    "/insights/execute",
    json={**definition, "project_id": project_id, "refresh": True},
).raise_for_status().json()["result"]
print(result["columns"], result["rows"][:5])
```

The order of `analysis.values` is the table-column and chart-series order. A
value's `field` is its default result and view reference. To hide a value
without removing it from the analysis, add that reference to the shared view
setting, for example `{"kind": "table", "hidden_values":
["metadata/sample/sample_name"]}`.

Add optional `"as": "percent_mapped"` when a field needs a shorter reference
or when the same field appears more than once. View bindings use `as` when it is
present and `field` otherwise.

For a scatter chart, keep the same values and replace the view with explicit
field or alias bindings. Matching charts use an inner join for independently
resolved values by default.

## Save and execute

```python
saved = client.post(
    "/insights",
    json={
        **definition,
        "insight_id": "sample-qc-overview",
        "project_id": project_id,
        "name": "Sample QC overview",
    },
).raise_for_status().json()

result = client.post(
    f"/insights/{saved['insight_id']}/execute",
    json={
        "project_id": project_id,
        "limit": 5000,
        "random": True,
    },
).raise_for_status().json()["result"]
```

Saved execution accepts `limit`, `random`, `export`, and `refresh` overrides,
not analytical changes. Patch the saved insight to change its values or view.

## Compose a report

```python
report_definition = {
    "version": 1,
    "name": "RNA-seq QC",
    "layout": {"columns": 12, "row_height": 64},
    "insights": [
        {
            "id": saved["insight_id"],
            "layout": {"x": 0, "y": 0, "width": 12, "height": 6},
        }
    ],
    "refresh_policy": {"mode": "manual"},
}

check = client.post(
    "/reports/validate",
    json={**report_definition, "project_id": project_id},
).raise_for_status().json()
if not check["valid"]:
    raise ValueError(check["messages"])

report = client.post(
    "/reports",
    json={
        **report_definition,
        "project_id": project_id,
    },
).raise_for_status().json()
```

Use `/reports/{id}/execute` for structured results and `/reports/render` for a
persisted HTML snapshot. Export saved definitions through their `/export.yaml`
or `/export.json` routes.
