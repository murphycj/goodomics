# Goodomics documentation

Goodomics is an open, deploy-anywhere context layer for omics computational
work. Start with a folder of pipeline outputs, generate a clear QC report, and
add durable run context over time.

```bash
pip install goodomics
goodomics report ./results
```

Goodomics is useful in a few modes:

- Standalone report generation for local or pipeline outputs.
- Lightweight Python SDK instrumentation.
- Local database mode for runs, samples, metrics, files, and reports.
- API, dashboard, and MCP access for browsing and querying run context.

!!! note "Initial adoption path"
    The first Goodomics workflow should stay simple: point it at outputs,
    generate a report, and add persistent context only when you need it.

## Documentation map

- [Getting started](getting-started.md): install Goodomics and generate the
  first standalone report.
- [Data model and storage](concepts/architecture.md): understand projects,
  runs, samples, contracts, control metadata, DuckDB analytics, and files.
- [Data contracts and fields](concepts/data-contracts.md): understand the
  semantic catalog and physical query routing.
- [CLI](interfaces/cli.md): run reports and ingest outputs from the command
  line.
- [Python SDK](interfaces/sdk.md): record runs, samples, metrics, and files from
  Python code.
- [Custom parsers](interfaces/custom-parsers.md): ingest lab-specific tables,
  dataframes, and notebook objects without writing a full plugin.
- [Server](interfaces/server.md): run the optional FastAPI, MCP, database, and
  dashboard server.
- [Dashboard](interfaces/dashboard.md): browse runs and edit reports and insights.
- [Insights and reports](reports/index.md): build, execute, save, compose, and
  render analytical tables and charts.

## Trust boundary

Goodomics helps preserve, query, compare, and review omics computational
outputs. It should not be treated as a LIMS, workflow orchestrator, broad
biological interpretation engine, giant data lake, or blackbox AI
decision-maker.

Agents and AI tools can query, summarize, compare, draft, and suggest against
Goodomics context. Deterministic storage, provenance, policies, and human review
remain the trust layer.
