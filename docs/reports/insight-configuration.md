# Insight configuration

Saved insights, REST requests, MCP tools, AI drafts, and the dashboard use the same
strict version 2 document:

```json
{
  "version": 2,
  "name": "Cancer types",
  "query": {
    "kind": "summary",
    "grain": "subject",
    "group_by": [
      {"field": "cbioportal:clinical:subjects/cancer_type", "as": "cancer_type"}
    ],
    "aggregations": [
      {
        "field": "metadata/subject/subject_id",
        "aggregation": "count_distinct",
        "as": "subject_count"
      }
    ],
    "calculations": [
      {"calculation": "percent_of_total", "input": "subject_count", "as": "frequency"}
    ],
    "order_by": [{"by": "subject_count", "direction": "desc"}],
    "limit": 1000
  },
  "view": {"kind": "table"}
}
```

## Query families

Choose `query.kind` according to the analytical structure:

- `rows`: grain and selected columns;
- `summary`: groups, descriptive aggregations, and explicit percentages;
- `relationship`: X/Y measures matched by an approved identity;
- `distribution`: one value, optional splits, bins, and descriptive summaries;
- `series`: ordered position, series groups, and measurements;
- `matrix`: row identity, column identity, and raw cell value;
- `alteration_matrix`: features, entities, alteration states, and coverage selectors;
- `variant_position`: position, recurrence frequency, color, and annotations;
- `genome_profile`: genomic coordinate, value, and groups;
- `survival`: duration, event, groups, and explicit provider settings;
- `timeline`: subject, start/end, track, and label;
- `association`: features, states, entities, and coverage selectors.

Common query settings include filters, ordering, a bounded `limit`, deterministic
`sampling`, and occurrence `scope` on field selections. Inline results default to
1,000 rows and cannot exceed 10,000. Matrices default to 250,000 cells and cannot
exceed 1,000,000.

Field references remain strings in `<contract>/<field>` or
`metadata/<entity>/<field>` form. Use `as` only when a short or distinct output alias
is needed. References are resolved by the permission-scoped runtime catalog; queries
cannot name physical storage or SQL.

## Views and typed results

`view.kind` must be compatible with the query result. Row/summary results support
tables and appropriate category views; relationships support scatter/table;
distributions support histogram/box/violin/table; series support line/area/table;
matrices support heatmap/table; domain families support `oncoprint`, `lollipop`,
`genome_profile`, `survival`, `timeline`, or `association_matrix` views.

Every result includes its typed family payload, source/query provenance, coverage,
warnings, and provider requirements. The server compiles view options for rendering;
ECharts configuration and SQL are not saved definitions.

## Providers and previews

Core performs retrieval, deterministic descriptive summaries, and domain-aware
reshaping. Statistical tests, Kaplan–Meier estimation, regression, differential
expression, enrichment, clustering, and normalization require a registered analysis
provider or precomputed result contract. An unavailable provider produces an explicit
diagnostic; Goodomics never substitutes an approximation.

Validation returns a deterministic plain-language explanation. Before creating or
updating an insight, preview the exact definition and retain its
`preview_fingerprint`. Saving a different fingerprint is rejected.
