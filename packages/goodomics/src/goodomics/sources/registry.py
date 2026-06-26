from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from goodomics.schemas.models import DataProfile

ENTRY_POINT_GROUP = "goodomics.sources"


@dataclass(frozen=True)
class CallableRef:
    """A callable that can be imported only when it is needed."""

    dotted_path: str

    def load(self) -> Callable[..., Any]:
        module_name, _, attribute = self.dotted_path.partition(":")
        if not module_name or not attribute:
            raise ValueError(
                f"CallableRef must use 'module:attribute' syntax: {self.dotted_path}"
            )
        module = importlib.import_module(module_name)
        value = getattr(module, attribute)
        if not callable(value):
            raise TypeError(f"Referenced object is not callable: {self.dotted_path}")
        return value


CallableLike = Callable[..., Any] | CallableRef | str


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    ingest: CallableLike
    parser: CallableLike | None = None
    detector: CallableLike | None = None
    data_profile_provider: CallableLike | Iterable[DataProfile] | None = None
    result_printer: CallableLike | None = None
    # SourceSpec filters kwargs before dispatch so registry routing can support
    # built-ins, notebook parsers, and third-party plugins with one call path.
    ingest_parameters: tuple[str, ...] = ()
    run_id_parameter: str = "run_id"

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", normalize_source_key(self.key))

    def load_ingest(self) -> Callable[..., Any]:
        return _load_callable(self.ingest)

    def load_result_printer(self) -> Callable[..., Any] | None:
        if self.result_printer is None:
            return None
        return _load_callable(self.result_printer)

    def profiles(self) -> list[DataProfile]:
        provider = self.data_profile_provider
        if provider is None:
            return []
        if isinstance(provider, Iterable) and not isinstance(provider, str):
            return sorted(
                list(provider),
                key=lambda data_profile: data_profile.data_profile_id,
            )
        loaded = _load_callable(provider)
        value = loaded()
        if isinstance(value, dict):
            value = value.values()
        return sorted(list(value), key=lambda profile: profile.data_profile_id)


_IN_PROCESS_SOURCES: dict[str, SourceSpec] = {}


def normalize_source_key(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    normalized = "-".join(part for part in normalized.split("-") if part)
    if not normalized:
        raise ValueError("Source key cannot be blank")
    return normalized


def register_source(source: SourceSpec, *, replace: bool = False) -> SourceSpec:
    # In-process registration is what makes notebook-defined parsers usable
    # immediately without packaging them as entry points.
    key = normalize_source_key(source.key)
    existing = _IN_PROCESS_SOURCES.get(key)
    if existing is not None and not replace:
        raise ValueError(f"Source key is already registered: {key}")
    _IN_PROCESS_SOURCES[key] = source
    return source


def list_sources() -> list[SourceSpec]:
    sources = _sources_by_key()
    return [sources[key] for key in sorted(sources)]


def get_source(key: str) -> SourceSpec:
    normalized = normalize_source_key(key)
    sources = _sources_by_key()
    try:
        return sources[normalized]
    except KeyError as exc:
        available = ", ".join(sorted(sources)) or "none"
        raise ValueError(
            f"Unknown ingest type '{key}'. Available types: {available}"
        ) from exc


def _sources_by_key() -> dict[str, SourceSpec]:
    sources: dict[str, SourceSpec] = {}
    # Precedence is explicit: built-ins first, installed packages second, then
    # notebook/local overrides last when replace=True was used at registration.
    for source in _built_in_sources():
        _add_source(sources, source)
    for source in _entry_point_sources():
        _add_source(sources, source)
    for source in _IN_PROCESS_SOURCES.values():
        _add_source(sources, source)
    return sources


def _built_in_sources() -> list[SourceSpec]:
    from goodomics.sources.builtins import BUILT_IN_SOURCES

    return list(BUILT_IN_SOURCES)


def _entry_point_sources() -> list[SourceSpec]:
    # Entry points are the durable distribution path; notebook-defined parsers
    # live only in the current process and enter through register_source.
    entry_points = metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=ENTRY_POINT_GROUP)
    else:
        selected = entry_points.get(ENTRY_POINT_GROUP, [])

    sources: list[SourceSpec] = []
    for entry_point in selected:
        loaded = entry_point.load()
        source = (
            loaded()
            if callable(loaded) and not isinstance(loaded, SourceSpec)
            else loaded
        )
        if not isinstance(source, SourceSpec):
            raise TypeError(
                f"Entry point {entry_point.name} did not load a SourceSpec"
            )
        sources.append(source)
    return sources


def _add_source(sources: dict[str, SourceSpec], source: SourceSpec) -> None:
    key = normalize_source_key(source.key)
    if key in sources:
        raise ValueError(f"Duplicate source key registered: {key}")
    sources[key] = source


def _load_callable(value: CallableLike) -> Callable[..., Any]:
    if isinstance(value, CallableRef):
        return value.load()
    if isinstance(value, str):
        return CallableRef(value).load()
    if callable(value):
        return value
    raise TypeError(
        f"Expected callable or dotted reference, got {type(value).__name__}"
    )
