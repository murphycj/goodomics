# Goodomics Product Brief

Goodomics is an early-stage Python package for cohort-aware QC and durable
context around omics computational outputs.

The adoption path should stay simple:

```bash
pip install goodomics
goodomics report ./results
```

Start with a folder of pipeline outputs. Get a clear QC report. Add durable
context over time.

The broader product direction:

> Goodomics is an open, deploy-anywhere context layer for omics computational
> work.

Goodomics is not a LIMS, workflow orchestrator, broad biological interpretation
engine, giant data lake, or blackbox AI decision-maker. It sits after whatever
system already runs the workflow and helps teams preserve, query, compare, and
review the outputs of computational work.

QC/reporting is the first concrete wedge. The long-term product is broader:
structured context for production workflows, exploratory analyses, tool
benchmarks, parameter sweeps, metrics, artifacts, provenance, cohorts, policies,
references, reports, and decisions.

## Package Contract

Goodomics should feel like one product with multiple use modes.

Default full install:

```bash
pip install goodomics
```

Includes the CLI, SDK, report generation, local storage, API server, MCP server,
and dashboard runtime.

Lightweight install:

```bash
pip install goodomics-core
```

Provides the same `goodomics` Python import package and command-line entry point
for users who only need the SDK, parsers, report generation, and lightweight
pipeline integration.

The CLI should remain unified:

```bash
goodomics report ./results
goodomics init
goodomics ingest ./results --project my-project
goodomics serve
goodomics ui
```

Do not treat the server/dashboard as a separate branded product. They are part
of the same Goodomics workflow for teams that want local browsing, report
template editing, database-backed run tracking, API access, or MCP access.

## Product Boundaries

Goodomics should help users answer questions like:

- Does this run look good?
- What did this workflow, analysis, or benchmark produce?
- Does this sample look normal compared with previous samples?
- Which metrics are outliers?
- Which artifacts, logs, parameters, references, and tool versions were attached
  to this output?
- What cohort, report template, or QC policy was active?
- Can this review or decision be reproduced later?

The key differentiator is versioned, queryable context:

> This run was evaluated against this cohort, using this report version and this
> QC policy version.

Goodomics should provide computational and operational context. It should not
claim to make final scientific or QC decisions for users.

## Product Modes

### Standalone Report Mode

No account, no database, no setup.

```bash
goodomics report ./results
```

Outputs a shareable HTML report. This is the initial adoption path and should
stay as easy to try as MultiQC.

### Local Database Mode

For individuals and small teams.

```bash
goodomics init
goodomics ingest ./results --project my-project
goodomics ui
```

Uses SQLite by default and should also support Postgres for more durable local
or team deployments. Runs locally, in Docker, on HPC, or in private
infrastructure.

### Pipeline Integration Mode

For Nextflow, Snakemake, WDL, shell workflows, notebooks, and internal pipelines.

```bash
goodomics ingest ./results \
  --project rnaseq-core \
  --report rnaseq-qc@v3 \
  --cohort production-rnaseq-hg38@2026-05 \
  --run-id 2026-06-16_batch_042
```

Goodomics should be useful as a final workflow step that emits a report, stores
metrics and artifacts, or sends run context to a local or remote Goodomics
server.

### API, Dashboard, And MCP Mode

For browsing and querying run context.

```bash
goodomics serve
```

The server should expose:

- API routes for runs, samples, metrics, artifacts, reports, report templates,
  cohorts, and QC policies
- a dashboard for browsing and editing stored context
- MCP access so agents can query structured run history instead of scraping
  random files

### Future Hosted Mode

Hosted or managed Goodomics may add auth, sharing, backups, scheduled imports,
artifact storage, alerting, managed databases, and team workflows.

Keep this as a future direction. The open, deploy-anywhere Python package should
remain the core product surface.

## Core Concepts

Suggested object model:

- Project
- Assay
- Run
- Sample
- Metric
- Artifact
- Cohort
- Reference set
- QC policy
- Threshold rule
- Report template
- Report version
- QC decision
- Parser plugin
- Agent or MCP tool
- Interpretation note

Suggested hierarchy:

```text
Project
  Assay
    Batch / sequencing run / workflow run
      Sample
        Library / lane / replicate / modality
          Metrics / files / calls / artifacts
```

Suggested bundle format:

```text
goodomics_bundle/
  run.json
  samples.json
  metrics.jsonl
  files.json
  thresholds.yaml
  workflow.json
  provenance.json
  report.html
```

## Near-Term Feature Priorities

- Auto-discover common pipeline outputs
- Ingest MultiQC output, Nextflow trace files, logs, custom CSV/TSV/JSON/YAML,
  and common artifacts
- Generate standalone HTML reports
- Store runs, samples, metrics, logs, reports, references, provenance, and
  artifacts
- Create and export report templates for workflow integration
- Create cohorts from previous runs and samples
- Compare new runs against historical cohorts and trusted references
- Define visual thresholds for metrics
- Version QC policies, report templates, cohorts, references, and review
  decisions
- Provide a web UI for browsing runs, samples, metrics, cohorts, policies, and
  reports
- Offer a Python API for custom metrics
- Expose MCP/API access for structured run-history queries

## Python API Direction

The SDK should make lightweight instrumentation easy:

```python
import goodomics as go

with go.run(name="rnaseq_batch_042", assay="bulk_rnaseq") as run:
    run.log_context(
        pipeline="nf-core/rnaseq",
        pipeline_version="3.18",
        genome="GRCh38",
        aligner="STAR",
    )
    run.log_sample("S1", sample_type="tumor", batch="B42")
    run.log_metric("S1", "pct_mapped", 91.2, unit="percent")
    run.log_metric("S1", "duplication_rate", 38.4, unit="percent")
    run.log_artifact("multiqc_report.html")
    run.evaluate(reference_set="last_100_passed_runs")
```

The same tracking model should also work for exploratory and method-development
work:

```python
with go.run(name="variant_caller_benchmark_v12", assay="germline_wgs") as run:
    run.log_context(tool="new-caller", version="0.8.1", truth_set="GIAB-HG002")
    run.log_metric("HG002", "precision", 0.992)
    run.log_metric("HG002", "recall", 0.987)
    run.log_artifact("benchmark_plots/pr_curve.png")
```

## Config Direction

Goodomics configs and exported report templates should be workflow-friendly:

```yaml
project: rnaseq_qc
assay: bulk_rnaseq

inputs:
  - type: multiqc
    path: multiqc_data/
  - type: nextflow_trace
    path: trace.txt
  - type: custom_table
    path: qc/custom_metrics.tsv

metrics:
  pct_mapped:
    label: Percent mapped
    unit: percent
    direction: higher_is_better
    warning: "< 75"
    fail: "< 60"
    group_by: [sample_type, organism]

reference_sets:
  production_baseline:
    include:
      status: pass
      pipeline_version: ">=2.0"

reports:
  run_summary:
    sections:
      - overview
      - outliers
      - mapping
      - duplication
      - expression_complexity
```

## AI And MCP Trust Boundary

Goodomics can expose structured context through APIs and MCP so agents can query
run history without scraping random files.

Good AI-assisted features:

- Explain unfamiliar metrics in plain language
- Summarize sample-level or run-level QC issues
- Query run history in natural language through MCP
- Suggest parser schemas for new outputs
- Draft QC notes and run summaries
- Compare outlier samples to a cohort or reference set

Trust boundary:

> Agents query, compare, summarize, draft, and suggest. Goodomics preserves
> structured evidence. Scientists and teams make the final call.

Avoid implying that AI makes final QC or scientific decisions. Deterministic
thresholds, cohort comparisons, stored references, and user-reviewed policies
should remain the source of truth.
