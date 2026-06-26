# Public profile helpers intentionally hide provider layout so users can import
# profile contracts without knowing which source module owns each definition.
from goodomics.profiles.base import (
    PROFILE_NAMESPACE_PREFIXES,
    DataProfileProvider,
    profile,
)
from goodomics.profiles.registry import (
    all_built_in_data_profiles,
    built_in_data_profile,
)

__all__ = [
    "DataProfileProvider",
    "PROFILE_NAMESPACE_PREFIXES",
    "all_built_in_data_profiles",
    "built_in_data_profile",
    "profile",
]
