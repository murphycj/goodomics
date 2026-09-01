# Data model and storage overview

Goodomics stores data in three layers: a metadata store, an analytical store, and a file store. Each layer uses a different storage backend and serves different purposes.

| Layer            | Storage backend                | Examples                                                            |
| ---------------- | ------------------------------ | ------------------------------------------------------------------- |
| Metadata store   | SQL (e.g. SQLite)              | Projects, runs, samples, subjects, sample groups, insights, reports |
| Analytical store | OLAP database (e.g. DuckDB)    | Scalar metrics, sample attributes, variants, CNA segments           |
| File store       | Filestore (e.g. filestore, S3) | Workflow generated artifacts such as reports, logs, VCFs, BAMs      |

As the name indicates, the metadata store is for storing metadata, such projects, permissions, samples, file metadata, and so on. The analytical and file stores are meant to store the actual omics data.

## Metadata store

The metadata store is the glue that links Goodomics together. It records stable
identities, relationships, provenance, permissions, and saved application state.
Some of its tables describe the datasets available in the analytical store,
including their shapes, contracts, fields, and run-specific availability. Others
catalog objects in the file store and connect them to projects, imports, runs,
samples, and contracts. This lets Goodomics find and interpret data without
putting large analytical values or file contents in the metadata database.

### Projects, users, and access

| Table | Purpose |
| --- | --- |
| `projects` | Project identity, settings, and visibility. |
| `users` | User accounts and authentication state. |
| `project_roles` | Named roles within projects. |
| `project_role_permissions` | Permissions granted to project roles. |
| `project_memberships` | Links users to projects and their assigned roles. |
| `installation_state` | First-run installation and administrator setup state. |

### Samples, runs, and provenance

| Table | Purpose |
| --- | --- |
| `subjects` | Subject identities associated with projects and samples. |
| `samples` | Stable biological or material sample identities. |
| `analysis_types` | Controlled categories of analysis performed. |
| `analysis_methods` | Workflows, tools, importers, or other methods that produce results. |
| `runs` | Individual computation, import, notebook, or analysis events. |
| `run_samples` | Links samples to the runs in which they participated. |
| `run_relationships` | Provenance relationships between runs. |
| `data_imports` | Acquisition history and provenance for imported data. |
| `sample_groups` | Saved definitions of related samples. |
| `sample_group_members` | Membership of run samples in sample groups. |
| `qc_decisions` | Quality-control outcomes for runs. |
| `qc_policies` | Project-specific quality-control thresholds. |

### Analytical data catalog

| Table | Purpose |
| --- | --- |
| `data_shapes` | Stable identities for reusable, high-level dataset structures. |
| `data_shape_versions` | Versioned definitions of data shapes. |
| `data_contracts` | Descriptions of discoverable datasets and their meaning. |
| `data_contract_analysis_types` | Links data contracts to applicable analysis types. |
| `data_contract_fields` | Describes the fields available within each data contract. |
| `data_contract_profiles` | Optional dataset-level summaries used for discovery. |
| `data_contract_field_profiles` | Optional field-level summaries used for discovery. |
| `run_contracts` | Records a run-specific occurrence of a data contract. |
| `run_contract_samples` | Records per-sample availability for a run contract. |

### Files

| Table | Purpose |
| --- | --- |
| `files` | Catalogs file-store objects and their locations, formats, and checksums. |
| `file_links` | Links files to projects, imports, runs, samples, and data contracts. |

### Insights and reports

| Table | Purpose |
| --- | --- |
| `insights` | Saved insight definitions. |
| `insight_revisions` | Historical configurations for saved insights. |
| `insight_result_cache` | Cached results for insight queries. |
| `reports` | Saved report definitions. |
| `report_revisions` | Historical configurations for saved reports. |
| `rendered_reports` | Generated report output and its project/run context. |
| `report_result_cache` | Cached results used by reports. |

Data shapes and data contracts provide the high-level vocabulary Goodomics uses
to describe analytical datasets without exposing their physical storage layout.
See [Semantic data contracts](data-contracts.md) for their lifecycle, fields,
discovery behavior, and coverage model.

## Analytical store

The analytical store contains the authoritative observations that users filter,
scan, and aggregate, such as metrics, attributes, feature values, variant calls,
genomic regions, and structured results. It exists separately because these
large datasets benefit from column-oriented analytical storage and can evolve
independently of the smaller relational records in the metadata store.

## File store

The file store contains original inputs and generated artifacts such as reports,
logs, VCFs, and BAMs. It exists separately so large or binary objects can use
storage designed for durable object access, independent scaling, and different
retention policies. The metadata store keeps their descriptive records and
relationships; the file store holds the content itself.
