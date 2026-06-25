# Python SDK

Use the Goodomics Python SDK to record run, sample, metric, and file context
from Python code.

## Import the SDK

```python
from goodomics import run
```

The lightweight `goodomics-core` distribution should expose the same
`goodomics` import package and command-line entry point for users who only need
SDK, parser, report generation, and pipeline integration features.

## Record run context

```python
from goodomics import run

with run("rnaseq-batch-042", project="rnaseq-core", assay="bulk_rnaseq") as ctx:
    ctx.log_metric("S1", "pct_mapped", 97.2, unit="percent")
    ctx.metric("duplication_rate", 0.18)
    ctx.file("multiqc_report.html")
```

Logged SDK metrics are written to the DuckDB analytical store as generic metric
records, not to the SQL catalog database. The context manager records the run
and sample catalog metadata in SQLite, then flushes metric observations to the
project DuckDB store when the block exits successfully.

## Pipeline integration

The SDK should stay lightweight enough to use from Nextflow, Snakemake, WDL,
shell workflows, notebooks, and internal Python pipelines.

!!! info "Context over control"
    Goodomics sits after whatever system already runs the workflow. It records
    and reviews outputs; it should not become the workflow orchestrator.
