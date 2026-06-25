# Goodomics Core Data Model

This file is the source of truth for Goodomics data model terminology and
schema-direction discussions. Use it when working on core data concepts, table
shapes, SQL vs DuckDB responsibilities, data profiles, processed samples, files,
observations, and agent/MCP data-query behavior.

The guiding split:

- **SQL control store**: remembers what exists, where it came from, and how
  entities relate.
- **DuckDB analytical store**: stores and query-optimizes measurements, calls,
  matrices, summaries, and derived views.

## Core Relationship Model

| Concept | User-facing meaning | Implementation role |
| --- | --- | --- |
| Project | Workspace or data boundary | Owns runs, samples, files, sample sets, profiles, and analytical store |
| Subject | Optional patient, donor, organism, cell line, or individual | Links related samples |
| Sample | Biological or material sample users recognize and navigate | Stable sample identity across runs |
| Run | Computational, import, benchmark, or analysis event | Captures one execution or iteration; may be sample-linked or sample-less |
| Processed sample | A sample within a specific run | Internal `run_sample` grain for latest-run lookup, comparison, and metrics |
| File | Original or derived file | Tracks physical evidence and outputs |
| Data profile | Smallest logical queryable dataset | Declares data type, provenance, and query behavior |
| Sample set | Saved group of processed samples | General primitive behind cohorts and reference sets |
| Cohort | Sample set used for grouping or comparison | Specialized sample set |
| Reference set | Sample set used as a baseline | Specialized sample set |
| Feature | Thing being measured | Metric, gene, transcript, protein, antibody, variant, interval, pathway, signature |
| Observation | Value, call, or measurement | Conceptual analytical fact stored in modular tables |

Short version:

| Term | Meaning |
| --- | --- |
| Sample | The biological sample users care about |
| Run | What happened to, from, or independently of samples |
| Processed sample | That sample in that run |
| Data profile | What kind of data was produced |
| Observation | A value/call/measurement inside that profile |
| Cohort/reference set | Selected processed samples |

## SQL Control Store

These tables are smaller, relational, and CRUD-oriented.

### `projects`

Main workspace boundary.

| Column | Notes |
| --- | --- |
| `project_id` | Primary key |
| `name` | Human-readable name |
| `description` | Optional description |
| `metadata_json` | Flexible project metadata |
| `created_at` | Creation timestamp |

### `subjects`

Optional. Useful for patients, donors, organisms, cell lines, or longitudinal
studies.

| Column | Notes |
| --- | --- |
| `subject_id` | Primary key |
| `project_id` | Owning project |
| `metadata_json` | Subject-level metadata |

### `samples`

The stable biological or material sample users recognize. Samples are the
primary way users interact with biological data: a sample page should be able to
show the latest run data for that sample while still preserving older runs for
comparison. The same sample can be processed by many pipelines, rerun by a newer
pipeline version, or appear in many imports.

Use sample metadata for stable biological context. Use runs and processed
samples for execution context, tool outputs, and per-run status.

| Column | Notes |
| --- | --- |
| `sample_id` | Primary key |
| `project_id` | Owning project |
| `subject_id` | Nullable subject link |
| `sample_name` | Human-readable sample name |
| `metadata_json` | Sample-level metadata |

### `runs`

A computational, import, benchmark, or analysis event. A run is one execution or
iteration: a pipeline run, cBioPortal import slice, notebook analysis,
optimization attempt, model-training experiment, or other produced result.

Runs do not have to correspond to samples. For algorithm optimization,
benchmarking, model training, or other sample-less work, keep the run without
`run_samples`. When a run does correspond to biological samples, connect it
through `run_samples` rather than baking sample identity into the run table
itself.

For sample-first imports such as cBioPortal, Goodomics may create one import
context run that owns shared source-file provenance plus one sample-scoped run
per biological sample. Analytical facts then reference the sample-scoped run ID,
while shared source files can remain linked to the import context run.

| Column | Notes |
| --- | --- |
| `run_id` | Primary key |
| `project_id` | Owning project |
| `name` | Human-readable run name |
| `run_kind` | Example: `pipeline_run`, `import_run`, `benchmark_run`, `notebook_run` |
| `assay` | Nullable assay label |
| `pipeline_name` | Nullable pipeline/workflow name |
| `pipeline_version` | Nullable pipeline/workflow version |
| `parameters_json` | Run-level parameters/configuration |
| `started_at` | Nullable start timestamp |
| `ended_at` | Nullable end timestamp |
| `status` | Run status |
| `metadata_json` | Flexible run metadata |

### `run_samples`

Internal linker/result table. User-facing wording should usually be
**processed sample** or **sample result**.

This is the key sample/run comparison grain. A sample can have many processed
samples across time as users rerun the same pipeline, run new tools, or ingest
new source data. Latest-run views for a sample should be derived from
`run_samples` joined to `runs`, usually ordered by run timestamps/status rather
than stored as a denormalized cache.

