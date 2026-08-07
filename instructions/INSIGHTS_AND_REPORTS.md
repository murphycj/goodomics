# Goodomics Insights And Reports Guide

This file is the source of truth for saved insight and report behavior.

## Builder model

The workflow is **Analyze by** → filters → **Choose data** → per-value filters
and **Results from** → **Matched by** → **View as**. Incomplete builder state remains client-side.

Public grains are `sample`, `subject`, `run`, `feature`, `variant`, and `file`.
`run_sample` is internal and never appears in definitions or builder labels.

Every selected field is one entry in `analysis.values`:

- `field` is the complete source-bearing reference;
- analytical fields use `<contract>/<field>`, such as
  `salmon:results/general_stats.salmon_percent_mapped`;
- SQL metadata fields use `metadata/<entity>/<field>`, such as
  `metadata/sample/sample_name`;
- `/` is reserved in data-contract and contract-field machine IDs so references
  never require escaping; display labels remain unrestricted;
- contract values may add `scope`, while metadata values may not;
- `field` is the default public reference used by views and result columns;
- optional `as` replaces that reference with a short safe alias and is needed
  when the same field is selected more than once;
- effective references (`as` when present, otherwise `field`) must be unique;
- `label` is the only insight-level field-label override;
- `aggregation` defaults to `raw` and `filters` defaults to an empty list.

Do not expose physical tables, database columns, or freeform SQL through saved
insights. Standalone database-browser routes are a separate inspection surface.

## Metadata fields

The server capability response owns the metadata field allow list and returns
the exact canonical `field` reference to store. The initial
entities are subject, sample, run, and file. Public fields include stable public
IDs and approved names, statuses, types, timestamps, file roles/formats/sizes,
and storage-location labels. Never expose integer keys, foreign keys,
`metadata_json`, parameters, paths, URIs, object keys, hashes, or arbitrary SQL
columns.

Metadata queries are always scoped to the current project. Analysis type and
method keys resolve to their public labels. Metadata and contract values are
resolved independently and joined using the same public grain identity.

## Result scope and joins

Every contract value owns `scope`. Sample-based grains default to
`latest_successful_per_sample`; run grain defaults to `all_eligible`. Optional
scope constraints include analysis types, methods, method versions, runs,
statuses, time bounds, and pinned run-contract IDs.

Tables default to an outer join. Missing values are null and diagnostics show
coverage. Multiple distinct values for one value/identity pair produce a null
cell and a duplicate-conflict diagnostic. Matching charts default to inner
joins. Histograms preserve independent distributions without joining them.

Rendered snapshots pin exact resolved occurrences. Saved insights and reports
remain dynamic and resolve again when their data changes.

## Views and result rows

`view` is a strict union keyed by `kind`. It owns all bindings, axes, colors,
tooltips, thresholds, sorting, null display, numeric formatting, and the shared
`hidden_values` visibility override. View bindings use each value's effective
reference: `as` when present, otherwise `field`. `analysis.values` declaration order is the
only value/series order. Tables derive columns as grain identities followed by
visible values in that order. Charts infer their rendered series from the same
ordered list, excluding role bindings such as `category` and entries in
`hidden_values`. Hiding a value never removes it from analysis, resolution,
diagnostics, fingerprints, or caches.

Required role bindings cannot be hidden: scatter `x` and `y`, metric `value`,
heatmap `x`, `y`, and `value`, and a value used as a chart `category`. Views do
not accept separate `columns` or `values` selection lists.

`analysis.limit` controls the number of completed result rows returned and
defaults to 1,000. `analysis.random` selects those final rows deterministically
when true and defaults to false. Both operate only after filters, aggregation,
and joining. Execution requests may override them. Full data export is a
separate execution-time, file-backed action.

Chart constraints:

- scatter binds exactly two numeric values;
- line and area bind numeric values;
- stacked bars bind at least two numeric values;
- histograms bind one or more numeric distributions;
- boxplots bind numeric values with an optional category;
- pie and donut bind exactly one value;
- tables accept any supported values.

ECharts remains an implementation detail compiled from `view`.

## Reports

Reports are validated grids of saved insights. Each entry in `insights` has the
saved insight's public `id` and a nested grid layout. An insight ID must be
unique within a report, so one saved insight can occur in a report only once.
The insight ID is also the render and grid identity.

Before persistence, validate dependency existence, project ownership,
permissions, layout bounds, and filters. Never silently drop missing insights.
Report filters intersect insight filters and cannot change grain, values,
matching, aggregation, or occurrence scopes. Optional report `limit` and
`random` values override the corresponding insight analysis defaults.

Result-row precedence is execution request → saved report → saved insight →
server default. Reports and insights store only complete valid definitions;
executable changes archive the previous JSON definition while metadata-only
changes do not create revisions.

Complete report documents always require a nonblank `name`. The server
generates `report_id`; create/import inputs and portable exports never own it.
Report execution returns each configured insight as `{id, layout, result}`.
The nested result omits the standalone insight result's `kind` and `insight_id`
because the report entry already supplies that context.

## Trust and size guardrails

Inline results default to 1,000 rows and remain bounded at 10,000. Random row
selection is deterministic, and full exports are file-backed. AI-created
insights must produce the same validated version 1 draft and cannot bypass the
metadata field allow list, resolver, joining, or result-row limits.
