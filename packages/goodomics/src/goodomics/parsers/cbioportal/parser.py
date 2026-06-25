from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from goodomics.ingest.base import AnalyticsBulkLoad, NormalizedIngestResult
from goodomics.schemas.models import (
    AnalyticsIngestBatch,
    AttributeDefinition,
    DataProfile,
    EntityAttributeNumeric,
    EntityAttributeString,
    FeatureSet,
    FileAsset,
    FileLink,
    ProfileObservationSet,
    ProfilePayload,
    Run,
    RunSample,
    Sample,
    SampleSet,
    SampleSetMember,
    Subject,
)

CBIOPORTAL_TOOL = "cbioportal"
MISSING_VALUES = {"", "NA", "N/A", "NaN", "nan", "null", "None"}


@dataclass(frozen=True)
class CbioPortalMeta:
    path: Path
    values: dict[str, str]

    @property
    def data_filename(self) -> str | None:
        return self.values.get("data_filename")

    @property
    def stable_id(self) -> str | None:
        return self.values.get("stable_id")

    @property
    def alteration_type(self) -> str | None:
        return self.values.get("genetic_alteration_type")

    @property
    def datatype(self) -> str | None:
        return self.values.get("datatype")


@dataclass
class CbioPortalParseContext:
    root: Path
    run_id: str
    sample_scoped_runs: bool
    project_id: str | None
    assay: str | None
    study_meta: dict[str, str]
    profiles_by_file: dict[str, DataProfile]
    source_files_by_path: dict[Path, FileAsset] = field(default_factory=dict)
    file_links: list[FileLink] = field(default_factory=list)
    subjects: dict[str, Subject] = field(default_factory=dict)
    samples: dict[str, Sample] = field(default_factory=dict)
    run_samples: dict[str, RunSample] = field(default_factory=dict)
    sample_sets: list[SampleSet] = field(default_factory=list)
    sample_set_members: list[SampleSetMember] = field(default_factory=list)
    batch: AnalyticsIngestBatch = field(default_factory=AnalyticsIngestBatch)
    bulk_loads: list[AnalyticsBulkLoad] = field(default_factory=list)

    def run_id_for_sample(self, sample_id: str) -> str:
        if not self.sample_scoped_runs:
            return self.run_id
        return f"{self.run_id}:{_normalize_id(sample_id)}"

    def run_sample_id_for_sample(self, sample_id: str) -> str:
        return _run_sample_id(self.run_id_for_sample(sample_id), sample_id)

    def data_profile_id_for_sample(
        self,
        profile: DataProfile,
        sample_id: str,
    ) -> str:
        if not self.sample_scoped_runs:
            return profile.data_profile_id
        return f"{self.run_id_for_sample(sample_id)}:{_profile_suffix(profile)}"


def parse_cbioportal_study(
    root: Path,
    *,
    run_id: str | None = None,
    project_id: str | None = None,
    assay: str | None = None,
    sample_scoped_runs: bool | None = None,
) -> NormalizedIngestResult:
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise ValueError(f"cBioPortal study directory does not exist: {root}")
    metas = _discover_metas(resolved_root)
    study_meta = _read_meta_file(resolved_root / "meta_study.txt")
    resolved_run_id = run_id or study_meta.get("cancer_study_identifier")
    if not resolved_run_id:
        resolved_run_id = _normalize_id(resolved_root.name)

    profiles_by_file = {
        meta.data_filename: _profile_from_meta(
            meta,
            run_id=resolved_run_id,
            project_id=project_id,
            assay=assay,
        )
        for meta in metas
        if meta.data_filename
    }
    context = CbioPortalParseContext(
        root=resolved_root,
        run_id=resolved_run_id,
        sample_scoped_runs=run_id is None
        if sample_scoped_runs is None
        else sample_scoped_runs,
        project_id=project_id,
        assay=assay,
        study_meta=study_meta,
        profiles_by_file=profiles_by_file,
    )

    _register_source_files(context, metas)
    _parse_clinical_files(context)
    _parse_case_lists(context)
    _plan_profile_loads(context)

    base_run = Run(
        run_id=resolved_run_id,
        project_id=project_id,
        name=study_meta.get("name") or study_meta.get("short_name") or resolved_run_id,
        run_kind="import_run",
        assay=assay,
        pipeline_name=CBIOPORTAL_TOOL,
        status="complete",
        metadata_json={
            "source_format": "cbioportal_study",
            "source_path": str(resolved_root),
            "study": study_meta,
        },
        samples=sorted(context.samples.values(), key=lambda sample: sample.sample_id),
    )
    runs = _runs_from_context(context, base_run)
    return NormalizedIngestResult(
        run=runs[0] if runs else base_run,
        runs=runs,
        subjects=sorted(
            context.subjects.values(), key=lambda subject: subject.subject_id
        ),
        samples=sorted(context.samples.values(), key=lambda sample: sample.sample_id),
        run_samples=sorted(
            context.run_samples.values(),
            key=lambda run_sample: run_sample.run_sample_id,
        ),
        data_profiles=sorted(
            _data_profiles_from_context(context),
            key=lambda profile: profile.data_profile_id,
        ),
        files=sorted(
            context.source_files_by_path.values(), key=lambda file: file.file_id
        ),
        file_links=_file_links_from_context(context),
        sample_sets=context.sample_sets,
        sample_set_members=context.sample_set_members,
        analytics_batch=context.batch,
        bulk_loads=context.bulk_loads,
        summary={
            "profiles_found": len(profiles_by_file),
            "files_registered": len(context.source_files_by_path),
            "bulk_loads": len(context.bulk_loads),
        },
    )


def _discover_metas(root: Path) -> list[CbioPortalMeta]:
    metas = []
    for path in sorted(root.glob("meta_*.txt")):
        if path.name == "meta_study.txt":
            continue
        values = _read_meta_file(path)
        if values:
            metas.append(CbioPortalMeta(path=path, values=values))
    return metas


def _read_meta_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _profile_from_meta(
    meta: CbioPortalMeta,
    *,
    run_id: str,
    project_id: str | None,
    assay: str | None,
) -> DataProfile:
    data_type, feature_type, value_type = _profile_shape(meta)
    stable_part = meta.stable_id or Path(meta.data_filename or meta.path.stem).stem
    profile_id = f"{run_id}:{_normalize_id(stable_part)}"
    genome_build = (
        meta.values.get("reference_genome_id")
        or meta.values.get("reference_genome")
        or _genome_from_build(meta.values.get("ncbi_build"))
    )
    return DataProfile(
        data_profile_id=profile_id,
        project_id=project_id,
        run_id=run_id,
        name=meta.values.get("profile_name")
        or meta.values.get("description")
        or stable_part,
        data_type=data_type,
        assay=assay,
        producer_tool=CBIOPORTAL_TOOL,
        genome_build=genome_build,
        feature_type=feature_type,
        value_type=value_type,
        query_modes_json=_query_modes(data_type),
        mcp_description=meta.values.get("profile_description")
        or meta.values.get("description"),
        metadata_json={
            "source_format": "cbioportal",
            "source_meta_file": meta.path.name,
            "cbioportal": dict(meta.values),
        },
    )


def _profile_shape(meta: CbioPortalMeta) -> tuple[str, str | None, str | None]:
    alteration = meta.alteration_type
    datatype = meta.datatype
    if alteration == "CLINICAL":
        return "entity_attributes", None, "mixed"
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "DISCRETE":
        return "feature_calls", "gene", "call"
    if alteration == "COPY_NUMBER_ALTERATION" and datatype == "SEG":
        return "copy_number_segments", "interval", "numeric"
    if alteration == "MUTATION_EXTENDED":
        return "small_variants", "gene", "call"
    if alteration == "STRUCTURAL_VARIANT":
        return "structural_variants", "gene", "call"
    if alteration == "GENE_PANEL_MATRIX":
        return "profile_availability", "gene_panel", "categorical"
    if alteration == "GENERIC_ASSAY":
        return "feature_matrix", "compound", "numeric"
    if alteration in {"MRNA_EXPRESSION", "PROTEIN_LEVEL"}:
        return (
            "feature_matrix",
            "gene" if alteration == "MRNA_EXPRESSION" else "protein",
            "numeric",
        )
    return "profile_payload", None, None


