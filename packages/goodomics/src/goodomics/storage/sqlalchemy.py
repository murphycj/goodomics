# pyright: reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.schemas.models import Metric, Run, Sample


class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: str = Field(primary_key=True, max_length=255)
    project: str | None = Field(default=None, max_length=255)
    assay: str | None = Field(default=None, max_length=255)
    created_at: datetime


class SampleRecord(SQLModel, table=True):
    __tablename__ = "samples"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    sample_id: str = Field(max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class MetricRecord(SQLModel, table=True):
    __tablename__ = "metrics"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    sample_id: str | None = Field(default=None, max_length=255)
    name: str = Field(max_length=255)
    value: Any = Field(sa_type=JSON)
    unit: str | None = Field(default=None, max_length=255)


class ArtifactRecord(SQLModel, table=True):
    __tablename__ = "artifacts"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    path: str = Field(max_length=2048)


class QCDecisionRecord(SQLModel, table=True):
    __tablename__ = "qc_decisions"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.run_id", max_length=255, index=True)
    status: str = Field(max_length=32)
    reasons: list[str] = Field(default_factory=list, sa_type=JSON)
    cohort: str | None = Field(default=None, max_length=255)
    report_version: str | None = Field(default=None, max_length=255)
    policy_version: str | None = Field(default=None, max_length=255)


metadata = SQLModel.metadata
runs_table = RunRecord.__table__
samples_table = SampleRecord.__table__
metrics_table = MetricRecord.__table__
artifacts_table = ArtifactRecord.__table__
qc_decisions_table = QCDecisionRecord.__table__


class SQLModelGoodomicsStore:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self.database_url = database_url
        self.engine = engine

    def _get_engine(self) -> AsyncEngine:
        if self.engine is None:
            self.engine = create_async_engine(self.database_url)
        return self.engine

    async def ensure_schema(self) -> None:
        async with self._get_engine().begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def save_run(self, run: Run) -> None:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            await session.exec(
                delete(QCDecisionRecord).where(QCDecisionRecord.run_id == run.run_id)
            )
            await session.exec(
                delete(ArtifactRecord).where(ArtifactRecord.run_id == run.run_id)
            )
            await session.exec(
                delete(MetricRecord).where(MetricRecord.run_id == run.run_id)
            )
            await session.exec(
                delete(SampleRecord).where(SampleRecord.run_id == run.run_id)
            )

            existing = await session.get(RunRecord, run.run_id)
            if existing is not None:
                await session.delete(existing)

            session.add(
                RunRecord(
                    run_id=run.run_id,
                    project=run.project,
                    assay=run.assay,
                    created_at=run.created_at,
                )
            )
            if run.samples:
                session.add_all(
                    [
                        SampleRecord(
                            run_id=run.run_id,
                            sample_id=sample.sample_id,
                            metadata_json=dict(sample.metadata),
                        )
                        for sample in run.samples
                    ]
                )
            if run.metrics:
                session.add_all(
                    [
                        MetricRecord(
                            run_id=run.run_id,
                            sample_id=metric.sample_id,
                            name=metric.name,
                            value=metric.value,
                            unit=metric.unit,
                        )
                        for metric in run.metrics
                    ]
                )
            await session.commit()

    async def get_run(self, run_id: str) -> Run | None:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            run_row = await session.get(RunRecord, run_id)
            if run_row is None:
                return None
            sample_rows = (
                await session.exec(
                    select(SampleRecord).where(SampleRecord.run_id == run_id)
                )
            ).all()
            metric_rows = (
                await session.exec(
                    select(MetricRecord).where(MetricRecord.run_id == run_id)
                )
            ).all()
        return Run(
            run_id=run_row.run_id,
            project=run_row.project,
            assay=run_row.assay,
            created_at=run_row.created_at,
            samples=[_sample_from_row(row) for row in sample_rows],
            metrics=[_metric_from_row(row) for row in metric_rows],
        )

    async def list_metrics(self, run_id: str) -> list[Metric]:
        await self.ensure_schema()
        async with AsyncSession(self._get_engine()) as session:
            metric_rows = (
                await session.exec(
                    select(MetricRecord).where(MetricRecord.run_id == run_id)
                )
            ).all()
        return [_metric_from_row(row) for row in metric_rows]


def _sample_from_row(row: SampleRecord) -> Sample:
    metadata_value = row.metadata_json
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(sample_id=row.sample_id, metadata=metadata_dict)


def _metric_from_row(row: MetricRecord) -> Metric:
    return Metric(
        sample_id=row.sample_id,
        name=row.name,
        value=row.value,
        unit=row.unit,
    )


# Backward-compatible alias for existing imports.
SQLAlchemyGoodomicsStore = SQLModelGoodomicsStore
