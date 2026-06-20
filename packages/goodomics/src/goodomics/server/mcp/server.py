from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Goodomics", json_response=True)


@mcp.tool()
def summarize_run(run_id: str) -> dict[str, str]:
    """Summarize QC status for a Goodomics run."""
    return {
        "run_id": run_id,
        "status": "unknown",
        "summary": "Run summary is not implemented yet.",
    }


@mcp.resource("goodomics://runs/{run_id}")
def get_run(run_id: str) -> dict[str, str]:
    """Fetch a run by ID."""
    return {
        "run_id": run_id,
        "status": "unknown",
    }
