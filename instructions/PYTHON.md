# Goodomics Python Guide

Use this file for Python package layout, uv commands, CLI checks, verification,
and Python coding style.

## Package Layout

- Root workspace uses `uv` with package members under `packages/`.
- `packages/goodomics` builds the `goodomics-core` distribution and provides
  the canonical `goodomics` Python import package.
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

## Python Commands

```bash
uv sync --all-packages --group dev
uv run pytest
uv run ruff format --check .
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

Package build with dashboard assets:

```bash
scripts/build-python-packages.sh
```

## Verification

- Use `uv run pytest` as the main verification command for Python changes.
- For packaging or CLI changes, also run Ruff, Pyright, and both package builds
  when feasible.
- For CLI or user-facing SDK/API changes that should update docs, update the
  relevant docs and run `uv run mkdocs build` when feasible. See
  `instructions/DOCS.md`.

## Coding Style

- Use Ruff as the canonical Python formatter and linter. Prefer
  `uv run ruff format .` for formatting and `uv run ruff check --fix .` for
  safe lint fixes before committing Python changes.
- Keep the configured 88-character line length. Let Ruff wrap calls, dicts, and
  comprehensions instead of hand-compressing code to fit on one line.
- Install commit hooks with `uv run pre-commit install` after syncing the dev
  environment. Hooks run Ruff fixes and formatting on staged files; CI also
  runs `uv run ruff format --check .` and `uv run ruff check .`.
- Prefer readable structure over dense expressions: split complex conditions,
  payload construction, or nested transformations into named intermediate
  values when that makes the code easier to scan.
- Add docstrings or lightweight comments for public APIs, parser/ingest
  helpers, storage boundaries, non-trivial transformations, trust boundaries,
  and important constraints; skip obvious one-line helpers and comments that
  merely restate the code.
- For public Python APIs rendered in MkDocs or shown in editor hover, follow a
  non-duplicative docstring pattern: module/class docstrings should explain
  purpose, lifecycle, examples, and behavior; dataclass/model attribute
  docstrings should describe individual fields. Avoid repeating the same field
  descriptions in both a class-level `Attributes:` section and per-attribute
  docstrings. If a class does not use per-attribute docstrings, a concise
  class-level `Attributes:` section is fine.
