"""Export the committed Goodomics OpenAPI contract from canonical models."""

from __future__ import annotations

from pathlib import Path

from goodomics.openapi import export_openapi


def main() -> None:
    """Export the contract to the repository's canonical OpenAPI path."""

    repository_root = Path(__file__).resolve().parents[1]
    export_openapi(repository_root / "openapi" / "goodomics.openapi.json")


if __name__ == "__main__":
    main()
