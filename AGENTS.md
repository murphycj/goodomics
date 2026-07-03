# Goodomics Agent Guide

This repo contains the Goodomics Python monorepo. Keep this file lightweight,
operational, and focused on how to work in the repo.

## Product Source Of Truth

- Use `instructions/PRODUCT.md` for product narrative, positioning, messaging,
  feature framing, competitive context, audience, product modes, priorities, and
  trust boundaries.
- Use `instructions/DATA_MODEL.md` for data model terminology and schema
  direction, including projects, runs, samples, subjects, processed samples /
  `run_samples`, data imports, files, data profiles, observations, SQL control
  tables, DuckDB analytical tables, and MCP/data-query concepts.
- Do not duplicate product or data model briefs here. If product strategy
  changes, update `instructions/PRODUCT.md`; if data model direction changes,
  update `instructions/DATA_MODEL.md`.

## Repo Shape

- Root workspace uses `uv` with package members under `packages/`.
- `packages/goodomics` builds the `goodomics-core` distribution and provides the
  canonical `goodomics` Python import package.
- `packages/goodomics-full` builds the default `goodomics` distribution, which
  depends on `goodomics-core` with the full server/report/dashboard extras.
- Main CLI entry point: `packages/goodomics/src/goodomics/cli.py`.
- Core schemas, parsing, ingest, reporting, SDK, and storage live under
  `packages/goodomics/src/goodomics/`.
- Parser modules should be flat, descriptive files under
  `packages/goodomics/src/goodomics/parsers/`, such as `cbioportal.py` or
  `multiqc.py`. Do not create nested parser packages with generic names like
  `parsers/<source>/parser.py` unless a parser genuinely needs multiple
  source-specific modules.
- API, MCP, server settings, and dashboard serving live under
  `packages/goodomics/src/goodomics/server/`.
- React/Vite dashboard source lives in `packages/goodomics/dashboard/`.
- Built dashboard assets are generated into
  `packages/goodomics/src/goodomics/server/web/static/`, ignored by git, and
  included in Python wheels when present during package build.
- Docs are MkDocs Markdown files in `docs/`, with navigation and Material theme
  settings in `mkdocs.yml`.
- Server Dockerfile lives at `docker/Dockerfile.server`.

## Commands

```bash
uv sync --all-packages --group dev
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
uv run mkdocs build
```

Useful CLI checks:

```bash
uv run --package goodomics goodomics --help
uv run --package goodomics-core goodomics --help
uv run --package goodomics goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///./goodomics.db uv run --package goodomics goodomics serve --reload
```

Dashboard commands:

```bash
npm --prefix packages/goodomics/dashboard ci
npm --prefix packages/goodomics/dashboard run build
```

Package build with dashboard assets:

```bash
scripts/build-python-packages.sh
```

Docker build check:

```bash
docker build -f docker/Dockerfile.server -t goodomics/server:local .
```

Use `uv run pytest` as the main verification command for Python changes. For
packaging or CLI changes, also run Ruff, Pyright, and both package builds when
feasible. For dashboard or Docker changes, run the relevant npm or Docker build.
For documentation changes, and for CLI or user-facing SDK/API changes that
should update docs, run `uv run mkdocs build` when feasible.

## Coding Style

- The app has not been deployed anywhere yet. For code changes, do not add
  database migrations, backwards compatibility layers, compatibility shims, or
  migration strategy docs unless the user explicitly asks for them. Prefer
  directly updating the current schema, models, tests, fixtures, and docs.
- Use Ruff as the canonical Python formatter and linter. Prefer
  `uv run ruff format .` for formatting and `uv run ruff check --fix .` for
  safe lint fixes before committing Python changes.
- Keep the configured 88-character line length. Let Ruff wrap calls, dicts, and
  comprehensions instead of hand-compressing code to fit on one line.
- Install commit hooks with `uv run pre-commit install` after syncing the dev
  environment. Hooks run Ruff fixes and formatting on staged files; CI also runs
  `uv run ruff format --check .` and `uv run ruff check .`.