def _query_modes(data_type: str) -> dict[str, Any]:
    modes = {
        "entity_attributes": ["sample", "subject", "attribute"],
        "feature_matrix": ["sample", "feature", "cohort"],
        "feature_calls": ["sample", "feature", "call", "cohort"],
        "small_variants": ["sample", "variant", "gene", "region"],
        "copy_number_segments": ["sample", "region"],
        "structural_variants": ["sample", "gene", "event"],
        "profile_availability": ["sample", "profile", "feature_set"],
    }
    return {"modes": modes.get(data_type, ["payload"])}


def _register_source_files(
    context: CbioPortalParseContext,
    metas: list[CbioPortalMeta],
) -> None:
    _register_file(context, context.root / "meta_study.txt", role="cbioportal_meta")
    for meta in metas:
        _register_file(context, meta.path, role="cbioportal_meta")
        if meta.data_filename:
            data_path = context.root / meta.data_filename
            file = _register_file(context, data_path, role="cbioportal_data")
            profile = context.profiles_by_file.get(meta.data_filename)
            if profile is not None:
                context.file_links.append(
                    FileLink(
                        file_id=file.file_id,
                        project_id=context.project_id,
                        run_id=context.run_id,
                        data_profile_id=profile.data_profile_id,
                        link_role="source",
                    )
                )
    for path in sorted((context.root / "case_lists").glob("*.txt")):
        _register_file(context, path, role="cbioportal_case_list")


def _register_file(
    context: CbioPortalParseContext,
    path: Path,
    *,
    role: str,
) -> FileAsset:
    resolved = path.resolve()
    existing = context.source_files_by_path.get(resolved)
    if existing is not None:
        return existing
    file = FileAsset(
        file_id=f"{context.run_id}:source:{_normalize_id(str(path.relative_to(context.root)))}",
        project_id=context.project_id,
        path=str(resolved),
        file_role=role,
        format=path.suffix.lstrip(".") or "txt",
        size_bytes=path.stat().st_size if path.exists() else None,
        sha256=_sha256_file(path)
        if path.exists() and path.stat().st_size < 20_000_000
        else None,
        metadata_json={"source_path": str(path)},
    )
    context.source_files_by_path[resolved] = file
    context.file_links.append(
        FileLink(
            file_id=file.file_id,
            project_id=context.project_id,
            run_id=context.run_id,
            link_role="source",
        )
    )
    return file


def _parse_clinical_files(context: CbioPortalParseContext) -> None:
    for filename, profile in context.profiles_by_file.items():
        meta = profile.metadata_json.get("cbioportal", {})
        if (
            not isinstance(meta, dict)
            or meta.get("genetic_alteration_type") != "CLINICAL"
        ):
            continue
        path = context.root / filename
        source_file = context.source_files_by_path.get(path.resolve())
        clinical = _read_cbioportal_table(path)
        if clinical is None:
            continue
        entity_scope = (
            "subject" if meta.get("datatype") == "PATIENT_ATTRIBUTES" else "sample"
        )
        _add_attribute_definitions(context, profile, clinical, entity_scope)
        for row in clinical.rows:
            if entity_scope == "subject":
                subject_id = _clean(
                    row.get("PATIENT_ID") or row.get("Patient Identifier")
                )
                if subject_id is None:
                    continue
                _ensure_subject(context, subject_id, row)
                _add_attribute_values(
                    context,
                    profile,
                    source_file_id=source_file.file_id if source_file else None,
                    entity_scope="subject",
                    entity_key=subject_id,
                    row=row,
                    table=clinical,
                    id_columns={"PATIENT_ID", "Patient Identifier"},
                )
            else:
                sample_id = _clean(row.get("SAMPLE_ID") or row.get("Sample Identifier"))
                if sample_id is None:
                    continue
                subject_id = _clean(
                    row.get("PATIENT_ID") or row.get("Patient Identifier")
                )
                if subject_id is not None:
                    _ensure_subject(context, subject_id, {})
                _ensure_sample(context, sample_id, subject_id=subject_id, row=row)
                _add_attribute_values(
                    context,
                    profile,
                    source_file_id=source_file.file_id if source_file else None,
                    entity_scope="sample",
                    entity_key=sample_id,
                    row=row,
                    table=clinical,
                    id_columns={"SAMPLE_ID", "Sample Identifier", "PATIENT_ID"},
                )


@dataclass(frozen=True)
class CbioPortalTable:
    header: list[str]
    descriptions: dict[str, str]
    value_types: dict[str, str]
    priorities: dict[str, str]
    rows: list[dict[str, str]]


def _read_cbioportal_table(path: Path) -> CbioPortalTable | None:
    if not path.exists():
        return None
    comments: list[list[str]] = []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        header: list[str] | None = None
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line.startswith("#"):
                comments.append(line.removeprefix("#").split("\t"))
                continue
            header = line.split("\t")
            reader = csv.DictReader(handle, delimiter="\t", fieldnames=header)
            rows = [dict(row) for row in reader]
            break
    if header is None:
        return None
    descriptions = (
        dict(zip(header, comments[1], strict=False)) if len(comments) > 1 else {}
    )
    value_types = (
        dict(zip(header, comments[2], strict=False)) if len(comments) > 2 else {}
    )
    priorities = (
        dict(zip(header, comments[3], strict=False)) if len(comments) > 3 else {}
    )
    return CbioPortalTable(
        header=header,
        descriptions=descriptions,
        value_types=value_types,
        priorities=priorities,
        rows=rows,
    )


def _add_attribute_definitions(
    context: CbioPortalParseContext,
    profile: DataProfile,
    table: CbioPortalTable,
    entity_scope: str,
) -> None:
    for column in table.header:
        if column in {"SAMPLE_ID", "PATIENT_ID"}:
            continue
        value_type = _attribute_value_type(table.value_types.get(column))
        context.batch.attribute_definitions.append(
            AttributeDefinition(
                attribute_key=None,
                attribute_id=_normalize_id(column),
                entity_scope=entity_scope,
                display_name=column.replace("_", " ").title(),
                value_type=value_type,
                description=table.descriptions.get(column),
                priority=table.priorities.get(column),
                metadata_json={
                    "data_profile_key": profile.data_profile_id,
                    "source": "cbioportal_clinical",
                },
            )
        )


def _add_attribute_values(
    context: CbioPortalParseContext,
    profile: DataProfile,
    *,
    source_file_id: str | None,
    entity_scope: str,
    entity_key: str,
    row: dict[str, str],
    table: CbioPortalTable,
    id_columns: set[str],
) -> None:
    for column, raw_value in row.items():
        if column in id_columns:
            continue
        value = _clean(raw_value)
        if value is None:
            continue
        attribute_key = _attribute_key(entity_scope, column)
        value_type = _attribute_value_type(table.value_types.get(column))
        if value_type == "numeric" and (number := _to_float(value)) is not None:
            context.batch.entity_attribute_numeric.append(
                EntityAttributeNumeric(
                    entity_scope=entity_scope,
                    entity_key=entity_key,
                    attribute_key=attribute_key,
                    data_profile_key=profile.data_profile_id,
                    source_file_id=source_file_id,
                    value=number,
                )
            )
        else:
            context.batch.entity_attribute_string.append(
                EntityAttributeString(
                    entity_scope=entity_scope,
                    entity_key=entity_key,
                    attribute_key=attribute_key,
                    data_profile_key=profile.data_profile_id,
                    source_file_id=source_file_id,
                    value=value,
                )
            )


