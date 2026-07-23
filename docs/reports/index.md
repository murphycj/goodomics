# Insights and reports

An **insight** is one reusable analysis: a table, metric, or chart backed by a
declarative configuration. A **report** arranges saved insights into a layout
and can execute or render them as one result.

The builder follows this conceptual workflow:

1. **Analyze by**: choose the public grain—sample, subject, run, feature,
   variant, or file.
2. **Context**: optionally restrict the analysis to samples or a saved sample
   group.
3. **Choose data**: select one or more fields grouped under their data
   contracts.
4. **Results from**: decide which produced result occurrence to use for every
   field or series.
5. **Matched by**: select the biological or computational identity that aligns
   multiple series.
6. **View as**: choose a compatible table, metric, or chart.

The dashboard, API, report renderer, and AI-assisted drafting use the same
server-owned capabilities and config grammar. Chart configs describe Goodomics
intent; ECharts options are compiled output rather than the primary authoring
format.

## Saved versus ad hoc insights

An ad hoc insight is a config sent directly to
`POST /api/v1/insights/execute`. It is useful for previews, notebooks, and code
that does not need a durable builder object.

A saved insight stores a stable ID, project, name, description, and config in
the SQL metadata store. Creating or updating its config records an immutable
revision. Saved insights can be exported as YAML or JSON and referenced by
reports.

Saved insight configs are dynamic: the default result resolver can select newer
compatible results when data arrives. An executed result includes the exact
run-contract and run-sample IDs that were selected, so the result remains
explainable.

## Reports compose insights

A saved report config primarily contains ordered layout items:

```yaml
version: 1
layout:
  columns: 12
items:
  - insight_id: mapping-rate
    x: 0
    y: 0
    w: 6
    h: 4
  - insight_id: gc-distribution
    x: 6
    y: 0
    w: 6
    h: 4
```

During execution, Goodomics loads those insights in item order. Report-level
`linker` and `result_policy` values are inherited only when an
insight does not define its own value. Report filters are prepended to each
insight's filters.

The structured report result contains the normalized report config plus each
compiled insight result. Rendering produces HTML and can persist the snapshot
in `rendered_reports`.

## Result selection is explicit

The same contract can be produced by many runs and method versions. Each
series or table column can therefore define a `result_scope`. Sample-based
analysis defaults to the latest successful compatible result per sample. Run
analysis defaults to all eligible runs.

Execution diagnostics report:

- resolved run-contract and run-sample IDs;
- excluded failed and incompatible results;
- represented methods and versions;
- missing samples and superseded occurrences;
- observed versus profiled-empty availability;
- mixed-version warnings;
- matched, unmatched, and conflicting linker values.

These diagnostics are part of the result payload and should be shown to users
instead of hiding selection decisions behind a chart.

## Choose the next guide

- [Use insights and reports from Python](python-api.md) shows the user workflow
  for discovering fields, validating configs, executing insights, and
  composing reports.
- [Configuration reference](configuration.md) documents the insight and report
  config structures.
- [Compilation and execution](execution.md) describes the backend resolver,
  query compiler, result compiler, caching, and rendering path.
- [Report templates and rendering](report-templates.md) explains portable
  exports and the difference between saved-report and standalone CLI rendering.
