# Insight compilation and execution

The insight backend is the bridge between a declarative builder config and a
JSON-ready table, metric, or chart payload. It deliberately keeps result
selection, query planning, and chart compilation on the server so the
dashboard, API, reports, MCP tools, and AI drafting use the same rules.

## Execution pipeline

`execute_insight` performs these stages:

1. Normalize defaults in the config.
2. Validate config shape and chart constraints.
3. Identify the semantic or physical data source.
4. Compute a canonical config hash and source fingerprint.
5. Reuse a matching cached result unless `refresh` is true.
6. Resolve eligible run-contract occurrences for each contract series/column.
7. Compile and execute safe queries against DuckDB or the SQL metadata store.
8. Convert internal sample/run identities to readable labels.
9. Apply the result-size policy.
10. Compile rows into a table, metric, or ECharts option payload.
11. Persist the result cache when the caller has permission to do so.

Normalization copies the supplied config before execution and adds transient
`_runtime` metadata for linker and result-selection diagnostics. That runtime
metadata is reflected in the result but is not part of the saved config.

## Source selection

The preferred path is contract-first:

```json
{
  "kind": "data_contract",
  "data_contract_id": "salmon:results"
}
```

For contract-backed charts, every `series` can select a different contract. The
executor fingerprints all selected contracts, resolves each series, runs each
query independently, and aligns the rows afterward.

Two escape hatches also exist:

- a physical `metadata` (metadata store) or `analytics` table source;
- a read-only `SELECT`/`WITH` SQL statement.

Raw SQL is rejected unless it starts with `SELECT` or `WITH`, and statements
containing write/DDL keywords such as `INSERT`, `UPDATE`, `DELETE`, `DROP`,
`ALTER`, `CREATE`, `COPY`, or `PRAGMA` are blocked. Storage adapters still apply
response limits. Raw sources are useful for advanced work but are more tightly
coupled to implementation tables than contract-first configs.

## Result resolution

The shared result resolver begins in the SQL metadata store. For a selected data
contract it joins:

- `run_contracts` for produced-result occurrences;
- `runs` for project, run status, method version, and timestamps;
- `analysis_types` and `analysis_methods` for compatibility and scope filters;
- `run_contract_samples`, `run_samples`, and `samples` for per-sample
  availability and biological identity.

It first excludes analysis types not declared compatible with the contract,
then applies the series `result_scope`. For
`latest_successful_per_sample`, eligible runs must have a successful run status
and an available/complete/observed contract status. Per-sample availability
must be `observed` or `profiled_empty`.

Candidates for each sample are ranked by occurrence/run end time, start time,
run creation time, and run ID. The resolver returns exact integer primary keys
for DuckDB filtering and public IDs for diagnostics.

The diagnostic object includes selection mode, resolved occurrences and
run-sample links, excluded failures, incompatible analysis types, missing
samples, method/version counts, superseded results, availability counts, and
mixed-version warnings.

## Contract and field routing

After result resolution, the compiler uses field metadata to choose a table and
value column:

1. Resolve `data_contract_id` to the project-scoped contract definition.
2. Resolve `field_id` under that contract.
3. Read `query_ref.table` or fall back to `primary_table`.
4. Read `query_ref.value_column` or derive it from `value_type`.
5. Match the field using either its SQL integer ID or readable DuckDB dimension
   label.
6. Add exact run-contract and run-sample predicates from the resolver.
7. Add context, global, query, and per-series filters as bound parameters.

Supported contract-series tables include scalar metrics, attributes, numeric
features, feature calls, copy-number segments, small and structural variants,
result payloads, and derived gene-alteration state.

Some typed tables expose synthetic fields when a dedicated field definition
is not present. Examples include `call_code`, `segment_mean`, `genotype`,
`allele_fraction`, `payload_kind`, and `payload_name`.

## Table compilation

A simple contract table selects the natural identity columns and the routed
field value. Measures compile to the bounded aggregation vocabulary, and
dimensions form `GROUP BY` keys.

Table previews can select multiple fields from compatible tables in the same
contract. The compiler normalizes each field into:

```text
identity columns + logical field alias + numeric/string/JSON value bucket
```

It combines those rows with `UNION ALL`, then pivots them into one wide row per
identity using conditional aggregates. Missing identity columns become `NULL`.
This mixed-table path is restricted to scalar metrics, entity attributes, and
result payloads; typed feature/variant data needs additional domain keys and is
not silently flattened.

## Series compilation and matching

For a chart, each series becomes a separate parameterized query. The compiler:

- resolves its contract and field;
- selects raw values or applies its aggregation;
- applies its own result scope and filters;
- includes the selected linker column as `__linker` when needed.

The matching stage builds one map per series and computes the intersection of
linker keys. Only keys represented unambiguously in every series become plot
rows. The result includes counts for matched keys, unmatched keys, duplicate
conflicts, and excluded source rows.

Histograms are different: series are distributions, so values are overlaid
without biological row matching. A one-series pie/donut query groups the
categorical value and returns counts.

## Result compilation

All executions produce a common envelope containing:

```text
kind, insight_id, title, description, context, analysis_grain,
linker, filters, result_policy, linker_diagnostics,
result_selection_diagnostics, visualization, display,
columns, column_labels, rows, plot_table, computed_at, cached
```

Tables return that envelope directly. Metric visualizations add a compact
`metric` object. Other visualizations validate the row types and add compiled
`echarts_options`.

`plot_table` is the authoritative bounded set of columns and rows used by the
visualization. It is useful for data inspection, accessibility, exports, and
explaining a chart independently of ECharts.

## Caching and invalidation

Insight caches are keyed by:

- the normalized config;
- project ID;
- result format version;
- normalized source identity;
- a source fingerprint.

For contract sources, the fingerprint includes the contract fingerprint,
profiling timestamp, field count, run-contract count, per-sample availability
count, and latest occurrence time. Raw analytical tables use row counts and the
DuckDB file size as a lightweight freshness signal. Metadata tables use scoped
row counts.

An unchanged config can therefore reuse a result until either its semantic
definition or source state changes. `refresh: true` skips cache lookup and
recomputes the result. Cache entries retain the computed JSON payload; they are
not the analytical source of truth.

## Report execution

`execute_report` loads the insight IDs in `report.config.items` order. It merges
report context, linker, result policy, and filters into each effective insight
config, then fingerprints all insight sources.

Each insight executes through the same pipeline described above. The final
report result contains report identity/config plus the ordered insight results.
Report caching uses a hash of the report config, effective insight configs,
project, and all source fingerprints.

The HTML renderer embeds the structured report payload and produces fallback
tables for insight rows. `POST /api/v1/reports/render` can persist that HTML as
a `rendered_reports` snapshot. Structured execution and rendered snapshots are
separate so API clients can consume data without parsing HTML.

## Persistence tables

The SQL metadata store keeps the builder lifecycle auditable:

| Table | Purpose |
| --- | --- |
| `insights` | Current saved insight name, description, and config |
| `insight_revisions` | Historical configs created when an insight config changes |
| `reports` | Current saved report layout/config |
| `report_revisions` | Historical report configs |
| `insight_result_cache` | Computed insight payloads keyed by spec/source hashes |
| `report_result_cache` | Computed report payloads keyed by spec/source hashes |
| `rendered_reports` | Persisted HTML snapshots and their report/run association |

Deleting a saved insight or report also removes its revisions and caches. A
deleted default report clears the affected project's `default_report_id`.
