# Goodomics Insights And Reports Guide

Use this file as the source of truth for saved insight and report behavior,
including builder modes, chart grammar, context, linker rules, result-size
policies, report inheritance, and AI-created insight guardrails.

## Builder Model

- Insight builders expose tab-style modes. **Cohort analysis** is first,
  **Sample** is second, followed by **Comparison** and **Table**.
- Cohort context uses canonical `sample_sets` and `sample_set_members`.
  Do not expand the legacy lightweight `cohorts` placeholder for new builder
  behavior.
- The mode-first v1 builder supports:
  - `profile_metrics`: cohort-level metric panels and “add all numeric fields”.
    The cohort selector appears below the series constructor as the first
    advanced filter option in this mode.
  - `sample_detail`: sample or processed-sample inspection.
  - `comparison`: aligned multi-series plots such as RNA vs protein.
  - `variant_table`: variant, feature-call, and generic table outputs.
- SQL access is selected from the per-series data source picker instead of a
  top-level Advanced SQL mode tab.
- Saved insight configs should include `context`, `mode`, `series`, `linker`,
  `filters`, and `result_policy`.
- Report configs may define `context`, `filters`, `linker`, or `result_policy`.
  Referenced insights inherit those values unless they explicitly override them.

## Server Catalog

- The server owns the insight catalog endpoint. It defines modes, chart IDs,
  icons, series constraints, linker rules, result policies, and validation
  messages.
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
  - Protein expression vs RNA expression: two profiles, two feature filters,
    shared linker `sample`.
  - All KRAS mutations: `variant_table` mode, mutations profile, gene filter
    `KRAS`, table output.

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
- `profile_metrics`: supports adding all numeric fields from a profile.

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
  language explanation of profiles, filters, linker, result policy, and chart.
- AI-created insights should open in the same builder UI for review and
  adjustment. They must not bypass catalog validation or linker/result-size
  guardrails.