def _parse_case_lists(context: CbioPortalParseContext) -> None:
    case_root = context.root / "case_lists"
    if not case_root.exists():
        return
    for path in sorted(case_root.glob("*.txt")):
        values = _read_meta_file(path)
        stable_id = values.get("stable_id") or path.stem
        sample_set = SampleSet(
            sample_set_id=f"{context.run_id}:{_normalize_id(stable_id)}",
            project_id=context.project_id,
            name=values.get("case_list_name") or stable_id,
            kind="cohort"
            if values.get("case_list_category") != "all_cases_in_study"
            else "case_group",
            description=values.get("case_list_description"),
            definition_json={"source": "cbioportal_case_list", "stable_id": stable_id},
            metadata_json={"cbioportal": values, "source_run_id": context.run_id},
        )
        context.sample_sets.append(sample_set)
        for sample_id in _split_case_ids(values.get("case_list_ids")):
            _ensure_sample(context, sample_id, subject_id=sample_id, row={})
        context.sample_set_members.append(
            SampleSetMember(
                sample_set_id=sample_set.sample_set_id,
                run_sample_id=context.run_sample_id_for_sample(sample_id),
            )
        )


def _plan_profile_loads(context: CbioPortalParseContext) -> None:
    for filename, profile in sorted(context.profiles_by_file.items()):
        meta = profile.metadata_json.get("cbioportal", {})
        if not isinstance(meta, dict):
            continue
        if meta.get("genetic_alteration_type") == "CLINICAL":
            continue
        path = context.root / filename
        source_file = context.source_files_by_path.get(path.resolve())
        source_file_id = source_file.file_id if source_file is not None else None
        alteration = meta.get("genetic_alteration_type")
        datatype = meta.get("datatype")
        if alteration == "GENE_PANEL_MATRIX":
            _parse_gene_panel_matrix(context, profile, path, source_file_id)
        elif alteration == "COPY_NUMBER_ALTERATION" and datatype == "DISCRETE":
            context.bulk_loads.append(
                CnaMatrixBulkLoad(
                    context.run_id,
                    profile,
                    path,
                    source_file_id,
                    sample_scoped_runs=context.sample_scoped_runs,
                )
            )
        elif alteration == "COPY_NUMBER_ALTERATION" and datatype == "SEG":
            context.bulk_loads.append(
                SegmentBulkLoad(
                    context.run_id,
                    profile,
                    path,
                    source_file_id,
                    sample_scoped_runs=context.sample_scoped_runs,
                )
            )
        elif alteration == "MUTATION_EXTENDED":
            context.bulk_loads.append(
                MutationBulkLoad(
                    context.run_id,
                    profile,
                    path,
                    source_file_id,
                    sample_scoped_runs=context.sample_scoped_runs,
                )
            )
        elif alteration == "STRUCTURAL_VARIANT":
            context.bulk_loads.append(
                StructuralVariantBulkLoad(
                    context.run_id,
                    profile,
                    path,
                    source_file_id,
                    sample_scoped_runs=context.sample_scoped_runs,
                )
            )
        elif alteration in {"MRNA_EXPRESSION", "PROTEIN_LEVEL", "GENERIC_ASSAY"}:
            context.bulk_loads.append(
                FeatureMatrixBulkLoad(
                    context.run_id,
                    profile,
                    path,
                    source_file_id,
                    sample_scoped_runs=context.sample_scoped_runs,
                )
            )
        else:
            _add_payload(context, profile, path, source_file_id, "cbioportal_table")


def _parse_gene_panel_matrix(
    context: CbioPortalParseContext,
    profile: DataProfile,
    path: Path,
    source_file_id: str | None,
) -> None:
    rows = _read_tsv_rows(path)
    profile_lookup = {
        _normalize_id(
            candidate.metadata_json.get("cbioportal", {}).get("stable_id", "")
        ): candidate
        for candidate in context.profiles_by_file.values()
        if isinstance(candidate.metadata_json.get("cbioportal"), dict)
    }
    seen_panels: set[str] = set()
    for row in rows:
        sample_id = _clean(row.get("SAMPLE_ID"))
        if sample_id is None:
            continue
        _ensure_sample(context, sample_id, subject_id=sample_id, row={})
        for column, panel in row.items():
            if column == "SAMPLE_ID" or _clean(panel) is None:
                continue
            panel_key = f"gene_panel:{_normalize_id(panel)}"
            if panel_key not in seen_panels:
                seen_panels.add(panel_key)
                context.batch.feature_sets.append(
                    FeatureSet(
                        feature_set_key=panel_key,
                        feature_set_id=panel_key,
                        feature_set_type="gene_panel",
                        name=panel,
                        metadata_json={"source": "cbioportal_gene_panel_matrix"},
                    )
                )
            target_profile = profile_lookup.get(_normalize_id(column)) or profile
            run_id = context.run_id_for_sample(sample_id)
            context.batch.profile_observation_sets.append(
                ProfileObservationSet(
                    data_profile_key=context.data_profile_id_for_sample(
                        target_profile,
                        sample_id,
                    ),
                    run_id=run_id,
                    run_sample_key=_run_sample_id(run_id, sample_id),
                    sample_key=sample_id,
                    availability_status="profiled",
                    feature_set_key=panel_key,
                    source_file_id=source_file_id,
                )
            )
    _add_payload(context, profile, path, source_file_id, "gene_panel_matrix")


@dataclass(frozen=True)
class FeatureMatrixBulkLoad:
    run_id: str
    profile: DataProfile
    path: Path
    source_file_id: str | None
    sample_scoped_runs: bool = False

    def load(self, connection: Any) -> None:
        feature_type = self.profile.feature_type or "generic_entity"
        value_semantics = _value_semantics(self.profile)
        source = _feature_matrix_source_sql(
            self.path,
            feature_type=feature_type,
            include_values=False,
        )
        _replace_features_from_source(connection, source, [str(self.path)])
        connection.execute(
            f"""
            INSERT INTO features ({", ".join(_FEATURE_COLUMNS)})
            SELECT DISTINCT
                feature_key,
                feature_key AS feature_id,
                ? AS feature_type,
                symbol,
                stable_id,
                NULL AS namespace,
                NULL AS genome_build,
                metadata_json
            FROM ({source})
            """,
            [feature_type, str(self.path)],
        )

        source = _feature_matrix_source_sql(
            self.path,
            feature_type=feature_type,
            include_values=True,
        )
        mapped = _mapped_sample_source_sql(
            source,
            base_run_id=self.run_id,
            profile_suffix=_profile_suffix(self.profile),
            sample_scoped_runs=self.sample_scoped_runs,
        )
        connection.execute(
            f"""
            INSERT INTO feature_value_numeric ({", ".join(_FEATURE_VALUE_COLUMNS)})
            SELECT
                data_profile_key,
                mapped_run_id AS run_id,
                mapped_run_id || ':' || sample_key AS run_sample_key,
                sample_key,
                feature_key,
                value,
                ? AS value_semantics,
                ? AS source_file_id
            FROM ({mapped})
            WHERE value IS NOT NULL
            """,
            [
                value_semantics,
                self.source_file_id,
                str(self.path),
            ],
        )


