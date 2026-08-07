# Goodomics Frontend And Reporting Guide

Use this file for dashboard, report-rendering, charting, and UI guidance.

For React component, hook, rendering, data-fetching, styling, or bundle-size
work in `packages/goodomics/dashboard`, also use
`$vercel-react-best-practices` and the dashboard-local guide at
`packages/goodomics/dashboard/AGENTS.md`.

## Frontend Stack

- Prefer shadcn/ui-style components with Tailwind, Radix primitives, and
  `lucide-react` icons for dashboard UI. Keep components editable and
  consistent with Goodomics' biotech/R&D product feel.
- Use TanStack primitives for dashboard data workflows already in the app.
  Reach for TanStack Table and virtualization for large tabular views.
- Use Apache ECharts as the default report and dashboard charting engine.
  Prefer a Goodomics-owned chart/spec layer that compiles to ECharts options
  instead of exposing raw ECharts config as the primary user interface.
- Do not add Plotly, Observable, Vega-Lite, uPlot, or another charting stack
  unless a concrete report/dashboard feature clearly requires it. If one is
  added, keep it behind the Goodomics report/chart abstraction.

## Report Rendering

- Default reports should be self-contained offline HTML files: no CDN
  dependencies, no required internet access, and no required external JS/CSS
  assets for the normal `goodomics report` path.
- YAML or JSON report templates should be the portable template format for the
  CLI and dashboard. The dashboard report builder should edit the same model
  rather than introducing a separate dashboard-only template format.
- For large chart payloads, prefer summary views, downsampling, static SVG/PNG
  output, or explicit opt-in expansion instead of embedding huge raw datasets
  in report HTML.

## CLI Progress And Reports

- Use Rich for user-facing progress and logging in long-running CLI workflows,
  especially ingestion and report generation.
- Future parsers should expose quiet library APIs by default, then let CLI
  entry points opt into Rich progress for parse/discovery, SQL metadata writes,
  analytical-store writes, bulk loads, and report rendering.
- Keep progress bars visually stable: put the spinner/progress bar/counts
  before changing descriptive text, use a fixed bar width, and clip long
  descriptions instead of letting them compress the bar.

## Visual Guardrails

- Visual and UI work should feel credible for biotech/R&D while staying
  approachable.
- Avoid generic DNA stock imagery, abstract SaaS gradients, and mascot-heavy
  first impressions.

## Insight Builder

- Keep one searchable field picker as the main data selection control. Present
  **All / Results / Metadata** as understated source tabs below search, omit
  fields that are incompatible with the current grain, and keep already-selected
  incompatible fields visible with a warning. Use friendly result-source labels;
  reserve data-contract identifiers for provenance and advanced details.
- Split value editing, data picking, result scope, and diagnostics into focused
  components instead of growing one page component indefinitely.
- Fetch contract-compatible result options with bounded TanStack queries and
  explicit loading, error, and empty states.
- Store builder state in one typed version 1 insight draft. Field selection edits
  `analysis.values`; switching views preserves values; table and chart series order
  follows value order. Dragging or moving a field changes that canonical order.
  Use `field` as a value's default reference and generate optional `as` aliases
  only for duplicates or other cases that need a distinct short reference.
- Use compact value rows with progressive disclosure. Tables use a column-oriented,
  multi-select editor; charts use view-appropriate series or binding language. The
  same visibility control edits `view.hidden_values` for tables and charts; disable
  it for values currently used by a required role binding.
- Keep **Analyze by** and **View as** in the builder toolbar. Separate per-field
  settings from visualization and final result-row settings.
- Show inferred **Results from** scope compactly; keep detailed overrides
  collapsed until requested.
- Never expose internal `run_sample` as an Analyze by grain, Matched by choice,
  filter tab, template, or user-facing label.
