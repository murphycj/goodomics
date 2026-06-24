from __future__ import annotations

from copy import deepcopy
from typing import Any

from uvicorn.config import LOGGING_CONFIG


def build_uvicorn_log_config(log_level: str) -> dict[str, Any]:
    """Return Uvicorn logging config that also emits Goodomics app logs.

    Uvicorn's `log_level` option adjusts Uvicorn's own loggers, but it does not
    explicitly configure `goodomics.*`. Adding the package logger here makes
    `goodomics serve --log-level debug` include debug logs from AI and MCP code.
    """

    normalized_level = log_level.upper()
    config = deepcopy(LOGGING_CONFIG)
    loggers = config.setdefault("loggers", {})
    loggers["goodomics"] = {
        "handlers": ["default"],
        "level": normalized_level,
        "propagate": False,
    }
    return config
