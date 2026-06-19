from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.sql.schema import Column

from goodomics.schemas.models import Metric, Run, Sample

metadata = MetaData()

runs_table = Table(
    "runs",
    metadata,
    Column("run_id", String(length=255), primary_key=True),
    Column("project", String(length=255), nullable=True),
    Column("assay", String(length=255), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

samples_table = Table(
    "samples",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("sample_id", String(length=255), nullable=False),
    Column("metadata", JSON, nullable=False),
)

metrics_table = Table(
    "metrics",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("sample_id", String(length=255), nullable=True),
    Column("name", String(length=255), nullable=False),
    Column("value", JSON, nullable=False),
    Column("unit", String(length=255), nullable=True),
)

artifacts_table = Table(
    "artifacts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("path", String(length=2048), nullable=False),
)

qc_decisions_table = Table(
    "qc_decisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("status", String(length=32), nullable=False),
    Column("reasons", JSON, nullable=False),
    Column("cohort", String(length=255), nullable=True),
    Column("report_version", String(length=255), nullable=True),
    Column("policy_version", String(length=255), nullable=True),
)


class SQLAlchemyGoodomicsStore:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self.database_url = database_url
        self.engine = engine

    def _get_engine(self) -> AsyncEngine:
        if self.engine is None:
            self.engine = create_async_engine(self.database_url)
        return self.engine

    async def ensure_schema(self) -> None:
        async with self._get_engine().begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def save_run(self, run: Run) -> None:
        await self.ensure_schema()
        async with self._get_engine().begin() as connection:
            await connection.execute(
                delete(qc_decisions_table).where(qc_decisions_table.c.run_id == run.run_id)
            )
            await connection.execute(
                delete(artifacts_table).where(artifacts_table.c.run_id == run.run_id)
            )
            await connection.execute(
                delete(metrics_table).where(metrics_table.c.run_id == run.run_id)
            )
            await connection.execute(
                delete(samples_table).where(samples_table.c.run_id == run.run_id)
            )
            await connection.execute(delete(runs_table).where(runs_table.c.run_id == run.run_id))
            await connection.execute(
                insert(runs_table).values(
                    run_id=run.run_id,
                    project=run.project,
                    assay=run.assay,
                    created_at=run.created_at,
                )
            )
            if run.samples:
                await connection.execute(
                    insert(samples_table),
                    [
                        {
                            "run_id": run.run_id,
                            "sample_id": sample.sample_id,
                            "metadata": dict(sample.metadata),
                        }
                        for sample in run.samples
                    ],
                )
            if run.metrics:
                await connection.execute(
                    insert(metrics_table),
                    [
                        {
                            "run_id": run.run_id,
                            "sample_id": metric.sample_id,
                            "name": metric.name,
                            "value": metric.value,
                            "unit": metric.unit,
                        }
                        for metric in run.metrics
                    ],
                )

    async def get_run(self, run_id: str) -> Run | None:
        await self.ensure_schema()
        async with self._get_engine().connect() as connection:
            run_row = (
                await connection.execute(select(runs_table).where(runs_table.c.run_id == run_id))
            ).mappings().first()
            if run_row is None:
                return None
            sample_rows = (
                await connection.execute(
                    select(samples_table).where(samples_table.c.run_id == run_id)
                )
            ).mappings().all()
            metric_rows = (
                await connection.execute(
                    select(metrics_table).where(metrics_table.c.run_id == run_id)
                )
            ).mappings().all()
        run_data = dict(run_row)
        return Run(
            run_id=str(run_data["run_id"]),
            project=_optional_str(run_data, "project"),
            assay=_optional_str(run_data, "assay"),
            created_at=run_data["created_at"],
            samples=[_sample_from_row(dict(row)) for row in sample_rows],
            metrics=[_metric_from_row(dict(row)) for row in metric_rows],
        )

    async def list_metrics(self, run_id: str) -> list[Metric]:
        await self.ensure_schema()
        async with self._get_engine().connect() as connection:
            metric_rows = (
                await connection.execute(
                    select(metrics_table).where(metrics_table.c.run_id == run_id)
                )
            ).mappings().all()
        return [_metric_from_row(dict(row)) for row in metric_rows]


def _sample_from_row(row: Mapping[str, Any]) -> Sample:
    metadata_value = row["metadata"]
    metadata_dict = metadata_value if isinstance(metadata_value, dict) else {}
    return Sample(sample_id=str(row["sample_id"]), metadata=metadata_dict)


def _metric_from_row(row: Mapping[str, Any]) -> Metric:
    return Metric(
        sample_id=_optional_str(row, "sample_id"),
        name=str(row["name"]),
        value=row["value"],
        unit=_optional_str(row, "unit"),
    )


def _optional_str(row: Mapping[str, Any], key: str) -> str | None:
    value = row[key]
    return value if isinstance(value, str) else None
