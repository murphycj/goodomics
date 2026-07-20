# Use insights and reports from Python

The current Python SDK records runs, samples, metrics, and files. Insight and
report authoring is exposed by the Goodomics server's JSON API; there is not yet
a dedicated `goodomics` Python builder client. Python applications and
notebooks can use `httpx` with ordinary dictionaries, and the same configs can
be saved as JSON or YAML.

Start the server before running these examples:

```bash
goodomics serve
```

## Create an API client

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000/api/v1")
project_id = "rnaseq-core"
```

If authentication is enabled, add an `Authorization: Bearer ...` header to the
client. All builder examples below are project-scoped so contract resolution
and analytical storage use the intended project.

## Discover contracts and fields

Do not guess field IDs. Ask the contract catalog which values are available:

```python
contracts = client.get(
    "/contracts",
    params={"project_id": project_id},
).raise_for_status().json()

salmon = client.get(
    "/contracts/salmon:results",
    params={"project_id": project_id},
).raise_for_status().json()

numeric_fields = [
    field
    for field in salmon["fields"]
    if field["value_type"] == "numeric"
]
```

Each field response includes its stable `field_id`, display name, type, unit,
description, summary, and backend routing metadata. The builder config normally
needs only the contract ID and field ID.

## Execute an ad hoc table

This config selects one contract field and returns one raw value per sample:

```python
field_id = "general_stats.salmon_percent_mapped"

config = {
    "version": 1,
    "title": "Mapping rate by sample",
    "analysis_grain": "sample",
    "context": {"kind": "cohort"},
    "visualization": "table",
    "query": {
        "source": {
            "kind": "data_contract",
            "data_contract_id": "salmon:results",
        },
        "fields": [field_id],
        "dimensions": ["sample_id"],
    },
    "table_columns": [
        {"kind": "identity", "column": "sample_id", "label": "Sample"},
        {
            "kind": "contract_field",
            "contract_id": "salmon:results",
            "field_id": field_id,
            "label": "Percent mapped",
            "value_mode": "raw",
            "result_scope": {
                "selection": "latest_successful_per_sample",
            },
        },
    ],
    "result_policy": {"mode": "preview", "limit": 1000},
}

response = client.post(
    "/insights/execute",
    json={"project_id": project_id, "config": config, "refresh": True},
)
result = response.raise_for_status().json()["result"]

print(result["columns"])
print(result["rows"][:5])
print(result["result_selection_diagnostics"])
```

The result contains readable identity labels, the rows used for plotting, the
normalized result-size policy, and selection/linker diagnostics.

## Build a chart from contract series

Charts use `series` entries. Each series selects its own contract, field,
aggregation, filters, and result scope:

```python
scatter_config = {
    "version": 1,
    "title": "Mapping rate versus GC",
    "analysis_grain": "sample",
    "visualization": "scatter",
    "series": [
        {
            "id": "mapped",
            "contract_id": "salmon:results",
            "field_id": "general_stats.salmon_percent_mapped",
            "name": "Percent mapped",
            "aggregation": "avg",
            "result_scope": {
                "selection": "latest_successful_per_sample",
            },
        },
        {
            "id": "gc",
            "contract_id": "fastqc:results",
            "field_id": "general_stats.fastqc_raw_percent_gc",
            "name": "Percent GC",
            "aggregation": "avg",
            "result_scope": {
                "selection": "latest_successful_per_sample",
            },
        },
    ],
    "linker": {"kind": "sample"},
    "filters": [],
    "result_policy": {"mode": "preview", "limit": 1000},
    "display": {
        "colors": {"percent_mapped": "#38BDF8", "percent_gc": "#7C3AED"},
    },
}
```

The two series are resolved independently, then inner-aligned by biological
sample. Samples available in only one series appear in linker diagnostics rather
than producing a misleading unmatched point.

## Validate before execution

Use the shared validator to normalize defaults and catch catalog-level errors:

```python
validation = client.post(
    "/insights/validate",
    json={"config": scatter_config},
).raise_for_status().json()

if not validation["valid"]:
    raise ValueError(validation["messages"])

print(validation["explanation"])
normalized = validation["normalized_config"]
```

The validation endpoint checks config shape and chart series counts. Execution
adds data-specific checks, such as field existence, value types, valid linkers,
and available produced results.

## Save and execute an insight

```python
saved = client.post(
    "/insights",
    json={
        "insight_id": "mapping-vs-gc",
        "project_id": project_id,
        "name": "Mapping versus GC",
        "description": "Latest successful results matched by sample.",
        "config": scatter_config,
    },
).raise_for_status().json()

result = client.post(
    f"/insights/{saved['insight_id']}/execute",
    json={"project_id": project_id, "refresh": False},
).raise_for_status().json()["result"]
```

The first execution computes and caches the payload. A later identical request
can return `cached: true`. Set `refresh` to `True` to bypass a reusable cache.

## Compose and render a report

Save the component insights first, then reference their IDs from a report:

```python
report = client.post(
    "/reports",
    json={
        "report_id": "rnaseq-qc",
        "project_id": project_id,
        "name": "RNA-seq QC",
        "config": {
            "version": 1,
            "layout": {"columns": 12},
            "items": [
                {
                    "insight_id": "mapping-vs-gc",
                    "x": 0,
                    "y": 0,
                    "w": 6,
                    "h": 4,
                }
            ],
            "refresh_policy": {"mode": "manual"},
        },
    },
).raise_for_status().json()

structured = client.post(
    f"/reports/{report['report_id']}/execute",
    json={"project_id": project_id, "refresh": True},
).raise_for_status().json()["result"]

rendered = client.post(
    "/reports/render",
    json={
        "report_id": report["report_id"],
        "project_id": project_id,
        "title": "RNA-seq QC",
        "refresh": False,
    },
).raise_for_status().json()

html = rendered["html"]
```

Use `/execute` when code needs structured insight payloads. Use `/reports/render`
when it needs persisted HTML. Saved insights and reports can also be exported
through their `/export.yaml` and `/export.json` routes.