@dataclass(frozen=True)
class CnaMatrixBulkLoad:
    run_id: str
    profile: DataProfile
    path: Path
    source_file_id: str | None
    sample_scoped_runs: bool = False

    def load(self, connection: Any) -> None:
        source = _cna_source_sql(self.path, include_values=False)
        _replace_features_from_source(connection, source, [str(self.path)])
        connection.execute(
            f"""
            INSERT INTO features ({", ".join(_FEATURE_COLUMNS)})
            SELECT DISTINCT
                feature_key,
                feature_key AS feature_id,
                'gene' AS feature_type,
                symbol,
                NULL AS stable_id,
                NULL AS namespace,
                NULL AS genome_build,
                json_object() AS metadata_json
            FROM ({source})
            """,
            [str(self.path)],
        )

        source = _cna_source_sql(self.path, include_values=True)
        mapped = _mapped_sample_source_sql(
            source,
            base_run_id=self.run_id,
            profile_suffix=_profile_suffix(self.profile),
            sample_scoped_runs=self.sample_scoped_runs,
        )
        connection.execute(
            f"""
            INSERT INTO feature_call ({", ".join(_FEATURE_CALL_COLUMNS)})
            SELECT
                data_profile_key,
                mapped_run_id AS run_id,
                mapped_run_id || ':' || sample_key AS run_sample_key,
                sample_key,
                feature_key,
                CASE call_rank
                    WHEN -2 THEN 'HOMDEL'
                    WHEN -1 THEN 'LOSS'
                    WHEN 0 THEN 'DIPLOID'
                    WHEN 1 THEN 'GAIN'
                    WHEN 2 THEN 'AMP'
                    ELSE raw_value
                END AS call_code,
                CASE call_rank
                    WHEN -2 THEN 'Deep deletion'
                    WHEN -1 THEN 'Shallow deletion'
                    WHEN 0 THEN 'Diploid'
                    WHEN 1 THEN 'Gain'
                    WHEN 2 THEN 'Amplification'
                    ELSE raw_value
                END AS call_label,
                call_rank,
                NULL AS score,
                NULL AS confidence,
                NULL AS source_event_id,
                ? AS source_file_id
            FROM ({mapped})
            WHERE call_rank IS NOT NULL
            """,
            [
                self.source_file_id,
                str(self.path),
            ],
        )


@dataclass(frozen=True)
class SegmentBulkLoad:
    run_id: str
    profile: DataProfile
    path: Path
    source_file_id: str | None
    sample_scoped_runs: bool = False

    def load(self, connection: Any) -> None:
        mapped_run_id = _mapped_run_id_sql(
            "ID",
            base_run_id=self.run_id,
            sample_scoped_runs=self.sample_scoped_runs,
        )
        data_profile_key = _mapped_data_profile_key_sql(
            mapped_run_id,
            base_profile_id=self.profile.data_profile_id,
            profile_suffix=_profile_suffix(self.profile),
            sample_scoped_runs=self.sample_scoped_runs,
        )
        connection.execute(
            f"""
            INSERT INTO copy_number_segments ({", ".join(_SEGMENT_COLUMNS)})
            SELECT
                {data_profile_key} AS data_profile_key,
                {mapped_run_id} AS run_id,
                {mapped_run_id} || ':' || ID AS run_sample_key,
                ID AS sample_key,
                ? AS genome_build,
                chrom AS contig,
                try_cast("loc.start" AS BIGINT) AS start_pos,
                try_cast("loc.end" AS BIGINT) AS end_pos,
                try_cast("num.mark" AS BIGINT) AS num_probes,
                try_cast("seg.mean" AS DOUBLE) AS segment_mean,
                NULL AS total_copy_number,
                NULL AS minor_copy_number,
                NULL AS call_label,
                ? AS source_file_id
            FROM read_csv(
                ?,
                delim = '\t',
                header = true,
                all_varchar = true,
                nullstr = ['NA', '']
            )
            WHERE ID IS NOT NULL
            AND try_cast("seg.mean" AS DOUBLE) IS NOT NULL
            """,
            [
                self.profile.genome_build or "unknown",
                self.source_file_id,
                str(self.path),
            ],
        )


@dataclass(frozen=True)
class MutationBulkLoad:
    run_id: str
    profile: DataProfile
    path: Path
    source_file_id: str | None
    sample_scoped_runs: bool = False

    def load(self, connection: Any) -> None:
        source = _mutation_source_sql(self.path, self.profile.genome_build)
        params = [str(self.path)]
        _replace_features_from_source(connection, source, params)
        connection.execute(
            f"""
            DELETE FROM variants
            WHERE variant_key IN (
                SELECT DISTINCT variant_key
                FROM ({source})
            )
            """,
            params,
        )
        connection.execute(
            f"""
            DELETE FROM variant_annotations
            WHERE (data_profile_key, variant_key, feature_key, consequence) IN (
                SELECT DISTINCT
                    ? AS data_profile_key,
                    variant_key,
                    feature_key,
                    consequence
                FROM ({source})
            )
            """,
            [self.profile.data_profile_id, *params],
        )
        connection.execute(
            f"""
            INSERT INTO features ({", ".join(_FEATURE_COLUMNS)})
            SELECT DISTINCT
                feature_key,
                feature_key AS feature_id,
                'gene' AS feature_type,
                symbol,
                stable_id,
                NULL AS namespace,
                NULL AS genome_build,
                json_object() AS metadata_json
            FROM ({source})
            """,
            params,
        )
        connection.execute(
            f"""
            INSERT INTO variants ({", ".join(_VARIANT_COLUMNS)})
            SELECT DISTINCT
                variant_key,
                variant_key AS variant_id,
                genome_build,
                contig,
                pos,
                end_pos,
                ref,
                alt,
                variant_type,
                variant_key AS normalized_key
            FROM ({source})
            """,
            params,
        )
        connection.execute(
            f"""
            INSERT INTO variant_annotations ({", ".join(_VARIANT_ANNOTATION_COLUMNS)})
            SELECT DISTINCT
                ? AS data_profile_key,
                variant_key,
                feature_key,
                consequence,
                NULL AS impact,
                NULL AS clinvar_significance,
                gnomad_af,
                info_json
            FROM ({source})
            """,
            [self.profile.data_profile_id, *params],
        )
        connection.execute(
            f"""
            INSERT INTO sample_variant_calls ({", ".join(_SAMPLE_VARIANT_CALL_COLUMNS)})
            SELECT
                data_profile_key,
                mapped_run_id AS run_id,
                mapped_run_id || ':' || sample_key AS run_sample_key,
                sample_key,
                variant_key,
                genotype,
                depth,
                NULL AS genotype_quality,
                allele_depth_ref,
                allele_depth_alt,
                CASE
                    WHEN allele_depth_alt IS NOT NULL AND depth > 0
                    THEN allele_depth_alt::DOUBLE / depth
                    ELSE NULL
                END AS allele_fraction,
                filter,
                format_json,
                ? AS source_file_id
            FROM ({
                _mapped_sample_source_sql(
                    source,
                    base_run_id=self.run_id,
                    profile_suffix=_profile_suffix(self.profile),
                    sample_scoped_runs=self.sample_scoped_runs,
                )
            })
            """,
            [
                self.source_file_id,
                str(self.path),
            ],
        )


