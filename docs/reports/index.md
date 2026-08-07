# Insights and reports

An **insight** is one reusable analysis. A **report** arranges saved insights in a validated grid and can
execute or render them as one result.

The builder follows this workflow:

1. **Analyze by** selects the public grain: sample, subject, run, feature,
   variant, or file.
2. **Add series**, **Add fields**, or **Add columns** opens one searchable field
   picker. **Results** contains analysis measurements grouped by their friendly
   source name; **Metadata** contains approved subject, sample, run, and file
   fields. Both add entries to one ordered `analysis.values` list.
3. **Results from** optionally changes the occurrence scope of each contract
   value.
4. **Matched by** controls how independently resolved values are joined.
5. **View as** presents the same ordered values as a table, metric, or chart.
   Drag values to set their shared order, use the eye control to add them to
   `view.hidden_values`, and configure only required chart roles such as axes or
   category.
6. **Settings** configures the selected visualization and completed result-row
   limit. Clicking a selected field opens its aggregation,
   filters, label, and result-scope controls.

The dashboard, API, report renderer, and AI-assisted drafting use the same
server-owned capabilities and definition grammar. Saved insights do not accept
physical table names or freeform SQL. The standalone database browser remains
available for database inspection.

## Saved and ad hoc insights

Send a complete definition to `POST /api/v1/insights/execute` for an ad hoc
preview. Save it with `POST /api/v1/insights` to give it a stable ID and make it
available to reports. Executable changes archive the previous JSON definition;
metadata-only changes do not create a revision.

Saved definitions remain dynamic. Each execution resolves current compatible
contract occurrences, while result diagnostics and rendered snapshots record
the exact resolved occurrences.

## Reports compose insights

Each saved insight may appear once in a report. Its public ID is also its grid
identity:

```yaml
version: 1
name: RNA-seq QC
layout: { columns: 12, row_height: 64 }
insights:
  - id: mapping-rate
    layout: { x: 0, y: 0, width: 12, height: 4 }
refresh_policy: { mode: manual }
```

The server validates every dependency, project boundary, permission, filter,
and layout bound before saving. Report filters narrow insight filters; they do
not replace an insight's grain, values, aggregation, matching, or result scope.

## Learn more

- [Insight configuration](insight-configuration.md)
- [Report configuration](report-configuration.md)
- [Compilation and execution](execution.md)
- [Use the JSON API from Python](python-api.md)
- [Report documents and rendering](report-templates.md)
