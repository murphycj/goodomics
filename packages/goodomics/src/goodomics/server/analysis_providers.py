"""Explicit provider boundary for scientific or inferential analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from goodomics.schemas.insights import ProviderRequirement, QueryNode, SurvivalQuery


@dataclass(frozen=True)
class AnalysisProviderResult:
    """Provenance-bearing typed result returned by an external provider."""

    records: list[dict[str, Any]]
    method: str
    version: str
    parameters: dict[str, Any]
    input_contracts: list[str]
    resolved_run_contract_ids: list[str]
    output_contract_id: str | None


class AnalysisProvider(Protocol):
    """Registered provider for model-dependent scientific computations."""

    @property
    def provider_id(self) -> str:
        """Return the provider's stable registered ID."""

        raise NotImplementedError

    def supports(self, method: str) -> bool:
        """Return whether the provider implements an explicit method."""

        raise NotImplementedError

    async def execute(
        self,
        *,
        query: QueryNode,
        inputs: list[dict[str, Any]],
        provenance: dict[str, Any],
    ) -> AnalysisProviderResult:
        """Execute a pinned, provenance-bearing scientific analysis."""

        raise NotImplementedError


class AnalysisProviderRegistry:
    """Process-local registry of explicitly installed analysis providers."""

    def __init__(self) -> None:
        """Create an empty provider registry."""

        self._providers: dict[str, AnalysisProvider] = {}

    def register(self, provider: AnalysisProvider) -> None:
        """Register one provider under a unique stable ID."""

        if provider.provider_id in self._providers:
            raise ValueError(
                f"Analysis provider already registered: {provider.provider_id}"
            )
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> AnalysisProvider | None:
        """Return a provider by ID when installed."""

        return self._providers.get(provider_id)

    def compatible(self, method: str) -> tuple[str, ...]:
        """Return provider IDs supporting a named method."""

        return tuple(
            sorted(
                provider_id
                for provider_id, provider in self._providers.items()
                if provider.supports(method)
            )
        )


ANALYSIS_PROVIDERS = AnalysisProviderRegistry()


def provider_requirement(query: QueryNode) -> ProviderRequirement | None:
    """Describe the external capability required by a typed query."""

    if not isinstance(query, SurvivalQuery):
        return None
    compatible = ANALYSIS_PROVIDERS.compatible(query.provider.method)
    requested = query.provider.provider_id
    available = requested in compatible if requested is not None else bool(compatible)
    selected = requested or (compatible[0] if compatible else None)
    return ProviderRequirement(
        required=True,
        method=query.provider.method,
        provider_id=selected,
        available=available,
        message=(
            None
            if available
            else (
                "A registered analysis provider for "
                f"{query.provider.method!r} is required."
            )
        ),
    )
