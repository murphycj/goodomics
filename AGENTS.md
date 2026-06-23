# Goodomics Agent Guide

This repo contains the Goodomics Python monorepo. Keep this file lightweight,
operational, and focused on how to work in the repo.

## Product Source Of Truth

- Use `instructions/PRODUCT.md` for product narrative, positioning, messaging,
  feature framing, competitive context, audience, product modes, priorities, and
  trust boundaries.
- Use `instructions/DATA_MODEL.md` for data model terminology and schema
  direction, including projects, runs, samples, subjects, processed samples /
  `run_samples`, files, data profiles, observations, SQL control tables, DuckDB
  analytical tables, and MCP/data-query concepts.
- Do not duplicate product or data model briefs here. If product strategy
  changes, update `instructions/PRODUCT.md`; if data model direction changes,
  update `instructions/DATA_MODEL.md`.

## Repo Shape

- Root workspace uses `uv` with package members under `packages/`.
- `packages/goodomics` builds the `goodomics-core` distribution and provides the
  canonical `goodomics` Python import package.
- `packages/goodomics-full` builds the default `goodomics` distribution, which
  depends on `goodomics-core` with the `server`, `reports`, `tables`, and `sqlite`
  extras.
- Main CLI entry point: `packages/goodomics/src/goodomics/cli.py`.
- Core schemas, parsing, ingest, reporting, SDK, and storage live under
  `packages/goodomics/src/goodomics/`.
- API, MCP, server settings, and dashboard serving live under
  `packages/goodomics/src/goodomics/server/`.
- React/Vite dashboard source lives in `packages/goodomics/dashboard/`.
- Built dashboard assets are generated into
  `packages/goodomics/src/goodomics/server/web/static/`, ignored by git, and
  included in Python wheels when present during package build.
- Docs are portable MDX files in `docs/`.
- Server Dockerfile lives at `docker/Dockerfile.server`.

## Commands

```bash
uv sync --all-packages --group dev
uv run pytest
uv run ruff check .
uv run pyright
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
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

## Documentation Guidelines

- Keep edits scoped to the requested task.
- Preserve the current `uv` workspace and package split unless the task is
  explicitly about packaging architecture.
- Treat `goodomics` as the unified product and CLI surface.
- Keep model definitions and shared product concepts in the canonical
  `goodomics` package; server code should consume shared schemas/storage rather
  than defining parallel concepts when practical.
- Use concrete, technical, approachable copy. Avoid generic SaaS language.
- Do not rewrite unrelated copy, assets, formatting, lockfiles, generated
  dashboard assets, or docs.
- Dashboard build output under `goodomics/server/web/static` is generated and
  ignored by git. If dashboard source changes, run the dashboard build for
  verification, but do not commit hashed static assets.

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