| Column | Notes |
| --- | --- |
| `run_sample_id` | Primary key |
| `project_id` | Owning project |
| `run_id` | Run that processed or produced this result |
| `sample_id` | Nullable sample link |
| `assay` | Nullable assay label |
| `role` | Optional role, such as `tumor`, `normal`, `control`, `truth_set` |
| `status` | Processed-sample status |
| `metadata_json` | Flexible per-run sample metadata |

### `data_profiles`

Stable semantic query contracts. A data profile declares what kind of data a
parser, SDK workflow, or user-defined source writes, how it should be queried,
and how agents should understand it. Built-in profile IDs are stable across
projects, runs, samples, and source datasets, so MCP tools and agents can ask
for `cbioportal:mutations:maf` or `multiqc:qc_metrics` without learning a
specific import run ID.

A data profile is not a dataset instance and is not sample membership. Runs,
files, file links, `data_sources`, fact-table `run_id` columns, payload
metadata, and source metadata carry provenance such as cBioPortal study IDs,
source filenames, generated import IDs, source `stable_id` values, and platform
descriptions.

A data profile is also not the same thing as a metric definition. A profile
might be `multiqc:qc_metrics`; the metrics inside it might be
`duplication_rate`, `insert_size_mean`, and `mean_coverage`. Keep profile-level
query behavior and agent descriptions on `data_profiles`, and keep per-metric
labels, units, directions, and descriptions in `metric_definitions`.

| Column | Notes |
| --- | --- |
| `data_profile_id` | Primary key |
| `project_id` | Nullable owner for user/project-defined profiles; built-ins are global |
| `name` | Human-readable profile name |
| `data_type` | Example: `generic_metrics`, `feature_matrix`, `feature_calls`, `small_variants`, `copy_number_segments` |
| `assay` | Nullable assay label |
| `producer_tool` | Tool that produced this logical dataset |
| `producer_tool_version` | Tool version |
| `producer_pipeline` | Pipeline/workflow that produced this profile |
| `genome_build` | Nullable genome/reference build |
| `feature_type` | Example: `metric`, `gene`, `transcript`, `protein`, `antibody`, `variant`, `interval`, `pathway`, `signature` |
| `value_type` | Example: `numeric`, `categorical`, `call`, `matrix` |
| `unit` | Nullable default unit |
| `query_modes_json` | Supported query modes, such as sample, metric, gene, region |
| `mcp_description` | Agent-readable description |
| `metadata_json` | Flexible profile metadata |

Examples:

| Data profile | Data type | Producer |
| --- | --- | --- |
| `multiqc:qc_metrics` | `generic_metrics` | MultiQC |
| `cbioportal:mutations:maf` | `small_variants` | cBioPortal |
| `cbioportal:copy_number:segments` | `copy_number_segments` | cBioPortal |
| `picard_alignment_metrics` | `generic_metrics` | Picard |
| `mutect2_somatic_variants` | `small_variants` | Mutect2 |
| `salmon_gene_tpm` | `feature_matrix` | Salmon |
| `gistic_gene_cna` | `feature_calls` | GISTIC |
| `bwa_alignment_files` | `alignment_files` | BWA |

### `files`

Physical files Goodomics knows about.

| Column | Notes |
| --- | --- |
| `file_id` | Primary key |
| `project_id` | Owning project |
| `path` | Local path, if applicable |
| `uri` | URI/object-store location, if applicable |
| `file_role` | Example: `fastq`, `bam`, `bai`, `vcf`, `tbi`, `report`, `log` |
| `format` | File format |
| `size_bytes` | File size |
| `sha256` | Content hash |
| `created_at` | Creation or registration timestamp |
| `metadata_json` | Flexible file metadata |

### `file_links`

Links files to the entities they support without overloading `files` with many
nullable ownership columns.

| Column | Notes |
| --- | --- |
| `file_id` | Linked file |
| `project_id` | Owning project |
| `run_id` | Nullable linked run |
| `run_sample_id` | Nullable linked processed sample |
| `sample_id` | Nullable linked raw sample |
| `data_profile_id` | Nullable linked data profile |
| `link_role` | Relationship role, such as `source`, `index`, `derived`, `preview` |

### `sample_sets`

General saved grouping primitive.

| Column | Notes |
| --- | --- |
| `sample_set_id` | Primary key |
| `project_id` | Owning project |
| `name` | Human-readable set name |
| `kind` | Example: `cohort`, `reference_set`, `benchmark_set`, `case_group` |
| `description` | Optional description |
| `definition_json` | Optional rule/filter definition |
| `created_at` | Creation timestamp |
| `metadata_json` | Flexible sample-set metadata |

### `sample_set_members`

Usually points to processed samples, not raw samples. Reference sets for QC
should generally be `run_sample_id` based.

| Column | Notes |
| --- | --- |
| `sample_set_id` | Owning sample set |
| `run_sample_id` | Included processed sample |

### Other SQL Control Tables

These stay in the control store and should point to projects, runs, processed
samples, data profiles, sample sets, and files where relevant.

| Table | Purpose |
| --- | --- |
| `reports` | Rendered reports and report metadata |
| `report_templates` | Versioned report template definitions |
| `qc_policies` | Threshold and decision policies |
| `qc_decisions` | Stored review/evaluation decisions |
| `interpretation_notes` | Human- or agent-drafted notes |