@dataclass(frozen=True)
class StructuralVariantBulkLoad:
    run_id: str
    profile: DataProfile
    path: Path
    source_file_id: str | None
    sample_scoped_runs: bool = False

    def load(self, connection: Any) -> None:
        features: list[tuple[Any, ...]] = []
        events: list[tuple[Any, ...]] = []
        calls: list[tuple[Any, ...]] = []
        seen_features: set[str] = set()
        seen_events: set[str] = set()
        for row in _read_tsv_iter(self.path):
            sample_id = _clean(row.get("Sample_Id"))
            if sample_id is None:
                continue
            site1_feature = (
                _feature_key("gene", row["Site1_Hugo_Symbol"])
                if _clean(row.get("Site1_Hugo_Symbol"))
                else None
            )
            site2_feature = (
                _feature_key("gene", row["Site2_Hugo_Symbol"])
                if _clean(row.get("Site2_Hugo_Symbol"))
                else None
            )
            for feature_key, symbol in (
                (site1_feature, row.get("Site1_Hugo_Symbol")),
                (site2_feature, row.get("Site2_Hugo_Symbol")),
            ):
                if feature_key and feature_key not in seen_features:
                    seen_features.add(feature_key)
                    features.append(
                        _feature_row(feature_key, str(symbol), "gene", None)
                    )
            event_key = _structural_variant_key(row)
            if event_key not in seen_events:
                seen_events.add(event_key)
                events.append(
                    (
                        event_key,
                        event_key,
                        _event_class(row),
                        _genome_from_build(row.get("NCBI_Build"))
                        or self.profile.genome_build,
                        site1_feature,
                        site2_feature,
                        _clean(row.get("Site1_Chromosome")),
                        _to_int(row.get("Site1_Position")),
                        _clean(row.get("Site2_Chromosome")),
                        _to_int(row.get("Site2_Position")),
                        None,
                        _clean(row.get("Event_Info")),
                        _json_extra(row, _SV_CORE_COLUMNS),
                    )
                )
            calls.append(
                (
                    _data_profile_id_for_sample(
                        self.run_id,
                        self.profile,
                        sample_id,
                        sample_scoped_runs=self.sample_scoped_runs,
                    ),
                    _run_id_for_sample(
                        self.run_id,
                        sample_id,
                        sample_scoped_runs=self.sample_scoped_runs,
                    ),
                    _run_sample_id(
                        _run_id_for_sample(
                            self.run_id,
                            sample_id,
                            sample_scoped_runs=self.sample_scoped_runs,
                        ),
                        sample_id,
                    ),
                    sample_id,
                    event_key,
                    _clean(row.get("SV_Status")) or "called",
                    None,
                    None,
                    None,
                    None,
                    _to_int(row.get("Tumor_Split_Read_Count")),
                    _to_int(row.get("Tumor_Paired_End_Read_Count")),
                    _json_extra(row, _SV_CORE_COLUMNS),
                    self.source_file_id,
                )
            )
            if len(calls) >= 10_000:
                self._flush(connection, features, events, calls)
        self._flush(connection, features, events, calls)

    def _flush(
        self,
        connection: Any,
        features: list[tuple[Any, ...]],
        events: list[tuple[Any, ...]],
        calls: list[tuple[Any, ...]],
    ) -> None:
        _replace_dimension_rows(connection, "features", ("feature_key",), features)
        _replace_dimension_rows(
            connection, "structural_variant_events", ("structural_variant_key",), events
        )
        _insert_rows(connection, "features", _FEATURE_COLUMNS, features)
        _insert_rows(connection, "structural_variant_events", _SV_EVENT_COLUMNS, events)
        _insert_rows(
            connection, "sample_structural_variant_calls", _SV_CALL_COLUMNS, calls
        )
        features.clear()
        events.clear()
        calls.clear()


