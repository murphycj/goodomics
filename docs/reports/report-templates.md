# Report templates

Saved reports and insights are the portable contract between the CLI,
dashboard, and stored rendered report history. The same YAML or JSON model
should be usable from `goodomics report`, editable in the dashboard, and
versioned for workflow integration.

Dashboard insight edits are stored in `insights` and `insight_revisions`.
Dashboard report edits are stored in `reports` and `report_revisions`.
Generated HTML snapshots are stored separately in `rendered_reports`.

## Rendering model

Goodomics reports should render as self-contained offline HTML by default. A
generated `report.html` should include the report structure, data needed for
display, CSS, and JavaScript runtime without depending on CDN-hosted assets or
an internet connection.

PDF export should use the same report model. The preferred path is to render the
self-contained HTML file and print it with a local browser renderer, with print
CSS and chart export behavior tuned for stable output.

Large payloads should not be embedded blindly. Template authors and built-in
profiles should prefer summarized data, downsampling, binned distributions,
static SVG or PNG chart output, or explicit opt-in expansion when full raw data
would make the report unwieldy.

## Template shape

Templates should describe what the report means rather than exposing low-level
chart-library details first. Goodomics compiles the template into a normalized
report model, resolves input data, caches computed insight/report payloads, and
renders charts, tables, text, thresholds, and layout.

```yaml
version: 1
title: RNA-seq QC Report

insights:
  - insight_id: mapped_reads
    name: Mapped reads
    visualization: stacked_bar
    query:
      source:
        kind: data_profile
        data_profile_id: multiqc:qc_metrics
      fields: [general_stats.salmon_percent_mapped]
      entity: run_sample
      dimensions: [sample_id]
      measures:
        - field: general_stats.salmon_percent_mapped
          aggregation: sum
          label: Reads

report:
  report_id: rnaseq-qc
  name: RNA-seq QC
  items:
    - insight_id: mapped_reads
      x: 0
      y: 0
      w: 6
      h: 4
```

??? info "Advanced chart options"
    Advanced templates may eventually allow raw ECharts options as an escape
    hatch, but the default authoring surface should stay Goodomics-specific and
    stable.

## Charting

Apache ECharts is the default charting engine for Goodomics reports. It covers
the common MultiQC- and cBioPortal-like chart families Goodomics needs:
stacked/grouped bars, lines, scatter plots, histograms, heatmaps, boxplots,
matrix-like views, legends, tooltips, zooming, and custom series.

Histogram insights use a numeric raw-value column and can set `query.bins` or
`display.bins` to control bin count:

```yaml
insight_id: insert_size_distribution
name: Insert size distribution
visualization: histogram
query:
  source:
    kind: data_profile
    data_profile_id: multiqc:qc_metrics
  fields: [multiqc_picard.insert_size]
  y: multiqc_picard.insert_size
  bins: 30
```

Goodomics should keep chart intent in its own schema and compile that schema to
ECharts options internally. Additional charting libraries should only be added
for concrete gaps and should remain behind the Goodomics report/chart
abstraction.

## Dashboard editing

The dashboard report builder should visually edit the same YAML/JSON-compatible
model consumed by the CLI. Drag-and-drop placement, chart resizing, section
ordering, data bindings, thresholds, and export settings should update template
metadata rather than creating a separate dashboard-only format.

## Caching and defaults

Insight and report executions are cached by project, canonical config hash, and
source fingerprint. The dashboard normally reuses a valid cached payload and
offers a refresh action to recompute it. A project can set `default_report_id`
so opening the project lands on the saved report instead of the sample list.
