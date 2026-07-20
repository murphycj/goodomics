# Getting started

Install `goodomics`, generate a standalone report against pipeline results, then
move to the SDK or server when you need persistence.

## Install

```bash
pip install goodomics
```

For local development from the repository, sync the workspace and inspect the
CLI:

```bash
uv sync --all-packages --group dev
uv run --package goodomics goodomics --help
```

## Generate a report

Run the report command against a directory of workflow outputs:

```bash
goodomics report ./results --template rnaseq-qc.yaml --out report.html
```

The default report path is designed to be boring and portable: a self-contained
HTML file that can be shared or opened without a running Goodomics server.

!!! info "Standalone first"
    You do not need an account, database, dashboard, or hosted service to try
    Goodomics. The standalone report mode is the first adoption path.

## Add persistent context

When you want Goodomics to retain run history, initialize local database mode:

```bash
goodomics init
goodomics ingest ./results --project rnaseq-core
goodomics ui
```

SQLite is the default metadata store. DuckDB is the default
local analytical store for project-level tables.

See [Data model and storage](concepts/architecture.md) for how metadata,
analytical values, and files relate.

## Use the SDK

Use the Python SDK when you want workflow code, notebooks, or scripts to record
context directly:

```python
from goodomics import run

with run(
    "rnaseq-batch-042",
    project="rnaseq-core",
    analysis_type_id="rna_sequencing",
    method_id="nf-core/rnaseq",
    method_version="3.18",
) as ctx:
    ctx.log_metric("S1", "pct_mapped", 97.2, unit="percent")
```

## Parse custom outputs

Use [custom parsers](interfaces/custom-parsers.md) when you have a lab-specific
table, dataframe, or notebook object that Goodomics does not parse yet. You
write a small Python parser; Goodomics handles persistence.

## Run the server

Start the optional server when you want API, dashboard, database-backed run
tracking, or MCP access:

```bash
goodomics serve
```

For development from the repository:

```bash
uv run --package goodomics goodomics serve --reload
```
