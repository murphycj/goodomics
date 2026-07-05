# Goodomics Core Data Model

This file is the source of truth for Goodomics data model terminology and
schema-direction discussions. Use it when working on core data concepts, table
shapes, SQL vs DuckDB responsibilities, data imports, data contracts, processed
samples, files, observations, and agent/MCP data-query behavior.

The guiding split:

- **SQL control store**: remembers what exists, where it came from, and how
  entities relate.
- **DuckDB analytical store**: stores and query-optimizes measurements, calls,
  matrices, summaries, and derived views.

The guiding identity rule:

- SQL control store tables use integer `id` primary keys and integer foreign keys for internal
  relationships.
- Human-readable/source identifiers such as `sample_id`, `run_id`,
  `data_contract_id`, `file_id`, and `feature_label` are stable, indexed label
  columns, not the physical join mechanism.
- DuckDB analytical fact tables use integer columns named for the referenced
  entity, such as `sample_id`, `run_sample_id`, `feature_id`, `field_id`, and
  `data_contract_id`.
- User/API/ingest boundaries may accept readable labels, then resolve them to
  integer IDs before writing analytical rows.

## Core Relationship Model

| Concept          | User-facing meaning                                         | Implementation role                                                                |
| ---------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Project          | Workspace or data boundary                                  | Owns runs, samples, files, sample sets, contracts, and analytical store             |
| Subject          | Optional patient, donor, organism, cell line, or individual | Links related samples                                                              |
| Sample           | Biological or material sample users recognize and navigate  | Stable sample identity across runs                                                 |
| Data import      | Data entry/audit event                                      | Records how files/results entered Goodomics                                        |
| Run              | Computational, benchmark, or imported analytical result     | Captures one result-producing execution or result snapshot                         |
| Processed sample | A sample within a specific run                              | Internal `run_sample` grain for latest-run lookup, comparison, and metrics         |
| File             | Original or derived file                                    | Tracks physical evidence and outputs                                               |
| Data contract     | Smallest logical queryable dataset                          | Declares data type, provenance, and query behavior                                 |
| Sample set       | Saved group of processed samples                            | General primitive behind cohorts and reference sets                                |
| Cohort           | Sample set used for grouping or comparison                  | Specialized sample set                                                             |
| Reference set    | Sample set used as a baseline                               | Specialized sample set                                                             |
| Feature          | Thing being measured                                        | Metric, gene, transcript, protein, antibody, variant, interval, pathway, signature |
| Observation      | Value, call, or measurement                                 | Conceptual analytical fact stored in modular tables                                |

Short version:

| Term                 | Meaning                                                     |
| -------------------- | ----------------------------------------------------------- |
| Sample               | The biological sample users care about                      |
| Data import          | How data entered Goodomics                                  |
| Run                  | Analytical or computational result represented in Goodomics |
| Processed sample     | That sample in that run                                     |
| Data contract         | What kind of data was produced                              |
| Observation          | A value/call/measurement inside that contract                |
| Cohort/reference set | Selected processed samples                                  |

## SQL Control Store

These tables are smaller, relational, and CRUD-oriented.

### `projects`

Main workspace boundary.

| Column          | Notes                                      |
| --------------- | ------------------------------------------ |
| `id`            | Integer primary key                        |
| `project_id`    | Stable readable project ID, unique/indexed |
| `slug`          | Optional readable project slug, indexed    |
| `name`          | Human-readable name                        |
| `description`   | Optional description                       |
| `metadata_json` | Flexible project metadata                  |
| `created_at`    | Creation timestamp                         |

### `subjects`

Optional. Useful for patients, donors, organisms, cell lines, or longitudinal
studies.

| Column          | Notes                                      |
| --------------- | ------------------------------------------ |
| `id`            | Integer primary key                        |
| `subject_id`    | Stable readable subject ID, unique/indexed |
| `project_id`    | Owning project integer ID                  |
| `metadata_json` | Subject-level metadata                     |

### `samples`

The stable biological or material sample users recognize. Samples are the
primary way users interact with biological data: a sample page should be able to
show the latest run data for that sample while still preserving older runs for
comparison. The same sample can be processed by many pipelines, rerun by a newer
pipeline version, or appear in many imports.

Use sample metadata for stable biological context. Use runs and processed
samples for execution context, tool outputs, and per-run status.

| Column          | Notes                                     |
| --------------- | ----------------------------------------- |
| `id`            | Integer primary key                       |
| `sample_id`     | Stable readable sample ID, unique/indexed |
| `project_id`    | Owning project integer ID                 |
| `subject_id`    | Nullable subject integer ID               |
| `sample_name`   | Human-readable sample name                |
| `metadata_json` | Sample-level metadata                     |

### `data_imports`

An audit/provenance record for data entering Goodomics. Every explicit ingest
path, such as cBioPortal, MultiQC, FastQC, BWA outputs, or user-provided files,
should create a `data_imports` row. This table answers "how did this data get
into Goodomics?" without forcing raw imports to masquerade as analytical runs.

| Column             | Notes                                                           |
| ------------------ | --------------------------------------------------------------- |
| `id`               | Integer primary key                                             |
| `data_import_id`   | Stable readable import ID, unique/indexed                       |
| `project_id`       | Owning project integer ID                                       |
| `source_type`      | Source family, such as `cbioportal`, `multiqc`, `fastqc`, `bwa` |
| `source_uri`       | Optional remote/object-store source                             |
| `source_path`      | Optional local source path                                      |
| `importer_name`    | Goodomics importer/parser name                                  |
| `importer_version` | Optional importer/parser version                                |
| `status`           | Import status                                                   |
| `started_at`       | Nullable import start timestamp                                 |
| `ended_at`         | Nullable import end timestamp                                   |
| `parameters_json`  | Import parameters/configuration                                 |
| `summary_json`     | Counts and summary information                                  |
| `metadata_json`    | Source-specific provenance metadata                             |
| `created_at`       | Creation timestamp                                              |

### `runs`

A computational, benchmark, or imported analytical result. A run is one
result-producing execution, result snapshot, notebook analysis, optimization
attempt, model-training experiment, or imported external result represented
inside Goodomics.

Runs do not have to correspond to samples. For algorithm optimization,
benchmarking, model training, or other sample-less work, keep the run without
`run_samples`. When a run does correspond to biological samples, connect it
through `run_samples` rather than baking sample identity into the run table
itself.

For sample-first sources such as cBioPortal, Goodomics creates one
`data_imports` row plus one imported-result run per biological sample. It does
not create an extra import-context run. Analytical facts reference the
per-sample run IDs; source files link back to the `data_imports` row and the
relevant data contracts.

