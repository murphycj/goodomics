from __future__ import annotations

import typer
import uvicorn

app = typer.Typer(help="Goodomics server commands.")


@app.callback()
def main() -> None:
    """Goodomics server commands."""


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the Goodomics API server."""
    uvicorn.run(
        "goodomics_server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


if __name__ == "__main__":
    app()
