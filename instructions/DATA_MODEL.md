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
| Sample | Biological, material, or analytical input | Stable sample identity across runs |
| Run | Computational, import, benchmark, or analysis event | Captures pipeline/tool execution context |
| Processed sample | A sample within a specific run | Internal `run_sample` grain for comparison and metrics |
| File | Original or derived file | Tracks physical evidence and outputs |
| Data profile | Smallest logical queryable dataset | Declares data type, provenance, and query behavior |
| Sample set | Saved group of processed samples | General primitive behind cohorts and reference sets |
| Cohort | Sample set used for grouping or comparison | Specialized sample set |
| Reference set | Sample set used as a baseline | Specialized sample set |
| Feature | Thing being measured | Metric, gene, transcript, variant, interval, pathway |
| Observation | Value, call, or measurement | Conceptual analytical fact stored in modular tables |

Short version:

| Term | Meaning |
| --- | --- |
| Sample | What was processed |
| Run | What happened |
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
| `external_id` | Optional external/study ID |
| `metadata_json` | Subject-level metadata |

### `samples`

The biological, material, or analytical input.

| Column | Notes |
| --- | --- |
| `sample_id` | Primary key |
| `project_id` | Owning project |
| `subject_id` | Nullable subject link |
| `external_id` | Optional external/study ID |
| `sample_name` | Human-readable sample name |
| `metadata_json` | Sample-level metadata |

### `runs`

A computational, import, benchmark, or analysis event.

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

This is the key comparison grain.

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

Smallest logical queryable dataset. A data profile declares what kind of data a
run produced or imported, how it should be queried, and how agents should
understand it.

A data profile is not the same thing as a metric definition. A profile might be
`picard_alignment_metrics`; the metrics inside it might be `duplication_rate`,
`insert_size_mean`, and `mean_coverage`. Keep profile-level provenance and
query behavior on `data_profiles`, and keep per-metric labels, units,
directions, and descriptions in `metric_definitions`.

| Column | Notes |
| --- | --- |
| `data_profile_id` | Primary key |
| `project_id` | Owning project |
| `run_id` | Nullable producing/importing run |
| `name` | Human-readable profile name |
| `data_type` | Example: `generic_metrics`, `small_variants`, `expression_matrix` |
| `assay` | Nullable assay label |
| `producer_tool` | Tool that produced this logical dataset |
| `producer_tool_version` | Tool version |
| `producer_pipeline` | Pipeline/workflow that produced this profile |
| `genome_build` | Nullable genome/reference build |
| `feature_type` | Example: `metric`, `gene`, `variant`, `transcript`, `interval` |
| `value_type` | Example: `numeric`, `categorical`, `call`, `matrix` |
| `unit` | Nullable default unit |
| `query_modes_json` | Supported query modes, such as sample, metric, gene, region |
| `mcp_description` | Agent-readable description |
| `metadata_json` | Flexible profile metadata |

Examples:

| Data profile | Data type | Producer |
| --- | --- | --- |
| `multiqc_qc_metrics` | `generic_metrics` | MultiQC |
| `picard_alignment_metrics` | `generic_metrics` | Picard |
| `mutect2_somatic_variants` | `small_variants` | Mutect2 |
| `salmon_gene_tpm` | `expression_matrix` | Salmon |
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
`data_profile_id`.

Each project should have its own DuckDB analytical store by default, so large
analytics tables do not need to repeat `project_id` on every row. Store project
identity once in DuckDB metadata and keep `project_id` in the SQL control store.

Dimension tables do not always need `data_profile_id`.

The analytical store is modular by design. Do not force every ingested result
into one universal table:

| Layer | Purpose | Examples |
| --- | --- | --- |
| Generic metrics | Default target for arbitrary QC and pipeline outputs | MultiQC scalar metrics, Picard summary metrics, custom TSV metrics |
| Logical payloads | Store results that are naturally consumed as one object | Parsed tables, arrays, matrices, JSON payloads, report sections |
| Typed omics tables | Use specialized schemas for data families with distinct query shapes | Variants, expression, genomic intervals, copy-number alterations, methylation, annotations |
| Derived query layouts | Duplicate or reshape canonical data for hot access patterns | By-sample metrics, by-metric metrics, by-gene expression, by-region variants |