| Column             | Notes                                                                       |
| ------------------ | --------------------------------------------------------------------------- |
| `id`               | Integer primary key                                                         |
| `run_id`           | Stable readable run ID, unique/indexed                                      |
| `project_id`       | Owning project integer ID                                                   |
| `data_import_id`   | Nullable import integer ID that created this run                            |
| `name`             | Human-readable run name                                                     |
| `run_kind`         | Example: `pipeline_run`, `imported_result`, `benchmark_run`, `notebook_run` |
| `assay`            | Nullable assay label                                                        |
| `pipeline_name`    | Nullable pipeline/workflow name                                             |
| `pipeline_version` | Nullable pipeline/workflow version                                          |
| `parameters_json`  | Run-level parameters/configuration                                          |
| `started_at`       | Nullable start timestamp                                                    |
| `ended_at`         | Nullable end timestamp                                                      |
| `status`           | Run status                                                                  |
| `metadata_json`    | Flexible run metadata                                                       |

### `run_samples`

Internal linker/result table. User-facing wording should usually be
**processed sample** or **sample result**.

This is the key sample/run comparison grain. A sample can have many processed
samples across time as users rerun the same pipeline, run new tools, or ingest
new source data. Latest-run views for a sample should be derived from
`run_samples` joined to `runs`, usually ordered by run timestamps/status rather
than stored as a denormalized cache.

| Column          | Notes                                                            |
| --------------- | ---------------------------------------------------------------- |
| `id`            | Integer primary key                                              |
| `run_sample_id` | Stable readable processed-sample ID, unique/indexed              |
| `project_id`    | Owning project integer ID                                        |
| `run_id`        | Integer run ID that processed or produced this result            |
| `sample_id`     | Nullable integer sample ID                                       |
| `assay`         | Nullable assay label                                             |
| `role`          | Optional role, such as `tumor`, `normal`, `control`, `truth_set` |
| `status`        | Processed-sample status                                          |
| `metadata_json` | Flexible per-run sample metadata                                 |

### `data_contracts`

Stable semantic query contracts. A data contract declares what kind of data a
parser, SDK workflow, or user-defined source writes, how it should be queried,
and how agents should understand it. Built-in contract IDs are stable across
projects, runs, samples, and source datasets, so MCP tools and agents can ask
for `cbioportal:mutations:maf` or `salmon:metrics` without learning a
specific import run ID.

A data contract is not a dataset instance and is not sample membership. Data
imports, runs, files, file links, `data_sources`, fact-table `run_id` columns,
payload metadata, and source metadata carry provenance such as cBioPortal study
IDs, source filenames, generated import IDs, source `stable_id` values, and
platform descriptions.

A data contract is also not the same thing as a field definition. A contract might
be `fastqc:raw:metrics`; the fields inside it might be
`general_stats.fastqc_raw_percent_duplicates` and
`general_stats.fastqc_raw_total_sequences`. Keep contract-level query behavior,
source fingerprints, summaries, and agent descriptions on `data_contracts`, and
keep per-field labels, units, directions, query refs, and compact summaries in
`data_contract_fields`.

| Column                  | Notes                                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------- |
| `id`                    | Integer primary key                                                                                           |
| `data_contract_id`       | Stable readable contract ID, unique/indexed                                                                    |
| `project_id`            | Nullable integer owner for user/project-defined contracts; built-ins are global                                |
| `name`                  | Human-readable contract name                                                                                   |
| `data_type`             | Example: `generic_metrics`, `feature_matrix`, `feature_calls`, `small_variants`, `copy_number_segments`       |
| `assay`                 | Nullable assay label                                                                                          |
| `producer_tool`         | Tool that produced this logical dataset                                                                       |
| `producer_tool_version` | Tool version                                                                                                  |
| `producer_pipeline`     | Pipeline/workflow that produced this contract                                                                  |
| `genome_build`          | Nullable genome/reference build                                                                               |
| `feature_type`          | Example: `metric`, `gene`, `transcript`, `protein`, `antibody`, `variant`, `interval`, `pathway`, `signature` |
| `value_type`            | Example: `numeric`, `categorical`, `call`, `matrix`                                                           |
| `unit`                  | Nullable default unit                                                                                         |
| `entity_grain`          | Default entity grain, such as `run_sample`, `sample`, `subject`, `feature`, or `run`                          |
| `value_semantics`       | Contract-level meaning, such as `tpm`, `count`, `log2_cna`, `beta`, `score`, or `zscore`                       |
| `primary_table`         | Default analytical table for contract-first queries                                                            |
| `physical_tables_json`  | Physical tables/views used by the contract                                                                     |
| `summary_json`          | Compact contract-level summary                                                                                 |
| `last_profiled_at`      | Last time field/contract summaries were computed                                                               |
| `source_fingerprint`    | Fingerprint for invalidating derived summaries/cache rows                                                     |
| `query_modes_json`      | Supported query modes, such as sample, metric, gene, region                                                   |
| `mcp_description`       | Agent-readable description                                                                                    |
| `metadata_json`         | Flexible contract metadata                                                                                     |

Examples:

| Data contract                      | Data type              | Producer   |
| --------------------------------- | ---------------------- | ---------- |
| `salmon:metrics`                  | `generic_metrics`      | Salmon     |
| `fastqc:raw:metrics`              | `generic_metrics`      | FastQC     |
| `cbioportal:mutations:maf`        | `small_variants`       | cBioPortal |
| `cbioportal:copy_number:segments` | `copy_number_segments` | cBioPortal |
| `picard:alignment:metrics`        | `generic_metrics`      | Picard     |
| `mutect2_somatic_variants`        | `small_variants`       | Mutect2    |
| `salmon_gene_tpm`                 | `feature_matrix`       | Salmon     |
| `gistic_gene_cna`                 | `feature_calls`        | GISTIC     |
| `bwa_alignment_files`             | `alignment_files`      | BWA        |

### `files`

Physical files Goodomics knows about.

| Column          | Notes                                                         |
| --------------- | ------------------------------------------------------------- |
| `id`            | Integer primary key                                           |
| `file_id`       | Stable readable file ID, unique/indexed                       |
| `project_id`    | Owning project integer ID                                     |
| `path`          | Local path, if applicable                                     |
| `uri`           | URI/object-store location, if applicable                      |
| `file_role`     | Example: `fastq`, `bam`, `bai`, `vcf`, `tbi`, `report`, `log` |
| `format`        | File format                                                   |
| `size_bytes`    | File size                                                     |
| `sha256`        | Content hash                                                  |
| `created_at`    | Creation or registration timestamp                            |
| `metadata_json` | Flexible file metadata                                        |

