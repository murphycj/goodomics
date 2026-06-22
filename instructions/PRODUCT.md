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

## Related Source Of Truth

Use `instructions/DATA_MODEL.md` for detailed data model terminology, SQL
control table direction, DuckDB analytical table direction, data profiles,
processed samples, files, and MCP/data-query concepts. Keep this file focused
on product direction, user-facing framing, adoption path, boundaries, and
priorities.

The broader product direction:

> Goodomics is an open, deploy-anywhere context layer for omics computational
> work.

Goodomics is not a LIMS, workflow orchestrator, broad biological interpretation
engine, giant data lake, or blackbox AI decision-maker. It sits after whatever
system already runs the workflow and helps teams preserve, query, compare, and
review the outputs of computational work.

Goodomics should make omics outputs agent-ready and MCP-ready by default: the
same run history, metrics, files, templates, and policies that humans browse in
the UI should also be available as structured context that agents can query,
summarize, compare, and draft against through MCP and API access.
Deterministic storage and reviewable provenance remain the trust layer.

QC/reporting is the first concrete wedge. The long-term product is broader:
structured context for production workflows, exploratory analyses, tool
benchmarks, parameter sweeps, metrics, files, provenance, cohorts, policies,
references, reports, and decisions.

The default storage path should stay boring and easy: SQLite for product and
project metadata, DuckDB for local analytical tables, and ordinary filesystem
paths or object storage for files. As teams grow, Goodomics should be able to swap
SQLite for Postgres/MySQL and optionally add larger analytical backends, without
changing the basic adoption path.

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
- Which files, logs, parameters, references, and tool versions were attached
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

Uses SQLite by default for the control plane and DuckDB for project-level
analytics. The control plane stores users, projects, runs, samples, permissions,
reports, cohorts, policies, and file metadata. Each project can have its own
DuckDB analytical store for metrics and omics-shaped tables.

Goodomics should also support Postgres or MySQL for more durable local or team
deployments. Runs locally, in Docker, on HPC, or in private infrastructure.

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
metrics and files, or sends run context to a local or remote Goodomics
server.

### API, Dashboard, And MCP Mode

For browsing and querying run context.

```bash
goodomics serve
```

The server should expose:

- API routes for runs, samples, metrics, files, reports, report templates,
  cohorts, and QC policies
- a dashboard for browsing and editing stored context
- MCP access so agents can query structured run history instead of scraping
  random files

### Future Hosted Mode

Hosted or managed Goodomics may add auth, sharing, backups, scheduled imports,
file storage, alerting, managed databases, and team workflows.

Keep this as a future direction. The open, deploy-anywhere Python package should
remain the core product surface.

## Storage And Data Model Direction

Goodomics should keep a layered storage model: a control store for product
metadata, a file store for original and derived evidence, and a project-level
analytical store for queryable metrics and omics-shaped data. SQLite should
remain the default control store, DuckDB should be the default local analytical
store, and ordinary files or object storage should hold reports, logs, pipeline
outputs, BAM/VCF files, notebooks, plots, and other evidence.

The analytical model should be modular rather than one universal table. Generic
metrics should remain the lowest-friction target for arbitrary QC and pipeline
outputs, while richer data profiles can unlock typed storage, validation, query
performance, UI behavior, and MCP/agent understanding for variants, expression,
copy-number calls, genomic intervals, methylation, annotations, and future data
families.

The ingestion and analytical storage hierarchy should stay explicit:

- Generic metrics are the default target for arbitrary QC and pipeline outputs.
- Array, matrix, or blob-like payloads are supported when a result is naturally
  consumed as one logical object.
- Typed omics tables exist for data families with distinct shapes and access
  patterns, such as variants, gene or transcript expression, genomic intervals,
  copy-number alterations, methylation, and annotations.
- Derived tables or views may duplicate and reshape canonical data for common
  queries, such as sample-centric browsing, metric-centric comparison,
  gene-centric lookup, or region-centric lookup.

Use `instructions/DATA_MODEL.md` as the canonical reference for data model terms
and table direction, including processed samples, data profiles, observations,
SQL control tables, DuckDB analytical tables, and derived query layouts.

## Core Concepts

The user-facing model should stay approachable:

```text
Sample = what was processed.
Run = what happened.
Processed sample = that sample in that run.
Data profile = what kind of data was produced.
Observation = a value, call, or measurement inside that profile.
Cohort or reference set = selected processed samples.
```

Goodomics should expose bioinformatics-shaped concepts without becoming a LIMS.
Projects, runs, samples, optional subjects, files, data profiles, cohorts,
reference sets, QC policies, report templates, review decisions, parser plugins,
and MCP tools should work together as one product surface. Detailed terminology
and schema direction live in `instructions/DATA_MODEL.md`.

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
  and common output files
- Generate standalone HTML reports
- Store runs, samples, metrics, logs, reports, references, provenance, and file
  metadata while preserving pointers to original files
- Store project-level analytical data in DuckDB by default
- Support generic metrics, matrix-like payloads, and typed omics tables for
  variants, expression, genomic intervals, CNAs, and related data families
- Add derived analytical tables or views for common sample-, metric-, gene-, and
  region-centric queries when useful
- Create and export report templates for workflow integration
- Create cohorts from previous processed samples
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
    run.log_file("multiqc_report.html")
    run.evaluate(reference_set="last_100_passed_runs")
```

The same tracking model should also work for exploratory and method-development
work:

```python
with go.run(name="variant_caller_benchmark_v12", assay="germline_wgs") as run:
    run.log_context(tool="new-caller", version="0.8.1", truth_set="GIAB-HG002")
    run.log_metric("HG002", "precision", 0.992)
    run.log_metric("HG002", "recall", 0.987)
    run.log_file("benchmark_plots/pr_curve.png")
```

The API should also support progressively more structured data when users have
well-shaped omics outputs:

```python
with go.run(name="rnaseq_batch_042", assay="bulk_rnaseq") as run:
    run.log_table("counts", "counts.tsv", data_type="expression_matrix")
    run.log_table("variants", "calls.vcf.gz", data_type="small_variants")
```

Generic metrics and files should remain the lowest-friction path. Typed
data should add validation, better query performance, and richer UI behavior
without becoming mandatory for basic reporting.

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
    data_type: generic_metrics
  - type: table
    path: quant/gene_counts.tsv
    data_type: expression_matrix
  - type: vcf
    path: variants/calls.vcf.gz
    data_type: small_variants

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
