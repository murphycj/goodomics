from __future__ import annotations

from pathlib import Path


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
    return multiqc_dir