### `file_links`

Links files to the entities they support without overloading `files` with many
nullable ownership columns.

| Column            | Notes                                                              |
| ----------------- | ------------------------------------------------------------------ |
| `id`              | Integer primary key                                                |
| `file_id`         | Linked file integer ID                                             |
| `project_id`      | Owning project integer ID                                          |
| `data_import_id`  | Nullable linked data import integer ID                             |
| `run_id`          | Nullable linked run integer ID                                     |
| `run_sample_id`   | Nullable linked processed sample integer ID                        |
| `sample_id`       | Nullable linked raw sample integer ID                              |
| `data_contract_id` | Nullable linked data contract integer ID                            |
| `link_role`       | Relationship role, such as `source`, `index`, `derived`, `preview` |

### `sample_sets`

General saved grouping primitive.

| Column            | Notes                                                             |
| ----------------- | ----------------------------------------------------------------- |
| `id`              | Integer primary key                                               |
| `sample_set_id`   | Stable readable sample-set ID, unique/indexed                     |
| `project_id`      | Owning project integer ID                                         |
| `name`            | Human-readable set name                                           |
| `kind`            | Example: `cohort`, `reference_set`, `benchmark_set`, `case_group` |
| `description`     | Optional description                                              |
| `definition_json` | Optional rule/filter definition                                   |
| `created_at`      | Creation timestamp                                                |
| `metadata_json`   | Flexible sample-set metadata                                      |

### `sample_set_members`

Usually points to processed samples, not raw samples. Reference sets for QC
should generally be `run_sample_id` based.

| Column          | Notes                                |
| --------------- | ------------------------------------ |
| `id`            | Integer primary key                  |
| `sample_set_id` | Owning sample set integer ID         |
| `run_sample_id` | Included processed sample integer ID |

### Other SQL Control Tables

These stay in the control store and should point to projects, runs, processed
samples, data contracts, sample sets, and files where relevant.

| Table                  | Purpose                               |
| ---------------------- | ------------------------------------- |
| `insights`             | Saved chart, metric, and table definitions |
| `insight_revisions`    | Version history for saved insights    |
| `reports`              | Saved report layouts composed of insights |
| `report_revisions`     | Version history for saved reports     |
| `rendered_reports`     | Generated HTML report snapshots       |
| `insight_result_cache` | Cached computed insight payloads      |
| `report_result_cache`  | Cached computed report payloads       |
| `qc_policies`          | Threshold and decision policies       |
| `qc_decisions`         | Stored review/evaluation decisions    |
| `interpretation_notes` | Human- or agent-drafted notes         |

## DuckDB Analytical Store

These tables are larger and query-oriented. Any analytical table that stores
actual values, calls, measurements, or contract-specific rows should include the
integer `data_contract_id`.

Each project should have its own DuckDB analytical store by default, so large
analytics tables do not need to repeat `project_id` on every row. Store project
identity once in DuckDB metadata and keep `project_id` in the SQL control store.

Dimension tables do not always need contract identity.

The analytical store is modular by design. Do not force every ingested result
into one universal table. Use a small catalog of reusable biological data
shapes, and add derived layouts only for hot query paths.

| Shape                  | Purpose                                                          | Examples                                                                     |
| ---------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Scalar metrics         | QC and pipeline scalar values                                    | MultiQC metrics, Picard summary metrics, custom TSV metrics                  |
| Entity attributes      | Queryable metadata and clinical/context fields                   | Sample attributes, subject attributes, run batch, disease, tissue            |
| Contract availability   | Records what was profiled, even when no observation exists       | RNA-seq available, WGS profiled, gene panel coverage                         |
| Numeric feature values | Sample x feature quantitative matrices                           | TPM, counts, methylation beta values, protein abundance, pathway scores      |
| Feature calls          | Sample x feature categorical, binary, ordinal, or discrete calls | CNA AMP/HOMDEL, cluster labels, alteration present/absent                    |
| Small variants         | Exact variant identities and sample calls                        | SNVs, indels, MAF/VCF-derived calls                                          |
| Genomic intervals      | BED-like intervals and per-interval values                       | Peaks, coverage windows, accessible regions                                  |
| Copy-number segments   | Continuous genomic copy-number segments                          | Segment means, total copy number, minor copy number                          |
| Structural variants    | Paired breakend or fusion-like events                            | Fusions, translocations, inversions, deletions                               |
| Timeline events        | Subject/sample events over time                                  | Treatment, collection, diagnosis, outcome events                             |
| Logical payloads       | Queryable escape hatch for object-like outputs                   | Parsed tables, arrays, JSON payloads, logs, report sections                  |
| Derived query layouts  | Duplicate or reshape canonical data for hot access patterns      | By-metric metrics, by-feature matrices, by-region variants, alteration state |

Data contracts sit above these physical choices. A data contract names the logical
dataset and its provenance, while the contract's `data_type` determines whether
Goodomics stores it as scalar metrics, feature values, feature calls, variants,
intervals, segments, structural variants, logical payloads, and/or derived query
layouts.

Canonical tables preserve biological meaning and provenance. Derived tables
preserve speed and query semantics. Derived tables should be reproducible from
canonical tables and marked as caches or query layouts, not as the source of
truth.

### Physical Layout And Indexing

Use compact integer IDs in DuckDB analytical tables. Readable/source labels are
resolved at ingest/API boundaries and kept in SQL control tables or small DuckDB
dimension tables for lookup and display.

Examples:

| Fact column       | References readable label                                                 |
| ----------------- | ------------------------------------------------------------------------- |
| `data_contract_id` | `data_contracts.data_contract_id` or `dim_data_contracts.data_contract_label` |
| `run_id`          | `runs.run_id` or `dim_runs.run_key`                                       |
| `run_sample_id`   | `run_samples.run_sample_id` or `dim_run_samples.run_sample_label`         |
| `sample_id`       | `samples.sample_id` or `dim_samples.sample_label`                         |
| `subject_id`      | `subjects.subject_id` or `dim_subjects.subject_label`                     |
| `feature_id`      | `features.feature_label` or `dim_features.feature_label`                  |
| `field_id`        | `data_contract_fields.field_id` or `dim_fields.field_label`                |
| `variant_id`      | `variants.variant_label` or `dim_variants.variant_label`                  |

DuckDB analytical fact tables should rely primarily on physical ordering and
derived layouts, not many secondary indexes. Use indexes sparingly for selective
point lookups and small dimension tables. For large fact tables, choose one
canonical sort order that matches the main detail path, then add one duplicate
derived layout when a second axis is clearly hot.

General rule:

| Query family                   | Preferred layout                                              |
| ------------------------------ | ------------------------------------------------------------- |
| Sample/run detail              | `data_contract_id, run_id, run_sample_id, ...`                 |
| Feature/gene across a cohort   | `data_contract_id, feature_id, run_sample_id`                  |
| Metric scans/distributions     | `data_contract_id, field_id, value_numeric, run_sample_id`     |
| Attribute facets/filters       | `entity_scope, field_id, value_*, entity_id`                  |
| Genomic range queries          | `genome_build, contig, start_pos, end_pos`                    |
| Alteration frequency/OncoPrint | `feature_id, alteration_type, data_contract_id, run_sample_id` |

Do not maintain many duplicate layouts speculatively. Add a derived layout when
it serves a named UI, SDK, MCP, report, or notebook access path.

### `data_contract_fields`

SQL-side field catalog for queryable metrics, clinical attributes, metadata
facets, and other user-facing fields inside a data contract.

`data_contracts` describe a logical dataset. `data_contract_fields` describe the
queryable columns or measures inside that dataset. For example,
`fastqc:raw:metrics` is a data contract; `percent_duplicates` and
`general_stats.fastqc_raw_percent_gc` are fields.

| Column            | Notes                                                                     |
| ----------------- | ------------------------------------------------------------------------- |
| `data_contract_id` | SQL FK to the owning contract                                              |
| `field_id`        | Stable readable/source field key                                          |
| `field_role`      | Example: `metric`, `attribute`, `dimension`, `measure`                    |
| `entity_scope`    | Example: `subject`, `sample`, `run`, `run_sample`, `file`, `data_contract` |
| `display_name`    | Human-readable label                                                      |
| `value_type`      | Example: `numeric`, `string`, `boolean`, `date`, `json`                   |
| `unit`            | Nullable unit                                                             |
| `direction`       | Example: `higher_is_better`, `lower_is_better`                            |
| `description`     | Field description                                                         |
| `priority`        | Optional UI/report priority                                               |
| `query_ref_json`  | Physical table/value column hints for the query resolver                  |
| `summary_json`    | Compact min/max/top-values/examples summary                               |
| `metadata_json`   | Flexible field metadata                                                   |

### Entity Attributes

Unified EAV-style table for faceted metadata and clinical/context values:
`entity_attributes`.

| Column            | Notes                                                          |
| ----------------- | -------------------------------------------------------------- |
| `entity_scope`    | Entity type the value belongs to                               |
| `entity_id`       | Internal or stable entity key                                  |
| `field_id`        | Data contract field integer ID                                  |
| `data_contract_id` | Nullable source contract integer ID, when imported as a contract |
| `source_file_id`  | Nullable source file integer ID                                |
| `value_type`      | `numeric`, `string`, `boolean`, `date`, or `json`              |
| `value_numeric`   | Numeric value when `value_type = numeric`                      |
| `value_string`    | String/categorical value when `value_type = string`            |
| `value_boolean`   | Boolean value when `value_type = boolean`                      |
| `value_datetime`  | Date/time value when `value_type = date`                       |
| `value_json`      | Rare structured value when `value_type = json`                 |

Recommended physical layouts:

| Table/layout            | Physical order                           | Optimized for                                          |
| ----------------------- | ---------------------------------------- | ------------------------------------------------------ |
| Canonical attributes    | `entity_scope, entity_id, field_id`      | Fetch all attributes for one entity                    |
| Attribute filter layout | `entity_scope, field_id, value_*, entity_id` | Facets, counts, filters, histograms, cohort comparison |

### Sample Metrics

Unified table for generic sample/run metrics: `sample_metrics`.

| Column            | Notes                                             |
| ----------------- | ------------------------------------------------- |
| `data_contract_id` | Logical contract integer ID this metric belongs to |
| `run_id`          | Producing/importing run integer ID                |
| `run_sample_id`   | Nullable processed sample integer ID              |
| `sample_id`       | Nullable sample integer ID shortcut for filtering |
| `field_id`        | Data contract field integer ID                     |
| `source_file_id`  | Nullable source file integer ID                   |
| `value_type`      | `numeric`, `string`, or `json`                    |
| `value_numeric`   | Numeric value when `value_type = numeric`         |
| `value_string`    | String/categorical value when `value_type = string` |
| `value_json`      | Rare structured value when `value_type = json`    |

Recommended physical layouts:

| Table/layout                      | Physical order                                      | Optimized for                                            |
| --------------------------------- | --------------------------------------------------- | -------------------------------------------------------- |
| `sample_metrics`                  | `data_contract_id, run_id, run_sample_id, field_id`  | Canonical table and fast run/sample detail queries       |
| `sample_metric_numeric_by_metric` | `data_contract_id, field_id, value_numeric, run_sample_id` | Derived table for numeric scans, distributions, and top-N |

Keep direct table/SQL access available as an advanced mode, but use contracts and
fields as the default report, insight, dashboard, and MCP query surface.

### `features`

Shared feature/entity dictionary.

Features are broader than genes. Use the same dictionary for genes,
transcripts, proteins, antibodies, pathways, signatures, intervals, compounds,
metrics, and generic assay entities when they are measured across samples.

| Column          | Notes                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| `id`            | Optional integer dictionary ID when materialized                                                                     |
| `feature_label` | Stable readable feature key, unique/indexed                                                                          |
| `feature_id`    | Stable external/source feature ID when distinct from `feature_label`                                                 |
| `feature_type`  | Example: `gene`, `transcript`, `protein`, `antibody`, `pathway`, `signature`, `interval`, `metric`, `generic_entity` |
| `symbol`        | Human-readable symbol/name                                                                                           |
| `stable_id`     | Stable external ID                                                                                                   |
| `namespace`     | External namespace, such as HGNC, Ensembl, UniProt, MSigDB                                                           |
| `genome_build`  | Nullable genome build for genomic features                                                                           |
| `metadata_json` | Flexible feature metadata                                                                                            |

### `feature_aliases`

Aliases and alternate identifiers for shared features.

| Column       | Notes                  |
| ------------ | ---------------------- |
| `feature_id` | Feature integer ID     |
| `alias`      | Alias text             |
| `namespace`  | Alias namespace/source |

### `feature_sets`

Named feature collections used for gene panels, pathway definitions, selected
metric groups, interval sets, and reference feature universes.

