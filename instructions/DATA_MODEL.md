# Goodomics Semantic Data Model

This file is the source of truth for Goodomics data terminology and schema direction.

## Architecture

Goodomics uses one semantic path from ingestion to visualization:

```text
data shape → data contract and fields → trusted adapter → runtime catalog
           → typed query → family runner → typed result → compatible view
```

Public metadata describes meaning. Physical DuckDB tables, columns, SQL, internal
integer keys, and adapter implementation details are trusted internals and must not
appear in contracts, catalog responses, saved insights, AI tools, or MCP tools.

## Projects, entities, and provenance

- A project is the permission and discovery boundary.
- Subjects, samples, runs, processed samples, files, features, variants, and
  genomic coordinates are logical identities used for matching.
- `run_sample` is an internal storage/link identity. User-facing APIs use sample
  or processed-sample language.
- A data import records acquisition of external data.
- A run records a workflow, tool, importer, notebook, benchmark, or analysis event.
- A run contract records the actual producer, version, parameters, reference
  context, occurrence availability, and output contract for one run.

Availability states are `observed`, `profiled_empty`, `failed`, and `unavailable`.
They are occurrence facts, not contract properties.

## Data shapes and versions

`data_shapes` owns stable identity, optional project ownership, built-in status,
name, and description. `data_shape_versions` owns an integer version, `draft` or
`published` status, declarative definition, trusted registered adapter key, and
timestamps.

Built-in shape IDs are:

| Shape | Meaning |
|---|---|
| `entity` | Values attached to subjects, samples, runs, processed samples, or files |
| `feature` | Values or calls for an entity and biological/analytical feature |
| `variant` | Variant identities, annotations, and entity-level calls |
| `region` | Values or events over genomic coordinates |
| `series` | Ordered points over position, cycle, depth, or time |
| `timeline` | Dated or relative-time subject events |
| `records` | Application-managed typed rows with stable `row_id` |
| `structured` | Opaque or partially queryable result payloads |

Shape definitions contain logical keys, cardinality, permitted field purposes and
scalar types, required bindings, and logical capabilities. They never contain
physical routing or executable code paths.

Shape lifecycle is draft → validate against representative rows → publish. A
published version is immutable. Contracts pin a published version; later changes
require a new draft version. This repository is undeployed, so update the current
schema and fixtures directly—do not add migrations or compatibility layers unless
explicitly requested.

## Data contracts and fields

A data contract describes one discoverable dataset:

- stable `data_contract_id` and optional project owner;
- name and description;
- published `data_shape_id` and `data_shape_version` reference;
- semantic `bindings`, such as entity type, feature domain, assay, coordinate
  system, position domain, time origin, or row identity;
- search tags and flexible non-routing metadata.

A data-contract field describes one canonical field:

- stable `field_id` and display name;
- purpose: `key`, `value`, `coordinate`, or `annotation`;
- scalar type: `numeric`, `integer`, `string`, `boolean`, `categorical`, `date`,
  `datetime`, or `json`;
- semantic type, unit, direction, description, numeric priority, and domain tags.

Contract and field machine IDs cannot contain `/`. Public field references remain
strings:

```text
<contract>/<field>
metadata/<entity>/<field>
```

The runtime catalog returns these strings directly, and every definition, revision,
export, diagnostic, and cache fingerprint preserves them unchanged.

## Trusted shape adapters

A registered `ShapeAdapter` validates shape definitions and bindings, maps logical
observations to canonical storage, exposes logical relations and keys, profiles
authoritative rows, and reports supported query operations. Adapters do not own
permissions, project-wide discovery, saved insights, or complete query planning.

Keep the existing canonical DuckDB serializers. Normalized additions are limited to
named workflows: ordered series points, annotation spans, feature-set coverage, and
application-managed record tables. Managed tables use approved scalar types and
application-generated private names. Users cannot provide DDL or routing metadata.
Novel storage behavior requires trusted code or a plugin adapter.

## Ingestion and inference

Importers should infer scalar types, candidate keys, and compatible built-in shapes,
then allow users to accept or correct that inference. Adapters choose storage.
Mixed tool output is split into shape-consistent contracts while retaining shared
import and producer provenance.

Arbitrary well-typed tables use the `records` shape. Every managed row has a stable
`row_id`; unknown fields and scalar-type mismatches are rejected before replacement.

## Profiles and coverage

Project-scoped dataset and field profiles are optional, lazy, disposable discovery
indexes. They contain a source fingerprint, timestamp, row and distinct-entity
counts, missing count, numeric min/max, categorical distinct count, and at most a
bounded set of top values. They may improve builder choices, AI discovery, cost
warnings, and diagnostics, but never replace authoritative analytical rows or change
query correctness.

Feature-aware analyses additionally use per-occurrence/per-sample feature-set
coverage. Coverage distinguishes altered, profiled but unaltered, profiled with no
emitted rows, not profiled, and unavailable. Eligible denominators for alteration
frequencies, OncoPrints, and descriptive associations come from this coverage.

## Runtime catalog and analytical storage

The request-scoped runtime catalog assembles visible published shapes, contracts,
fields, occurrence and coverage metadata, optional profiles/values, logical joins,
query families, compatible views, diagnostics, and provider requirements. It uses
request-level memoization, pagination, bounded sampling, and stable source
fingerprints. Do not add a cross-request catalog cache until profiling justifies it.

SQLite/PostgreSQL metadata records durable entities and provenance. DuckDB stores
authoritative analytical rows and private application-managed tables. Compiled SQL
is parameterized, ephemeral, and never the saved definition.
