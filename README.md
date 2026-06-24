# goodomics

> ⚠️ Warning: Goodomics is under heavy development and is not ready for production use.

Goodomics is an early-stage Python package for cohort-aware QC and durable context around omics computational outputs. It starts from a folder of pipeline results, generates a clear report, and then lets you keep building up structured run history, files, metrics, and reviewable context over time. The same grounded context is meant to be agent-ready and MCP-ready, so humans and tools can work from the same run history, files, metrics, and policies.

The repo is organized as a Python monorepo with two package surfaces:

- `goodomics`: the default full install for reports, ingestion, local storage, API, MCP, and the dashboard runtime
- `goodomics-core`: the lightweight SDK/CLI package for pipeline and report-only use

## Install

```bash
pip install goodomics
```

## Quick Start

Start with a report:

```bash
goodomics report ./examples/rnaseq
```

Then initialize local state, ingest a run, and open the UI:

```bash
goodomics init
goodomics ingest ./examples/rnaseq --project my-project
goodomics serve
```

## Core Commands

```bash
goodomics --help
goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
goodomics init
goodomics ingest ./examples/rnaseq --project my-project
goodomics serve
```

## Workspace

This repository uses a root `uv` workspace with package members under `packages/`.

### Full package

```bash
uv run --package goodomics goodomics --help
uv run --package goodomics goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

### Server and dashboard

```bash
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///.goodomics/goodomics.db uv run --package goodomics goodomics serve --reload
cd packages/goodomics/dashboard && npm run dev
cd packages/goodomics/dashboard && npm run build
```

### Lightweight package

```bash
uv run --package goodomics-core goodomics --help
uv run --package goodomics-core goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

### Docs

Docs are authored as portable Astro-compatible MDX in `docs/`. The Astro marketing site should import or sync these files into a `docs` content collection and render them at `/docs/*`.

## Development

```bash
uv sync --all-packages --group dev
uv run pytest
uv run ruff check .
uv run pyright
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
```

## Licensing

- `goodomics`: Apache-2.0
- `goodomics-core`: Apache-2.0
