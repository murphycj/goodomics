from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fixtures import write_multiqc_fixture
from goodomics.contracts import (
    all_built_in_data_contracts,
    contract,
    tool_metrics_contract,
)
from goodomics.contracts.cbioportal import contract_for_meta
from goodomics.custom_parser import ParserOutput, parser
from goodomics.ingest.multiqc import ingest_multiqc
from goodomics.sources import SourceSpec, get_source, list_sources, register_source
from goodomics.sources import registry as source_registry
from goodomics.storage.duckdb import DuckDBAnalyticsStore
from goodomics.storage.sqlalchemy import (
    DataContractFieldRecord,
    DataContractRecord,
    RunRecord,
    SQLModelGoodomicsStore,
)
from sqlmodel import select


def _scalar(row: tuple[Any, ...] | None) -> Any:
    assert row is not None
    return row[0]


def _run_pk(database_url: str, run_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with catalog_store.session() as session:
            row = (
                await session.exec(select(RunRecord).where(RunRecord.run_id == run_id))
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def _data_contract_pk(database_url: str, data_contract_id: str) -> int:
    async def load() -> int:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with catalog_store.session() as session:
            row = (
                await session.exec(
                    select(DataContractRecord).where(
                        DataContractRecord.data_contract_id == data_contract_id
                    )
                )
            ).one()
        assert row.id is not None
        return row.id

    return asyncio.run(load())


def test_built_in_sources_list_without_importing_ingestor_modules() -> None:
    # Listing sources should stay cheap; concrete ingestors are selected lazily.
    sys.modules.pop("goodomics.ingest.multiqc", None)
    sys.modules.pop("goodomics.ingest.cbioportal", None)

    keys = {source.key for source in list_sources()}

    assert {"multiqc", "cbioportal"} <= keys
    assert "goodomics.ingest.multiqc" not in sys.modules
    assert "goodomics.ingest.cbioportal" not in sys.modules


def test_get_source_reports_unknown_keys() -> None:
    with pytest.raises(ValueError, match="Unknown ingest type 'missing'"):
        get_source("missing")


def test_duplicate_source_keys_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(source_registry, "_IN_PROCESS_SOURCES", {})
    register_source(SourceSpec(key="dupe", label="First", ingest=lambda path: path))

    with pytest.raises(ValueError, match="Source key is already registered: dupe"):
        register_source(
            SourceSpec(key="dupe", label="Second", ingest=lambda path: path)
        )


def test_fake_entry_point_source_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate package discovery without installing an actual test package.
    @dataclass(frozen=True)
    class FakeEntryPoint:
        name: str

        def load(self) -> SourceSpec:
            return SourceSpec(
                key="external-demo",
                label="External demo",
                ingest=lambda path: path,
            )

    class FakeEntryPoints(list[FakeEntryPoint]):
        def select(self, *, group: str) -> list[FakeEntryPoint]:
            return list(self) if group == source_registry.ENTRY_POINT_GROUP else []

    monkeypatch.setattr(
        source_registry.metadata,
        "entry_points",
        lambda: FakeEntryPoints([FakeEntryPoint("external-demo")]),
    )

    assert get_source("external-demo").label == "External demo"


def test_contract_providers_cover_built_in_contracts() -> None:
    built_ins = {item.data_contract_id for item in all_built_in_data_contracts()}

    assert "multiqc:payloads" in built_ins
    assert "goodomics:sdk_metrics" in built_ins
    assert tool_metrics_contract("salmon").data_contract_id == "salmon:results"
    assert (
        contract_for_meta(
            {
                "genetic_alteration_type": "MUTATION_EXTENDED",
                "datatype": "MAF",
            },
            source_meta_file="meta_mutations.txt",
        ).data_contract_id
        == "cbioportal:mutations:maf"
    )
    custom = contract_for_meta(
        {"stable_id": "weird_custom_contract", "datatype": "WEIRD"},
        source_meta_file="meta_custom.txt",
    )
    assert custom.data_contract_id == "cbioportal:custom:unknown:weird_custom_contract"


def test_run_ingest_routes_multiqc_through_source_registry(tmp_path: Path) -> None:
    from goodomics.ingest import run_ingest

    multiqc_dir = write_multiqc_fixture(tmp_path / "results")
    analytics_path = tmp_path / "state" / "analytics.duckdb"
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"

    result = run_ingest(
        multiqc_dir,
        ingest_type="multiqc",
        project="demo",
        analysis_type_id="rna_sequencing",
        run_id="registry-run",
        database_url=database_url,
        analytics_path=analytics_path,
        file_root=tmp_path / "state" / "files",
    )

    assert result.ingest_type == "multiqc"
    assert result.source.key == "multiqc"
    assert result.payload[0].run_id == "registry-run"
    assert DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_url, "registry-run:S1:analysis")
    )


