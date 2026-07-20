# Data contracts and fields

Data contracts are the semantic layer between an imported result and the
physical table that stores it. They let SDK, dashboard, report, API, and MCP
callers ask for a stable result such as `fastqc:results` without hard-coding a
DuckDB schema.

## Contract, occurrence, and field

These three records answer different questions:

| Record | Question it answers | Example |
| --- | --- | --- |
| Data contract | What logical dataset is this? | `fastqc:results` |
| Run contract | Which run produced this occurrence, and with what version/reference? | FastQC results from `run-042` |
| Data contract field | Which value can be queried, and where is it stored? | `general_stats.fastqc_raw_percent_gc` |

A stable contract describes data type, entity grain, feature/value semantics,
query modes, and intrinsic producer families. Execution-specific provenance
belongs on the run and run contract instead. In particular, actual tool
versions, genome builds, run timestamps, and references should not be baked
into the stable contract definition.

## Contract properties

Common contract properties include:

| Property | Meaning |
| --- | --- |
| `data_contract_id` | Stable public identifier |
| `name` | Display name |
| `data_type` | Logical/physical family, such as `generic_metrics`, `feature_matrix`, `small_variants`, or `result_payload` |
| `feature_type` | Kind of measured feature, such as metric, gene, transcript, or variant |
| `value_type` | Contract-level value shape |
| `entity_grain` | Default entity the values describe |
| `value_semantics` | Meaning such as `tpm`, `count`, `beta`, or `zscore` |
| `query_modes` | Supported access paths such as sample, metric, cohort, or payload |
| `summary` | Compact profiled summary |
| `source_fingerprint` | Input fingerprint used to invalidate summaries and caches |
| `intrinsic_producer_families` | Tool or pipeline families that can emit the contract |

Contracts may be global built-ins or project-owned definitions. When a project
has its own definition for the same readable ID, the project-scoped definition
is preferred.

## Field properties

A field is the queryable unit inside a contract. It carries both user-facing
meaning and physical routing information.

| Property | Meaning |
| --- | --- |
| `field_id` | Stable key inside the contract |
| `field_role` | Metric, attribute, dimension, or measure |
| `entity_scope` | Subject, sample, run, run sample, file, or contract |
| `display_name` | Human-readable label |
| `value_type` | `numeric`, `string`, `boolean`, `date`, or `json` |
| `unit` | Optional unit |
| `direction` | Optional interpretation such as `higher_is_better` |
| `primary_table` | Main DuckDB table containing the field |
| `physical_tables` | Complete physical footprint |
| `query_ref` | Exact field discriminator and value-column hints |
| `summary` | Counts, ranges, examples, or top values |

For example, this field routes a stable FastQC metric to the numeric value
column in `sample_metrics`:

```yaml
- field_id: general_stats.fastqc_raw_percent_gc
  entity_scope: sample
  display_name: Percent GC
  value_type: numeric
  unit: percent
  primary_table: sample_metrics
  physical_tables: [sample_metrics]
  query_ref_json:
    table: sample_metrics
    field_column: field_id
    field_value: general_stats.fastqc_raw_percent_gc
    value_column: value_numeric
```

The builder treats field metadata as authoritative for query routing. A
contract's `data_type` supplies grouping and fallback behavior, but it does not
replace field-level routing.

## Built-in contract specifications

Built-in contracts are declarative YAML files under
`goodomics/contracts/tools/` and `goodomics/contracts/sources/`. Each file has a
source descriptor and one or more contracts:

```yaml
source:
  id: example-tool
  kind: tool
  name: Example Tool

contracts:
  - data_contract_id: example:results
    name: Example results
    data_type: generic_metrics
    producer_tool: example-tool
    feature_type: metric
    value_type: numeric
    entity_grain: sample
    query_modes: [sample, metric, cohort]
    description: Scalar metrics emitted by Example Tool.
    fields:
      - field_id: example.score
        display_name: Example score
        value_type: numeric
        entity_scope: sample
        primary_table: sample_metrics
        physical_tables: [sample_metrics]
        query_ref_json:
          table: sample_metrics
          field_column: field_id
          field_value: example.score
          value_column: value_numeric
```

Package loading validates duplicate contract IDs and duplicate
`(data_contract_id, field_id)` pairs. Parsers can also emit project-specific
contracts and fields during ingestion. SDK-logged metrics use the
`goodomics:sdk_metrics` contract, with field definitions derived from the
logged metric names and value types.

## Produced-result availability

A run contract records the occurrence of a contract from a particular run. It
contains the direct producer method, producer version, reference context,
status, timestamps, and execution-specific metadata.

`run_contract_samples` records per-sample availability:

- `observed`: one or more observations are present.
- `profiled_empty`: profiling succeeded but emitted no rows.
- `failed`: production failed for that sample.
- `unavailable`: the result does not exist for that sample.

The result resolver considers `observed` and `profiled_empty` eligible and
preserves the distinction in diagnostics. This prevents an intentionally empty
result from being mistaken for missing data.

## Browse contracts through the API

List the data contracts available to a project:

```http
GET /api/v1/contracts?project_id=rnaseq-core
```

Fetch one contract, including its fields:

```http
GET /api/v1/contracts/fastqc:results?project_id=rnaseq-core
```

Fetch bounded result-scope choices such as compatible methods, versions, runs,
and statuses:

```http
GET /api/v1/contract-result-options/fastqc:results?project_id=rnaseq-core
```

The returned field summaries help a client select appropriate controls and
visualizations. Numeric fields can drive histograms and scatter plots;
categorical fields can drive counts and grouped charts; `primary_table` and
`query_ref` remain backend routing details.

## Contract-first queries

Prefer a contract and field over a raw table name:

```json
{
  "query": {
    "source": {
      "kind": "data_contract",
      "data_contract_id": "fastqc:results"
    },
    "fields": ["general_stats.fastqc_raw_percent_gc"]
  }
}
```

This query remains tied to semantic IDs while Goodomics resolves the physical
table, field discriminator, value column, eligible result occurrences, and
internal integer IDs. Raw table and read-only SQL sources exist as advanced
escape hatches, but they couple a config to storage details and bypass much of
the data contract and field abstractions.
