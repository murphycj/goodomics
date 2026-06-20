from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Metric(BaseModel):
    sample_id: str | None = None
    name: str
    value: float | int | str
    unit: str | None = None


class Sample(BaseModel):
    sample_id: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Run(BaseModel):
    run_id: str
    project: str | None = None
    assay: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    samples: list[Sample] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)


class QCDecision(BaseModel):
    status: Literal["pass", "warn", "fail", "unknown"]
    reasons: list[str] = Field(default_factory=list)
    cohort: str | None = None
    report_version: str | None = None
    policy_version: str | None = None
