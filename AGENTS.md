# Goodomics Agent Guide

This repo contains the Goodomics Python monorepo. Keep this file lightweight,
operational, and focused on how to work in the repo.

## Instruction Source Of Truth

- Use `instructions/PRODUCT.md` for product narrative, positioning, messaging,
  feature framing, competitive context, audience, product modes, priorities, and
  trust boundaries.
- Use `instructions/DATA_MODEL.md` for data model terminology and schema
  direction, including projects, runs, samples, subjects, processed samples /
  `run_samples`, data imports, files, data contracts, observations, SQL metadata
  tables, DuckDB analytical tables, and MCP/data-query concepts.
- Use `instructions/PYTHON.md` for Python package layout, uv commands, CLI
  checks, verification, and Python coding style.
- Use `instructions/FRONTEND.md` for dashboard, report-rendering, charting,
  visual, and UI guidance.
- Use `instructions/INSIGHTS_AND_REPORTS.md` for saved insight/report builder
  behavior, chart grammar, context/linker rules, result-size policies, and
  AI insight guardrails.
- Use `instructions/DOCS.md` for documentation rules, user-facing copy
  standards, and documentation verification expectations.
- Keep this file operational. If product strategy, data model direction,
  frontend/reporting guidance, insight/report behavior, or documentation rules
  change, update the relevant file under `instructions/`.

The app has not been deployed anywhere yet. For code changes, do not add database migrations, backwards compatibility layers, compatibility shims, or migration strategy docs unless the user explicitly asks for them. Prefer directly updating the current schema, models, tests, fixtures, and docs.

## Repo Shape

- Python package layout, uv commands, CLI checks, verification, and coding
  style live in `instructions/PYTHON.md`.
- React/Vite dashboard source lives in `packages/goodomics/dashboard/`.
- Dashboard-specific React styling and performance guidance lives in
  `packages/goodomics/dashboard/AGENTS.md`; use it with
  `$vercel-react-best-practices` when editing dashboard React code.
- Built dashboard assets are generated into
  `packages/goodomics/src/goodomics/server/web/static/`, ignored by git, and
  included in Python wheels when present during package build.
- Docs are MkDocs Markdown files in `docs/`, with navigation and Material theme
  settings in `mkdocs.yml`.
- Server Dockerfile lives at `docker/Dockerfile.server`.

## Commands

- See `instructions/PYTHON.md` for Python setup, test, lint, typecheck, build,
  and CLI commands.
- See `instructions/DOCS.md` for documentation verification commands.

Dashboard commands:

```bash
npm --prefix packages/goodomics/dashboard ci
npm --prefix packages/goodomics/dashboard run build
```

Docker build check:

```bash
docker build -f docker/Dockerfile.server -t goodomics/server:local .
```

For dashboard or Docker changes, run the relevant npm or Docker build when
feasible.

## Pull request expectations

When creating or finalizing a pull request:

- Open it as ready for review unless the task is explicitly incomplete.
- Do not leave `[WIP]` in the title once implementation and tests are done.
- Add a PR description with:
  - Summary
  - Tests run
  - Notes or risks
