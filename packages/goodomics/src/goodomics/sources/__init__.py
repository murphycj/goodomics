# Registry exports are the advanced/plugin-facing source API. The notebook path
# normally goes through goodomics.parser instead.
from goodomics.sources.registry import (
    CallableRef,
    SourceSpec,
    get_source,
    list_sources,
    normalize_source_key,
    register_source,
)

__all__ = [
    "CallableRef",
    "SourceSpec",
    "get_source",
    "list_sources",
    "normalize_source_key",
    "register_source",
]
