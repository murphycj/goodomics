# Report templates and rendering

Goodomics currently has two report paths with different capabilities:

- **Saved server reports** compose saved insights, execute against project data,
  and can be rendered and persisted as HTML.
- **Standalone CLI reports** scan a filesystem results path and render without
  requiring a server or database.

Do not assume that a saved-report export can be passed to the standalone CLI
and receive the same database-backed execution. Both formats are JSON/YAML
compatible, but they enter different execution paths today.

## Saved report document

A saved report API document wraps identity and display fields around its config:

```yaml
report_id: rnaseq-qc
project_id: rnaseq-core
name: RNA-seq QC
description: Latest compatible QC results for the production sample group.
config:
  version: 1
  layout:
    columns: 12
  context:
    kind: sample_group
    sample_group_id: production-rnaseq
  items:
    - insight_id: mapping-rate
      x: 0
      y: 0
      w: 6
      h: 4
  filters: []
  refresh_policy:
    mode: manual
```

Create the component insights before creating the report. At execution time,
Goodomics loads only referenced insight IDs that exist, preserving their order
from `items`.

Use these routes for the saved-report lifecycle:

| Route | Purpose |
| --- | --- |
| `POST /api/v1/reports` | Save a report and its initial revision |
| `PATCH /api/v1/reports/{report}` | Update metadata/config and record a config revision |
| `GET /api/v1/reports/{report}/export.yaml` | Export a portable YAML document |
| `GET /api/v1/reports/{report}/export.json` | Export a portable JSON document |
| `POST /api/v1/reports/{report}/execute` | Return a structured report result |
| `POST /api/v1/reports/render` | Execute and persist HTML |
| `GET /api/v1/rendered-reports/{id}/export.html` | Download a rendered snapshot |

See the [configuration reference](configuration.md) for insight and report
keys and [compilation and execution](execution.md) for inheritance, caching,
and rendering behavior.

## Insight exports

Reports reference insights by ID rather than embedding every insight config.
Export the component insights alongside a report when moving a complete report
definition between installations:

```http
GET /api/v1/insights/mapping-rate/export.yaml
GET /api/v1/reports/rnaseq-qc/export.yaml
```

An insight export contains:

```yaml
insight_id: mapping-rate
project_id: rnaseq-core
name: Mapping rate
description: Percent mapped for the latest successful result per sample.
config:
  version: 1
  analysis_grain: sample
  visualization: table
  # Remaining insight config omitted here.
```

## Structured results versus rendered HTML

Executing a report returns a JSON object with the normalized report config and
one result object per insight. This form is appropriate for Python, notebooks,
MCP tools, and clients that render their own UI.

Rendering a saved report runs the same insight execution first, converts the
result to HTML, and stores the snapshot in `rendered_reports`. The HTML embeds
the structured result as `window.goodomicsReport` and includes fallback tables
for the bounded rows in each insight.

Large result policies still apply during report execution. Use
`export_full_data` for a file-backed data artifact rather than embedding an
unbounded dataset in the report payload.

## Standalone CLI templates

The standalone path remains the lowest-friction way to point Goodomics at a
results folder:

```bash
goodomics report ./results --template report.yaml --out report.html
```

The current standalone renderer loads a YAML or JSON mapping and reads
`config.title` when present:

```yaml
config:
  title: RNA-seq QC Report
```

It records the scanned results path in the output and does not execute saved
insights against the server's SQL/DuckDB stores. Use a saved server report when
you need contract selection, result scopes, sample group context, compiled charts,
cache behavior, or durable report history.
