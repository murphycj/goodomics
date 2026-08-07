# Report documents and rendering

Goodomics has two report paths:

- saved server reports compose insights against project
  data and can persist rendered HTML snapshots;
- standalone CLI reports scan a filesystem results path without using saved
  server insights.

## Saved report document

```yaml
project_id: rnaseq-core
name: RNA-seq QC
version: 1
filters: []
limit: 1000
random: false
layout: { columns: 12, row_height: 64 }
insights:
  - id: mapping-rate
    layout: { x: 0, y: 0, width: 6, height: 4 }
refresh_policy: { mode: manual }
```

Create component insights first. `POST /api/v1/reports/validate` verifies every
dependency, project boundary, permission, filter, unique insight ID, and grid
bound. Save is rejected when any referenced insight is unavailable; missing
insights are never silently removed.

| Route                                           | Purpose                                  |
| ----------------------------------------------- | ---------------------------------------- |
| `POST /api/v1/reports/validate`                 | Validate a complete report before saving |
| `POST /api/v1/reports`                          | Save the current definition              |
| `PATCH /api/v1/reports/{report}`                | Update metadata or executable fields     |
| `GET /api/v1/reports/{report}/export.yaml`      | Export portable YAML                     |
| `POST /api/v1/reports/{report}/execute`         | Return structured results                |
| `POST /api/v1/reports/render`                   | Execute and persist HTML                 |
| `GET /api/v1/rendered-reports/{id}/export.html` | Download a snapshot                      |

Reports reference insights rather than embedding them. Export the component
insights alongside the report when moving a complete report between servers.

## Structured results and snapshots

Structured report results contain one ordered `{id, layout, result}` entry per
configured insight. The nested result omits the standalone result's `kind` and
`insight_id` because its report entry already identifies it. Rendering uses the
same execution path, embeds bounded result data, and stores the HTML in
`rendered_reports`. The stored snapshot pins the exact resolved occurrences;
the saved report remains dynamic.

## Standalone CLI reports

The standalone path remains a simple results-folder renderer:

```bash
goodomics report ./results --template report.yaml --out report.html
```

It does not execute version 1 saved insights against SQL/DuckDB data. Use a
saved server report for metadata values, occurrence scopes, matching, caching,
or durable report history.
