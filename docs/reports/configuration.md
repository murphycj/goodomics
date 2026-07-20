# Insight and report configuration

Goodomics configs are JSON-compatible mappings. YAML is a portable
serialization of the same structure. Configs describe analytical intent and do
not contain raw ECharts options or unrestricted SQL in the normal builder path.

## Normalized insight shape

The executor fills missing top-level values with these defaults:

```yaml
version: 1
context:
  kind: cohort
analysis_grain: sample
visualization: table
query: {}
series: []
linker:
  kind: auto
filters: []
result_policy:
  mode: preview
  limit: 1000
display: {}
```

The full top-level structure is:

| Key | Purpose |
| --- | --- |
| `version` | Config format version; currently `1` |
| `title` / `name` | Result title |
| `description` | Optional explanatory text |
| `analysis_grain` | Public entity being analyzed |
| `context` | Sample or cohort restriction |
| `visualization` | Table, metric, or chart ID |
| `query` | Source, fields, dimensions, measures, filters, and chart axes |
| `series` | Contract-backed chart values |
| `table_columns` | Identity and contract-field columns for table previews |
| `linker` | Identity used to align independent series |
| `filters` | Insight-wide filters |
| `result_policy` | Inline row, sample, or export limits |
| `display` | Presentation hints such as colors and histogram bins |

## Analysis grain

Supported public grains are `sample`, `subject`, `run`, `feature`, `variant`,
and `file`. `run_sample` is an internal provenance association and must not be
used as an analysis grain.

| Grain | Typical identity | Default matching behavior |
| --- | --- | --- |
| `sample` | `sample_id` | Sample |
| `subject` | `entity_id`, optionally `sample_id` | Entity or sample |
| `run` | `run_id` | Run |
| `feature` | `feature_id`, optionally `sample_id` | Feature or sample |
| `variant` | `variant_id`, `feature_id`, `sample_id` | Feature or sample |
| `file` | `source_file_id`, `run_id`, `sample_id` | Run or sample |

## Context

Contract-first execution currently applies two context forms:

```yaml
context:
  kind: sample
  sample_ids: [S1, S2]
```

```yaml
context:
  kind: cohort
  sample_group_id: production-rnaseq
```

Singular `sample_id` and plural `sample_ids` are both accepted. Cohort context
accepts singular `sample_group_id` or plural `sample_group_ids`. Sample groups contain
run-sample membership, so they preserve the result occurrence represented by a
cohort.

An empty cohort context is unbounded; it does not imply a particular saved
sample group.

## Contract query

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
  filters: []
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

Filters can be placed at the top level, in `query.filters`, or on an individual
series. The compiler combines applicable lists.

```yaml
filters:
  - field: value
    operator: gte
    value: 90
  - field: sample_id
    operator: in
    value: [S1, S2, S3]
```

Supported comparison operators are `eq`, `ne`, `gt`, `gte`, `lt`, and `lte`,
plus their symbolic forms. The builder compiler also accepts set-style `in`
filters. Common readable aliases such as `sample`, `feature`, `gene`, and
`metric` normalize to their corresponding identity/field columns.

Filters attached to a series affect only that series. Top-level and query
filters affect all relevant values.

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

| Visualization | Main constraint |
| --- | --- |
| `table` | Any supported fields |
| `metric` | One headline value |
| `bar` | One or more categorical/numeric series; multiple numeric series need matching |
| `stacked_bar` | At least two numeric series with a shared linker |
| `line`, `area` | Numeric series; multiple series require matching |
| `scatter` | Exactly two numeric series and a visible linker |
| `histogram` | One or more numeric distributions |
| `boxplot` | Numeric values, optionally grouped for comparison |
| `pie`, `donut` | Exactly one series |

Clients should fetch `GET /api/v1/insights/capabilities` rather than duplicating
these rules. The capability response also contains starter templates, grain descriptions,
linkers, result policies, and shared validation messages.

## Result-size policy

```yaml
result_policy:
  mode: preview
  limit: 1000
```

| Mode | Behavior |
| --- | --- |
| `preview` | Embed at most 1,000 rows |
| `more_rows` | Embed a requested limit, capped at 10,000 |
| `random_sample` | Deterministically sample up to 10,000 rows; accepts `seed` |
| `all_rows` | Embed all rows only when the result has at most 10,000 rows |
| `export_full_data` | Write a JSON artifact and embed the first 1,000 rows |

Limits are normalized into safe bounds. Full-data artifacts are written beside
the project's analytical database under `insight_artifacts/`.

## Report config

The report executor normalizes this shape:

```yaml
version: 1
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

Reports may also define `context`, `linker`, and `result_policy`. Those values
are inherited by an insight only when the insight omits the corresponding key.
Report `filters` are combined with every insight's own filters.

See [Insight compilation and execution](execution.md) for how these config
sections become SQL, result rows, chart options, caches, and rendered HTML.
