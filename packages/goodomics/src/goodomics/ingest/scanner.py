from __future__ import annotations

from pathlib import Path


def build_ingest_request(
    results: Path,
    *,
    project: str | None = None,
    report_name: str | None = None,
    cohort: str | None = None,
    run_id: str | None = None,
) -> dict[str, str | None]:
    return {
        "results": str(results),
        "project": project,
        "report": report_name,
        "cohort": cohort,
        "run_id": run_id,
    }
