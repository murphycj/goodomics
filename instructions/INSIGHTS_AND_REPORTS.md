# Goodomics Insights And Reports Guide

This file is the source of truth for saved insight and report behavior.

## Version 2 definition

Every surface uses the same complete, strict envelope:

```json
{
  "version": 2,
  "name": "Cancer types",
  "query": { "kind": "summary" },
  "view": { "kind": "table" }
}
```

There is no version 1 reader or universal `analysis.values` grammar. Definitions are
normalized deterministically, omit empty/no-op properties in compact displays, and
retain analytically important defaults. Physical tables, columns, adapters, SQL, and
internal keys are never serialized.

Canonical field references are `<contract>/<field>` or
`metadata/<entity>/<field>`. Keep feature, region, cohort, occurrence, and coverage
selectors separate from field references. Effective output aliases use `as` when
present and otherwise preserve the canonical field string; aliases must be unique.

## Query families

`query` is a discriminated union keyed by `kind`:

| Kind | Main bindings | Core behavior |
|---|---|---|
| `rows` | grain, columns | Identity-preserving retrieval |
| `summary` | grain, groups, aggregations, calculations | Descriptive grouping |
| `relationship` | X, Y, match identity | Matched raw measures |
| `distribution` | value, split fields, bins/summaries | Raw distributions |
| `series` | position, series fields, measurements | Ordered points |
| `matrix` | row, column, raw value | Bounded pivot |
| `alteration_matrix` | features, entities, states, coverage | OncoPrint states |
| `variant_position` | position, frequency, color/annotations | Lollipop recurrence |
| `genome_profile` | coordinate, value, groups | Genomic layout |
| `survival` | duration, event, groups, provider | Provider-backed modeling |
| `timeline` | subject, start/end, track, label | Subject-event layout |
| `association` | features, states, entities, coverage | Descriptive co-occurrence |

Common properties cover filters, ordering, bounded limits, deterministic sampling,
and occurrence selection. `referenced_fields(query)` is the single internal source
for permissions, resolution, provenance, explanation, and cache identity.

Core may select, filter, sort, join, count, distinct-count, sum, average, min/max,
calculate explicit eligible percentages, assemble histograms/categories, pivot raw
matrices, and perform domain-aware descriptive layouts. Core never silently derives
scientific measures or runs inferential/model-dependent methods.

Mann–Whitney, Kruskal–Wallis, Fisher/chi-square significance, multiple-testing
correction, Kaplan–Meier/log-rank, survival regression, differential expression,
enrichment, clustering, normalization, batch correction, and mutual-exclusivity
significance require a registered analysis provider or a precomputed result contract.
Provider execution records method/version, parameters, inputs, resolved occurrences,
output contract, time, and reference context.

## Validation and execution

Validation proceeds through schema, reference parsing, catalog resolution,
permissions/project scope, scalar and semantic bindings, joins/matching,
coverage/occurrence checks, core/provider capability, query/view compatibility, and
result-size limits. Errors identify the configuration path and canonical reference.

The runner registry is keyed by query kind. Runners resolve catalog fields, request
trusted logical relations from adapters, compile parameterized SQL, and return a
typed result with provenance, coverage, warnings, provider requirements, and cache
fingerprints. Compiled SQL is never authoritative.

Inline results default to 1,000 rows and hard-stop at 10,000. Full export is
file-backed. Matrix limits default to 250,000 cells and hard-stop at 1,000,000.
Sampling is deterministic and runs after query completion.

`explain_query` is deterministic application code for every family. It resolves
display labels when possible and describes grain, grouping, calculations,
denominator, matching, important filters, occurrence selection, and provider needs.
Validation, preview, builder review, MCP, and AI all return the same explanation.

## Representative insight catalog

These are architectural acceptance cases. All are representable; provider-backed
cases remain explicit.

1. Entity metadata table — `rows`, core.
2. Cross-assay feature scatter — `relationship`, core.
3. Genomic burden scatter — `relationship`, core over precomputed burden fields.
4. Categorical frequency summary — `summary`, core.
5. Numeric distribution — `distribution`, core.
6. Per-sample stacked QC bar — `rows`, core.
7. General QC statistics table — `rows`, core.
8. Positional QC profile — `series`, core.
9. QC status heatmap — `matrix`, core.
10. Feature-by-sample heatmap — `matrix`, core raw values.
11. OncoPrint — `alteration_matrix`, core with coverage.
12. Lollipop mutation plot — `variant_position`, core.
13. Variant detail table — `rows`, core.
14. Alteration-frequency summary — `summary`, core with eligible coverage.
15. Copy-number genomic profile — `genome_profile`, core.
16. Survival curve — `survival`, provider or precomputed result.
17. Subject timeline — `timeline`, core.
18. Group comparison — `distribution`, descriptive core; tests require provider.
19. Co-occurrence/exclusivity matrix — `association`, descriptive core; significance
    requires provider.
20. Run-history trend — `series`, core.

## Builder and views

The builder starts with query family, then presents only that family's editor. It
searches fields through the runtime catalog, stores canonical strings, filters views
by typed-result compatibility, shows provider requirements and the deterministic
explanation, and requires a successful preview of the exact query fingerprint before
save. Switching family replaces incompatible family-specific properties.

Views are a strict union keyed by `kind` and contain presentation only. Table,
scatter, metric, histogram/category, box/violin, heatmap, and specialized views are
compatible only with declared query result families. ECharts is an implementation
detail. Coverage and missingness remain visible even when a value is hidden.

## Reports, AI, and MCP

Reports are version 2 grids referencing saved insight IDs. Validate dependency
existence, ownership, permissions, compatible report filters, and layout bounds.
Report filters intersect insight filters and cannot change a query's family,
bindings, matching, occurrence scope, or scientific meaning. Snapshots pin exact
occurrences; saved definitions resolve dynamically.

REST, dashboard, MCP, and AI share catalog discovery, validation, explanation, and
bounded preview. MCP/AI can search datasets/fields, read profiles/values, find joins,
discover families/providers, validate, preview, and export exact provenance-bearing
inputs. Saving is a distinct authorized action after successful preview. Logical SQL
is deferred until permission-scoped logical views can hide storage completely.
