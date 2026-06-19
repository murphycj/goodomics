# goodomics

Goodomics is a Python monorepo with:

- `goodomics`: a lightweight SDK + CLI for cohort-aware QC
- `goodomics-server`: an optional FastAPI + MCP + database server

## Workspace

This repository uses a root `uv` workspace with package members under `packages/`.

### Core package

```bash
uv run --package goodomics goodomics --help
uv run --package goodomics goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

### Server package

```bash
uv run --package goodomics-server goodomics-server --help
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///./goodomics.db uv run --package goodomics-server goodomics-server serve
```

## Development

```bash
uv sync --all-packages --group dev
uv run pytest
uv run ruff check .
uv run pyright
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-server
```

## Licensing

- `goodomics`: Apache-2.0
- `goodomics-server`: FSL-1.1-Apache-2.0
