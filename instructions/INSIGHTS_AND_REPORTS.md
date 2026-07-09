# Goodomics Insights And Reports Guide

Use this file as the source of truth for saved insight and report behavior,
including analysis grains, chart grammar, context, linker rules, result-size
policies, report inheritance, and AI-created insight guardrails.

## Builder Model

- Insight builders are grain-first. The primary workflow is
  **Analyze by** → **Choose data** → **Filter** → **Matched by** → **View as**.
- `analysis_grain` is the entity grain and replaces saved insight `mode`.
  Supported grains are `run_sample`, `sample`, `subject`, `run`, `feature`,
  `variant`, and `file`.
- New insights default to `analysis_grain: run_sample` and
  `visualization: table`.
- `visualization` is the output choice: `table`, `bar`, `scatter`, `line`,
  `histogram`, `boxplot`, `metric`, and related chart types.
- Cohort context uses canonical `sample_sets` and `sample_set_members`.
  Do not expand the legacy lightweight `cohorts` placeholder for new builder
  behavior.
- The builder supports quick-start templates such as QC metrics across run
  samples, build a table, compare two fields, inspect one sample, explore a
  gene/feature, and variant/call table. Templates prefill editable config only;
  they do not create a separate workflow.
- SQL access is selected from the per-series data source picker instead of a
  top-level Advanced SQL mode tab.
- Saved insight configs should include `analysis_grain`, `visualization`,
  `context`, `series`, `table_columns`, `linker`, `filters`,
  `result_policy`, and `display`.
- Chart values are configured as `series`. Table-specific columns are
  configured as `table_columns` and should use raw values by default.
- Each chart value owns its `aggregation` / **Show** control. Supported choices
  are raw values, count rows, count distinct, average, sum, min, and max.
- Global quick filters live in `context` for broad cohort/sample/run-sample
  restrictions. Field-level conditions live in `filters` or
  `series[].filters`.
- Report configs may define `context`, `filters`, `linker`, or `result_policy`.
  Referenced insights inherit those values unless they explicitly override them.

## Server Catalog

- The server owns the insight catalog endpoint. It defines `analysis_grains`,
  templates, chart IDs, icons, value constraints, linker rules, result
  policies, and validation messages.
- Dashboard UI, API execution, report rendering, and future AI insight drafting
  should consume the catalog and shared validator instead of duplicating chart
  rules.
- ECharts is an implementation detail. Goodomics configs describe chart intent
  and compile to ECharts internally.

## Linkers

- Any plot aligning multiple values must show **Matched by**.
- `auto` may select the linker only when exactly one valid linker exists.
- If multiple valid linkers exist, require an explicit user choice.
- Linker diagnostics must be visible with matched, unmatched,
  duplicate/conflict, and excluded-row counts.
- Functional query examples:
  - RNA expression of two genes across samples: two feature-value series,
    gene filters, linker `sample` or `run_sample`.
  - Protein expression vs RNA expression: two contracts, two feature filters,
    shared linker `sample`.
  - All KRAS mutations: `analysis_grain: variant`, mutations contract, gene
    filter `KRAS`, table output.

## Plot Rules

- `scatter`: exactly two numeric measures and a visible linker.
- `line` / `area`: numeric series only, aligned by entity, feature, time, or
  selected linker.
- `bar`: one numeric series plots values by entity/linker; categorical series
  count categories; multiple numeric series align by linker.
- `stacked_bar`: two or more numeric series with a shared linker. Duplicate
  identical fields remain separate colored stacked series.
- `histogram`: one or more numeric series rendered as overlaid bins with
  opacity.
- `boxplot`: numeric only, grouped by sample set, sample, run, or category.
- `pie` / `donut`: exactly one series.
- `table`: any supported fields.
- `contract_metrics`: supports adding all numeric fields from a contract.

## Data Size

- `preview`: embed up to 1,000 rows.
- `more_rows`: embed a bounded user-selected limit.
- `random_sample`: embed a deterministic sampled subset using a seed.
- `all_rows`: embed all rows only when the result is below the configured
  response threshold.
- `export_full_data`: write complete plot/table data to a file-backed artifact
  instead of embedding it in the API response.
- Prefer server-side aggregation, binning, downsampling, or export for large
  datasets. Do not force huge raw datasets through ECharts.

## AI Readiness

- AI-created insights must produce a draft validated config plus a plain
  language explanation of contracts, filters, linker, result policy, and chart.
- AI-created insights should open in the same builder UI for review and
  adjustment. They must not bypass catalog validation or linker/result-size
  guardrails.
