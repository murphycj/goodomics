"""Canonical references for analytical and project-metadata fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, cast

from pydantic import AfterValidator

MetadataEntity = Literal["subject", "sample", "run", "file"]
METADATA_ENTITIES: frozenset[str] = frozenset({"subject", "sample", "run", "file"})


def validate_field_reference_segment(value: str) -> str:
    """Require one non-empty, unescaped path segment for a stable field ID."""

    if not value or value != value.strip():
        raise ValueError(
            "Field-reference IDs must be non-empty and have no surrounding whitespace."
        )
    if "/" in value:
        raise ValueError("Field-reference IDs cannot contain '/'.")
    return value


FieldReferenceSegment = Annotated[str, AfterValidator(validate_field_reference_segment)]


@dataclass(frozen=True)
class ParsedFieldReference:
    """Resolved source identity and source-local field ID."""

    kind: Literal["contract", "metadata"]
    field_id: str
    contract_id: str | None = None
    entity: MetadataEntity | None = None


def contract_field_reference(contract_id: str, field_id: str) -> str:
    """Build the canonical unprefixed reference for one analytical field."""

    return (
        f"{validate_field_reference_segment(contract_id)}/"
        f"{validate_field_reference_segment(field_id)}"
    )


def metadata_field_reference(entity: str, field_id: str) -> str:
    """Build the canonical namespaced reference for one metadata field."""

    if entity not in METADATA_ENTITIES:
        raise ValueError(f"Unknown metadata entity: {entity!r}.")
    return f"metadata/{entity}/{validate_field_reference_segment(field_id)}"


def parse_field_reference(value: str) -> ParsedFieldReference:
    """Parse the strict canonical field-reference grammar."""

    if not value or value != value.strip():
        raise ValueError(
            "Field reference must be non-empty and have no surrounding whitespace."
        )
    parts = value.split("/")
    if len(parts) == 2:
        contract_id, field_id = parts
        return ParsedFieldReference(
            kind="contract",
            contract_id=validate_field_reference_segment(contract_id),
            field_id=validate_field_reference_segment(field_id),
        )
    if len(parts) == 3 and parts[0] == "metadata":
        _, entity, field_id = parts
        if entity not in METADATA_ENTITIES:
            raise ValueError(f"Unknown metadata entity in field reference: {entity!r}.")
        return ParsedFieldReference(
            kind="metadata",
            entity=cast(MetadataEntity, entity),
            field_id=validate_field_reference_segment(field_id),
        )
    raise ValueError(
        "Field reference must be '<contract>/<field>' or 'metadata/<entity>/<field>'."
    )
