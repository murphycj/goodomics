# Insight configuration

Goodomics stores insights as YAML files that describe what data is fetched and
how it is filtered and visualized. The example below displays mapping metrics
as a table.

## Insight definition

```yaml
version: 1
insight_id: sample-qc-overview
name: Sample QC overview
description: Latest mapping metrics with sample names.

analysis:
  grain: sample
  values:
    - field: metadata/sample/sample_name

    - field: salmon:results/general_stats.salmon_percent_mapped
      label: Percent mapped
      aggregation: raw
      filters: []
      scope:
        selection: latest_successful_per_sample

  filters: []
  match_by: sample
  join: outer
  limit: 1000
  random: false

view:
  kind: table
```

The document has three required inputs: `version`, `analysis`, and `view`. The
insight ID, name, and description are saved metadata.

---

#### `version`

Required. The definition schema version. The only supported value is `1`.

---

### `insight_id`

Optional. A stable public identifier for a saved
insight. The server creates its own internal ID when the create request omits it.

---

### `name`

Required. The human-readable insight name shown in the dashboard, exports, result envelopes, and reports.

---

### `description`

Optional. Explanatory text stored with the saved insight and returned with its
results.

---

### `analysis`

Required. Describes what data is fetched, how it is filtered, and how values are joined.

The `analysis` object contains these inputs:

| Input      | Required | Default             | Purpose                                         |
| ---------- | -------- | ------------------- | ----------------------------------------------- |
| `grain`    | No       | `sample`            | Identity represented by each result row         |
| `values`   | Yes      | —                   | Ordered contract and metadata values to resolve |
| `filters`  | No       | `[]`                | Predicates applied across the analysis          |
| `match_by` | No       | The analysis grain  | Identity used to join values                    |
| `join`     | No       | Depends on the view | Which identities an outer or inner join retains |
| `limit`    | No       | `1000`              | Maximum completed result rows to return         |
| `random`   | No       | `false`             | Select completed result rows randomly           |

#### `analysis.grain`

Selects the public identity represented by each row or plotted point.

| Value     | Typical use                                    |
| --------- | ---------------------------------------------- |
| `sample`  | Measurements or metadata per biological sample |
| `subject` | Subject-level data                             |
| `run`     | Run status, methods, and run-level results     |
| `feature` | Gene, transcript, or other feature values      |
| `variant` | Variant-level data                             |
| `file`    | File metadata and file-level results           |

#### `analysis.values`

Required and must contain at least one value. Describes each series of data to include in the insight, including its source, label, aggregation, filters, and optional result scope. The order determines the display order for table columns and chart series.

##### Example

```yaml
analysis:
  values:
    - field: salmon:results/general_stats.salmon_percent_mapped
      label: Percent mapped
      aggregation: raw
      filters: []
      scope:
        selection: latest_successful_per_sample
```

##### `analysis.values[].field`

Required. References either an analytical data field or a project metadata field.

| Data source      | Format                      | Example                                              |
| ---------------- | --------------------------- | ---------------------------------------------------- |
| Analytical data  | `<contract>/<field>`        | `salmon:results/general_stats.salmon_percent_mapped` |
| Project metadata | `metadata/<entity>/<field>` | `metadata/sample/sample_name`                        |

The metadata entity must be `subject`, `sample`, `run`, or `file`, and the
selected field must support `analysis.grain`. Use the capabilities and contract
APIs rather than guessing references.

`/` is the only reserved separator. Data-contract IDs and contract-field IDs
cannot contain `/`. Display names and labels are not subject to this restriction.

##### `analysis.values[].as`

Optional. Replaces `field` with a different reference. It's mainly used when the same field is used more than once.

```yaml
values:
  - field: metadata/run/run_kind

  - field: metadata/run/run_kind
    as: run_count
    aggregation: count
```

##### `analysis.values[].label`

Optional. The display name for the value in the insight.

##### `analysis.values[].aggregation`

Optional; defaults to `raw`. Aggregation is validated against the declared
field type.

| Value type                   | Allowed aggregations                                         |
| ---------------------------- | ------------------------------------------------------------ |
| String, categorical, boolean | `raw`, `count`, `count_distinct`                             |
| Numeric                      | `raw`, `count`, `count_distinct`, `sum`, `avg`, `min`, `max` |
| Date or datetime             | `raw`, `min`, `max`                                          |

##### `analysis.values[].filters`

