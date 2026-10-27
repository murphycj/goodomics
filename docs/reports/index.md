# Insights and reports

An insight is one reusable typed semantic query and compatible view. A report
arranges saved insights in a validated grid.

The builder first selects a query family, then shows only its bindings: columns for
rows, groups and aggregations for summaries, X/Y for relationships, value/splits for
distributions, positions and measurements for series, row/column/value for matrices,
or a domain-specific editor for alteration, variant-position, genomic-profile,
survival, timeline, and association queries.

Fields come from the permission-scoped runtime catalog and remain canonical strings.
The review step shows the server's deterministic explanation, coverage/provider
diagnostics, and exact preview status. A successful preview of the current query
fingerprint is required before saving.

Send a complete v2 definition to `POST /api/v1/insights/execute` for a bounded ad hoc
preview. Save it with `POST /api/v1/insights` and the returned
`preview_fingerprint`. Executable changes archive the previous definition. Saved
definitions remain dynamic; results and snapshots record resolved occurrences and
provenance.

Reports reference saved insights by ID:

```yaml
version: 2
name: RNA-seq QC
layout: { columns: 12, row_height: 64 }
insights:
  - id: mapping-rate
    layout: { x: 0, y: 0, width: 12, height: 4 }
refresh_policy: { mode: manual }
```

Report filters can narrow compatible insight inputs but cannot change query family,
bindings, matching, occurrence scope, or scientific meaning.

## Learn more

- [Insight configuration](insight-configuration.md)
- [Report configuration](report-configuration.md)
- [Compilation and execution](execution.md)
- [Use the JSON API from Python](python-api.md)
- [Report documents and rendering](report-templates.md)
