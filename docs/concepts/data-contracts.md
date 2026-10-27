# Semantic data contracts

Goodomics exposes analytical data by meaning rather than storage layout. A data
shape defines a reusable semantic structure, a data contract describes one dataset
using a published shape version, and contract fields describe the values users can
query.

## Built-in shapes

| ID | Use |
|---|---|
| `entity` | Subject, sample, run, processed-sample, or file values |
| `feature` | Gene, protein, pathway, or other feature values/calls |
| `variant` | Variant identities, annotations, and calls |
| `region` | Genomic interval values or events |
| `series` | Ordered measurements over position, depth, cycle, or time |
| `timeline` | Subject events with absolute or relative time |
| `records` | Application-managed typed rows |
| `structured` | Opaque or partially queryable result payloads |

Shape versions begin as drafts. Goodomics validates a draft against its declarative
rules and representative rows, publishes it immutably, and pins contracts to that
published version. New behavior uses a new draft version.

## Contract fields

A contract has a stable ID, name, description, published shape version, semantic
bindings, search tags, and optional metadata. Bindings identify concepts such as
entity type, assay, feature domain, coordinate system, or time origin.

Each field has:

- a stable machine ID and display name;
- purpose: `key`, `value`, `coordinate`, or `annotation`;
- scalar type: numeric, integer, string, boolean, categorical, date, datetime, or
  JSON;
- optional semantic type, unit, direction, description, priority, and domain tags.

The runtime catalog returns a canonical string for every field:

```text
cbioportal:clinical:subjects/cancer_type
metadata/subject/subject_id
salmon:results/general_stats.salmon_percent_mapped
```

These references are safe to store in insights, revisions, exports, and logs. Table
names, columns, SQL, and adapter keys are private implementation details and never
belong in a contract or query.

## Discovery and profiles

Use the project runtime-catalog endpoints to list/search datasets, describe fields,
find logical joins, inspect optional field profiles and sampled values, and discover
valid query families/views. Catalog results are permission-scoped and use logical
identities such as subject, sample, run, file, feature, variant, and coordinate.

Profiles are lazy discovery indexes. Row counts, missing counts, numeric ranges, and
bounded categorical top values may be absent and are recomputed when the source
fingerprint changes. Queries always read authoritative analytical rows.

## Managed record datasets

For an arbitrary well-typed table, create a contract on the `records` shape with a
`row_identity` binding and typed fields. Replace rows through the managed-record API;
each row supplies `row_id`. Goodomics rejects unknown fields and scalar mismatches,
then chooses private application-generated storage names. Users never provide DDL.

## Coverage

Feature-aware datasets can record per-sample feature-set coverage. This distinguishes
altered, profiled but unaltered, profiled-empty, not profiled, and unavailable states.
OncoPrints and alteration/association percentages use the eligible covered population,
not the number of emitted alteration rows.