def test_decorated_custom_parser_ingests_without_packaging(tmp_path: Path) -> None:
    # This mirrors the notebook use case: define one function and ingest from
    # the current Python process, with no package metadata.
    rnaseq_tpm = contract(
        "user:rnaseq:tpm",
        name="RNA-seq TPM values",
        data_type="feature_matrix",
        producer_tool="notebook-parser",
        feature_type="gene",
        value_type="numeric",
        query_modes=["sample", "feature", "cohort"],
    )

    @parser(key="notebook-parser", label="Notebook parser", contracts=[rnaseq_tpm])
    def parse_table(path: object, out: ParserOutput) -> None:
        assert isinstance(path, Path)
        out.metric("rows", 2, sample_id="S1")
        out.feature_value(
            sample_id="S1",
            feature_id="TP53",
            value=42,
            contract=rnaseq_tpm,
        )

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'state' / 'goodomics.db'}"
    analytics_path = tmp_path / "state" / "analytics.duckdb"

    result = parse_table.ingest(
        tmp_path / "input.csv",
        project="demo",
        analysis_type_id="rna_sequencing",
        run_id="custom-run",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.run_id == "custom-run"
    assert result.samples_ingested == 1
    assert result.contracts_ingested == 2
    analytics = DuckDBAnalyticsStore(analytics_path)
    assert analytics.list_metric_values(_run_pk(database_url, "custom-run"))
    assert analytics.row_counts()["feature_value_numeric"] == 1


def test_custom_parser_reuses_tool_contract_id(tmp_path: Path) -> None:
    @parser(key="tool-contract-parser", contracts=["salmon:results"])
    def parse_metrics(path: object, out: ParserOutput) -> None:
        out.metric("pct_mapped", 99.0, sample_id="S1", contract="salmon:results")

    analytics_path = tmp_path / "analytics.duckdb"
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'goodomics.db'}"
    result = parse_metrics.ingest(
        tmp_path / "metrics.tsv",
        run_id="builtin-contract-run",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    assert result.contracts_ingested == 1
    values = DuckDBAnalyticsStore(analytics_path).list_metric_values(
        _run_pk(database_url, "builtin-contract-run")
    )
    metrics_contract_id = _data_contract_pk(database_url, "salmon:results")
    assert values[0].data_contract_id == metrics_contract_id


def test_tool_contract_reuse_preserves_existing_fields(tmp_path: Path) -> None:
    salmon_metrics = tool_metrics_contract("salmon")
    analytics_path = tmp_path / "analytics.duckdb"
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'goodomics.db'}"
    ingest_multiqc(
        write_multiqc_fixture(tmp_path / "results"),
        run_id="multiqc-run",
        project="demo",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    @parser(key="salmon-direct-parser", contracts=[salmon_metrics])
    def parse_salmon(path: object, out: ParserOutput) -> None:
        out.metric(
            "direct_percent_mapped", 98.0, sample_id="S1", contract=salmon_metrics
        )

    parse_salmon.ingest(
        tmp_path / "salmon.tsv",
        project="demo",
        run_id="direct-run",
        database_url=database_url,
        analytics_path=analytics_path,
    )

    async def load_salmon_fields() -> set[str]:
        catalog_store = SQLModelGoodomicsStore(database_url)
        async with catalog_store.session() as session:
            contract = (
                await session.exec(
                    select(DataContractRecord).where(
                        DataContractRecord.data_contract_id == "salmon:results"
                    )
                )
            ).one()
            assert contract.id is not None
            rows = (
                await session.exec(
                    select(DataContractFieldRecord).where(
                        DataContractFieldRecord.data_contract_id == contract.id
                    )
                )
            ).all()
        return {row.field_id for row in rows}

    fields = asyncio.run(load_salmon_fields())
    assert "general_stats.salmon_percent_mapped" in fields
    assert "salmon:results:direct_percent_mapped" in fields
