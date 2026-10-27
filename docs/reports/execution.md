# Insight compilation and execution

Every dashboard, REST, report, MCP, and AI preview uses the same pipeline:

1. Parse the strict v2 envelope and its discriminated query/view unions.
2. Parse canonical field references and resolve them through the request-scoped
   runtime catalog.
3. Validate permissions, project scope, scalar/semantic bindings, joins, occurrence
   selection, coverage, provider needs, view compatibility, and size limits.
4. Fingerprint the normalized query and authoritative sources.
5. Reuse an authorized cached result unless refresh is requested.
6. Dispatch to the runner registered for `query.kind`.
7. Ask trusted shape adapters for logical relations and compile parameterized SQL.
8. Perform only permitted deterministic retrieval, descriptive summaries, and
   domain-aware reshaping.
9. Return a typed result, provenance, coverage, warnings, and provider requirement.
10. Compile the selected presentation view and persist an authorized cache entry.

Physical storage and compiled SQL are never query inputs or saved output. Profiles are
optional discovery indexes and do not affect correctness.

Each field occurrence is resolved with its selection scope. Diagnostics retain exact
run-contract occurrences, excluded failures/incompatibilities, missing identities,
duplicate conflicts, methods/versions, and coverage. Outer matching preserves missing
values; inner matching retains only shared identities. Ambiguous multiple values for
one identity are reported rather than selected silently.

Core runners handle rows, summaries, relationships, distributions, ordered series,
raw matrices, alteration states, variant recurrence, genomic layout, timelines, and
descriptive associations. Model-dependent requests dispatch to an explicitly
registered provider with pinned inputs and provenance. If none is available, execution
stops with a provider-required diagnostic.

Results include the normalized v2 `query` and `view`, typed family payload, bounded
rows/plot table, source and query fingerprints, coverage, warnings, computed time, and
cache status. Preview also returns the exact `preview_fingerprint` required for save.

Reports validate every referenced insight, intersect compatible report filters, and
execute each entry through this same pipeline. Snapshot results pin resolved evidence;
saved reports and insights resolve current data on later execution.
