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

with run("rnaseq-batch-042") as ctx:
    ctx.metric("pct_mapped", 97.2)
    ctx.metric("duplication_rate", 0.18)
    ctx.file("multiqc_report.html")
```

## Pipeline integration

The SDK should stay lightweight enough to use from Nextflow, Snakemake, WDL,
shell workflows, notebooks, and internal Python pipelines.

!!! info "Context over control"
    Goodomics sits after whatever system already runs the workflow. It records
    and reviews outputs; it should not become the workflow orchestrator.