| Column              | Notes                                                                        |
| ------------------- | ---------------------------------------------------------------------------- |
| `id`                | Optional integer dictionary ID when materialized                             |
| `feature_set_label` | Stable readable feature-set key, unique/indexed                              |
| `feature_set_id`    | Stable external/source feature-set ID when distinct from `feature_set_label` |
| `feature_set_type`  | Example: `gene_panel`, `pathway_collection`, `interval_set`, `metric_group`  |
| `name`              | Human-readable name                                                          |
| `description`       | Optional description                                                         |
| `metadata_json`     | Flexible feature-set metadata                                                |

### `feature_set_members`

| Column           | Notes                         |
| ---------------- | ----------------------------- |
| `feature_set_id` | Owning feature set integer ID |
| `feature_id`     | Included feature integer ID   |
| `member_role`    | Optional role                 |
| `metadata_json`  | Flexible member metadata      |

### Observed Contract Availability

Goodomics does not maintain a separate sample/contract availability fact table.
Observed availability is derived from the typed fact tables and
`contract_payloads`: if a run sample has rows for a `data_contract_id`, that
contract is observed for that run sample. If a source needs to preserve
"profiled but no emitted rows" semantics later, add an explicit source-specific
fact or coverage table for that use case rather than duplicating every
sample/contract relationship by default.

### `feature_value_numeric`

For expression matrices and any similar sample x feature quantitative contract:
TPM, counts, methylation beta values, protein abundance, pathway scores,
signature scores, log2 copy-number values, and quantitative assay outputs.

| Column            | Notes                                                                       |
| ----------------- | --------------------------------------------------------------------------- |
| `data_contract_id` | Logical feature-value contract integer ID                                    |
| `run_id`          | Producing/importing run integer ID                                          |
| `run_sample_id`   | Processed sample integer ID                                                 |
| `sample_id`       | Sample integer ID shortcut for filtering                                    |
| `feature_id`      | Gene/transcript/protein/pathway/signature/generic entity integer ID         |
| `value`           | Numeric value                                                               |
| `value_semantics` | Example: `tpm`, `count`, `log2_cna`, `beta`, `abundance`, `score`, `zscore` |
| `source_file_id`  | Nullable source file integer ID                                             |

Recommended derived layouts:

| Layout    | Physical order                                      | Optimized for                                              |
| --------- | --------------------------------------------------- | ---------------------------------------------------------- |
| Canonical | `data_contract_id, feature_id, run_sample_id`        | Gene/feature across samples, cohort matrices, correlations |
| By sample | `data_contract_id, run_sample_id, feature_id`        | Sample detail pages and sample contract exports             |
| By value  | `data_contract_id, feature_id, value, run_sample_id` | Threshold filters and top/bottom values                    |

Expression-specific measurements should use `feature_value_numeric` with an
appropriate `value_semantics` value.

### `feature_call`

For sample x feature observations that are categorical, binary, ordinal, or
discrete instead of continuous numeric values.

| Column            | Notes                                                                          |
| ----------------- | ------------------------------------------------------------------------------ |
| `data_contract_id` | Logical call contract integer ID                                                |
| `run_id`          | Producing/importing run integer ID                                             |
| `run_sample_id`   | Processed sample integer ID                                                    |
| `sample_id`       | Sample integer ID shortcut for filtering                                       |
| `feature_id`      | Feature integer ID being called                                                |
| `call_code`       | Stable call code, such as `AMP`, `HOMDEL`, `GAIN`, `LOSS`, `present`, `absent` |
| `call_label`      | Human-readable call label                                                      |
| `call_rank`       | Nullable ordinal rank, such as -2 to 2 for discrete CNA                        |
| `score`           | Nullable call score                                                            |
| `confidence`      | Nullable confidence                                                            |
| `source_event_id` | Nullable link to canonical event/call source                                   |
| `source_file_id`  | Nullable source file integer ID                                                |

Recommended physical layouts:

| Layout    | Physical order                                          | Optimized for                             |
| --------- | ------------------------------------------------------- | ----------------------------------------- |
| Canonical | `data_contract_id, feature_id, call_code, run_sample_id` | Counts by feature/call and cohort filters |
| By sample | `data_contract_id, run_sample_id, feature_id`            | Sample detail pages and OncoPrint exports |

### `genomic_intervals`

Canonical interval dictionary for BED-like regions, peaks, windows, and other
coordinate-based features.

| Column           | Notes                                                        |
| ---------------- | ------------------------------------------------------------ |
| `id`             | Optional integer dictionary ID when materialized             |
| `interval_label` | Stable readable interval key, unique/indexed                 |
| `genome_build`   | Reference build                                              |
| `contig`         | Chromosome/contig                                            |
| `start_pos`      | 1-based inclusive start                                      |
| `end_pos`        | Inclusive end                                                |
| `strand`         | Nullable strand                                              |
| `feature_id`     | Nullable linked feature integer ID                           |
| `interval_type`  | Example: `peak`, `coverage_window`, `target_region`, `probe` |
| `metadata_json`  | Flexible interval metadata                                   |

Recommended physical order: `genome_build, contig, start_pos, end_pos`.

### `sample_interval_values`

Per-sample measurements over genomic intervals.

| Column            | Notes                                                                  |
| ----------------- | ---------------------------------------------------------------------- |
| `data_contract_id` | Logical interval-value contract integer ID                              |
| `run_id`          | Producing/importing run integer ID                                     |
| `run_sample_id`   | Processed sample integer ID                                            |
| `sample_id`       | Sample integer ID shortcut for filtering                               |
| `interval_id`     | Genomic interval integer ID                                            |
| `value`           | Numeric value                                                          |
| `value_semantics` | Example: `coverage`, `accessibility`, `peak_score`, `methylation_beta` |
| `source_file_id`  | Nullable source file integer ID                                        |

Recommended layouts: sample-first for detail queries, interval/region-first for
genome-browser and locus queries.

### `copy_number_segments`

Segmented copy-number data. Keep this separate from gene-level CNA calls.

| Column              | Notes                                    |
| ------------------- | ---------------------------------------- |
| `data_contract_id`   | Logical segment contract integer ID       |
| `run_id`            | Producing/importing run integer ID       |
| `run_sample_id`     | Processed sample integer ID              |
| `sample_id`         | Sample integer ID shortcut for filtering |
| `genome_build`      | Reference build                          |
| `contig`            | Chromosome/contig                        |
| `start_pos`         | Segment start                            |
| `end_pos`           | Segment end                              |
| `num_probes`        | Nullable probe/bin count                 |
| `segment_mean`      | Segment mean or log ratio                |
| `total_copy_number` | Nullable total copy number               |
| `minor_copy_number` | Nullable minor copy number               |
| `call_label`        | Nullable segment call                    |
| `source_file_id`    | Nullable source file integer ID          |

Recommended physical layouts:

