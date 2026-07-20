<div align="center">
  <img src="public/logo-name.png" alt="Goodomics logo" height="64">
</div>

<br>

> ## ⚠️ Warning: Goodomics is under heavy development and is not ready for production use.

Goodomics turns omics data and bioinformatics outputs into visual, structured, and queryable context. Start with a folder of pipeline results and generate a clear report. As your needs grow, add durable context around runs, samples, metrics, files, sample groups, and QC policies. Explore it through the dashboard, SQL, APIs, or AI agents. For shared deployments, enable user management for teams and organizations.

Explore Goodomics in the live demo: [demo.goodomics.com](https://demo.goodomics.com).

<br>

![Overview of how Goodomics works](https://www.goodomics.com/marketing/how-goodomics-works.png)

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for workspace setup, development
commands, testing, and documentation workflows.

## Licensing

- `goodomics`: Apache-2.0
- `goodomics-core`: Apache-2.0