## DuckDB Analytical Store

These tables are larger and query-oriented. Any fact table that stores actual
values, calls, measurements, or profile-specific rows should include
`data_profile_key` or `data_profile_id`.

Each project should have its own DuckDB analytical store by default, so large
analytics tables do not need to repeat `project_id` on every row. Store project
identity once in DuckDB metadata and keep `project_id` in the SQL control store.

Dimension tables do not always need profile identity.

The analytical store is modular by design. Do not force every ingested result
into one universal table. Use a small catalog of reusable biological data
shapes, and add derived layouts only for hot query paths.

| Shape | Purpose | Examples |
| --- | --- | --- |
| Scalar metrics | QC and pipeline scalar values | MultiQC metrics, Picard summary metrics, custom TSV metrics |
| Entity attributes | Queryable metadata and clinical/context fields | Sample attributes, subject attributes, run batch, disease, tissue |
| Profile availability | Records what was profiled, even when no observation exists | RNA-seq available, WGS profiled, gene panel coverage |
| Numeric feature values | Sample x feature quantitative matrices | TPM, counts, methylation beta values, protein abundance, pathway scores |
| Feature calls | Sample x feature categorical, binary, ordinal, or discrete calls | CNA AMP/HOMDEL, cluster labels, alteration present/absent |
| Small variants | Exact variant identities and sample calls | SNVs, indels, MAF/VCF-derived calls |
| Genomic intervals | BED-like intervals and per-interval values | Peaks, coverage windows, accessible regions |
| Copy-number segments | Continuous genomic copy-number segments | Segment means, total copy number, minor copy number |
| Structural variants | Paired breakend or fusion-like events | Fusions, translocations, inversions, deletions |
| Timeline events | Subject/sample events over time | Treatment, collection, diagnosis, outcome events |
| Logical payloads | Queryable escape hatch for object-like outputs | Parsed tables, arrays, JSON payloads, logs, report sections |
| Derived query layouts | Duplicate or reshape canonical data for hot access patterns | By-metric metrics, by-feature matrices, by-region variants, alteration state |

Data profiles sit above these physical choices. A data profile names the logical
dataset and its provenance, while the profile's `data_type` determines whether
Goodomics stores it as scalar metrics, feature values, feature calls, variants,
intervals, segments, structural variants, logical payloads, and/or derived query
layouts.

Canonical tables preserve biological meaning and provenance. Derived tables
preserve speed and query semantics. Derived tables should be reproducible from
canonical tables and marked as caches or query layouts, not as the source of
truth.

### Physical Layout And Indexing

Prefer compact internal integer keys in large analytical tables, while keeping
stable string IDs in SQL/control tables and small dimensions.

Internal keys can live in DuckDB dimension/mapping tables or be materialized
during analytical-store build steps. They are a physical optimization, not a
replacement for stable public IDs.

Examples:

| Internal key | Stable ID it represents |
| --- | --- |
| `data_profile_key` | `data_profile_id` |
| `run_sample_key` | `run_sample_id` |
| `sample_key` | `sample_id` |
| `subject_key` | `subject_id` |
| `feature_key` | `feature_id` |
| `metric_key` | `metric_id` |
| `variant_key` | `variant_id` |

DuckDB analytical fact tables should rely primarily on physical ordering and
derived layouts, not many secondary indexes. Use indexes sparingly for selective
point lookups and small dimension tables. For large fact tables, choose one
canonical sort order that matches the main detail path, then add one duplicate
derived layout when a second axis is clearly hot.

General rule:

| Query family | Preferred layout |
| --- | --- |
| Sample/run detail | `data_profile_key, run_id, run_sample_key, ...` |
| Feature/gene across a cohort | `data_profile_key, feature_key, run_sample_key` |
| Metric scans/distributions | `data_profile_key, metric_key, value, run_sample_key` |
| Attribute facets/filters | `entity_scope, attribute_key, value, entity_key` |
| Genomic range queries | `genome_build, contig, start_pos, end_pos` |
| Alteration frequency/OncoPrint | `feature_key, alteration_type, data_profile_key, run_sample_key` |

Do not maintain many duplicate layouts speculatively. Add a derived layout when
it serves a named UI, SDK, MCP, report, or notebook access path.

### `duckdb_metadata`

One-row metadata table for the project-scoped analytical store.

| Column | Notes |
| --- | --- |
| `project_id` | Project this DuckDB belongs to |
| `project_name` | Optional copied project name for exports/debugging |
| `schema_version` | Analytical schema version |
| `created_at` | Creation timestamp |
| `updated_at` | Last metadata/schema update timestamp |
| `metadata_json` | Store-level metadata |

If Goodomics later supports a multi-project analytical warehouse backend, that
backend can add `project_id` back as a partition/key. The default local DuckDB
path stays project-scoped.

### `metric_definitions`

Metric dictionary for generic metrics.

`data_profiles` describe a logical dataset, while `metric_definitions` describe
individual metrics inside metric-oriented profiles. For example,
`picard_alignment_metrics` is a data profile; `duplication_rate` and
`insert_size_mean` are metric definitions.