Data profiles sit above these physical choices. A data profile names the logical
dataset and its provenance, while the profile's `data_type` determines whether
Goodomics stores it as generic metrics, a logical payload, a typed omics table,
and/or derived query layouts.

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
| `metric_id` | Primary key |
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
| `data_profile_id` | Logical profile this metric belongs to |
| `run_id` | Producing/importing run |
| `run_sample_id` | Nullable processed sample |
| `sample_id` | Nullable sample shortcut for filtering |
| `metric_id` | Metric definition |
| `source_file_id` | Nullable source file |

Recommended physical layouts:

| Table | Physical order | Optimized for |
| --- | --- | --- |
| `sample_metric_numeric` | `run_sample_id, metric_id` | Canonical table and fast sample detail queries |
| `sample_metric_numeric_by_metric` | `metric_id, value, run_sample_id` | Derived table for metric scans, distributions, and top-N |

The canonical numeric table should be physically sorted for sample-centric
queries. The by-metric table is the one duplicate needed for the other hot path.
This avoids maintaining three copies of numeric metrics. Add by-metric tables
for string or JSON metrics only if real query pressure appears.

### `features`

Optional shared feature dictionary.

| Column | Notes |
| --- | --- |
| `feature_id` | Primary key |
| `feature_type` | Example: `gene`, `transcript`, `pathway`, `interval`, `metric` |
| `symbol` | Human-readable symbol/name |
| `stable_id` | Stable external ID |
| `metadata_json` | Flexible feature metadata |

### `expression_values`

For expression matrices and similar sample x feature numeric profiles.

| Column | Notes |
| --- | --- |
| `data_profile_id` | Logical expression profile |
| `run_id` | Producing/importing run |
| `run_sample_id` | Processed sample |
| `sample_id` | Sample shortcut for filtering |
| `feature_id` | Gene/transcript/feature |
| `value` | Numeric expression value |
| `source_file_id` | Nullable source file |

Recommended derived layouts:

| Derived table | Optimized for |
| --- | --- |
| `expression_by_sample` | Fetch expression profile for one sample |
| `expression_by_feature` | Fetch one gene/feature across samples |

### `variants`

Canonical variant identity table.

| Column | Notes |
| --- | --- |
| `variant_id` | Primary key |
| `genome_build` | Reference build |
| `contig` | Chromosome/contig |
| `pos` | 1-based position |
| `end_pos` | End position |
| `ref` | Reference allele |
| `alt` | Alternate allele |
| `variant_type` | Example: SNV, insertion, deletion |
| `normalized_key` | Stable normalized identity |

### `variant_annotations`

Variant annotations. Some annotations may be profile-specific.

| Column | Notes |
| --- | --- |
| `data_profile_id` | Annotation profile/source |
| `variant_id` | Variant identity |
| `gene_id` | Nullable linked gene/feature |
| `consequence` | Nullable consequence |
| `impact` | Nullable impact |
| `clinvar_significance` | Nullable ClinVar annotation |
| `gnomad_af` | Nullable population frequency |
| `info_json` | Full or extra INFO-style data |

### `sample_variant_calls`

Sample-level variant calls.

| Column | Notes |
| --- | --- |
| `data_profile_id` | Logical variant-call profile |
| `run_id` | Producing/importing run |
| `run_sample_id` | Processed sample |
| `sample_id` | Sample shortcut for filtering |
| `variant_id` | Variant identity |
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

| Derived table | Optimized for |
| --- | --- |
| `sample_variant_calls_by_sample` | Fetch all calls for one processed sample |
| `sample_variant_calls_by_variant` | Fetch all samples with one variant |
| `variants_by_position` | Genomic range queries |
| `variants_by_gene` | Gene-centric variant queries |

### `sample_profile_cache`

UI and MCP convenience cache. Not the analytical source of truth.

| Column | Notes |
| --- | --- |
| `run_sample_id` | Processed sample |
| `profile_summary_json` | Summary of available profiles, metrics, files, and status |
| `updated_at` | Cache update timestamp |

