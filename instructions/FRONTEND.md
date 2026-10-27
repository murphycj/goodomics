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

- Store one complete typed v2 draft: `version + name + query + view`.
- Present query families as plain-language analysis types such as Build a table,
  Summarize groups, Compare two fields, and Show a profile or trend. Use a visual
  card selector for discovery, then keep the selected analysis type compact in the
  builder toolbar.
- Preserve the compact toolbar/editor/preview hierarchy: analysis type, logical
  identity, and compatible view across the top; family-specific inputs on the
  left; preview on the right.
- Use family-specific editors for rows, summaries, relationships, distributions,
  series, matrices, alteration matrices, variant positions, genomic profiles,
  survival, timelines, and associations.
- Group catalog fields by data contract in a searchable All / Results / Metadata
  selector. Represent selected table columns as reorderable field cards with
  visibility and action controls.
- Search and filter canonical fields through the request-scoped runtime catalog.
  Preserve returned `<contract>/<field>` and `metadata/<entity>/<field>` strings.
- Filter view choices by typed-result compatibility. Switching family replaces
  incompatible family-specific state instead of carrying generic value settings.
- Fetch catalog choices with bounded TanStack queries and explicit loading, error,
  and empty states. Keep heavy visualization modules out of initial list bundles
  when practical.
- Show deterministic query explanation, coverage/missingness diagnostics, and
  provider requirements in the review step.
- Require a successful preview of the exact current query fingerprint before save.
- Keep occurrence selectors and scope controls separate from field references.
- Never expose physical routing, SQL, adapter keys, internal integer IDs, or
  `run_sample` as a user-facing grain or label.
