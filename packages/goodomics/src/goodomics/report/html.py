from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import yaml


def load_report_template(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    return value if isinstance(value, dict) else {}


def render_report(
    results: Path | str,
    *,
    title: str = "Goodomics Report",
    template: dict[str, Any] | None = None,
) -> str:
    template = template or {}
    config = template.get("config")
    if isinstance(config, dict) and isinstance(config.get("title"), str):
        title = config["title"]
    safe_results = escape(str(results))
    safe_title = escape(title)
    return (
        "<!doctype html>"
        f"<title>{safe_title}</title>"
        f"<h1>{safe_title}</h1>"
        f"<p>Scanned results: {safe_results}</p>"
    )


def write_report(
    results: Path,
    out: Path,
    *,
    title: str = "Goodomics Report",
    template: dict[str, Any] | None = None,
) -> Path:
    out.write_text(render_report(results, title=title, template=template), encoding="utf-8")
    return out