| Column | Notes |
| --- | --- |
| `metric_key` | Internal key |
| `metric_id` | Stable metric ID |
| `namespace` | Namespace/tool/module prefix |
| `metric_name` | Stable metric name |
| `display_name` | Human-readable label |
| `value_type` | Example: `numeric`, `string`, `json` |
| `unit` | Nullable unit |
| `direction` | Example: `higher_is_better`, `lower_is_better` |
| `description` | Metric description |
| `producer_tool` | Tool most associated with this metric |
| `producer_module` | Tool/module section |
| `schema_version` | Metric schema/parser version |

### `attribute_definitions`

Dictionary for queryable metadata and clinical/context attributes.

Control-store `metadata_json` fields can keep flexible provenance and display
metadata, but any attribute that participates in filters, facets, histograms,
cohort comparisons, joins, dashboards, or MCP queries should also be stored in
typed analytical attribute tables.

| Column | Notes |
| --- | --- |
| `attribute_key` | Internal key |
| `attribute_id` | Stable attribute ID |
| `entity_scope` | Example: `subject`, `sample`, `run`, `run_sample`, `file`, `data_profile` |
| `display_name` | Human-readable label |
| `value_type` | Example: `numeric`, `string`, `boolean`, `date`, `json` |
| `unit` | Nullable unit |
| `description` | Attribute description |
| `priority` | Optional UI/report priority |
| `metadata_json` | Flexible attribute metadata |

### Entity Attribute Fact Tables

Typed EAV-style tables for faceted metadata and clinical/context values.

| Table | Value column | Purpose |
| --- | --- | --- |
| `entity_attribute_numeric` | `value DOUBLE` | Numeric attributes and histogram/binning inputs |
| `entity_attribute_string` | `value TEXT` | Categorical/string attributes and faceted filters |
| `entity_attribute_boolean` | `value BOOLEAN` | Boolean attributes |
| `entity_attribute_date` | `value TIMESTAMP` | Date/time attributes |
| `entity_attribute_json` | `value_json JSON` | Rare structured attributes |

Common columns:

| Column | Notes |
| --- | --- |
| `entity_scope` | Entity type the value belongs to |
| `entity_key` | Internal entity key |
| `attribute_key` | Attribute definition |
| `data_profile_key` | Nullable source profile, when imported as a profile |
| `source_file_id` | Nullable source file |

Recommended physical layouts:

| Table/layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical attribute tables | `entity_scope, entity_key, attribute_key` | Fetch all attributes for one entity |
| Attribute-filter layouts | `entity_scope, attribute_key, value, entity_key` | Facets, counts, filters, histograms, cohort comparison |

### Generic Metric Fact Tables

Canonical tables for generic metrics.

| Table | Value column | Purpose |
| --- | --- | --- |
| `sample_metric_numeric` | `value DOUBLE` | Numeric metric observations |
| `sample_metric_string` | `value TEXT` | String/categorical metric observations |
| `sample_metric_json` | `value_json JSON` | Rare structured metric observations |

Common columns:

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical profile this metric belongs to |
| `run_id` | Producing/importing run |
| `run_sample_key` | Nullable processed sample |
| `sample_key` | Nullable sample shortcut for filtering |
| `metric_key` | Metric definition |
| `source_file_id` | Nullable source file |

Recommended physical layouts:

| Table | Physical order | Optimized for |
| --- | --- | --- |
| `sample_metric_numeric` | `data_profile_key, run_id, run_sample_key, metric_key` | Canonical table and fast run/sample detail queries |
| `sample_metric_numeric_by_metric` | `data_profile_key, metric_key, value, run_sample_key` | Derived table for metric scans, distributions, and top-N |

The canonical numeric table should be physically sorted for sample-centric
queries. The by-metric table is the one duplicate needed for the other hot path.
This avoids maintaining three copies of numeric metrics. Add by-metric tables
for string or JSON metrics only if real query pressure appears.

### `features`

Shared feature/entity dictionary.

Features are broader than genes. Use the same dictionary for genes,
transcripts, proteins, antibodies, pathways, signatures, intervals, compounds,
metrics, and generic assay entities when they are measured across samples.

| Column | Notes |
| --- | --- |
| `feature_key` | Internal key |
| `feature_id` | Stable feature ID |
| `feature_type` | Example: `gene`, `transcript`, `protein`, `antibody`, `pathway`, `signature`, `interval`, `metric`, `generic_entity` |
| `symbol` | Human-readable symbol/name |
| `stable_id` | Stable external ID |
| `namespace` | External namespace, such as HGNC, Ensembl, UniProt, MSigDB |
| `genome_build` | Nullable genome build for genomic features |
| `metadata_json` | Flexible feature metadata |

### `feature_aliases`

Aliases and alternate identifiers for shared features.

| Column | Notes |
| --- | --- |
| `feature_key` | Feature being aliased |
| `alias` | Alias text |
| `namespace` | Alias namespace/source |

### `feature_sets`

Named feature collections used for gene panels, pathway definitions, selected
metric groups, interval sets, and reference feature universes.

