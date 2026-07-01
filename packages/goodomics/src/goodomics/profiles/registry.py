from __future__ import annotations

from goodomics.profiles import cbioportal, multiqc, sdk
from goodomics.schemas.models import DataProfile


def built_in_profiles() -> dict[str, DataProfile]:
    # Aggregate source-owned providers into the central discovery surface used
    # by MCP/query tooling, custom parser reuse, and public profile helpers.
    profiles: dict[str, DataProfile] = {}
    for provider in (cbioportal, multiqc, sdk):
        for data_profile in provider.profiles():
            profiles[data_profile.data_profile_id] = data_profile
    return profiles


def built_in_data_profile(data_profile_id: str) -> DataProfile:
    return built_in_profiles()[data_profile_id]


def all_built_in_data_profiles() -> list[DataProfile]:
    return sorted(
        built_in_profiles().values(), key=lambda profile: profile.data_profile_id
    )