- Prefer readable structure over dense expressions: split complex conditions,
  payload construction, or nested transformations into named intermediate values
  when that makes the code easier to scan.
- Add docstrings or lightweight comments for public APIs, parser/ingest helpers,
  storage boundaries, non-trivial transformations, trust boundaries, and
  important constraints; skip obvious one-line helpers and comments that merely
  restate the code.
- For public Python APIs rendered in MkDocs or shown in editor hover, follow a
  non-duplicative docstring pattern: module/class docstrings should explain
  purpose, lifecycle, examples, and behavior; dataclass/model attribute
  docstrings should describe individual fields. Avoid repeating the same field
  descriptions in both a class-level `Attributes:` section and per-attribute
  docstrings. If a class does not use per-attribute docstrings, a concise
  class-level `Attributes:` section is fine.

## Documentation Guidelines

- Keep edits scoped to the requested task.
- Preserve the current `uv` workspace and package split unless the task is
  explicitly about packaging architecture.
- Treat `goodomics` as the unified product and CLI surface.
- Keep model definitions and shared product concepts in the canonical
  `goodomics` package; server code should consume shared schemas/storage rather
  than defining parallel concepts when practical.
- When changing CLI behavior, CLI flags, user-facing SDK APIs, custom parser
  APIs, or other user-facing Python interfaces, update the MkDocs documentation
  in `docs/` and `mkdocs.yml` in the same change when relevant.
- Use concrete, technical, approachable copy. Avoid generic SaaS language.
- Do not rewrite unrelated copy, assets, formatting, lockfiles, generated
  dashboard assets, or docs.
- Dashboard build output under `goodomics/server/web/static` is generated and
  ignored by git. If dashboard source changes, run the dashboard build for
  verification, but do not commit hashed static assets.

## Frontend And Reporting Stack

- Use Rich for user-facing progress and logging in long-running CLI workflows,
  especially ingestion and report generation. Future parsers should expose quiet
  library APIs by default, then let CLI entry points opt into Rich progress for
  parse/discovery, SQL control writes, analytical-store writes, bulk loads, and
  report rendering. Keep progress bars visually stable: put the spinner/progress
  bar/counts before changing descriptive text, use a fixed bar width, and clip
  long descriptions instead of letting them compress the bar.
- Prefer shadcn/ui-style components with Tailwind, Radix primitives, and
  `lucide-react` icons for dashboard UI. Keep components editable and consistent
  with Goodomics' biotech/R&D product feel.
- Use TanStack primitives for dashboard data workflows already in the app.
  Reach for TanStack Table and virtualization for large tabular views.
- Use Apache ECharts as the default report and dashboard charting engine.
  Prefer a Goodomics-owned chart/spec layer that compiles to ECharts options
  instead of exposing raw ECharts config as the primary user interface.
- Default reports should be self-contained offline HTML files: no CDN
  dependencies, no required internet access, and no required external JS/CSS
  assets for the normal `goodomics report` path.
- YAML or JSON report templates should be the portable template format for the
  CLI and dashboard. The dashboard report builder should edit the same model
  rather than introducing a separate dashboard-only template format.
- For large chart payloads, prefer summary views, downsampling, static SVG/PNG
  output, or explicit opt-in expansion instead of embedding huge raw datasets in
  report HTML.
- Do not add Plotly, Observable, Vega-Lite, uPlot, or another charting stack
  unless a concrete report/dashboard feature clearly requires it. If one is
  added, keep it behind the Goodomics report/chart abstraction.

## Product Guardrails

- Lead with a concrete adoption path: point Goodomics at outputs, generate a
  report, add durable context over time.
- Do not position Goodomics as a LIMS, workflow orchestrator, broad biological
  interpretation engine, giant data lake, or blackbox AI decision-maker.
- AI/agent language should emphasize grounded assistance: agents can query,
  summarize, compare, draft, and suggest, while deterministic policies and human
  review remain the trust layer.
- Visual and UI work should feel credible for biotech/R&D while staying
  approachable. Avoid generic DNA stock imagery, abstract SaaS gradients, and
  mascot-heavy first impressions.
