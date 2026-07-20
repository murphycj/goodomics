# Contributing to Goodomics

Goodomics uses a root `uv` workspace with package members under `packages/`.
Install the development dependencies from the repository root:

```bash
uv sync --all-packages --group dev
```

## Work with the Python packages

Run the full `goodomics` package:

```bash
uv run --package goodomics goodomics --help
uv run --package goodomics goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

Run the lightweight `goodomics-core` package:

```bash
uv run --package goodomics-core goodomics --help
uv run --package goodomics-core goodomics report ./examples/rnaseq --out /tmp/goodomics_report.html
```

## Work on the server and dashboard

Start the development server with reload enabled:

```bash
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///.goodomics/goodomics.db uv run --package goodomics goodomics serve --reload
```

Run or build the dashboard:

```bash
npm --prefix packages/goodomics/dashboard run dev
npm --prefix packages/goodomics/dashboard run build
```

## Work on the documentation

Documentation source lives in `docs/`, with navigation and Material theme
settings in `mkdocs.yml`. The files are portable Astro-compatible MDX so the
marketing site can import or sync them into its `docs` content collection and
render them at `/docs/*`.

Build the documentation and serve it locally with:

```bash
uv run mkdocs build
uv run mkdocs serve --dev-addr 127.0.0.1:8001
```

The local documentation server is available at `http://127.0.0.1:8001/docs/`.

## Validate changes

Run the relevant checks before opening a pull request:

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
```