| Column | Notes |
| --- | --- |
| `feature_set_key` | Internal key |
| `feature_set_id` | Stable feature-set ID |
| `feature_set_type` | Example: `gene_panel`, `pathway_collection`, `interval_set`, `metric_group` |
| `name` | Human-readable name |
| `description` | Optional description |
| `metadata_json` | Flexible feature-set metadata |

### `feature_set_members`

| Column | Notes |
| --- | --- |
| `feature_set_key` | Owning feature set |
| `feature_key` | Included feature |
| `member_role` | Optional role |
| `metadata_json` | Flexible member metadata |

### Observed Profile Availability

Goodomics does not maintain a separate sample/profile availability fact table.
Observed availability is derived from the typed fact tables and
`profile_payloads`: if a run sample has rows for a `data_profile_key`, that
profile is observed for that run sample. If a source needs to preserve
"profiled but no emitted rows" semantics later, add an explicit source-specific
fact or coverage table for that use case rather than duplicating every
sample/profile relationship by default.

### `feature_value_numeric`

For expression matrices and any similar sample x feature quantitative profile:
TPM, counts, methylation beta values, protein abundance, pathway scores,
signature scores, log2 copy-number values, and quantitative assay outputs.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical feature-value profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `feature_key` | Gene/transcript/protein/pathway/signature/generic entity |
| `value` | Numeric value |
| `value_semantics` | Example: `tpm`, `count`, `log2_cna`, `beta`, `abundance`, `score`, `zscore` |
| `source_file_id` | Nullable source file |

Recommended derived layouts:

| Layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical | `data_profile_key, feature_key, run_sample_key` | Gene/feature across samples, cohort matrices, correlations |
| By sample | `data_profile_key, run_sample_key, feature_key` | Sample detail pages and sample profile exports |
| By value | `data_profile_key, feature_key, value, run_sample_key` | Threshold filters and top/bottom values |

`expression_values` can exist as a view or compatibility alias over
`feature_value_numeric` where `value_semantics` is expression-specific.

### `feature_call`

For sample x feature observations that are categorical, binary, ordinal, or
discrete instead of continuous numeric values.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical call profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `feature_key` | Feature being called |
| `call_code` | Stable call code, such as `AMP`, `HOMDEL`, `GAIN`, `LOSS`, `present`, `absent` |
| `call_label` | Human-readable call label |
| `call_rank` | Nullable ordinal rank, such as -2 to 2 for discrete CNA |
| `score` | Nullable call score |
| `confidence` | Nullable confidence |
| `source_event_id` | Nullable link to canonical event/call source |
| `source_file_id` | Nullable source file |

Recommended physical layouts:

| Layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical | `data_profile_key, feature_key, call_code, run_sample_key` | Counts by feature/call and cohort filters |
| By sample | `data_profile_key, run_sample_key, feature_key` | Sample detail pages and OncoPrint exports |

### `genomic_intervals`

Canonical interval dictionary for BED-like regions, peaks, windows, and other
coordinate-based features.

| Column | Notes |
| --- | --- |
| `interval_key` | Internal key |
| `genome_build` | Reference build |
| `contig` | Chromosome/contig |
| `start_pos` | 1-based inclusive start |
| `end_pos` | Inclusive end |
| `strand` | Nullable strand |
| `feature_key` | Nullable linked feature |
| `interval_type` | Example: `peak`, `coverage_window`, `target_region`, `probe` |
| `metadata_json` | Flexible interval metadata |

Recommended physical order: `genome_build, contig, start_pos, end_pos`.

### `sample_interval_values`

Per-sample measurements over genomic intervals.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical interval-value profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `interval_key` | Genomic interval |
| `value` | Numeric value |
| `value_semantics` | Example: `coverage`, `accessibility`, `peak_score`, `methylation_beta` |
| `source_file_id` | Nullable source file |

Recommended layouts: sample-first for detail queries, interval/region-first for
genome-browser and locus queries.

### `copy_number_segments`

Segmented copy-number data. Keep this separate from gene-level CNA calls.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical segment profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `genome_build` | Reference build |
| `contig` | Chromosome/contig |
| `start_pos` | Segment start |
| `end_pos` | Segment end |
| `num_probes` | Nullable probe/bin count |
| `segment_mean` | Segment mean or log ratio |
| `total_copy_number` | Nullable total copy number |
| `minor_copy_number` | Nullable minor copy number |
| `call_label` | Nullable segment call |
| `source_file_id` | Nullable source file |

Recommended physical layouts:

| Layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical | `data_profile_key, run_sample_key, contig, start_pos` | Sample segment plots |
| By region | `genome_build, contig, start_pos, end_pos, data_profile_key, run_sample_key` | Region/locus queries and IGV context |

### `variants`

Canonical variant identity table.

| Column | Notes |
| --- | --- |
| `variant_key` | Internal key |
| `variant_id` | Stable variant ID |
| `genome_build` | Reference build |
| `contig` | Chromosome/contig |
| `pos` | 1-based position |
| `end_pos` | End position |
| `ref` | Reference allele |
| `alt` | Alternate allele |
| `variant_type` | Example: SNV, insertion, deletion |
| `normalized_key` | Stable normalized identity |

