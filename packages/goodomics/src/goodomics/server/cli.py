from __future__ import annotations

import typer
import uvicorn

from goodomics.server.logging import build_uvicorn_log_config

app = typer.Typer(help="Goodomics server commands.")


@app.callback()
def main() -> None:
    """Goodomics server commands."""


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    log_level: str = typer.Option(
        "info",
        "--log-level",
        help="Uvicorn log level: critical, error, warning, info, debug, or trace.",
    ),
) -> None:
    """Run the Goodomics API, MCP server, AI chat, and dashboard."""
    uvicorn.run(
        "goodomics.server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        log_config=build_uvicorn_log_config(log_level),
        factory=True,
    )


if __name__ == "__main__":
    app()
