# Insight compilation and execution

The server uses one planning pipeline for metadata and contract values. This
keeps result selection, matching, row limits, and visualization compilation
consistent across the dashboard, API, reports, and rendered snapshots.

## Value-planning pipeline

`execute_insight` performs these stages:

1. Strictly parse version 1 and expand deterministic defaults.
2. Validate the project, metadata fields, contracts, field types,
   aggregations, scopes, filters, view references, and chart constraints.
3. Fingerprint every referenced contract and metadata entity.
4. Reuse a matching cached result unless `refresh` is true.
5. Resolve each contract value through the occurrence-aware contract resolver,
   and each metadata value through the fixed project-scoped metadata query.
6. Apply value filters and aggregation.
7. Join results by the declared public grain and matching policy.
8. Derive visible table columns or chart series from `analysis.values` order,
   excluding `view.hidden_values` and required role bindings where appropriate.
9. Select random rows when requested, then apply `analysis.limit`.
10. Compile the selected view and persist an authorized cache entry.

Physical tables and freeform SQL are not insight inputs. Standalone
database-browser routes are unchanged and remain separate from insight
execution.

## Metadata values

Metadata queries are generated from a fixed entity/field mapping. They always
include the current project predicate. `analysis_type_id`, `method_id`, and
`method_version` are resolved through metadata joins to their public labels.
Sample, subject, run, and file identities are returned as public IDs.

## Contract resolution

For each contract value, the resolver joins project-scoped contracts, produced
run-contract occurrences, compatible analysis types and methods, runs,
run-sample availability, and biological samples. It applies the value's scope,
then ranks eligible occurrences when latest-per-sample selection is requested.

Diagnostics record exact resolved occurrences, excluded failures,
incompatibilities, missing identities, superseded results, represented methods
and versions, and mixed-version warnings. Rendered snapshots preserve this
resolved evidence even though the saved definition remains dynamic.

## Joining and conflicts

Each value is resolved independently into identity/value pairs. An outer join
uses the union of identities; an inner join uses the intersection. Multiple
distinct results for one value and identity are ambiguous, so the cell becomes
null and conflict diagnostics identify it. Coverage diagnostics report missing
cells per value. Histograms skip joining and retain separate distributions.

## Result envelope

Results include normalized `analysis` and `view` blocks plus bounded
`columns`, `column_labels`, `rows`, `plot_table`, diagnostics, computed time,
cache state, returned row count, and total row count. Metric and chart views add
their compiled payloads. Each
value's effective reference—`as` when present, otherwise `field`—is its result
column and view reference. Private SQL aliases are generated internally. Hiding is a view operation, so hidden values
remain part of analysis and source fingerprinting. Table payloads omit hidden
columns; chart compilers omit hidden series.

## Caching

Cache keys include the normalized definition, project, result format,
and fingerprints for every referenced contract and metadata entity. Contract
fingerprints include definition, profiling, occurrence, and availability
state. Metadata fingerprints include the scoped entity state. `refresh: true`
skips lookup and recomputes the result.

## Report execution

The report executor validates and loads every referenced insight; a missing or
cross-project dependency is an error. It intersects report filters with each
insight's filters and resolves `limit` and `random` in this order:

1. execution request;
2. saved report;
3. saved insight;
4. server defaults of `limit: 1000` and `random: false`.

Each configured insight executes through the same value planner. Report results
preserve configuration order and return `{id, layout, result}` entries. The
nested result omits `kind` and `insight_id`; standalone insight execution keeps
both fields. Report caches fingerprint the report, all effective insight
definitions, and all referenced sources.
