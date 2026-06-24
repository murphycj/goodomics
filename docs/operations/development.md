# Development workflow

Use the root `uv` workspace for Python development and the dashboard package for
React work.

## Sync the workspace

```bash
uv sync --all-packages --group dev
```

## Validate Python changes

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## Build Python packages

```bash
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
```

## Work on the dashboard

```bash
npm --prefix packages/goodomics/dashboard ci
npm --prefix packages/goodomics/dashboard run build
```

## Work on the docs

```bash
uv run mkdocs serve
uv run mkdocs build
```

The MkDocs source lives in `docs/`, and the navigation hierarchy is defined in
`mkdocs.yml`.
