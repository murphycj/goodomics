# Dashboard

The dashboard is a Vite React TypeScript app under
`packages/goodomics/dashboard`. It builds into `goodomics/server/web/static` for
FastAPI to serve.

## UI stack

Dashboard UI should use editable shadcn/ui-style components with Tailwind,
Radix primitives, and `lucide-react` icons. Keep the interface credible for
biotech/R&D work: dense enough for repeated review, clear enough for new users,
and consistent with the Goodomics product language.

The dashboard already uses TanStack Query and TanStack Router. Prefer TanStack
Table and virtualization for large tabular views so sample, metric, file, and
run data can scale without changing the visual system.

## Report builder

The report builder should edit the same YAML/JSON-compatible report template
model used by `goodomics report`. Drag-and-drop layout, chart resizing, section
ordering, data bindings, thresholds, and export settings should persist as
template metadata that the CLI can consume.

## Charting

Apache ECharts is the default charting engine for dashboard previews and
generated reports. Dashboard chart controls should manipulate Goodomics chart
specs first; Goodomics can compile those specs to ECharts options internally.

!!! warning "Keep chart libraries behind Goodomics abstractions"
    Avoid adding another charting stack unless a concrete report feature
    requires it and the integration can remain behind the Goodomics report/chart
    abstraction.

## Build

```bash
cd packages/goodomics/dashboard
npm run build
```
