"""Helpers for building normalized ingest request payloads."""

from __future__ import annotations

from pathlib import Path


def build_ingest_request(
    results: Path,
    *,
    project: str | None = None,
    report_name: str | None = None,
    sample_group_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, str | None]:
    """Return CLI-facing ingest request fields with the path serialized as a string."""

    return {
        "results": str(results),
        "project": project,
        "report": report_name,
        "sample_group_id": sample_group_id,
        "run_id": run_id,
    }