Recommended physical order: `genome_build, contig, pos, end_pos, variant_key`.

### `variant_annotations`

Variant annotations. Some annotations may be profile-specific.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Annotation profile/source |
| `variant_key` | Variant identity |
| `feature_key` | Nullable linked gene/feature |
| `consequence` | Nullable consequence |
| `impact` | Nullable impact |
| `clinvar_significance` | Nullable ClinVar annotation |
| `gnomad_af` | Nullable population frequency |
| `info_json` | Full or extra INFO-style data |

### `variant_transcript_annotations`

Transcript-level annotations for variants. Use this when consequences,
protein changes, exon/intron context, or canonical-transcript status matter.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Annotation profile/source |
| `variant_key` | Variant identity |
| `transcript_feature_key` | Transcript feature |
| `gene_feature_key` | Nullable gene feature |
| `consequence` | Consequence term |
| `impact` | Nullable impact |
| `protein_change` | Nullable protein change |
| `cdna_change` | Nullable cDNA change |
| `protein_pos_start` | Nullable protein start |
| `protein_pos_end` | Nullable protein end |
| `canonical` | Nullable canonical-transcript flag |
| `annotation_json` | Full or extra annotation data |

### `sample_variant_calls`

Sample-level variant calls.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical variant-call profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `variant_key` | Variant identity |
| `genotype` | Genotype/call |
| `depth` | Read depth |
| `genotype_quality` | Genotype quality |
| `allele_depth_ref` | Reference allele depth |
| `allele_depth_alt` | Alternate allele depth |
| `allele_fraction` | Alternate allele fraction |
| `filter` | Variant/call filter |
| `format_json` | Full or extra FORMAT-style data |
| `source_file_id` | Nullable source file |

Recommended derived layouts:

| Layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical | `data_profile_key, run_sample_key, variant_key` | Fetch all calls for one processed sample |
| By variant | `data_profile_key, variant_key, run_sample_key` | Exact variant recurrence and carrier lookup |
| By position | `genome_build, contig, pos, end_pos, variant_key` | Genomic range queries |
| By gene | `feature_key, data_profile_key, run_sample_key, variant_key` | Gene-centric variant queries |

### `structural_variant_events`

Canonical structural variant or fusion-like events.

| Column | Notes |
| --- | --- |
| `structural_variant_key` | Internal key |
| `event_id` | Stable event ID |
| `event_class` | Example: `fusion`, `translocation`, `inversion`, `deletion`, `duplication` |
| `genome_build` | Reference build |
| `site1_feature_key` | Nullable gene/transcript feature at site 1 |
| `site2_feature_key` | Nullable gene/transcript feature at site 2 |
| `site1_contig` | Nullable site 1 contig |
| `site1_pos` | Nullable site 1 position |
| `site2_contig` | Nullable site 2 contig |
| `site2_pos` | Nullable site 2 position |
| `frame_status` | Nullable in-frame/out-of-frame status |
| `event_info` | Nullable display/event string |
| `annotation_json` | Full or extra annotation data |

### `sample_structural_variant_calls`

Sample-level calls for structural variant events.

| Column | Notes |
| --- | --- |
| `data_profile_key` | Logical SV profile |
| `run_id` | Producing/importing run |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut for filtering |
| `structural_variant_key` | Structural variant event |
| `call_status` | Example: `called`, `filtered`, `uncalled` |
| `dna_support` | Nullable DNA support description |
| `rna_support` | Nullable RNA support description |
| `tumor_read_count` | Nullable tumor read count |
| `normal_read_count` | Nullable normal read count |
| `split_read_count` | Nullable split-read count |
| `paired_end_read_count` | Nullable paired-end count |
| `format_json` | Extra call fields |
| `source_file_id` | Nullable source file |

Recommended layouts: sample-first for detail pages, gene/site-first for
gene-centric SV queries.

### `timeline_events`

Subject/sample events over time. Optional for early QC, but useful for clinical
or longitudinal data.

| Column | Notes |
| --- | --- |
| `event_key` | Internal key |
| `subject_key` | Subject |
| `sample_key` | Nullable sample |
| `run_sample_key` | Nullable processed sample |
| `event_type` | Example: `collection`, `treatment`, `diagnosis`, `outcome`, `status` |
| `start_time` | Nullable start time or relative time |
| `end_time` | Nullable end time |
| `time_unit` | Nullable unit for relative time |
| `event_status` | Nullable status/result |
| `metadata_json` | Flexible event details |

Recommended physical order: `subject_key, event_type, start_time`.

### `profile_payloads`

Logical payloads for results that are naturally consumed as one object or are
not yet worth promoting into typed facts.

| Column | Notes |
| --- | --- |
| `payload_id` | Primary key |
| `data_profile_key` | Logical profile this payload belongs to |
| `run_id` | Producing/importing run |
| `run_sample_key` | Nullable processed sample |
| `payload_name` | Stable payload name |
| `payload_kind` | Example: `table`, `matrix`, `json`, `array`, `log`, `report_section` |
| `storage_format` | Example: `parquet`, `arrow`, `json`, `text`, `html` |
| `path` | Local path if materialized |
| `uri` | Object-store or remote URI if applicable |
| `schema_json` | Optional schema for tabular payloads |
| `row_count` | Nullable row count |
| `source_file_id` | Nullable source file |
| `metadata_json` | Flexible payload metadata |

