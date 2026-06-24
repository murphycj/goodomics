# Report templates

Report templates are the portable contract between the CLI, dashboard, and
stored report history. The same YAML or JSON model should be usable from
`goodomics report`, editable in the dashboard, and versioned for workflow
integration.

Dashboard edits are stored in `report_templates` and
`report_template_revisions`; exports are available as YAML or JSON configs for
the standalone CLI.

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
report model, resolves input data, and renders charts, tables, text, thresholds,
and layout.

```yaml
version: 1
title: RNA-seq QC Report

data:
  sample_metrics:
    source: metrics.samples

sections:
  - title: Alignment
    blocks:
      - id: mapped_reads
        type: chart
        chart: stacked_bar
        data: sample_metrics
        x: sample_id
        series:
          - field: mapped_reads
            label: Mapped
          - field: unmapped_reads
            label: Unmapped

      - id: qc_table
        type: table
        data: sample_metrics
        columns:
          - sample_id
          - pct_mapped
          - duplication_rate
```

??? info "Advanced chart options"
    Advanced templates may eventually allow raw ECharts options as an escape
    hatch, but the default authoring surface should stay Goodomics-specific and
    stable.

## Charting

Apache ECharts is the default charting engine for Goodomics reports. It covers
the common MultiQC- and cBioPortal-like chart families Goodomics needs:
stacked/grouped bars, lines, scatter plots, heatmaps, boxplots, matrix-like
views, legends, tooltips, zooming, and custom series.

Goodomics should keep chart intent in its own schema and compile that schema to
ECharts options internally. Additional charting libraries should only be added
for concrete gaps and should remain behind the Goodomics report/chart
abstraction.

## Dashboard editing

The dashboard report builder should visually edit the same YAML/JSON-compatible
model consumed by the CLI. Drag-and-drop placement, chart resizing, section
ordering, data bindings, thresholds, and export settings should update template
metadata rather than creating a separate dashboard-only format.
