# Contributing to Goodomics

Goodomics uses a root `uv` workspace with package members under `packages/`.
Install the development dependencies from the repository root:

```bash
uv sync --all-packages --group dev
uv run pre-commit install
```

The pre-commit hook runs Ruff lint fixes and formatting on staged Python files.
If Ruff updates a file during a commit, review and stage the formatting change,
then commit again. To check the entire repository at any time, run:

```bash
uv run pre-commit run --all-files
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
npm --prefix packages/goodomics/dashboard ci
npm --prefix packages/goodomics/dashboard run dev
npm --prefix packages/goodomics/dashboard run build
```

## Maintain the API contract

Goodomics has one API ownership chain:

```text
Pydantic models -> FastAPI OpenAPI -> generated TypeScript SDK and Zod schemas -> React
```

The canonical insight and report models live in
`goodomics.schemas.insights`. The OpenAPI document and dashboard client are
derived, committed artifacts. Do not edit
`openapi/goodomics.openapi.json` or
`packages/goodomics/dashboard/src/api/generated/` by hand.

Export or regenerate each artifact independently with:

```bash
uv run python scripts/export-openapi.py
npm --prefix packages/goodomics/dashboard run generate:api
```

Regenerate the full chain or check that committed artifacts are current with:

```bash
bash scripts/generate-api.sh
bash scripts/check-api-codegen.sh
```

FastAPI route function names become generated operation names and are therefore
part of the stable client contract. Give every JSON endpoint a named Pydantic
request and response model, including `204` responses, then regenerate both
artifacts and update dashboard callers and tests. Keep Pydantic semantic and
cross-field validators authoritative; generated Zod schemas validate browser
JSON boundaries.

The dashboard's shared generated client owns bearer authentication, `401`
session invalidation, response validation, and API error normalization. Use the
small handwritten transport layer only for blobs and object URLs, multipart
uploads, YAML/JSON/HTML exports, streaming, arbitrary paths, and intentionally
dynamic result rows. These exceptions must use the same authentication and
`401` lifecycle. Dashboard builds and container builds consume committed
generated files and do not run Python code generation.

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
uv run ruff format --check .
uv run ruff check .
uv run pyright
bash scripts/check-api-codegen.sh
npm --prefix packages/goodomics/dashboard run test
npm --prefix packages/goodomics/dashboard run build
uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
uv run mkdocs build
```
