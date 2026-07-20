# Data model and storage overview

Goodomics preserves two kinds of information that have different storage and
query needs:

- **Metadata** describes what exists, how it is related, and where it
  came from.
- **Analytical data** contains the measurements, calls, matrices, and payloads
  produced by computational work.

Goodomics keeps these concerns separate instead of forcing every value and
relationship into one database.

## The three storage layers

| Layer | Default | Stores | Typical access |
| --- | --- | --- | --- |
| Metadata store | SQLite | Projects, runs, samples, subjects, imports, contracts, fields, files, sample groups, saved insights, reports, revisions, and cache records | CRUD, relationships, permissions, and result selection |
| Analytical store | One DuckDB database per project | Scalar metrics, attributes, feature values and calls, variants, segments, and logical payloads | Filtering, aggregation, comparison, and plotting |
| File store | Local filesystem | Original evidence and generated artifacts such as reports, logs, VCFs, BAMs, and exported insight data | Download, archival, and provenance |

SQLite is the default metadata store. A server installation can use another
supported SQL database for metadata, while DuckDB remains the default local
analytical engine. File records stay in the metadata store; the file
bytes stay on the filesystem or a configured object store.

## How the core entities fit together

The central relationship is:

```text
Project
  ├── Sample ── optional Subject
  ├── Run ── Run sample ── Sample
  │    └── Run contract ── Data contract
  │         └── Run contract sample ── Run sample
  ├── Data import
  ├── File ── File link ── import/run/sample/contract
  └── Sample group ── Sample group member ── Run sample
```

The terms have distinct meanings:

- A **sample** is the stable biological or material identity a user recognizes.
- A **run** is one computation, import, notebook result, or benchmark snapshot.
- A **run sample** means that a sample participated in a particular run. It is
  an internal provenance and membership link, not a public analysis grain.
- An **analysis type** is a controlled biological category, such as RNA
  sequencing.
- An **analysis method** is the workflow, tool, algorithm, notebook, script,
  benchmark, or importer that produced a result.
- A **data contract** describes a stable logical result type.
- A **run contract** is one run's occurrence of that contract.
- An **observation** is a value, call, or measurement stored in an analytical
  table under that contract.

This separation lets one sample appear in several runs, lets one run produce
several kinds of results, and preserves which method version produced each
result.

## Metadata versus analytical values

Use the metadata store for identity and provenance. Examples include a run's
status, its method version, a sample's stable name, a contract definition, and a
saved report layout. These records are small, relational, and frequently
created or edited individually.

Use DuckDB for values that users scan or aggregate. Examples include mapping
percentages, expression values, variant calls, copy-number segments, and parsed
plot payloads. These records are larger and benefit from columnar queries.

A query usually crosses both layers:

1. Resolve readable labels such as `sample_id`, `data_contract_id`, and
   `run_contract_id` in the metadata store.
2. Select the eligible result occurrences using run status, analysis type,
   method, version, and per-sample availability.
3. Query the corresponding integer IDs in DuckDB.
4. Replace internal identity keys with readable labels in the response.

SQL metadata tables use integer primary and foreign keys internally. DuckDB fact
tables also use those compact integer IDs. Public APIs and configuration use
stable readable IDs; Goodomics resolves them at the boundary.

## Why analytical storage is modular

Omics outputs do not share one useful physical shape. Goodomics therefore uses
several analytical tables rather than a universal observations table.

| Shape | Example table | Examples |
| --- | --- | --- |
| Scalar sample/run metrics | `sample_metrics` | Mapping rate, duplication, read count |
| Queryable attributes | `entity_attributes` | Tissue, disease, batch, subject sex |
| Numeric feature matrices | `feature_value_numeric` | TPM, counts, beta values, pathway scores |
| Categorical feature calls | `feature_call` | Amplification, deletion, present/absent |
| Variant calls | `sample_variant_calls` | SNVs and indels |
| Genomic segments | `copy_number_segments` | Continuous copy-number segments |
| Logical objects | `result_payloads` | Point series, compact tables, matrices, JSON |

Every analytical fact belongs to a data contract. The selected contract field
routes a builder query to the correct table and value column. Derived layouts
may duplicate canonical facts for common access paths, but they are caches or
query layouts rather than new sources of truth.

## From ingest to an insight

An ingest or SDK run normally produces the following chain:

1. Goodomics creates or finds the project, samples, analysis type, and method.
2. It records the run and its sample/run links in the metadata store.
3. It registers the stable data contracts and fields emitted by the source.
4. It records a run-contract occurrence and per-sample availability.
5. It writes measurements or payloads to the appropriate DuckDB tables.
6. The insight builder lists registered data contracts and field definitions.
7. At execution time, the result resolver selects exact occurrences and the
   insight compiler queries DuckDB.

See [Data contracts and fields](data-contracts.md) for the semantic query layer
and [Insight compilation and execution](../reports/execution.md) for the full
builder execution path.
