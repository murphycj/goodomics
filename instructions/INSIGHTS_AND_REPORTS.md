# Goodomics Insights And Reports Guide

This file is the source of truth for saved insight and report behavior.

## Builder model

- The workflow is **Analyze by** → sample/cohort context → **Choose data** →
  per-series filters and **Results from** → **Matched by** → **View as**.
- Public grains are `sample`, `subject`, `run`, `feature`, `variant`, and `file`.
  `run_sample` is internal and must not appear in builder grains, templates,
  linkers, labels, or default configs.
- New insights default to `analysis_grain: sample` and `visualization: table`.
- The primary picker combines contracts and fields, grouping searchable fields
  beneath their stable data contract.
- Selecting a field determines compatible analysis types, methods, result
  defaults, aggregations, and chart choices.
- Global context may restrict biological samples or canonical sample sets.
- Table columns use raw values by default. Chart series own aggregation and
  field-level filters.

## Result scope

Every series and table column owns `result_scope`:

- `selection`: `latest_successful_per_sample`, `specific_methods`,
  `specific_versions`, `specific_runs`, or `pinned_results`;
- optional `analysis_type_ids`, `method_ids`, `method_versions`, `run_ids`,
  `statuses`, `started_after`, `ended_before`, and `run_contract_ids`.

Empty optional filters derive compatible choices from the selected contract.
Sample-based grains default to latest successful compatible result per sample.
Run grain defaults to all eligible runs without per-sample ranking.

The collapsed summary should read like “Latest successful · RNA sequencing ·
nf-core/rnaseq · 2 method versions.” Expanding it exposes overrides with
bounded loading, error, and empty states. “Apply result scope to all series” is
available only when all selected contracts have a compatible scope.

Each series resolves independently. Intentional cross-analysis comparisons are
aligned by a biological linker such as sample; they do not share a hidden
execution occurrence.

## Resolver and diagnostics

All insight, report, API, MCP, and AI-created configs use the shared result
resolver defined in `instructions/DATA_MODEL.md`. Results include exact
run-contract/run-sample IDs and visible diagnostics for:

- excluded failed, incomplete, and incompatible results;
- samples missing the selected result or fixed version;
- represented methods and versions;
- mixed-version warnings;
- profiled-empty availability;
- superseded results;
- linker matched, unmatched, and conflict counts.

Rendered report snapshots pin exact resolved occurrence IDs. Dynamic saved
insights continue to update as new compatible runs arrive.

## Server catalog and config

The server owns grains, templates, charts, linkers, result-size policies,
validation, and explanations. Dashboard, API, report rendering, MCP, and AI
consume this catalog rather than duplicating rules.

Saved configs include `analysis_grain`, `visualization`, `context`, `series`,
`table_columns`, `linker`, `filters`, `result_policy`, and `display`. Each series
or column includes the selected contract/field and its result scope.

ECharts is an implementation detail. Goodomics configs describe chart intent.

## Linkers and plot rules

- Aligning multiple values must show **Matched by**.
- `auto` is valid only when exactly one linker is possible.
- Biological cross-analysis values normally match by `sample`.
- `scatter`: exactly two numeric measures and a visible linker.
- `line`/`area`: numeric series aligned by entity, feature, time, or linker.
- `bar`: one value by entity, categorical counts, or aligned numeric series.
- `stacked_bar`: at least two numeric series with a shared linker.
- `histogram`: one or more overlaid numeric distributions.
- `boxplot`: numeric values grouped by sample set, sample, run, or category.
- `pie`/`donut`: exactly one series.
- `table`: any supported fields.

## Data size and AI guardrails

- Preview embeds at most 1,000 rows.
- More rows and deterministic sampling remain bounded.
- All rows may be embedded only below the response threshold.
- Full data export uses a file-backed artifact.
- Prefer server aggregation, binning, downsampling, or export for large data.

AI-created insights produce a validated draft plus a plain-language explanation
of contracts, fields, scopes, filters, linker, result policy, and chart. They
open in the normal builder and cannot bypass resolver or size guardrails.