Payloads are the escape hatch, not the destination for hot analytical queries.
Promote payload contents into typed tables when users need filters, joins,
cohort comparisons, or dashboards over those rows.

### `gene_alteration_state`

Derived table for cBioPortal-like alteration queries. This is not a canonical
source of truth; it is built from variants, CNA calls, structural variants,
expression outliers, methylation calls, protein calls, and other typed sources.

| Column | Notes |
| --- | --- |
| `run_sample_key` | Processed sample |
| `sample_key` | Sample shortcut |
| `subject_key` | Nullable subject shortcut |
| `feature_key` | Usually a gene feature |
| `data_profile_key` | Source profile |
| `alteration_type` | Example: `mutation`, `cna`, `sv`, `expression_outlier`, `methylation`, `protein`, `signature` |
| `alteration_subtype` | More specific type or call |
| `is_altered` | Boolean alteration state |
| `value_numeric` | Nullable numeric value |
| `value_string` | Nullable string/call value |
| `driver_status` | Nullable driver/passenger/unknown annotation |
| `source_table` | Canonical source table |
| `source_event_id` | Source event/call identifier |

Recommended physical layouts:

| Layout | Physical order | Optimized for |
| --- | --- | --- |
| Canonical | `feature_key, alteration_type, data_profile_key, run_sample_key` | Alteration frequency, filters, OncoPrint matrices |
| By sample | `run_sample_key, feature_key, alteration_type` | Sample detail and sample-centric exports |

### Cohort Summary Tables

Precomputed reference-set and cohort statistics. Start with metric summaries,
then add feature/profile summaries as query pressure appears.

| Column | Notes |
| --- | --- |
| `sample_set_id` | Cohort/reference set |
| `data_profile_key` | Profile summarized |
| `metric_key` | Nullable metric summarized |
| `feature_key` | Nullable feature summarized |
| `n` | Observation count |
| `mean` | Mean |
| `median` | Median |
| `stddev` | Standard deviation |
| `min` | Minimum |
| `max` | Maximum |
| `q05` | 5th percentile |
| `q25` | 25th percentile |
| `q75` | 75th percentile |
| `q95` | 95th percentile |

## Data Profile Rule

Every analytical fact table should include `data_profile_key` or
`data_profile_id` when the row stores an actual value, call, measurement, or
profile-specific record. Prefer `data_profile_key` in large DuckDB fact tables
and keep `data_profile_id` as the stable external/control-store identifier.

Examples:

| Table | Should include profile identity? | Why |
| --- | --- | --- |
| `sample_metric_numeric` | Yes | Metric value belongs to a logical metric profile |
| `feature_value_numeric` | Yes | Numeric feature value belongs to one feature-value profile |
| `feature_call` | Yes | Feature call belongs to one call profile |
| `sample_variant_calls` | Yes | Call belongs to one variant-call profile |
| `copy_number_segments` | Yes | Segment belongs to one segment profile |
| `sample_structural_variant_calls` | Yes | SV call belongs to one SV profile |
| `profile_payloads` | Yes | Payload belongs to one logical profile |
| `variant_annotations` | Usually yes | Annotation meaning/source can vary by profile |
| `variants` | No | Canonical variant identity is shared |
| `features` | No | Shared feature dictionary |
| `genomic_intervals` | No | Canonical interval identity can be shared |
| `samples` | No | Control-store entity, not an analytical fact |
| `files` | No | File entity; use `file_links` to connect to profiles |

## Worked Example

### Project

| Field | Value |
| --- | --- |
| `project_id` | `precision-oncology-demo` |

### Subjects

| subject_id |
| --- |
| `P001` |
| `P002` |

### Samples

| sample_id | subject_id | sample_name |
| --- | --- | --- |
| `P001_Tumor_DNA` | `P001` | P001 tumor DNA |
| `P001_Normal_DNA` | `P001` | P001 normal DNA |
| `P001_Tumor_RNA` | `P001` | P001 tumor RNA |
| `P002_Tumor_DNA` | `P002` | P002 tumor DNA |
| `P002_Normal_DNA` | `P002` | P002 normal DNA |
| `P002_Tumor_RNA` | `P002` | P002 tumor RNA |

### Runs

| run_id | assay | pipeline_name | pipeline_version |
| --- | --- | --- | --- |
| `run_wes_batch_042` | `tumor_normal_wes` | `nf-core/sarek` | `3.5` |
| `run_rnaseq_batch_042` | `bulk_rnaseq` | `nf-core/rnaseq` | `3.18` |
| `run_rnaseq_batch_042_rerun` | `bulk_rnaseq` | `nf-core/rnaseq` | `3.19` |

### Processed Samples

