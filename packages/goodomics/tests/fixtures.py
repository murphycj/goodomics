from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import duckdb


def write_multiqc_fixture(
    root: Path,
    *,
    sample_id: str = "S1",
    report_prefix: str = "demo",
) -> Path:
    multiqc_dir = root / "multiqc"
    data_dir = multiqc_dir / f"{report_prefix}_multiqc_report_data"
    data_dir.mkdir(parents=True)
    (multiqc_dir / f"{report_prefix}_multiqc_report.html").write_text(
        "<html><body>MultiQC</body></html>",
        encoding="utf-8",
    )
    (data_dir / "multiqc_general_stats.txt").write_text(
        "\n".join(
            [
                "Sample\tsalmon-percent_mapped\tfastqc_raw-percent_gc\tfastqc_raw-total_sequences",
                f"{sample_id}\t95.5\t48.1\t1000",
                f"{sample_id} Read 1\t\t47.9\t500",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "multiqc_salmon.txt").write_text(
        "\n".join(
            [
                "Sample\tsalmon_version\tnum_processed\tnum_mapped\tpercent_mapped",
                f"{sample_id}\t1.10.3\t1000\t955\t95.5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "multiqc_sources.txt").write_text(
        "\n".join(
            [
                "Module\tSection\tSample Name\tSource",
                f"Salmon\tall_sections\t{sample_id}\t/work/{sample_id}/libParams/flenDist.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "multiqc_software_versions.txt").write_text(
        "Salmon\tFastQC\n1.10.3\t0.12.1\n",
        encoding="utf-8",
    )
    (data_dir / "salmon_plot.txt").write_text(
        f"Sample\t0\t1\t2\n{sample_id}\t(0, 0.1)\t(1, 0.2)\t(2, 0.3)\n",
        encoding="utf-8",
    )
    (data_dir / "multiqc.log").write_text("MultiQC fixture log\n", encoding="utf-8")
    _write_multiqc_parquet_fixture(data_dir / "multiqc.parquet", sample_id=sample_id)
    return multiqc_dir


def _write_multiqc_parquet_fixture(path: Path, *, sample_id: str) -> None:
    columns = (
        "anchor",
        "type",
        "creation_date",
        "plot_type",
        "plot_input_data",
        "dt_anchor",
        "section_key",
        "section_order",
        "sample",
        "row_sample",
        "metric",
        "val_raw",
        "val_raw_type",
        "val_mod",
        "val_mod_type",
        "val_fmt",
        "column_meta",
        "show_table_by_default",
        "pconfig",
        "config",
        "data_sources",
        "multiqc_version",
        "modules",
        "software_versions",
    )
    fastqc_meta = {
        "rid": "fastqc_raw-percent_gc",
        "clean_rid": "fastqc_raw-percent_gc",
        "title": "GC",
        "namespace": "FastQC: raw",
        "suffix": "%",
    }
    salmon_meta = {
        "rid": "salmon-percent_mapped",
        "clean_rid": "salmon-percent_mapped",
        "title": "Mapped",
        "namespace": "Salmon",
        "suffix": "%",
    }
    rows = [
        (
            None,
            "run_metadata",
            datetime(2026, 1, 1),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "1.35",
            json.dumps([{"name": "Salmon", "anchor": "salmon"}]),
            json.dumps(
                {
                    "Salmon": {"Salmon": ["1.10.3"]},
                    "FastQC": {"FastQC": ["0.12.1"]},
                }
            ),
        ),
        (
            "salmon_plot",
            "plot_input",
            None,
            "x/y line",
            json.dumps({"rows": [{"Sample": sample_id, "0": "(0, 0.1)"}]}),
            None,
            "salmon",
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            json.dumps({sample_id: [f"/work/{sample_id}/libParams/flenDist.txt"]}),
            None,
            None,
            None,
        ),
        _parquet_metric_row(sample_id, sample_id, "percent_mapped", 95.5, salmon_meta),
        _parquet_metric_row(sample_id, sample_id, "percent_gc", 48.1, fastqc_meta),
        _parquet_metric_row(
            sample_id,
            f"{sample_id} R1",
            "percent_gc",
            47.9,
            fastqc_meta,
        ),
        (
            "general_stats_table",
            "plot_input_row",
            None,
            None,
            None,
            None,
            None,
            None,
            sample_id,
            sample_id,
            "status",
            None,
            None,
            None,
            None,
            "pass",
            json.dumps(
                {
                    "rid": "salmon-status",
                    "clean_rid": "salmon-status",
                    "title": "Status",
                    "namespace": "Salmon",
                }
            ),
            True,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]
    with duckdb.connect() as connection:
        connection.execute(
            """
            CREATE TABLE fixture_multiqc_parquet (
                anchor VARCHAR,
                type VARCHAR,
                creation_date TIMESTAMP,
                plot_type VARCHAR,
                plot_input_data VARCHAR,
                dt_anchor VARCHAR,
                section_key VARCHAR,
                section_order BIGINT,
                sample VARCHAR,
                row_sample VARCHAR,
                metric VARCHAR,
                val_raw DOUBLE,
                val_raw_type VARCHAR,
                val_mod DOUBLE,
                val_mod_type VARCHAR,
                val_fmt VARCHAR,
                column_meta VARCHAR,
                show_table_by_default BOOLEAN,
                pconfig VARCHAR,
                config VARCHAR,
                data_sources VARCHAR,
                multiqc_version VARCHAR,
                modules VARCHAR,
                software_versions VARCHAR
            )
            """
        )
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO fixture_multiqc_parquet VALUES ({placeholders})",
            rows,
        )
        connection.execute(
            "COPY fixture_multiqc_parquet TO ? (FORMAT PARQUET)",
            [str(path)],
        )


def _parquet_metric_row(
    sample_id: str,
    row_sample: str,
    metric: str,
    value: float,
    column_meta: Mapping[str, object],
) -> tuple[object, ...]:
    return (
        "general_stats_table",
        "plot_input_row",
        None,
        None,
        None,
        None,
        None,
        None,
        sample_id,
        row_sample,
        metric,
        value,
        "float",
        value,
        "float",
        f"{value:.1f}",
        json.dumps(column_meta),
        True,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def write_cbioportal_fixture(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "case_lists").mkdir()
    (root / "meta_study.txt").write_text(
        "\n".join(
            [
                "type_of_cancer: mixed",
                "cancer_study_identifier: demo_cbio",
                "name: Demo cBioPortal Study",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "meta_clinical_patient.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "genetic_alteration_type: CLINICAL",
                "datatype: PATIENT_ATTRIBUTES",
                "data_filename: data_clinical_patient.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "data_clinical_patient.txt").write_text(
        "\r\n".join(
            [
                "#Patient Identifier\tSex\tAge",
                "#Identifier\tSex\tAge at diagnosis",
                "#STRING\tSTRING\tNUMBER",
                "#1\t1\t1",
                "PATIENT_ID\tSEX\tAGE",
                "S1\tFemale\t45",
                "S2\tMale\t52",
            ]
        )
        + "\r\n",
        encoding="utf-8",
    )
    (root / "meta_clinical_sample.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "genetic_alteration_type: CLINICAL",
                "datatype: SAMPLE_ATTRIBUTES",
                "data_filename: data_clinical_sample.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "data_clinical_sample.txt").write_text(
        "\n".join(
            [
                "#Sample Identifier\tPatient Identifier\tCancer Type\tTMB",
                "#Identifier\tPatient\tCancer type\tTumor mutation burden",
                "#STRING\tSTRING\tSTRING\tNUMBER",
                "#1\t1\t1\t1",
                "SAMPLE_ID\tPATIENT_ID\tCANCER_TYPE\tTMB",
                "S1\tS1\tLung Cancer\t12.5",
                "S2\tS2\tBreast Cancer\t3.2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_meta(
        root,
        "meta_mrna_seq_rpkm.txt",
        "MRNA_EXPRESSION",
        "CONTINUOUS",
        "rna_seq_mrna",
        "mRNA expression",
        "data_mrna_seq_rpkm.txt",
    )
    (root / "data_mrna_seq_rpkm.txt").write_text(
        "Hugo_Symbol\tEntrez_Gene_Id\tS1\tS2\nTP53\t7157\t1.2\t2.4\nEGFR\t1956\t0\t3.5\n",
        encoding="utf-8",
    )
    _write_meta(
        root,
        "meta_cna.txt",
        "COPY_NUMBER_ALTERATION",
        "DISCRETE",
        "cna",
        "Copy number",
        "data_cna.txt",
    )
    (root / "data_cna.txt").write_text(
        "Hugo_Symbol\tEntrez_Gene_Id\tS1\tS2\nTP53\t7157\t-1\t0\nEGFR\t1956\t2\t1\n",
        encoding="utf-8",
    )
    (root / "meta_cna_hg19_seg.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "genetic_alteration_type: COPY_NUMBER_ALTERATION",
                "datatype: SEG",
                "reference_genome_id: hg19",
                "data_filename: data_cna_hg19.seg",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "data_cna_hg19.seg").write_text(
        "ID\tchrom\tloc.start\tloc.end\tnum.mark\tseg.mean\nS1\t1\t10\t20\t2\t0.4\n",
        encoding="utf-8",
    )
    _write_meta(
        root,
        "meta_mutations.txt",
        "MUTATION_EXTENDED",
        "MAF",
        "mutations",
        "Mutations",
        "data_mutations.txt",
    )
    (root / "data_mutations.txt").write_text(
        "\n".join(
            [
                "#genome_nexus_version: test",
                "Hugo_Symbol\tEntrez_Gene_Id\tNCBI_Build\tChromosome\tStart_Position\tEnd_Position\tConsequence\tVariant_Classification\tVariant_Type\tReference_Allele\tTumor_Seq_Allele1\tTumor_Seq_Allele2\tTumor_Sample_Barcode\tMutation_Status\tt_ref_count\tt_alt_count",
                "TP53\t7157\tGRCh37\t17\t7579472\t7579472\tmissense_variant\tMissense_Mutation\tSNP\tC\tC\tT\tS1\tSOMATIC\t20\t8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_meta(
        root,
        "meta_sv.txt",
        "STRUCTURAL_VARIANT",
        "SV",
        "structural_variants",
        "SV Data",
        "data_sv.txt",
    )
    (root / "data_sv.txt").write_text(
        "\n".join(
            [
                "Sample_Id\tSV_Status\tSite1_Hugo_Symbol\tSite1_Chromosome\tSite1_Position\tSite2_Hugo_Symbol\tSite2_Chromosome\tSite2_Position\tTumor_Split_Read_Count\tTumor_Paired_End_Read_Count\tEvent_Info\tNCBI_Build",
                "\t".join(
                    [
                        "S1",
                        "SOMATIC",
                        "EML4",
                        "2",
                        "42522656",
                        "ALK",
                        "2",
                        "29446394",
                        "4",
                        "7",
                        "EML4-ALK fusion",
                        "GRCh37",
                    ]
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_meta(
        root,
        "meta_drug_treatment_auc.txt",
        "GENERIC_ASSAY",
        "LIMIT-VALUE",
        "drug_auc",
        "Treatment response",
        "data_drug_treatment_auc.txt",
    )
    (root / "data_drug_treatment_auc.txt").write_text(
        "\n".join(
            [
                "ENTITY_STABLE_ID\tNAME\tURL\tDESCRIPTION\tS1\tS2",
                "DrugA\tDrug A\thttps://example.test/drug-a\tDemo drug\t0.9\t0.1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "meta_gene_panel_matrix.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "genetic_alteration_type: GENE_PANEL_MATRIX",
                "datatype: GENE_PANEL_MATRIX",
                "data_filename: data_gene_panel_matrix.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "data_gene_panel_matrix.txt").write_text(
        "SAMPLE_ID\tmutations\tcna\tstructural_variants\nS1\tWXS\tWXS\tWXS\nS2\tWXS\tWXS\tWXS\n",
        encoding="utf-8",
    )
    (root / "case_lists" / "cases_all.txt").write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                "stable_id: demo_all",
                "case_list_name: All samples",
                "case_list_category: all_cases_in_study",
                "case_list_ids: S1\tS2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def _write_meta(
    root: Path,
    filename: str,
    alteration_type: str,
    datatype: str,
    stable_id: str,
    profile_name: str,
    data_filename: str,
) -> None:
    (root / filename).write_text(
        "\n".join(
            [
                "cancer_study_identifier: demo_cbio",
                f"genetic_alteration_type: {alteration_type}",
                f"datatype: {datatype}",
                f"stable_id: {stable_id}",
                f"profile_name: {profile_name}",
                f"profile_description: {profile_name}",
                f"data_filename: {data_filename}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
