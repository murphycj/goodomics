from __future__ import annotations

from pathlib import Path

from goodomics import run
from goodomics.schemas.models import Metric, QCDecision, Run, Sample


def test_sdk_run_collects_metrics_and_files() -> None:
    qc_run = run("demo", assay="rnaseq")
    qc_run.log_metric("sample-1", "reads", 42, unit="count")
    qc_run.log_file(Path("results") / "multiqc.html")

    assert qc_run.name == "demo"
    assert qc_run.assay == "rnaseq"
    assert qc_run.metrics[0]["name"] == "reads"
    assert qc_run.files == [Path("results") / "multiqc.html"]


def test_schema_models_have_expected_defaults() -> None:
    model = Run(
        run_id="run-1",
        project="project-1",
        assay="rnaseq",
        samples=[Sample(sample_id="sample-1")],
        metrics=[Metric(sample_id="sample-1", name="reads", value=123)],
    )

    assert model.created_at.tzinfo is not None
    assert model.samples[0].metadata == {}
    assert model.metrics[0].value == 123


def test_qc_decision_status_values() -> None:
    decision = QCDecision(status="warn", reasons=["low depth"], cohort="study-a")

    assert decision.status == "warn"
    assert decision.reasons == ["low depth"]
