# Goodomics Documentation Guide

Use this file for Goodomics documentation rules, user-facing copy standards,
and documentation verification expectations.

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
- Dashboard build output under
  `packages/goodomics/src/goodomics/server/web/static/` is generated and
  ignored by git. If dashboard source changes, run the dashboard build for
  verification, but do not commit hashed static assets.

## Verification

- For documentation-only changes, run `uv run mkdocs build` when feasible.
- For CLI or user-facing SDK/API changes that should update docs, run
  `uv run mkdocs build` when feasible after updating the relevant docs.
