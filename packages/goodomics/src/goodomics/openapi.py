"""Deterministic OpenAPI export for the generated dashboard contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goodomics.server.app import create_app
from goodomics.server.settings import Settings


def build_openapi_document() -> dict[str, Any]:
    """Build the API document without starting the server or initializing data."""

    return create_app(Settings()).openapi()


def export_openapi(path: Path) -> None:
    """Write the canonical OpenAPI JSON with deterministic ordering and spacing."""

    document = build_openapi_document()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