| run_sample_id | run_id | sample_id |
| --- | --- | --- |
| `run_wes_batch_042:P001_Tumor_DNA` | `run_wes_batch_042` | `P001_Tumor_DNA` |
| `run_wes_batch_042:P001_Normal_DNA` | `run_wes_batch_042` | `P001_Normal_DNA` |
| `run_wes_batch_042:P002_Tumor_DNA` | `run_wes_batch_042` | `P002_Tumor_DNA` |
| `run_wes_batch_042:P002_Normal_DNA` | `run_wes_batch_042` | `P002_Normal_DNA` |
| `run_rnaseq_batch_042:P001_Tumor_RNA` | `run_rnaseq_batch_042` | `P001_Tumor_RNA` |
| `run_rnaseq_batch_042:P002_Tumor_RNA` | `run_rnaseq_batch_042` | `P002_Tumor_RNA` |
| `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `run_rnaseq_batch_042_rerun` | `P001_Tumor_RNA` |
| `run_rnaseq_batch_042_rerun:P002_Tumor_RNA` | `run_rnaseq_batch_042_rerun` | `P002_Tumor_RNA` |

### Data Profiles

| data_profile_id | data_type | producer_tool | Notes |
| --- | --- | --- | --- |
| `multiqc:qc_metrics` | `generic_metrics` | MultiQC | Built-in QC metric contract reused across runs |
| `cbioportal:mutations:maf` | `small_variants` | cBioPortal | Built-in cBioPortal mutation contract |
| `cbioportal:copy_number:segments` | `copy_number_segments` | cBioPortal | Built-in segment-level CNA contract |
| `goodomics:sdk_metrics` | `generic_metrics` | goodomics-sdk | Native SDK metric contract |
| `project_rnaseq:salmon_gene_tpm` | `feature_matrix` | Salmon | Example project-defined profile |

### Files

| file_id | file_role | Linked profile |
| --- | --- | --- |
| `P001_T.bam` | `bam` | `bwa_alignment_files` |
| `P001_T.bam.bai` | `bai` | `bwa_alignment_files` |
| `P001.mutect2.vcf.gz` | `vcf` | `mutect2_somatic_variants` |
| `P001.mutect2.vcf.gz.tbi` | `tbi` | `mutect2_somatic_variants` |
| `multiqc_report.html` | `report` | `multiqc:qc_metrics` |
| `P001_salmon_quant.sf` | `expression_table` | `salmon_gene_tpm_v318` |
| `P002_salmon_quant.sf` | `expression_table` | `salmon_gene_tpm_v318` |

### Example Metric Observations

| data_profile_id | run_sample_id | metric | value |
| --- | --- | --- | --- |
| `multiqc:qc_metrics` | `run_rnaseq_batch_042:P001_Tumor_RNA` | `pct_mapped` | `91.2` |
| `multiqc:qc_metrics` | `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `pct_mapped` | `93.8` |

### Example Numeric Feature Observations

| data_profile_id | run_sample_id | feature | value_semantics | value |
| --- | --- | --- | --- | --- |
| `salmon_gene_tpm_v318` | `run_rnaseq_batch_042:P001_Tumor_RNA` | `TP53` | `tpm` | `12.4` |
| `salmon_gene_tpm_v319` | `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `TP53` | `tpm` | `13.1` |

### Example Profile Availability

| data_profile_id | run_sample_id | availability_status | feature_set |
| --- | --- | --- | --- |
| `mutect2_somatic_variants` | `run_wes_batch_042:P001_Tumor_DNA` | `profiled` | `wes_targets` |
| `salmon_gene_tpm_v318` | `run_rnaseq_batch_042:P001_Tumor_RNA` | `profiled` | `protein_coding_genes` |

### Example Variant Call

| data_profile_id | run_sample_id | variant | gene | genotype | depth | allele_fraction |
| --- | --- | --- | --- | --- | --- | --- |
| `mutect2_somatic_variants` | `run_wes_batch_042:P001_Tumor_DNA` | `chr17:7674220:G>A` | `TP53` | `0/1` | `118` | `0.37` |

### Example Alteration State

| run_sample_id | gene | alteration_type | alteration_subtype | is_altered | source_profile |
| --- | --- | --- | --- | --- | --- |
| `run_wes_batch_042:P001_Tumor_DNA` | `TP53` | `mutation` | `missense` | `true` | `mutect2_somatic_variants` |

### Reference Set

| sample_set_id | kind |
| --- | --- |
| `production-rnaseq-reference-v318` | `reference_set` |

Members:

| sample_set_id | run_sample_id |
| --- | --- |
| `production-rnaseq-reference-v318` | `run_rnaseq_batch_042:P001_Tumor_RNA` |
| `production-rnaseq-reference-v318` | `run_rnaseq_batch_042:P002_Tumor_RNA` |

The reference set includes processed samples from the RNA-seq 3.18 run. It does
not include raw sample `P001_Tumor_RNA` by itself, because that sample was also
processed by RNA-seq 3.19.

### Agent/MCP Interpretation

Given this model, an MCP layer can accurately say:

> This project has WES variants from Mutect2, WES alignment files from BWA,
> RNA-seq QC metrics from MultiQC, and gene TPM profiles from Salmon. Sample
> `P001_Tumor_RNA` has two RNA-seq processed results: one from nf-core/rnaseq
> 3.18 and one from 3.19.
