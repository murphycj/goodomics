# Use insights and reports from Python

Insight and report authoring is available through the server JSON API. Python
applications can use `httpx` with ordinary dictionaries.

For typed construction and local validation, import the canonical executable
and portable-document contracts from `goodomics.schemas.insights`:

```python
from goodomics.schemas.insights import (
    InsightSpec,
    ReportSpec,
)
```

`InsightSpec` and `ReportSpec` are the canonical executable v2 definitions. The
server's saved-resource models add project ownership and persisted identifiers.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000/api/v1")
project_id = "rnaseq-core"
```

## Discover selectable values

Use `/projects/{project}/catalog/datasets`, `/catalog/fields`, and
`/catalog/query-families` for permission-scoped semantic discovery. Do not guess
field IDs or send table and column names.

```python
fields = client.get(
    f"/projects/{project_id}/catalog/fields",
    params={"query_kind": "rows", "search": "mapping"},
).raise_for_status().json()["items"]
```

## Validate and execute an ad hoc insight

```python
definition = {
    "version": 2,
    "name": "Sample QC overview",
    "query": {
        "kind": "rows",
        "grain": "sample",
        "columns": [
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

The order of a rows query's `columns` is table-column order. A selection's
`field` is its default result and view reference. To hide a value
without removing it from the query, add that reference to the shared view
setting, for example `{"kind": "table", "hidden_values":
["metadata/sample/sample_name"]}`.

Add optional `"as": "percent_mapped"` when a field needs a shorter reference
or when the same field appears more than once. View bindings use `as` when it is
present and `field` otherwise.

For a scatter chart, use a `relationship` query with explicit `x`, `y`, and
`match_by`, then choose a compatible `scatter` view.

## Save and execute

```python
saved = client.post(
    "/insights",
    json={
        **definition,
        "insight_id": "sample-qc-overview",
        "project_id": project_id,
        "preview_fingerprint": result["preview_fingerprint"],
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
    "version": 2,
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
