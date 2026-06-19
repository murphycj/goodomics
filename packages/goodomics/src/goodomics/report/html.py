from __future__ import annotations

from html import escape
from pathlib import Path


def render_report(results: Path) -> str:
    safe_results = escape(str(results))
    return (
        "<!doctype html>"
        "<title>Goodomics Report</title>"
        "<h1>Goodomics Report</h1>"
        f"<p>Scanned results: {safe_results}</p>"
    )


def write_report(results: Path, out: Path) -> Path:
    out.write_text(render_report(results), encoding="utf-8")
    return out
