"""Typed server configuration with TOML, environment, and CLI precedence."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from goodomics.storage.database import DEFAULT_DATABASE_URL


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    dashboard_dev_url: str | None = None
    trusted_proxies: list[str] = Field(default_factory=list)


class DatabaseSettings(BaseModel):
    url: str = DEFAULT_DATABASE_URL


class AnalyticsSettings(BaseModel):
    path: str | None = None
    root: str = ".goodomics"


class PasswordSettings(BaseModel):
    min_length: int = Field(default=6, ge=1)
    max_length: int | None = Field(default=None, ge=1)
    require_uppercase: bool = False
    require_lowercase: bool = False
    require_number: bool = False
    require_symbol: bool = False

    @model_validator(mode="after")
    def validate_length_range(self) -> PasswordSettings:
        """Require the maximum password length to allow the configured minimum."""

        if self.max_length is not None and self.max_length < self.min_length:
            raise ValueError("password max_length must be at least min_length")
        return self


class AuthSettings(BaseModel):
    enabled: bool = False
    signup_enabled: bool = False
    secret: str | None = None
    secret_file: str | None = None
    issuer: str = "goodomics"
    audience: str = "goodomics-api"
    token_minutes: int = Field(default=60, ge=1, le=1440)
    password: PasswordSettings = Field(default_factory=PasswordSettings)

    @model_validator(mode="after")
    def require_secret_when_enabled(self) -> AuthSettings:
        """Load a file-backed secret and require a secret when auth is enabled."""

        if self.secret_file and not self.secret:
            path = Path(self.secret_file)
            if path.is_file():
                self.secret = path.read_text(encoding="utf-8").strip()
        if self.enabled and not self.secret:
            raise ValueError(
                "GOODOMICS_AUTH_SECRET is required when authentication is enabled"
            )
        return self


class AnonymousSettings(BaseModel):
    permissions: list[str] = Field(
        default_factory=lambda: [
            "project.read",
            "data.read",
            "database.read",
            "files.read",
            "insight.read",
            "insight.execute",
            "report.read",
            "report.execute",
            "sample_group.read",
            "qc_policy.read",
            "ai.chat",
        ]
    )


class AISettings(BaseModel):
    provider: str = "openai-compatible"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    max_tool_rounds: int = Field(default=4, ge=1, le=20)


class RateLimitSettings(BaseModel):
    backend_uri: str = "memory://"
    login: list[str] = Field(default_factory=lambda: ["5/minute"])
    ai: list[str] = Field(default_factory=lambda: ["5/minute", "50/day"])
    ai_concurrent: int = Field(default=2, ge=1)
    ai_installation: list[str] = Field(default_factory=lambda: ["100/minute"])


class StorageLocationSettings(BaseModel):
    driver: Literal["filesystem", "s3"] = "filesystem"
    root: str | None = None
    bucket: str | None = None
    prefix: str = ""
    endpoint_url: str | None = None
    region: str | None = None

    @model_validator(mode="after")
    def validate_driver_options(self) -> StorageLocationSettings:
        """Require the location fields needed by the selected storage driver."""

        if self.driver == "filesystem" and not self.root:
            raise ValueError("filesystem storage locations require root")
        if self.driver == "s3" and not self.bucket:
            raise ValueError("S3 storage locations require bucket")
        return self


class StorageSettings(BaseModel):
    default_location: str = "default"
    locations: dict[str, StorageLocationSettings] = Field(
        default_factory=lambda: {
            "default": StorageLocationSettings(
                driver="filesystem", root=".goodomics/files"
            )
        }
    )

    @model_validator(mode="after")
    def validate_default_location(self) -> StorageSettings:
        """Require the default storage location to reference a named location."""

        if self.default_location not in self.locations:
            raise ValueError(
                f"Unknown default storage location: {self.default_location}"
            )
        return self


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    anonymous: AnonymousSettings = Field(default_factory=AnonymousSettings)
    ai: AISettings = Field(default_factory=AISettings)
    rate_limits: RateLimitSettings = Field(default_factory=RateLimitSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    config_path: Path | None = Field(default=None, exclude=True)

    # Compatibility properties keep the rest of the server concise while the
    # public configuration format is nested and typed.
    @property
    def database_url(self) -> str:
        """Return the configured database URL through the legacy flat interface."""

        return self.database.url

    @property
    def analytics_path(self) -> str | None:
        """Return the optional analytics database path."""

        return self.analytics.path

    @property
    def analytics_root(self) -> str:
        """Return the root directory used for project analytics databases."""

        return self.analytics.root

    @property
    def file_root(self) -> str:
        """Return the filesystem root for the default storage location."""

        location = self.storage.locations[self.storage.default_location]
        return location.root or ".goodomics/files"

    @property
    def dashboard_dev_url(self) -> str | None:
        """Return the optional dashboard development server URL."""

        return self.server.dashboard_dev_url

    @property
    def ai_provider(self) -> str:
        """Return the configured AI provider identifier."""

        return self.ai.provider

    @property
    def ai_api_key(self) -> str | None:
        """Return the configured AI API key, if one was supplied."""

        return self.ai.api_key

    @property
    def ai_base_url(self) -> str:
        """Return the base URL for the configured AI provider."""

        return self.ai.base_url

    @property
    def ai_model(self) -> str:
        """Return the configured AI model identifier."""

        return self.ai.model

    @property
    def ai_max_tool_rounds(self) -> int:
        """Return the maximum number of tool-call rounds allowed per AI request."""

        return self.ai.max_tool_rounds

    @ai_max_tool_rounds.setter
    def ai_max_tool_rounds(self, value: int) -> None:
        """Set the maximum number of tool-call rounds through the flat interface."""

        self.ai.max_tool_rounds = value


_ENV_PATHS: dict[str, tuple[str, ...]] = {
    "GOODOMICS_DATABASE_URL": ("database", "url"),
    "GOODOMICS_ANALYTICS_PATH": ("analytics", "path"),
    "GOODOMICS_ANALYTICS_ROOT": ("analytics", "root"),
    "GOODOMICS_FILE_ROOT": ("storage", "locations", "default", "root"),
    "GOODOMICS_DASHBOARD_DEV_URL": ("server", "dashboard_dev_url"),
    "GOODOMICS_AUTH_ENABLED": ("auth", "enabled"),
    "GOODOMICS_AUTH_SIGNUP_ENABLED": ("auth", "signup_enabled"),
    "GOODOMICS_AUTH_SECRET": ("auth", "secret"),
    "GOODOMICS_AUTH_SECRET_FILE": ("auth", "secret_file"),
    "GOODOMICS_AUTH_PASSWORD_MIN_LENGTH": ("auth", "password", "min_length"),
    "GOODOMICS_AUTH_PASSWORD_MAX_LENGTH": ("auth", "password", "max_length"),
    "GOODOMICS_AUTH_PASSWORD_REQUIRE_UPPERCASE": (
        "auth",
        "password",
        "require_uppercase",
    ),
    "GOODOMICS_AUTH_PASSWORD_REQUIRE_LOWERCASE": (
        "auth",
        "password",
        "require_lowercase",
    ),
    "GOODOMICS_AUTH_PASSWORD_REQUIRE_NUMBER": (
        "auth",
        "password",
        "require_number",
    ),
    "GOODOMICS_AUTH_PASSWORD_REQUIRE_SYMBOL": (
        "auth",
        "password",
        "require_symbol",
    ),
    "GOODOMICS_AI_PROVIDER": ("ai", "provider"),
    "GOODOMICS_AI_API_KEY": ("ai", "api_key"),
    "GOODOMICS_AI_BASE_URL": ("ai", "base_url"),
    "GOODOMICS_AI_MODEL": ("ai", "model"),
    "GOODOMICS_AI_MAX_TOOL_ROUNDS": ("ai", "max_tool_rounds"),
    "GOODOMICS_RATE_LIMIT_BACKEND_URI": ("rate_limits", "backend_uri"),
}


def ensure_config_file(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[Path, bool]:
    """Create a default first-run configuration without replacing existing files.

    The destination follows the same explicit path, ``GOODOMICS_CONFIG``, then
    ``./goodomics.toml`` selection order used by :func:`load_settings`.
    """

    environment = os.environ if environ is None else environ
    selected = _requested_config_path(config_path, environment)
    if selected.exists():
        if not selected.is_file():
            raise ValueError(f"Goodomics configuration path is not a file: {selected}")
        return selected, False
    default_config = (
        files("goodomics.server")
        .joinpath("goodomics.example.toml")
        .read_text(encoding="utf-8")
    )
    selected.parent.mkdir(parents=True, exist_ok=True)
    try:
        with selected.open("x", encoding="utf-8") as handle:
            handle.write(default_config)
    except FileExistsError:
        if not selected.is_file():
            raise ValueError(
                f"Goodomics configuration path is not a file: {selected}"
            ) from None
        return selected, False
    return selected, True


def load_settings(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> Settings:
    """Load settings using CLI > environment > TOML > defaults precedence."""

    environment = os.environ if environ is None else environ
    selected = _select_config_path(config_path, environment)
    values: dict[str, Any] = {}

    if selected is not None and selected.is_file():
        with selected.open("rb") as handle:
            values = tomllib.load(handle)
        _resolve_config_paths(values, selected.parent)

    for variable, path in _ENV_PATHS.items():
        if variable in environment:
            _set_nested(values, path, _parse_env_value(environment[variable]))

    for variable, raw in environment.items():
        if not variable.startswith("GOODOMICS_") or "__" not in variable:
            continue
        path = tuple(part.lower() for part in variable[11:].split("__"))
        _set_nested(values, path, _parse_env_value(raw))

    if cli_overrides:
        _deep_merge(values, dict(cli_overrides))

    values["config_path"] = selected

    return Settings.model_validate(values)


def _select_config_path(
    explicit: str | Path | None, environment: Mapping[str, str]
) -> Path | None:
    """Select an existing config file or return ``None`` when none is requested."""

    raw = explicit or environment.get("GOODOMICS_CONFIG")
    if raw:
        path = _requested_config_path(explicit, environment)
        if not path.is_file():
            raise ValueError(f"Goodomics configuration file not found: {path}")
        return path
    default = Path("goodomics.toml")
    return default.resolve() if default.is_file() else None


def _requested_config_path(
    explicit: str | Path | None, environment: Mapping[str, str]
) -> Path:
    """Resolve the requested or default config destination to an absolute path."""

    raw = explicit or environment.get("GOODOMICS_CONFIG") or "goodomics.toml"
    return Path(raw).expanduser().resolve()


def _resolve_config_paths(values: dict[str, Any], base: Path) -> None:
    """Resolve relative paths in parsed configuration against its directory."""

    _resolve_database_config_url(values, base)
    for path in (
        ("analytics", "path"),
        ("analytics", "root"),
        ("auth", "secret_file"),
    ):
        _resolve_nested_path(values, path, base)
    locations = values.get("storage", {}).get("locations", {})
    if isinstance(locations, dict):
        for location in locations.values():
            if (
                isinstance(location, dict)
                and location.get("driver", "filesystem") == "filesystem"
            ):
                root = location.get("root")
                if isinstance(root, str) and not Path(root).expanduser().is_absolute():
                    location["root"] = str((base / root).resolve())


def _resolve_database_config_url(values: dict[str, Any], base: Path) -> None:
    """Resolve a relative SQLite database URL against the config directory."""

    database = values.get("database")
    if not isinstance(database, dict):
        return
    url = database.get("url")
    prefix = "sqlite+aiosqlite:///"
    if not isinstance(url, str) or not url.startswith(prefix):
        return
    raw_path = url.removeprefix(prefix)
    if raw_path == ":memory:":
        return
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        database["url"] = f"{prefix}{(base / path).resolve()}"


def _resolve_nested_path(
    values: dict[str, Any], path: tuple[str, ...], base: Path
) -> None:
    """Resolve one nested filesystem path against the config directory in place."""

    current: Any = values
    for part in path[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if not isinstance(current, dict):
        return
    raw = current.get(path[-1])
    if not isinstance(raw, str) or not raw or "://" in raw:
        return
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        current[path[-1]] = str((base / candidate).resolve())


def _parse_env_value(raw: str) -> Any:
    """Coerce an environment string into a boolean, integer, list, or string."""

    lowered = raw.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if raw.strip().isdigit():
        return int(raw.strip())
    if "," in raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def _set_nested(values: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    """Assign a value at a nested mapping path, creating mappings as needed."""

    current = values
    for part in path[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[path[-1]] = value


def _deep_merge(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge non-null incoming values recursively into the target mapping."""

    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        elif value is not None:
            target[key] = value
