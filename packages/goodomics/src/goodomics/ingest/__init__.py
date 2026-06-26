from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from goodomics.ingest.multiqc import MultiQCIngestResult, ingest_multiqc
    from goodomics.ingest.runner import IngestRouteResult, IngestType, run_ingest
    from goodomics.ingest.scanner import build_ingest_request

__all__ = [
    "IngestRouteResult",
    "IngestType",
    "MultiQCIngestResult",
    "build_ingest_request",
    "ingest_multiqc",
    "run_ingest",
]


def __getattr__(name: str) -> Any:
    if name in {"MultiQCIngestResult", "ingest_multiqc"}:
        from goodomics.ingest.multiqc import MultiQCIngestResult, ingest_multiqc

        return {
            "MultiQCIngestResult": MultiQCIngestResult,
            "ingest_multiqc": ingest_multiqc,
        }[name]
    if name in {"IngestRouteResult", "IngestType", "run_ingest"}:
        from goodomics.ingest.runner import IngestRouteResult, IngestType, run_ingest

        return {
            "IngestRouteResult": IngestRouteResult,
            "IngestType": IngestType,
            "run_ingest": run_ingest,
        }[name]
    if name == "build_ingest_request":
        from goodomics.ingest.scanner import build_ingest_request

        return build_ingest_request
    raise AttributeError(name)