Optional. Filters are used to restrict what data is included (e.g. only certain samples), in addition to any filters defined in: [`analysis.filters`](#analysisfilters).

##### `analysis.values[].scope`

Optional and only available for analytical data fields. A field identifies
what was measured, but the same field may be produced by multiple runs or
methods. Use `scope` when you need to choose which of those results to use.

Most insights can omit it. By default, sample-based grains use
`latest_successful_per_sample`, while run grain uses `all_eligible`.

###### `analysis.values[].scope.selection`

Controls the occurrence-selection strategy:

| Value                          | Meaning                                                               |
| ------------------------------ | --------------------------------------------------------------------- |
| `latest_successful_per_sample` | Choose the latest compatible successful result for each sample        |
| `all_eligible`                 | Include every compatible occurrence allowed by the other scope inputs |
| `specific_methods`             | Restrict selection with `method_ids`                                  |
| `specific_versions`            | Restrict selection with `method_versions`                             |
| `specific_runs`                | Restrict selection with `run_ids`                                     |
| `pinned_results`               | Use exact `run_contract_ids`                                          |

###### Other `analysis.values[].scope` inputs

| Input               | Type                      | Default | Purpose                              |
| ------------------- | ------------------------- | ------- | ------------------------------------ |
| `analysis_type_ids` | List of strings           | `[]`    | Allowed public analysis-type IDs     |
| `method_ids`        | List of strings           | `[]`    | Allowed public method IDs            |
| `method_versions`   | List of strings           | `[]`    | Allowed method-version labels        |
| `run_ids`           | List of strings           | `[]`    | Allowed public run IDs               |
| `statuses`          | List of strings           | `[]`    | Allowed result or run statuses       |
| `started_after`     | ISO 8601 datetime or null | `null`  | Lower run-time bound                 |
| `ended_before`      | ISO 8601 datetime or null | `null`  | Upper run-time bound                 |
| `run_contract_ids`  | List of strings           | `[]`    | Exact produced-result occurrence IDs |

#### `analysis.filters`

Optional. These filters apply across the analysis. They are
combined with value filters using AND.

Example:

```yaml
filters:
  - field: status
    operator: eq
    value: completed
```

Each filter contains:

##### `analysis.filters[].field`

Required. The semantic field or identity to test. It must be valid for the
analysis and selected value sources.

##### `analysis.filters[].operator`

Optional; defaults to `eq`.

| Operator   | Meaning                         |
| ---------- | ------------------------------- |
| `eq`       | Equal                           |
| `ne`       | Not equal                       |
| `gt`       | Greater than                    |
| `gte`      | Greater than or equal           |
| `lt`       | Less than                       |
| `lte`      | Less than or equal              |
| `in`       | Included in a supplied list     |
| `not_in`   | Not included in a supplied list |
| `contains` | Contains the supplied text      |

##### `analysis.filters[].value`

Required. The comparison value. It may be a string, number, boolean, null,
object, or list as required by the selected operator and field.

The same `field`, `operator`, and `value` structure is used by
`analysis.values[].filters` and report-level `filters`.

#### `analysis.limit`

Optional integer from 1 to 10,000; defaults to `1000`. It limits the completed
result after filters, aggregation, and joining have finished. It does not
change which data participates in the analysis.

#### `analysis.random`

Optional boolean; defaults to `false`. When `true`, Goodomics returns a
deterministic random selection of up to `analysis.limit` completed result rows.
When `false`, it returns the first rows in the result's stable order.

Execution requests may override `limit` and `random`. Full-data export is a
separate execution-time action and is not saved in the insight definition.

#### `analysis.match_by`

Optional. Selects the identity used to join independently resolved values.
Allowed values are the public grains: `sample`, `subject`, `run`, `feature`,
`variant`, and `file`.

It defaults to `analysis.grain` for joined views. Metadata values currently
match by their declared analysis grain. Histograms do not join distributions
and therefore do not need `match_by`.

#### `analysis.join`

Optional. Controls which identities remain when multiple values are joined:

- `outer` keeps identities found in any value and fills missing cells with null;
- `inner` keeps only identities found in every value.

Tables default to `outer`. Matching charts default to `inner`. Histograms keep
independent distributions instead of joining rows. Duplicate values for one
identity become null and are reported in conflict diagnostics.

### `view`

Required. Describes how data is presented or plotted.

#### `view.kind`

Required. The type of chart. Can be either: `table`, `scatter`, `metric`,
`histogram`, `bar`, `stacked_bar`, `line`, `area`, `pie`, `donut`, `boxplot`,
or `heatmap`.

#### `view.hidden_values`

Optional. Contains one or more values to hide from the
view. Use either `as` or `field`. A value cannot be hidden if the chart type requires it, for example:
scatter `x` or `y`, metric `value`, heatmap `x`, `y`, or `value`, or a chart
`category`.

#### Table

```yaml
analysis:
  values:
    - field: metadata/sample/sample_name

    - field: salmon:results/general_stats.salmon_percent_mapped
      as: percent_mapped

view:
  kind: table
  hidden_values: [metadata/sample/sample_name]
  sorting:
    - by: percent_mapped
      direction: desc
  null_format: "—"
  numeric_format:
    percent_mapped:
      style: number
      decimals: 1
      suffix: "%"
```

| Input            | Required | Default | Purpose                                 |
| ---------------- | -------- | ------- | --------------------------------------- |
| `kind`           | Yes      | —       | Must be `table`                         |
| `hidden_values`  | No       | `[]`    | Hide selected analysis values           |
| `sorting`        | No       | `[]`    | Ordered sort rules                      |
| `null_format`    | No       | `—`     | Text shown for null cells               |
| `numeric_format` | No       | `{}`    | Number formats keyed by value reference |

Each `sorting` item has required `by` and optional `direction`, which defaults
to `asc` and also accepts `desc`. A table may sort by a hidden value. Column
order is always the grain identity followed by visible values in
`analysis.values` order.

In this example, the analytical value uses `as: percent_mapped`; the metadata
value has no alias and is therefore referenced by its complete field string.

The chart examples below use short references such as `percent_mapped` and
`percent_gc`; their corresponding analysis values must define those names with
`as`. A value without `as` is referenced by its complete field string instead.

#### Scatter plot

```yaml
view:
  kind: scatter
  x: percent_mapped
  y: percent_gc
  x_axis: { label: Percent mapped }
  y_axis: { label: Percent GC }
  colors: { percent_mapped: "#38bdf8" }
  tooltips: [sample_name]
```

`x` and `y` are required references to two different numeric values. Optional
inputs are `x_axis`, `y_axis`, `colors`, and `tooltips`.

#### Metric

```yaml
view:
  kind: metric
  value: sample_count
  number_format: { style: compact, decimals: 1 }
  thresholds:
    - value: 100
      label: Target
      color: "#16784a"
```

`value` is the required value reference. `number_format` is optional.
`thresholds` defaults to `[]`; each threshold has required numeric `value` and
optional `label` and `color`.

#### Histogram

```yaml
view:
  kind: histogram
  bins: 20
  x_axis: { label: Percent mapped }
  y_axis: { label: Samples }
  colors: { percent_mapped: "#38bdf8" }
```

Every visible analysis value becomes a distribution in declaration order. Use
`hidden_values` to omit a distribution. At least one visible value is required,
and every visible value must be numeric. `bins` defaults to `20` and accepts 1
through 500. Axis and color inputs are optional. Histogram values remain
independent distributions.

#### Bar, stacked-bar, line, area, pie, and donut plots

```yaml
view:
  kind: bar
  category: run_kind
  x_axis: { label: Run kind }
  y_axis: { label: Runs }
  colors: { run_count: "#38bdf8" }
  tooltips: [run_kind]
```

| Input              | Required | Purpose                                                        |
| ------------------ | -------- | -------------------------------------------------------------- |
| `kind`             | Yes      | One of `bar`, `stacked_bar`, `line`, `area`, `pie`, or `donut` |
| `category`         | No       | Identity or value reference used for categories                |
| `hidden_values`    | No       | Analysis values omitted as rendered series                     |
| `x_axis`, `y_axis` | No       | Axis configuration                                             |
| `colors`           | No       | Colors keyed by category or value reference                    |
| `tooltips`         | No       | Extra identity or value references shown in tooltips           |

Every visible analysis value other than `category` becomes a series in
declaration order. Pie and donut views require exactly one such visible value.
Stacked bars require at least two numeric visible values. Line and area visible
values must be numeric.

#### Boxplot

Every visible analysis value other than `category` becomes a numeric series in
declaration order. At least one is required. `category` is an optional identity
or value reference. Optional presentation inputs are `hidden_values`, `x_axis`,
`y_axis`, and `colors`.

#### Heatmap

`x`, `y`, and `value` are required references. `colors` is an optional ordered
color scale and `tooltips` is an optional list of extra references.

#### Axis input

An `x_axis` or `y_axis` object accepts:

| Input     | Type                                         | Purpose              |
| --------- | -------------------------------------------- | -------------------- |
| `label`   | String or null                               | Display label        |
| `scale`   | `linear`, `log`, `category`, `time`, or null | Axis scale           |
| `minimum` | Number or null                               | Explicit lower bound |
| `maximum` | Number or null                               | Explicit upper bound |

#### Number-format input

A table numeric format or metric `number_format` accepts:

| Input      | Type                                            | Default  | Purpose               |
| ---------- | ----------------------------------------------- | -------- | --------------------- |
| `style`    | `number`, `percent`, `scientific`, or `compact` | `number` | Formatting style      |
| `decimals` | Integer from 0 to 12 or null                    | `null`   | Decimal places        |
| `prefix`   | String or null                                  | `null`   | Text before the value |
| `suffix`   | String or null                                  | `null`   | Text after the value  |

## Strict validation

Insight create, executable patch, validation, preview, and execution requests
all use the same strict model. Unknown keys, invalid source combinations,
unsupported aggregations, invalid scopes, and missing view references are
rejected before persistence.

See the [report configuration reference](report-configuration.md) for report
filters, result-row overrides, grid layouts, insight references, and refresh policy.
