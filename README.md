# goodomics

Goodomics is a Python monorepo with:

- `goodomics`: the default full install for reports, ingestion, local storage, API,
  MCP, and the dashboard
- `goodomics-core`: the lightweight SDK/CLI package for pipeline and report-only use

## Workspace

This repository uses a root `uv` workspace with package members under `packages/`.

### Full package

```bash
uv run --package goodomics goodomics --help
uv run --package goodomics goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

### Server and dashboard

```bash
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///./goodomics.db uv run --package goodomics goodomics serve --reload
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