### `cohort_metric_summaries`

Precomputed reference-set statistics.

| Column | Notes |
| --- | --- |
| `sample_set_id` | Cohort/reference set |
| `data_profile_id` | Profile summarized |
| `metric_id` | Metric summarized |
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

Every analytical fact table should include `data_profile_id` when the row stores
an actual value, call, measurement, or profile-specific record.

Examples:

| Table | Should include `data_profile_id`? | Why |
| --- | --- | --- |
| `sample_metric_numeric` | Yes | Metric value belongs to a logical metric profile |
| `expression_values` | Yes | Expression value belongs to one expression profile |
| `sample_variant_calls` | Yes | Call belongs to one variant-call profile |
| `variant_annotations` | Usually yes | Annotation meaning/source can vary by profile |
| `variants` | No | Canonical variant identity is shared |
| `features` | No | Shared feature dictionary |
| `samples` | No | Control-store entity, not an analytical fact |
| `files` | No | File entity; use `file_links` to connect to profiles |

## Worked Example

### Project

| Field | Value |
| --- | --- |
| `project_id` | `precision-oncology-demo` |

### Subjects

| subject_id | external_id |
| --- | --- |
| `P001` | `P001` |
| `P002` | `P002` |

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

| data_profile_id | data_type | producer_tool | run_id | Notes |
| --- | --- | --- | --- | --- |
| `sarek_multiqc_qc_metrics` | `generic_metrics` | MultiQC | `run_wes_batch_042` | WES QC metrics |
| `mutect2_somatic_variants` | `small_variants` | Mutect2 | `run_wes_batch_042` | Somatic SNV/indel calls |
| `bwa_alignment_files` | `alignment_files` | BWA | `run_wes_batch_042` | BAM/BAI alignment files |
| `rnaseq_multiqc_qc_metrics_v318` | `generic_metrics` | MultiQC | `run_rnaseq_batch_042` | RNA-seq QC metrics |
| `salmon_gene_tpm_v318` | `expression_matrix` | Salmon | `run_rnaseq_batch_042` | Gene TPM profile |
| `salmon_gene_tpm_v319` | `expression_matrix` | Salmon | `run_rnaseq_batch_042_rerun` | Gene TPM profile from rerun |

### Files

| file_id | file_role | Linked profile |
| --- | --- | --- |
| `P001_T.bam` | `bam` | `bwa_alignment_files` |
| `P001_T.bam.bai` | `bai` | `bwa_alignment_files` |
| `P001.mutect2.vcf.gz` | `vcf` | `mutect2_somatic_variants` |
| `P001.mutect2.vcf.gz.tbi` | `tbi` | `mutect2_somatic_variants` |
| `multiqc_report.html` | `report` | `rnaseq_multiqc_qc_metrics_v318` |
| `P001_salmon_quant.sf` | `expression_table` | `salmon_gene_tpm_v318` |
| `P002_salmon_quant.sf` | `expression_table` | `salmon_gene_tpm_v318` |

### Example Metric Observations

| data_profile_id | run_sample_id | metric | value |
| --- | --- | --- | --- |
| `rnaseq_multiqc_qc_metrics_v318` | `run_rnaseq_batch_042:P001_Tumor_RNA` | `pct_mapped` | `91.2` |
| `rnaseq_multiqc_qc_metrics_v319` | `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `pct_mapped` | `93.8` |

### Example Expression Observations

| data_profile_id | run_sample_id | feature | value |
| --- | --- | --- | --- |
| `salmon_gene_tpm_v318` | `run_rnaseq_batch_042:P001_Tumor_RNA` | `TP53` | `12.4` |
| `salmon_gene_tpm_v319` | `run_rnaseq_batch_042_rerun:P001_Tumor_RNA` | `TP53` | `13.1` |

### Example Variant Call

| data_profile_id | run_sample_id | variant | gene | genotype | depth | allele_fraction |
| --- | --- | --- | --- | --- | --- | --- |
| `mutect2_somatic_variants` | `run_wes_batch_042:P001_Tumor_DNA` | `chr17:7674220:G>A` | `TP53` | `0/1` | `118` | `0.37` |

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