| Layout    | Physical order                                                             | Optimized for                        |
| --------- | -------------------------------------------------------------------------- | ------------------------------------ |
| Canonical | `data_contract_id, run_sample_id, contig, start_pos`                        | Sample segment plots                 |
| By region | `genome_build, contig, start_pos, end_pos, data_contract_id, run_sample_id` | Region/locus queries and IGV context |

### `variants`

Canonical variant identity table.

| Column          | Notes                                                                |
| --------------- | -------------------------------------------------------------------- |
| `id`            | Optional integer dictionary ID when materialized                     |
| `variant_label` | Stable readable variant key, unique/indexed                          |
| `variant_id`    | Stable external/source variant ID when distinct from `variant_label` |
| `genome_build`  | Reference build                                                      |
| `contig`        | Chromosome/contig                                                    |
| `pos`           | 1-based position                                                     |
| `end_pos`       | End position                                                         |
| `ref`           | Reference allele                                                     |
| `alt`           | Alternate allele                                                     |
| `variant_type`  | Example: SNV, insertion, deletion                                    |
| `normalized_id` | Stable normalized identity                                           |

Recommended physical order: `genome_build, contig, pos, end_pos, variant_id`.

### `variant_annotations`

Variant annotations. Some annotations may be contract-specific.

| Column                 | Notes                                   |
| ---------------------- | --------------------------------------- |
| `data_contract_id`      | Annotation contract/source integer ID    |
| `variant_id`           | Variant integer ID                      |
| `feature_id`           | Nullable linked gene/feature integer ID |
| `consequence`          | Nullable consequence                    |
| `impact`               | Nullable impact                         |
| `clinvar_significance` | Nullable ClinVar annotation             |
| `gnomad_af`            | Nullable population frequency           |
| `info_json`            | Full or extra INFO-style data           |

### `variant_transcript_annotations`

Transcript-level annotations for variants. Use this when consequences,
protein changes, exon/intron context, or canonical-transcript status matter.

| Column                  | Notes                                |
| ----------------------- | ------------------------------------ |
| `data_contract_id`       | Annotation contract/source integer ID |
| `variant_id`            | Variant integer ID                   |
| `transcript_feature_id` | Transcript feature integer ID        |
| `gene_feature_id`       | Nullable gene feature integer ID     |
| `consequence`           | Consequence term                     |
| `impact`                | Nullable impact                      |
| `protein_change`        | Nullable protein change              |
| `cdna_change`           | Nullable cDNA change                 |
| `protein_pos_start`     | Nullable protein start               |
| `protein_pos_end`       | Nullable protein end                 |
| `canonical`             | Nullable canonical-transcript flag   |
| `annotation_json`       | Full or extra annotation data        |

### `sample_variant_calls`

Sample-level variant calls.

| Column             | Notes                                    |
| ------------------ | ---------------------------------------- |
| `data_contract_id`  | Logical variant-call contract integer ID  |
| `run_id`           | Producing/importing run integer ID       |
| `run_sample_id`    | Processed sample integer ID              |
| `sample_id`        | Sample integer ID shortcut for filtering |
| `variant_id`       | Variant integer ID                       |
| `genotype`         | Genotype/call                            |
| `depth`            | Read depth                               |
| `genotype_quality` | Genotype quality                         |
| `allele_depth_ref` | Reference allele depth                   |
| `allele_depth_alt` | Alternate allele depth                   |
| `allele_fraction`  | Alternate allele fraction                |
| `filter`           | Variant/call filter                      |
| `format_json`      | Full or extra FORMAT-style data          |
| `source_file_id`   | Nullable source file integer ID          |

Recommended derived layouts:

| Layout      | Physical order                                           | Optimized for                               |
| ----------- | -------------------------------------------------------- | ------------------------------------------- |
| Canonical   | `data_contract_id, run_sample_id, variant_id`             | Fetch all calls for one processed sample    |
| By variant  | `data_contract_id, variant_id, run_sample_id`             | Exact variant recurrence and carrier lookup |
| By position | `genome_build, contig, pos, end_pos, variant_id`         | Genomic range queries                       |
| By gene     | `feature_id, data_contract_id, run_sample_id, variant_id` | Gene-centric variant queries                |

### `structural_variant_events`

Canonical structural variant or fusion-like events.

| Column                  | Notes                                                                      |
| ----------------------- | -------------------------------------------------------------------------- |
| `structural_variant_id` | Structural variant event integer ID                                        |
| `event_id`              | Stable event ID                                                            |
| `event_class`           | Example: `fusion`, `translocation`, `inversion`, `deletion`, `duplication` |
| `genome_build`          | Reference build                                                            |
| `site1_feature_id`      | Nullable gene/transcript feature integer ID at site 1                      |
| `site2_feature_id`      | Nullable gene/transcript feature integer ID at site 2                      |
| `site1_contig`          | Nullable site 1 contig                                                     |
| `site1_pos`             | Nullable site 1 position                                                   |
| `site2_contig`          | Nullable site 2 contig                                                     |
| `site2_pos`             | Nullable site 2 position                                                   |
| `frame_status`          | Nullable in-frame/out-of-frame status                                      |
| `event_info`            | Nullable display/event string                                              |
| `annotation_json`       | Full or extra annotation data                                              |

### `sample_structural_variant_calls`

Sample-level calls for structural variant events.

| Column                  | Notes                                     |
| ----------------------- | ----------------------------------------- |
| `data_contract_id`       | Logical SV contract integer ID             |
| `run_id`                | Producing/importing run integer ID        |
| `run_sample_id`         | Processed sample integer ID               |
| `sample_id`             | Sample integer ID shortcut for filtering  |
| `structural_variant_id` | Structural variant event integer ID       |
| `call_status`           | Example: `called`, `filtered`, `uncalled` |
| `dna_support`           | Nullable DNA support description          |
| `rna_support`           | Nullable RNA support description          |
| `tumor_read_count`      | Nullable tumor read count                 |
| `normal_read_count`     | Nullable normal read count                |
| `split_read_count`      | Nullable split-read count                 |
| `paired_end_read_count` | Nullable paired-end count                 |
| `format_json`           | Extra call fields                         |
| `source_file_id`        | Nullable source file integer ID           |

Recommended layouts: sample-first for detail pages, gene/site-first for
gene-centric SV queries.

### `timeline_events`

Subject/sample events over time. Optional for early QC, but useful for clinical
or longitudinal data.

