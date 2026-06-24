# CLI

The Goodomics CLI is the main entry point for standalone reports, local ingest,
and server startup.

## Inspect the command

```bash
goodomics --help
```

From a checkout of the repository:

```bash
uv run --package goodomics goodomics --help
```

## Generate a standalone report

```bash
goodomics report ./results --template rnaseq-qc.yaml --out report.html
```

The report command should support exported dashboard templates, so templates can
round-trip between local report generation and dashboard editing.

!!! note "Offline reports"
    Standalone reports should be self-contained HTML files by default. They
    should not require CDN-hosted JavaScript, CSS, fonts, or images.

## Ingest outputs

Use ingest when you want Goodomics to preserve run context in local or team
storage:

```bash
goodomics ingest ./results \
  --project rnaseq-core \
  --report rnaseq-qc@v3 \
  --cohort production-rnaseq-hg38@2026-05 \
  --run-id 2026-06-16_batch_042
```

## Start local services

```bash
goodomics serve
goodomics ui
```

`goodomics serve` starts the optional server surface. `goodomics ui` should stay
focused on the local dashboard workflow.
