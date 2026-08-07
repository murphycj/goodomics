"""Shared Pydantic behavior for Goodomics models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel as PydanticBaseModel
from pydantic import field_serializer


def serialize_datetime(value: datetime) -> str:
    """Serialize stored datetimes as timezone-qualified UTC RFC 3339 values."""

    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")


class BaseModel(PydanticBaseModel):
    """Pydantic base with a consistent public JSON datetime contract."""

    @field_serializer("*", check_fields=False, when_used="json")
    def serialize_public_fields(self, value: object):
        """Normalize direct datetime fields at the public JSON boundary."""

        return serialize_datetime(value) if isinstance(value, datetime) else value