| Column          | Notes                                                                |
| --------------- | -------------------------------------------------------------------- |
| `event_id`      | Event integer ID                                                     |
| `subject_id`    | Subject integer ID                                                   |
| `sample_id`     | Nullable sample integer ID                                           |
| `run_sample_id` | Nullable processed sample integer ID                                 |
| `event_type`    | Example: `collection`, `treatment`, `diagnosis`, `outcome`, `status` |
| `start_time`    | Nullable start time or relative time                                 |
| `end_time`      | Nullable end time                                                    |
| `time_unit`     | Nullable unit for relative time                                      |
| `event_status`  | Nullable status/result                                               |
| `metadata_json` | Flexible event details                                               |

Recommended physical order: `subject_id, event_type, start_time`.

### `contract_payloads`

Logical payloads for results that are naturally consumed as one object or are
not yet worth promoting into typed facts.

| Column            | Notes                                                                |
| ----------------- | -------------------------------------------------------------------- |
| `payload_id`      | Payload integer ID                                                   |
| `data_contract_id` | Logical contract integer ID this payload belongs to                   |
| `run_id`          | Producing/importing run integer ID                                   |
| `run_sample_id`   | Nullable processed sample integer ID                                 |
| `payload_name`    | Stable payload name                                                  |
| `payload_kind`    | Example: `table`, `matrix`, `json`, `array`, `log`, `report_section` |
| `storage_format`  | Example: `parquet`, `arrow`, `json`, `text`, `html`                  |
| `path`            | Local path if materialized                                           |
| `uri`             | Object-store or remote URI if applicable                             |
| `schema_json`     | Optional schema for tabular payloads                                 |
| `row_count`       | Nullable row count                                                   |
| `source_file_id`  | Nullable source file integer ID                                      |
| `metadata_json`   | Flexible payload metadata                                            |

Payloads are the escape hatch, not the destination for hot analytical queries.
Promote payload contents into typed tables when users need filters, joins,
cohort comparisons, or dashboards over those rows.

### `gene_alteration_state`

Derived table for cBioPortal-like alteration queries. This is not a canonical
source of truth; it is built from variants, CNA calls, structural variants,
expression outliers, methylation calls, protein calls, and other typed sources.

| Column               | Notes                                                                                         |
| -------------------- | --------------------------------------------------------------------------------------------- |
| `run_sample_id`      | Processed sample integer ID                                                                   |
| `sample_id`          | Sample integer ID shortcut                                                                    |
| `subject_id`         | Nullable subject integer ID shortcut                                                          |
| `feature_id`         | Usually a gene feature integer ID                                                             |
| `data_contract_id`    | Source contract integer ID                                                                     |
| `alteration_type`    | Example: `mutation`, `cna`, `sv`, `expression_outlier`, `methylation`, `protein`, `signature` |
| `alteration_subtype` | More specific type or call                                                                    |
| `is_altered`         | Boolean alteration state                                                                      |
| `value_numeric`      | Nullable numeric value                                                                        |
| `value_string`       | Nullable string/call value                                                                    |
| `driver_status`      | Nullable driver/passenger/unknown annotation                                                  |
| `source_table`       | Canonical source table                                                                        |
| `source_event_id`    | Source event/call identifier                                                                  |

Recommended physical layouts:

| Layout    | Physical order                                                | Optimized for                                     |
| --------- | ------------------------------------------------------------- | ------------------------------------------------- |
| Canonical | `feature_id, alteration_type, data_contract_id, run_sample_id` | Alteration frequency, filters, OncoPrint matrices |
| By sample | `run_sample_id, feature_id, alteration_type`                  | Sample detail and sample-centric exports          |

### Cohort Summary Tables

Precomputed reference-set and cohort statistics. Treat these as derived/cache
data keyed by the sample set, contract, field or feature, and source fingerprint.

| Column            | Notes                                  |
| ----------------- | -------------------------------------- |
| `sample_set_id`   | Cohort/reference set integer ID        |
| `data_contract_id` | Contract integer ID summarized          |
| `field_id`        | Nullable contract field integer ID summarized |
| `feature_id`      | Nullable feature integer ID summarized |
| `n`               | Observation count                      |
| `mean`            | Mean                                   |
| `median`          | Median                                 |
| `stddev`          | Standard deviation                     |
| `min`             | Minimum                                |
| `max`             | Maximum                                |
| `q05`             | 5th percentile                         |
| `q25`             | 25th percentile                        |
| `q75`             | 75th percentile                        |
| `q95`             | 95th percentile                        |

## Data Contract Rule

Every analytical fact table should include integer `data_contract_id` when the
row stores an actual value, call, measurement, or contract-specific record. Keep
the readable contract label in SQL control storage or DuckDB dimensions, and
resolve user-provided labels to integer IDs before writing fact rows.

Examples:

| Table                             | Should include contract identity? | Why                                                        |
| --------------------------------- | -------------------------------- | ---------------------------------------------------------- |
| `sample_metrics`                  | Yes                              | Metric value belongs to a logical metric contract           |
| `feature_value_numeric`           | Yes                              | Numeric feature value belongs to one feature-value contract |
| `feature_call`                    | Yes                              | Feature call belongs to one call contract                   |
| `sample_variant_calls`            | Yes                              | Call belongs to one variant-call contract                   |
| `copy_number_segments`            | Yes                              | Segment belongs to one segment contract                     |
| `sample_structural_variant_calls` | Yes                              | SV call belongs to one SV contract                          |
| `contract_payloads`                | Yes                              | Payload belongs to one logical contract                     |
| `variant_annotations`             | Usually yes                      | Annotation meaning/source can vary by contract              |
| `variants`                        | No                               | Canonical variant identity is shared                       |
| `features`                        | No                               | Shared feature dictionary                                  |
| `genomic_intervals`               | No                               | Canonical interval identity can be shared                  |
| `samples`                         | No                               | Control-store entity, not an analytical fact               |
| `files`                           | No                               | File entity; use `file_links` to connect to contracts       |

## Worked Example

The integer values below are illustrative. Readable labels remain available for
display and user input, but table relationships use the integer `id` columns.

### Project

| Field        | Value                     |
| ------------ | ------------------------- |
| `id`         | `1`                       |
| `project_id` | `precision-oncology-demo` |

### Subjects

| id  | subject_id |
| --- | ---------- |
| `1` | `P001`     |
| `2` | `P002`     |

### Samples

| id  | sample_id         | subject_id | sample_name     |
| --- | ----------------- | ---------- | --------------- |
| `1` | `P001_Tumor_DNA`  | `1`        | P001 tumor DNA  |
| `2` | `P001_Normal_DNA` | `1`        | P001 normal DNA |
| `3` | `P001_Tumor_RNA`  | `1`        | P001 tumor RNA  |
| `4` | `P002_Tumor_DNA`  | `2`        | P002 tumor DNA  |
| `5` | `P002_Normal_DNA` | `2`        | P002 normal DNA |
| `6` | `P002_Tumor_RNA`  | `2`        | P002 tumor RNA  |

