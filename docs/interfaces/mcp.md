# MCP integration

Goodomics can expose structured run context to MCP clients so agents can query
stored metrics, files, reports, templates, sample groups, and policies without
scraping random output files.

## Route separation

MCP routes remain separated under `/mcp/*`. API routes use `/api/v1/*`, and
dashboard routes fall back to React routing.

## Agent-ready context

The same run history, metrics, files, templates, and policies that humans browse
in the dashboard should also be available as structured context that agents can
query, summarize, compare, and draft against.

!!! note "Review remains the trust layer"
    MCP access does not turn Goodomics into a blackbox decision-maker.
    Deterministic storage, reviewable provenance, policies, and human review
    remain responsible for trust.