def _iter_feature_matrix_batches(
    path: Path,
    run_id: str,
    profile_id: str,
    *,
    feature_type: str,
    value_semantics: str,
    source_file_id: str | None,
) -> Iterator[tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return
        fieldnames = list(reader.fieldnames)
        id_columns = _matrix_id_columns(fieldnames)
        sample_columns = [column for column in fieldnames if column not in id_columns]
        features: list[tuple[Any, ...]] = []
        values: list[tuple[Any, ...]] = []
        for row in reader:
            feature_key, symbol, stable_id, metadata = _matrix_feature(
                row, feature_type
            )
            features.append(
                (
                    feature_key,
                    feature_key,
                    feature_type,
                    symbol,
                    stable_id,
                    None,
                    None,
                    metadata,
                )
            )
            for sample_id in sample_columns:
                value = _to_float(row.get(sample_id))
                if value is None:
                    continue
                values.append(
                    (
                        profile_id,
                        run_id,
                        _run_sample_id(run_id, sample_id),
                        sample_id,
                        feature_key,
                        value,
                        value_semantics,
                        source_file_id,
                    )
                )
                if len(values) >= 10_000:
                    yield features, values
                    features, values = [], []
        if features or values:
            yield features, values


def _iter_cna_batches(
    path: Path,
    run_id: str,
    profile_id: str,
    *,
    source_file_id: str | None,
) -> Iterator[tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            return
        sample_columns = [
            column for column in reader.fieldnames if column != "Hugo_Symbol"
        ]
        features: list[tuple[Any, ...]] = []
        calls: list[tuple[Any, ...]] = []
        for row in reader:
            symbol = _clean(row.get("Hugo_Symbol"))
            if symbol is None:
                continue
            feature_key = _feature_key("gene", symbol)
            features.append(_feature_row(feature_key, symbol, "gene", None))
            for sample_id in sample_columns:
                rank = _to_int(row.get(sample_id))
                if rank is None:
                    continue
                code, label = _cna_call(rank)
                calls.append(
                    (
                        profile_id,
                        run_id,
                        _run_sample_id(run_id, sample_id),
                        sample_id,
                        feature_key,
                        code,
                        label,
                        rank,
                        None,
                        None,
                        None,
                        source_file_id,
                    )
                )
                if len(calls) >= 10_000:
                    yield features, calls
                    features, calls = [], []
        if features or calls:
            yield features, calls


def _add_payload(
    context: CbioPortalParseContext,
    profile: DataProfile,
    path: Path,
    source_file_id: str | None,
    payload_kind: str,
) -> None:
    if not path.exists():
        return
    sample_ids = sorted(context.samples) if context.sample_scoped_runs else [None]
    for sample_id in sample_ids:
        payload_run_id = context.run_id
        payload_profile_id = profile.data_profile_id
        run_sample_id = None
        payload_metadata: dict[str, Any] = {"source_format": "cbioportal"}
        if sample_id is not None:
            payload_run_id = context.run_id_for_sample(sample_id)
            payload_profile_id = context.data_profile_id_for_sample(profile, sample_id)
            run_sample_id = _run_sample_id(payload_run_id, sample_id)
            payload_metadata["sample_key"] = sample_id
        context.batch.profile_payloads.append(
            ProfilePayload(
                payload_id=(
                    f"{payload_run_id}:{_normalize_id(path.name)}"
                    if sample_id is None
                    else f"{payload_run_id}:{_normalize_id(path.name)}:{sample_id}"
                ),
                data_profile_key=payload_profile_id,
                run_id=payload_run_id,
                run_sample_key=run_sample_id,
                payload_name=path.stem,
                payload_kind=payload_kind,
                storage_format="source_file",
                path=str(path),
                source_file_id=source_file_id,
                metadata_json=payload_metadata,
            )
        )


def _ensure_subject(
    context: CbioPortalParseContext,
    subject_id: str,
    row: dict[str, Any],
) -> Subject:
    subject = context.subjects.get(subject_id)
    if subject is not None:
        return subject
    subject = Subject(
        subject_id=subject_id,
        project_id=context.project_id or "",
        metadata_json={"cbioportal": _compact_row(row)},
    )
    context.subjects[subject_id] = subject
    return subject


def _ensure_sample(
    context: CbioPortalParseContext,
    sample_id: str,
    *,
    subject_id: str | None,
    row: dict[str, Any],
) -> Sample:
    if subject_id is not None:
        _ensure_subject(context, subject_id, {})
    sample = context.samples.get(sample_id)
    if sample is None:
        sample = Sample(
            sample_id=sample_id,
            project_id=context.project_id,
            subject_id=subject_id,
            sample_name=_clean(row.get("NAME")) or sample_id,
            metadata_json={"cbioportal": _compact_row(row)},
        )
        context.samples[sample_id] = sample
    sample_run_id = context.run_id_for_sample(sample_id)
    run_sample_id = _run_sample_id(sample_run_id, sample_id)
    if run_sample_id not in context.run_samples:
        context.run_samples[run_sample_id] = RunSample(
            run_sample_id=run_sample_id,
            project_id=context.project_id,
            run_id=sample_run_id,
            sample_id=sample_id,
            assay=context.assay,
            status="complete",
            metadata_json={"source": "cbioportal_import"},
        )
    return sample


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_tsv_iter(
    path: Path, *, skip_comments: bool = False
) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        if skip_comments:
            for line in handle:
                if not line.startswith("#"):
                    header = line.rstrip("\n").split("\t")
                    break
            else:
                return
            reader = csv.DictReader(handle, delimiter="\t", fieldnames=header)
        else:
            reader = csv.DictReader(handle, delimiter="\t")
        yield from reader


def _feature_matrix_source_sql(
    path: Path,
    *,
    feature_type: str,
    include_values: bool,
) -> str:
    fieldnames = _read_header(path)
    id_columns = _matrix_id_columns(fieldnames)
    sample_columns = [column for column in fieldnames if column not in id_columns]
    if not sample_columns:
        raise ValueError(f"No sample columns found in matrix file: {path}")
    identifier, symbol, stable_id, metadata = _matrix_feature_sql(fieldnames)
    value_columns = ""
    unpivot = ""
    if include_values:
        value_columns = (
            ",\n                sample_key,"
            "\n                try_cast(raw_value AS DOUBLE) AS value"
        )
        unpivot = (
            "\n            UNPIVOT (raw_value FOR sample_key IN "
            f"({_sql_identifier_list(sample_columns)}))"
        )
    return f"""
            SELECT
                {_sql_feature_key(feature_type, identifier)} AS feature_key,
                {symbol} AS symbol,
                {stable_id} AS stable_id,
                {metadata} AS metadata_json
                {value_columns}
            FROM read_csv(
                ?,
                delim = '\t',
                header = true,
                all_varchar = true,
                nullstr = ['NA', '']
            ){unpivot}
            """


def _matrix_feature_sql(fieldnames: list[str]) -> tuple[str, str, str, str]:
    fields = set(fieldnames)
    if "ENTITY_STABLE_ID" in fields:
        identifier = _sql_identifier("ENTITY_STABLE_ID")
        symbol = f"coalesce(nullif({_sql_identifier('NAME')}, ''), {identifier})"
        metadata = (
            "json_object("
            f"'url', {_sql_identifier('URL')}, "
            f"'description', {_sql_identifier('DESCRIPTION')}"
            ")"
            if {"URL", "DESCRIPTION"}.issubset(fields)
            else "json('{}')"
        )
        return identifier, symbol, identifier, metadata
    if "Composite.Element.REF" in fields:
        composite = _sql_identifier("Composite.Element.REF")
        symbol = f"split_part({composite}, '|', 1)"
        stable_id = (
            f"CASE WHEN contains({composite}, '|') "
            f"THEN split_part({composite}, '|', 2) ELSE {composite} END"
        )
        return (
            composite,
            symbol,
            stable_id,
            f"json_object('composite_ref', {composite})",
        )
    identifier = (
        _sql_identifier("Hugo_Symbol") if "Hugo_Symbol" in fields else "'unknown'"
    )
    symbol = f"coalesce(nullif({identifier}, ''), 'unknown')"
    stable_id = (
        _sql_identifier("Entrez_Gene_Id") if "Entrez_Gene_Id" in fields else "NULL"
    )
    return identifier, symbol, stable_id, "json('{}')"


def _cna_source_sql(path: Path, *, include_values: bool) -> str:
    fieldnames = _read_header(path)
    sample_columns = [column for column in fieldnames if column != "Hugo_Symbol"]
    if "Hugo_Symbol" not in fieldnames or not sample_columns:
        raise ValueError(f"Invalid cBioPortal CNA matrix: {path}")
    value_columns = ""
    unpivot = ""
    if include_values:
        value_columns = (
            ",\n                sample_key,\n                raw_value,"
            "\n                try_cast(raw_value AS INTEGER) AS call_rank"
        )
        unpivot = (
            "\n            UNPIVOT (raw_value FOR sample_key IN "
            f"({_sql_identifier_list(sample_columns)}))"
        )
    symbol = _sql_identifier("Hugo_Symbol")
    return f"""
            SELECT
                {_sql_feature_key("gene", symbol)} AS feature_key,
                {symbol} AS symbol
                {value_columns}
            FROM read_csv(
                ?,
                delim = '\t',
                header = true,
                all_varchar = true,
                nullstr = ['NA', '']
            ){unpivot}
            WHERE {symbol} IS NOT NULL
            """


def _mutation_source_sql(path: Path, default_genome_build: str | None) -> str:
    skip = _leading_comment_lines(path)
    fieldnames = _read_header_after_comments(path)
    genome_build = _maf_genome_build_sql(fieldnames, default_genome_build)
    sample = _column_or_null(fieldnames, "Tumor_Sample_Barcode")
    symbol = (
        "coalesce(nullif("
        + _column_or_null(fieldnames, "Hugo_Symbol")
        + ", ''), 'unknown')"
    )
    stable_id = _column_or_null(fieldnames, "Entrez_Gene_Id")
    contig = _column_or_null(fieldnames, "Chromosome")
    start = f"try_cast({_column_or_null(fieldnames, 'Start_Position')} AS BIGINT)"
    end = f"try_cast({_column_or_null(fieldnames, 'End_Position')} AS BIGINT)"
    ref = _column_or_null(fieldnames, "Reference_Allele")
    alt = (
        "coalesce("
        f"{_column_or_null(fieldnames, 'Tumor_Seq_Allele2')}, "
        f"{_column_or_null(fieldnames, 'Tumor_Seq_Allele1')}"
        ")"
    )
    consequence = (
        "coalesce("
        f"{_column_or_null(fieldnames, 'Consequence')}, "
        f"{_column_or_null(fieldnames, 'Variant_Classification')}"
        ")"
    )
    ref_count = f"try_cast({_column_or_null(fieldnames, 't_ref_count')} AS BIGINT)"
    alt_count = f"try_cast({_column_or_null(fieldnames, 't_alt_count')} AS BIGINT)"
    filter_column = (
        _sql_identifier("FILTER")
        if "FILTER" in fieldnames
        else _column_or_null(fieldnames, "filter")
    )
    info_json = _json_object_sql(fieldnames, _MAF_CORE_COLUMNS)
    return f"""
            SELECT
                sample_key,
                {_sql_feature_key("gene", "symbol")} AS feature_key,
                symbol,
                stable_id,
                genome_build,
                contig,
                pos,
                end_pos,
                ref,
                alt,
                'variant:' || genome_build || ':' || contig || ':' ||
                    pos::VARCHAR || ':' || coalesce(end_pos, pos)::VARCHAR || ':' ||
                    coalesce(ref, '') || '>' || coalesce(alt, '') AS variant_key,
                variant_type,
                consequence,
                gnomad_af,
                genotype,
                CASE
                    WHEN allele_depth_ref IS NOT NULL OR allele_depth_alt IS NOT NULL
                    THEN coalesce(allele_depth_ref, 0) + coalesce(allele_depth_alt, 0)
                    ELSE NULL
                END AS depth,
                allele_depth_ref,
                allele_depth_alt,
                filter,
                info_json,
                format_json
            FROM (
                SELECT
                    {sample} AS sample_key,
                    {symbol} AS symbol,
                    {stable_id} AS stable_id,
                    {genome_build} AS genome_build,
                    {contig} AS contig,
                    {start} AS pos,
                    {end} AS end_pos,
                    {ref} AS ref,
                    {alt} AS alt,
                    {_column_or_null(fieldnames, "Variant_Type")} AS variant_type,
                    {consequence} AS consequence,
                    try_cast({_column_or_null(fieldnames, "ExAC_AF")} AS DOUBLE)
                        AS gnomad_af,
                    {_column_or_null(fieldnames, "Mutation_Status")} AS genotype,
                    {ref_count} AS allele_depth_ref,
                    {alt_count} AS allele_depth_alt,
                    {filter_column} AS filter,
                    {info_json} AS info_json,
                    {info_json} AS format_json
                FROM read_csv(
                    ?,
                    delim = '\t',
                    header = true,
                    all_varchar = true,
                    skip = {skip},
                    nullstr = ['NA', '']
                )
            )
            WHERE sample_key IS NOT NULL
            AND contig IS NOT NULL
            AND pos IS NOT NULL
            """


def _maf_genome_build_sql(
    fieldnames: list[str], default_genome_build: str | None
) -> str:
    fallback = _sql_literal(default_genome_build or "unknown")
    if "NCBI_Build" not in fieldnames:
        return fallback
    column = _sql_identifier("NCBI_Build")
    return (
        "CASE "
        f"WHEN {column} = 'GRCh37' THEN 'hg19' "
        f"WHEN {column} = 'GRCh38' THEN 'hg38' "
        f"ELSE coalesce({column}, {fallback}) END"
    )


def _json_object_sql(fieldnames: list[str], excluded: set[str]) -> str:
    columns = [column for column in fieldnames if column not in excluded]
    if not columns:
        return "json('{}')"
    arguments = ", ".join(
        f"{_sql_literal(column)}, {_sql_identifier(column)}" for column in columns
    )
    return f"json_object({arguments})"


def _replace_features_from_source(
    connection: Any,
    source_sql: str,
    parameters: list[Any],
) -> None:
    connection.execute(
        f"""
        DELETE FROM features
        WHERE feature_key IN (
            SELECT DISTINCT feature_key
            FROM ({source_sql})
        )
        """,
        parameters,
    )


def _sql_feature_key(feature_type: str, identifier_sql: str) -> str:
    normalized = (
        "nullif(trim(regexp_replace("
        f"coalesce({identifier_sql}, 'unknown'), "
        "'[^A-Za-z0-9_.:-]+', '_', 'g'), '_'), '')"
    )
    return f"{_sql_literal(feature_type + ':')} || coalesce({normalized}, 'unknown')"


def _read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return handle.readline().rstrip("\n").split("\t")


def _read_header_after_comments(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#"):
                return line.rstrip("\n").split("\t")
    return []


def _leading_comment_lines(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#"):
                return count
            count += 1
    return count


def _column_or_null(fieldnames: list[str], column: str) -> str:
    return _sql_identifier(column) if column in fieldnames else "NULL"


def _sql_identifier_list(values: list[str]) -> str:
    return ", ".join(_sql_identifier(value) for value in values)


def _sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _insert_rows(
    connection: Any,
    table: str,
    columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    connection.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        [_db_tuple(row) for row in rows],
    )


def _insert_model_dicts(
    connection: Any,
    table: str,
    columns: tuple[str, ...],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    _insert_rows(
        connection,
        table,
        columns,
        [tuple(row.get(column) for column in columns) for row in rows],
    )


def _replace_dimension_rows(
    connection: Any,
    table: str,
    key_columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    keys = {tuple(row[index] for index in range(len(key_columns))) for row in rows}
    where = " AND ".join(f"{column} IS NOT DISTINCT FROM ?" for column in key_columns)
    connection.executemany(
        f"DELETE FROM {table} WHERE {where}",
        [tuple(key) for key in keys],
    )


def _db_tuple(row: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(
        json.dumps(value, sort_keys=True) if isinstance(value, dict | list) else value
        for value in row
    )


def _matrix_id_columns(fieldnames: list[str]) -> set[str]:
    known = {
        "Hugo_Symbol",
        "Entrez_Gene_Id",
        "Composite.Element.REF",
        "ENTITY_STABLE_ID",
        "NAME",
        "URL",
        "DESCRIPTION",
    }
    return {field for field in fieldnames if field in known}


def _matrix_feature(
    row: dict[str, str],
    feature_type: str,
) -> tuple[str, str, str | None, dict[str, Any]]:
    if (entity_id := _clean(row.get("ENTITY_STABLE_ID"))) is not None:
        name = _clean(row.get("NAME")) or entity_id
        return (
            _feature_key(feature_type, entity_id),
            name,
            entity_id,
            {
                "url": _clean(row.get("URL")),
                "description": _clean(row.get("DESCRIPTION")),
            },
        )
    if (composite := _clean(row.get("Composite.Element.REF"))) is not None:
        symbol = composite.split("|", 1)[0]
        stable_id = composite.split("|", 1)[1] if "|" in composite else composite
        return (
            _feature_key(feature_type, composite),
            symbol,
            stable_id,
            {"composite_ref": composite},
        )
    symbol = _clean(row.get("Hugo_Symbol")) or "unknown"
    stable_id = _clean(row.get("Entrez_Gene_Id"))
    return _feature_key(feature_type, symbol), symbol, stable_id, {}


def _feature_row(
    feature_key: str,
    symbol: str,
    feature_type: str,
    stable_id: object,
) -> tuple[Any, ...]:
    return (
        feature_key,
        feature_key,
        feature_type,
        symbol,
        _clean(stable_id),
        None,
        None,
        {},
    )


def _value_semantics(profile: DataProfile) -> str:
    datatype = profile.metadata_json.get("cbioportal", {}).get("datatype")
    stable_id = profile.metadata_json.get("cbioportal", {}).get("stable_id")
    raw = stable_id or datatype or profile.data_profile_id
    return _normalize_id(str(raw))


def _attribute_value_type(
    raw: str | None,
) -> Literal["numeric", "string", "boolean", "date", "json"]:
    if raw == "NUMBER":
        return "numeric"
    if raw == "BOOLEAN":
        return "boolean"
    return "string"


def _attribute_key(entity_scope: str, column: str) -> str:
    return f"{entity_scope}:{_normalize_id(column).lower()}"


def _cna_call(rank: int) -> tuple[str, str]:
    calls = {
        -2: ("HOMDEL", "Deep deletion"),
        -1: ("LOSS", "Shallow deletion"),
        0: ("DIPLOID", "Diploid"),
        1: ("GAIN", "Gain"),
        2: ("AMP", "Amplification"),
    }
    return calls.get(rank, (str(rank), str(rank)))


def _event_class(row: dict[str, str]) -> str:
    event_info = (_clean(row.get("Event_Info")) or "").lower()
    if "fusion" in event_info:
        return "fusion"
    return (_clean(row.get("SV_Status")) or "structural_variant").lower()


def _variant_key(
    build: str,
    chrom: str,
    pos: int,
    end_pos: int | None,
    ref: str | None,
    alt: str | None,
) -> str:
    return f"variant:{build}:{chrom}:{pos}:{end_pos or pos}:{ref or ''}>{alt or ''}"


def _structural_variant_key(row: dict[str, str]) -> str:
    parts = [
        "sv",
        _clean(row.get("Sample_Id")) or "",
        _clean(row.get("Site1_Chromosome")) or "",
        str(_to_int(row.get("Site1_Position")) or ""),
        _clean(row.get("Site2_Chromosome")) or "",
        str(_to_int(row.get("Site2_Position")) or ""),
        _clean(row.get("Event_Info")) or "",
    ]
    return _normalize_id(":".join(parts))


def _json_extra(row: dict[str, str], core_columns: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, raw in row.items()
        if key not in core_columns and (value := _clean(raw)) is not None
    }


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if _clean(value) is not None}


def _split_case_ids(value: str | None) -> list[str]:
    clean = _clean(value)
    return [] if clean is None else [part for part in re.split(r"\s+", clean) if part]


def _runs_from_context(context: CbioPortalParseContext, base_run: Run) -> list[Run]:
    if not context.sample_scoped_runs:
        return [base_run]
    runs: list[Run] = []
    for sample in sorted(context.samples.values(), key=lambda item: item.sample_id):
        run_id = context.run_id_for_sample(sample.sample_id)
        runs.append(
            base_run.model_copy(
                update={
                    "run_id": run_id,
                    "name": sample.sample_name or sample.sample_id,
                    "samples": [sample],
                    "metadata_json": {
                        **base_run.metadata_json,
                        "source_import_run_id": context.run_id,
                        "source_sample_id": sample.sample_id,
                    },
                }
            )
        )
    return runs


def _data_profiles_from_context(context: CbioPortalParseContext) -> list[DataProfile]:
    profiles = list(context.profiles_by_file.values())
    if not context.sample_scoped_runs:
        return profiles

    expanded = [
        profile.model_copy(
            update={
                "run_id": None,
                "metadata_json": {
                    **profile.metadata_json,
                    "profile_scope": "study",
                },
            }
        )
        for profile in profiles
    ]
    for sample in sorted(context.samples.values(), key=lambda item: item.sample_id):
        run_id = context.run_id_for_sample(sample.sample_id)
        for profile in profiles:
            expanded.append(
                profile.model_copy(
                    update={
                        "data_profile_id": context.data_profile_id_for_sample(
                            profile,
                            sample.sample_id,
                        ),
                        "run_id": run_id,
                        "metadata_json": {
                            **profile.metadata_json,
                            "source_data_profile_id": profile.data_profile_id,
                            "source_import_run_id": context.run_id,
                            "source_sample_id": sample.sample_id,
                        },
                    }
                )
            )
    return expanded


def _file_links_from_context(context: CbioPortalParseContext) -> list[FileLink]:
    if not context.sample_scoped_runs:
        return context.file_links

    links: list[FileLink] = []
    samples = sorted(context.samples.values(), key=lambda item: item.sample_id)
    for link in context.file_links:
        if link.run_id != context.run_id:
            links.append(link)
            continue
        for sample in samples:
            run_id = context.run_id_for_sample(sample.sample_id)
            run_sample_id = context.run_sample_id_for_sample(sample.sample_id)
            data_profile_id = link.data_profile_id
            if data_profile_id is not None:
                profile = next(
                    (
                        candidate
                        for candidate in context.profiles_by_file.values()
                        if candidate.data_profile_id == data_profile_id
                    ),
                    None,
                )
                if profile is not None:
                    data_profile_id = context.data_profile_id_for_sample(
                        profile,
                        sample.sample_id,
                    )
            links.append(
                link.model_copy(
                    update={
                        "run_id": run_id,
                        "run_sample_id": run_sample_id,
                        "sample_id": sample.sample_id,
                        "data_profile_id": data_profile_id,
                    }
                )
            )
    return links


def _profile_suffix(profile: DataProfile) -> str:
    if profile.run_id and profile.data_profile_id.startswith(f"{profile.run_id}:"):
        return profile.data_profile_id.removeprefix(f"{profile.run_id}:")
    return _normalize_id(profile.data_profile_id)


def _run_id_for_sample(
    base_run_id: str,
    sample_id: str,
    *,
    sample_scoped_runs: bool,
) -> str:
    if not sample_scoped_runs:
        return base_run_id
    return f"{base_run_id}:{_normalize_id(sample_id)}"


def _data_profile_id_for_sample(
    base_run_id: str,
    profile: DataProfile,
    sample_id: str,
    *,
    sample_scoped_runs: bool,
) -> str:
    if not sample_scoped_runs:
        return profile.data_profile_id
    sample_run_id = _run_id_for_sample(
        base_run_id,
        sample_id,
        sample_scoped_runs=True,
    )
    return f"{sample_run_id}:{_profile_suffix(profile)}"


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _mapped_run_id_sql(
    sample_column: str,
    *,
    base_run_id: str,
    sample_scoped_runs: bool,
) -> str:
    if not sample_scoped_runs:
        return _sql_string(base_run_id)
    normalized_sample = (
        f"trim(BOTH '_' FROM regexp_replace(trim(CAST({sample_column} AS VARCHAR)), "
        "'[^A-Za-z0-9_.:-]+', '_', 'g'))"
    )
    return f"{_sql_string(base_run_id)} || ':' || {normalized_sample}"


def _mapped_data_profile_key_sql(
    mapped_run_id_sql: str,
    *,
    base_profile_id: str,
    profile_suffix: str,
    sample_scoped_runs: bool,
) -> str:
    if not sample_scoped_runs:
        return _sql_string(base_profile_id)
    return f"{mapped_run_id_sql} || ':' || {_sql_string(profile_suffix)}"


def _mapped_sample_source_sql(
    source_sql: str,
    *,
    base_run_id: str,
    profile_suffix: str,
    sample_scoped_runs: bool,
) -> str:
    mapped_run_id = _mapped_run_id_sql(
        "sample_key",
        base_run_id=base_run_id,
        sample_scoped_runs=sample_scoped_runs,
    )
    data_profile_key = _mapped_data_profile_key_sql(
        mapped_run_id,
        base_profile_id=f"{base_run_id}:{profile_suffix}",
        profile_suffix=profile_suffix,
        sample_scoped_runs=sample_scoped_runs,
    )
    return f"""
        SELECT
            *,
            {mapped_run_id} AS mapped_run_id,
            {data_profile_key} AS data_profile_key
        FROM ({source_sql})
    """


def _run_sample_id(run_id: str, sample_id: str) -> str:
    return f"{run_id}:{sample_id}"


def _feature_key(feature_type: str, identifier: str) -> str:
    return f"{feature_type}:{_normalize_id(identifier)}"


def _normalize_id(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    return clean.strip("_") or hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in MISSING_VALUES else text


def _to_float(value: object) -> float | None:
    clean = _clean(value)
    if clean is None:
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _to_int(value: object) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _genome_from_build(value: object) -> str | None:
    clean = _clean(value)
    if clean == "GRCh37":
        return "hg19"
    if clean == "GRCh38":
        return "hg38"
    return clean


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_FEATURE_COLUMNS = (
    "feature_key",
    "feature_id",
    "feature_type",
    "symbol",
    "stable_id",
    "namespace",
    "genome_build",
    "metadata_json",
)
_FEATURE_VALUE_COLUMNS = (
    "data_profile_key",
    "run_id",
    "run_sample_key",
    "sample_key",
    "feature_key",
    "value",
    "value_semantics",
    "source_file_id",
)
_FEATURE_CALL_COLUMNS = (
    "data_profile_key",
    "run_id",
    "run_sample_key",
    "sample_key",
    "feature_key",
    "call_code",
    "call_label",
    "call_rank",
    "score",
    "confidence",
    "source_event_id",
    "source_file_id",
)
_SEGMENT_COLUMNS = (
    "data_profile_key",
    "run_id",
    "run_sample_key",
    "sample_key",
    "genome_build",
    "contig",
    "start_pos",
    "end_pos",
    "num_probes",
    "segment_mean",
    "total_copy_number",
    "minor_copy_number",
    "call_label",
    "source_file_id",
)
_VARIANT_COLUMNS = (
    "variant_key",
    "variant_id",
    "genome_build",
    "contig",
    "pos",
    "end_pos",
    "ref",
    "alt",
    "variant_type",
    "normalized_key",
)
_VARIANT_ANNOTATION_COLUMNS = (
    "data_profile_key",
    "variant_key",
    "feature_key",
    "consequence",
    "impact",
    "clinvar_significance",
    "gnomad_af",
    "info_json",
)
_SAMPLE_VARIANT_CALL_COLUMNS = (
    "data_profile_key",
    "run_id",
    "run_sample_key",
    "sample_key",
    "variant_key",
    "genotype",
    "depth",
    "genotype_quality",
    "allele_depth_ref",
    "allele_depth_alt",
    "allele_fraction",
    "filter",
    "format_json",
    "source_file_id",
)
_SV_EVENT_COLUMNS = (
    "structural_variant_key",
    "event_id",
    "event_class",
    "genome_build",
    "site1_feature_key",
    "site2_feature_key",
    "site1_contig",
    "site1_pos",
    "site2_contig",
    "site2_pos",
    "frame_status",
    "event_info",
    "annotation_json",
)
_SV_CALL_COLUMNS = (
    "data_profile_key",
    "run_id",
    "run_sample_key",
    "sample_key",
    "structural_variant_key",
    "call_status",
    "dna_support",
    "rna_support",
    "tumor_read_count",
    "normal_read_count",
    "split_read_count",
    "paired_end_read_count",
    "format_json",
    "source_file_id",
)
_MAF_CORE_COLUMNS = {
    "Hugo_Symbol",
    "Entrez_Gene_Id",
    "NCBI_Build",
    "Chromosome",
    "Start_Position",
    "End_Position",
    "Consequence",
    "Variant_Classification",
    "Variant_Type",
    "Reference_Allele",
    "Tumor_Seq_Allele1",
    "Tumor_Seq_Allele2",
    "Tumor_Sample_Barcode",
    "Mutation_Status",
    "t_ref_count",
    "t_alt_count",
    "ExAC_AF",
}
_SV_CORE_COLUMNS = {
    "Sample_Id",
    "SV_Status",
    "Site1_Hugo_Symbol",
    "Site1_Chromosome",
    "Site1_Position",
    "Site2_Hugo_Symbol",
    "Site2_Chromosome",
    "Site2_Position",
    "Tumor_Split_Read_Count",
    "Tumor_Paired_End_Read_Count",
    "Event_Info",
    "NCBI_Build",
}