### Data Imports

| id  | data_import_id              | source_type  | Notes                                       |
| --- | --------------------------- | ------------ | ------------------------------------------- |
| `1` | `import_wes_batch_042`      | `bwa`        | Imported WES alignment and variant files    |
| `2` | `import_multiqc_rnaseq_042` | `multiqc`    | Imported MultiQC report and data payloads   |
| `3` | `import_cbioportal_demo`    | `cbioportal` | Imported external cBioPortal study snapshot |

### Runs

| id  | run_id                          | data_import_id | assay               | pipeline_name    | pipeline_version |
| --- | ------------------------------- | -------------- | ------------------- | ---------------- | ---------------- |
| `1` | `run_wes_batch_042`             | `1`            | `tumor_normal_wes`  | `nf-core/sarek`  | `3.5`            |
| `2` | `run_rnaseq_batch_042`          | `2`            | `bulk_rnaseq`       | `nf-core/rnaseq` | `3.18`           |
| `3` | `run_rnaseq_batch_042_rerun`    | null           | `bulk_rnaseq`       | `nf-core/rnaseq` | `3.19`           |
| `4` | `import_cbioportal_demo:TCGA-A` | `3`            | `external_oncology` | cBioPortal       | null             |

### Processed Samples

| id  | run_sample_id                               | run_id | sample_id |
| --- | ------------------------------------------- | ------ | --------- |
| `1` | `run_wes_batch_042:P001_Tumor_DNA`          | `1`    | `1`       |
| `2` | `run_wes_batch_042:P001_Normal_DNA`         | `1`    | `2`       |
| `3` | `run_wes_batch_042:P002_Tumor_DNA`          | `1`    | `4`       |
| `4` | `run_wes_batch_042:P002_Normal_DNA`         | `1`    | `5`       |
| `5` | `run_rnaseq_batch_042:P001_Tumor_RNA`       | `2`    | `3`       |
| `6` | `run_rnaseq_batch_042:P002_Tumor_RNA`       | `2`    | `6`       |
| `7` | `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `3`    | `3`       |
| `8` | `run_rnaseq_batch_042_rerun:P002_Tumor_RNA` | `3`    | `6`       |

### Data Contracts

| id  | data_contract_id                   | data_type              | producer_tool | Notes                                          |
| --- | --------------------------------- | ---------------------- | ------------- | ---------------------------------------------- |
| `1` | `salmon:metrics`                  | `generic_metrics`      | Salmon        | Tool-owned metric contract reused across runs  |
| `2` | `cbioportal:mutations:maf`        | `small_variants`       | cBioPortal    | Built-in cBioPortal mutation contract          |
| `3` | `cbioportal:copy_number:segments` | `copy_number_segments` | cBioPortal    | Built-in segment-level CNA contract            |
| `4` | `goodomics:sdk_metrics`           | `generic_metrics`      | goodomics-sdk | Native SDK metric contract                     |
| `5` | `fastqc:raw:metrics`              | `generic_metrics`      | FastQC        | Tool-owned raw-read QC metric contract         |
| `6` | `project_rnaseq:salmon_gene_tpm`  | `feature_matrix`       | Salmon        | Example project-defined contract                |

### Files

| id  | file_id                   | file_role          | linked data_contract_id |
| --- | ------------------------- | ------------------ | ---------------------- |
| `1` | `P001_T.bam`              | `bam`              | null                   |
| `2` | `P001_T.bam.bai`          | `bai`              | null                   |
| `3` | `P001.mutect2.vcf.gz`     | `vcf`              | `2`                    |
| `4` | `P001.mutect2.vcf.gz.tbi` | `tbi`              | `2`                    |
| `5` | `multiqc_report.html`     | `report`           | `1`                    |
| `6` | `P001_salmon_quant.sf`    | `expression_table` | `5`                    |
| `7` | `P002_salmon_quant.sf`    | `expression_table` | `5`                    |

### Example Metric Observations

| data_contract_id | run_id | run_sample_id | sample_id | field_id | value_numeric |
| --------------- | ------ | ------------- | --------- | --------- | ------ |
| `1`             | `2`    | `5`           | `3`       | `1`       | `91.2` |
| `1`             | `3`    | `7`           | `3`       | `1`       | `93.8` |

### Example Numeric Feature Observations

| data_contract_id | run_id | run_sample_id | sample_id | feature_id | value  |
| --------------- | ------ | ------------- | --------- | ---------- | ------ |
| `5`             | `2`    | `5`           | `3`       | `1`        | `12.4` |
| `5`             | `3`    | `7`           | `3`       | `1`        | `13.1` |

### Example Contract Availability

| data_contract_id | run_sample_id | availability_status | feature_set_id |
| --------------- | ------------- | ------------------- | -------------- |
| `2`             | `1`           | `profiled`          | `1`            |
| `5`             | `5`           | `profiled`          | `2`            |

### Example Variant Call

| data_contract_id | run_id | run_sample_id | sample_id | variant_id | feature_id | genotype | depth | allele_fraction |
| --------------- | ------ | ------------- | --------- | ---------- | ---------- | -------- | ----- | --------------- |
| `2`             | `1`    | `1`           | `1`       | `1`        | `1`        | `0/1`    | `118` | `0.37`          |

### Example Alteration State

| run_sample_id | feature_id | alteration_type | alteration_subtype | is_altered | data_contract_id |
| ------------- | ---------- | --------------- | ------------------ | ---------- | --------------- |
| `1`           | `1`        | `mutation`      | `missense`         | `true`     | `2`             |

### Reference Set

| id  | sample_set_id                      | kind            |
| --- | ---------------------------------- | --------------- |
| `1` | `production-rnaseq-reference-v318` | `reference_set` |

Members:

| sample_set_id | run_sample_id |
| ------------- | ------------- |
| `1`           | `5`           |
| `1`           | `6`           |

The reference set includes processed samples from the RNA-seq 3.18 run. It does
not include raw sample `P001_Tumor_RNA` by itself, because that sample was also
processed by RNA-seq 3.19.

### Agent/MCP Interpretation

Given this model, an MCP layer can accurately say:

> This project has WES variants from Mutect2, WES alignment files from BWA,
> RNA-seq QC metrics from Salmon and FastQC parsed via MultiQC, and gene TPM contracts from Salmon. Sample
> `P001_Tumor_RNA` has two RNA-seq processed results: one from nf-core/rnaseq
> 3.18 and one from 3.19.
