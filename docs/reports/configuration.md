# Insight and report configuration

The configuration is a declarative description of the analytical intent for a single insight or a report. It is a portable and shareable artifact that can be stored in a project, a Git repository, or a database. The executor compiles the config into SQL, result rows, chart options, caches, and rendered HTML. The executor also validates the config against the server capabilities and the contract schema. The executor may fill in missing values with defaults, normalize aliases, and report warnings or errors. The executor may also apply a result policy to limit the number of rows returned.

## Example saved insight

This example defines a sample-level table of Salmon mapping rates for selected
samples and a sample group. `name` and `description` identify the saved insight,
while `config` contains only its executable analytical definition.

```yaml
name: Salmon mapping rates
description: Percent mapped for the production RNA-seq sample group.
config:
  analysis_grain: sample
  visualization: table
  query:
    source:
      kind: data_contract
      data_contract_id: salmon:results
    fields:
      - general_stats.salmon_percent_mapped
    dimensions: [sample_id]
    order_by: sample_id
    limit: 1000
  series: []
  table_columns:
    - kind: identity
      column: sample_id
      label: Sample
    - kind: contract_field
      contract_id: salmon:results
      field_id: general_stats.salmon_percent_mapped
      label: Percent mapped
      value_mode: raw
      result_scope:
        selection: latest_successful_per_sample
  linker:
    kind: sample
  filters:
    - field: sample
      operator: in
      value:
        - kind: sample
          id: control-01
        - kind: sample
          id: control-02
        - kind: sample_group
          id: production-rnaseq
    - field: general_stats.salmon_percent_mapped
      operator: gte
      value: 90
  result_policy:
    mode: preview
    limit: 1000
  display: {}
```

The saved insight fields and config keys map to the reference sections below:

| Key              | Purpose                                                       | Details                                         |
| ---------------- | ------------------------------------------------------------- | ----------------------------------------------- |
| `name`           | Saved insight and rendered result name                         | [Name](#name)                                   |
| `description`    | Optional explanatory text returned with the result            | [Description](#description)                     |
| `analysis_grain` | What each row or plotted point represents                     | [Analysis grain](#analysis-grain)               |
| `visualization`  | Table, metric, or chart ID                                    | [Visualizations](#visualizations)               |
| `query`          | Source, fields, dimensions, measures, and chart axes          | [Query and data source](#query-and-data-source) |
| `series`         | Contract-backed chart values                                  | [Series](#series)                               |
| `table_columns`  | Identity and contract-field columns for table previews        | [Table columns](#table-columns)                 |
| `linker`         | Identity used to align independent series                     | [Linkers](#linkers)                             |
| `filters`        | Insight-wide filters                                          | [Filters](#filters)                             |
| `result_policy`  | Inline row, sample, or export limits                          | [Result-size policy](#result-size-policy)       |
| `display`        | Presentation hints such as colors and histogram bins          | [Display](#display)                             |

## Name

`name` identifies the insight in the dashboard, API, SDK, exports, and rendered
results:

```yaml
name: Salmon mapping rates
```

## Description

`description` adds optional explanatory text to the saved and compiled insight:

```yaml
description: Percent mapped for the production RNA-seq sample group.
```

## Analysis grain

`analysis_grain` defines what each row or plotted point represents. Choose
`sample`, `subject`, `run`, `feature`, `variant`, or `file`. Goodomics handles
the relationship between a sample and a particular run internally, so it is
not another option you need to select.

| Grain     | Typical identity                        | Default matching behavior |
| --------- | --------------------------------------- | ------------------------- |
| `sample`  | `sample_id`                             | Sample                    |
| `subject` | `entity_id`, optionally `sample_id`     | Entity or sample          |
| `run`     | `run_id`                                | Run                       |
| `feature` | `feature_id`, optionally `sample_id`    | Feature or sample         |
| `variant` | `variant_id`, `feature_id`, `sample_id` | Feature or sample         |
| `file`    | `source_file_id`, `run_id`, `sample_id` | Run or sample             |

## Query and data source

The `query` section supplies the main source and table/chart shaping hints:

```yaml
query:
  source:
    kind: data_contract
    data_contract_id: salmon:results
  fields:
    - general_stats.salmon_percent_mapped
  dimensions: [sample_id]
  measures: []
  order_by: sample_id
  limit: 1000
```

Fields may be collected from `query.fields`, measures, non-identity dimensions,
and `table_columns`. Field IDs containing punctuation are returned under safe
column aliases such as `general_stats_salmon_percent_mapped`.

Measures use a small aggregation vocabulary:

```yaml
measures:
  - field: general_stats.salmon_percent_mapped
    aggregation: avg
    label: Average mapped
```

Supported aggregations are `count`, `count_distinct`, `sum`, `avg`, `min`, and
`max`. `average` normalizes to `avg`; `count_rows` normalizes to `count`.

`query.x`, `query.y`, and `query.bins` help shape charts after rows have been
queried. Histogram bins may also be supplied as `display.bins`.

For a table or metric backed by one contract, `query.source` identifies that
contract as shown above. Contract-backed chart series identify their own
contracts and fields in `series`; in that form, `query` can still supply
shaping hints and a limit without repeating a single source.

## Series

Charts normally use one or more contract-backed series:

```yaml
series:
  - id: mapped
    contract_id: salmon:results
    field_id: general_stats.salmon_percent_mapped
    name: Percent mapped
    aggregation: avg
    color: "#38BDF8"
    filters:
      - field: value
        operator: gte
        value: 0
    result_scope:
      selection: latest_successful_per_sample
```

`contract_id`/`data_contract_id` and `field_id` are the important semantic
keys. A series alias is derived from `name`, `label`, or `field_id`. Duplicate
aliases receive a numeric suffix.

If aggregation is `raw`, `none`, `value`, or omitted, each selected value is
returned without aggregation. Otherwise Goodomics groups by the selected
linker when a linker is present.

## Table columns

Tables can mix identity columns and contract fields:

```yaml
table_columns:
  - kind: identity
    column: sample_id
    label: Sample
  - kind: contract_field
    contract_id: salmon:results
    field_id: general_stats.salmon_percent_mapped
    label: Percent mapped
    value_mode: raw
    result_scope:
      selection: latest_successful_per_sample
```

`value_mode: raw` is the normal table behavior. When selected fields from the
same contract live in compatible scalar/payload tables, the compiler can
normalize and pivot them into a wide table by the analysis grain's identity
columns. Feature and variant tables require their domain keys and are not
silently mixed into that scalar pivot.

## Filters

Top-level filters affect the whole insight. Filters on an individual series
affect only that series. The compiler combines applicable filters with AND.

```yaml
filters:
  - field: sample
    operator: in
    value:
      - kind: sample
        id: S1
      - kind: sample
        id: S2
      - kind: sample_group
        id: production-rnaseq
  - field: value
    operator: gte
    value: 90
```

The special top-level `sample` filter selects biological samples and saved
sample groups in one place. References inside its `value` list are combined
with OR, so the example includes S1, S2, and every occurrence in the
`production-rnaseq` group. You may select any mixture of the two kinds. An
empty list selects no rows; omit the filter to use all samples.

Goodomics resolves these references before it ranks eligible contract results.
This matters for sample groups because a group identifies particular processed
sample occurrences, not merely the biological samples associated with them.

Supported comparison operators are `eq`, `ne`, `gt`, `gte`, `lt`, and `lte`,
plus their symbolic forms. The builder compiler also accepts set-style `in`
filters. Common readable aliases such as `feature`, `gene`, and `metric`
normalize to their corresponding identity or field columns.

Multiple top-level filters are cumulative. Report filters are also combined
with insight filters, so separate sample filters narrow one another.

## Result scope

Each series or table column can decide which occurrence of its contract is
eligible:

```yaml
result_scope:
  selection: latest_successful_per_sample
  analysis_type_ids: [rna_sequencing]
  method_ids: [nf-core/rnaseq]
  method_versions: ["3.18"]
  run_ids: []
  statuses: []
  started_after: null
  ended_before: null
  run_contract_ids: []
```

Selection values are:

- `latest_successful_per_sample`: choose the most recent successful compatible
  occurrence for each sample. This is the default outside run grain.
- `all_eligible_runs`: retain eligible occurrences without per-sample ranking.
  This is the run-grain default.
- `specific_methods`, `specific_versions`, or `specific_runs`: use the
  corresponding filter lists.
- `pinned_results`: constrain execution to `run_contract_ids`.

The optional filters are cumulative. Dates use ISO 8601 strings. A produced
result must also be compatible with the contract's analysis types and have
eligible per-sample availability.

## Linkers

`linker` appears in the UI as **Matched by**:

```yaml
linker:
  kind: sample
```

Supported linkers are `auto`, `sample`, `run`, `feature`, `entity`, and `time`.
Contract series currently resolve physical linker columns for sample, feature,
run, and entity. `auto` succeeds when one valid linker is available. When a
chart requires matching and several linkers are possible, callers must choose
one explicitly.

Series are independently queried and inner-aligned on the linker. Conflicting
duplicate values and identities present in only some series are excluded and
reported in diagnostics.

## Visualizations

The server currently defines:

| Visualization  | Main constraint                                                               |
| -------------- | ----------------------------------------------------------------------------- |
| `table`        | Any supported fields                                                          |
| `metric`       | One headline value                                                            |
| `bar`          | One or more categorical/numeric series; multiple numeric series need matching |
| `stacked_bar`  | At least two numeric series with a shared linker                              |
| `line`, `area` | Numeric series; multiple series require matching                              |
| `scatter`      | Exactly two numeric series and a visible linker                               |
| `histogram`    | One or more numeric distributions                                             |
| `boxplot`      | Numeric values, optionally grouped for comparison                             |
| `pie`, `donut` | Exactly one series                                                            |

Clients should fetch `GET /api/v1/insights/capabilities` rather than duplicating
these rules. The capability response also contains starter templates, grain descriptions,
linkers, result policies, and shared validation messages.

## Result-size policy

```yaml
result_policy:
  mode: preview
  limit: 1000
```

| Mode               | Behavior                                                    |
| ------------------ | ----------------------------------------------------------- |
| `preview`          | Embed at most 1,000 rows                                    |
| `more_rows`        | Embed a requested limit, capped at 10,000                   |
| `random_sample`    | Deterministically sample up to 10,000 rows; accepts `seed`  |
| `all_rows`         | Embed all rows only when the result has at most 10,000 rows |
| `export_full_data` | Write a JSON artifact and embed the first 1,000 rows        |

Limits are normalized into safe bounds. Full-data artifacts are written beside
the project's analytical database under `insight_artifacts/`.

## Display

`display` contains presentation hints. It does not select data or change which
rows are eligible. An empty object uses renderer defaults.

Chart colors are keyed by a series alias or category:

```yaml
display:
  colors:
    percent_mapped: "#38BDF8"
    duplication_rate: "#636EFA"
```

Histograms accept a bin count from 1 through 100:

```yaml
display:
  bins: 30
```

`query.bins` takes precedence over `display.bins`; when neither is supplied,
the renderer uses 20 bins. The top-level `result_policy` is preferred, although
normalization also recognizes `display.result_policy` when no top-level policy
is present.

## Defaults and normalization

Missing keys are normalized before validation and execution. The principal
defaults are `analysis_grain: sample`, `visualization: table`, an automatic
linker, the preview result policy, and empty query, series, filter, and display
values.

Explicit values are preferable in stored or shared examples because they make
the analytical intent clear without requiring the reader to know the defaults.

## Report config

The report executor normalizes this shape:

```yaml
layout:
  columns: 12
items: []
filters: []
refresh_policy:
  mode: manual
```

Each item must reference a saved `insight_id`. Layout keys such as `x`, `y`,
`w`, and `h` are preserved for the dashboard and renderer:

```yaml
items:
  - insight_id: mapping-rate
    x: 0
    y: 0
    w: 6
    h: 4
```

Reports may also define `linker` and `result_policy`. Those values are inherited
by an insight only when the insight omits the corresponding key.
Report `filters` are combined with every insight's own filters.

See [Insight compilation and execution](execution.md) for how these config
sections become SQL, result rows, chart options, caches, and rendered HTML.
