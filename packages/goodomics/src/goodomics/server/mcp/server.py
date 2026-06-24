from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from goodomics.server.query_tools import GoodomicsQueryTools, QueryToolContext


def create_mcp_server(context: QueryToolContext) -> FastMCP:
    tools = GoodomicsQueryTools(context)
    mcp = FastMCP(
        "Goodomics",
        instructions=(
            "Read-only tools for querying Goodomics projects, runs, samples, "
            "files, and metrics. Tools return structured evidence for user-reviewed "
            "summaries and should not make scientific decisions."
        ),
        streamable_http_path="/",
        json_response=True,
    )

    @mcp.tool()
    async def list_projects(query: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List Goodomics projects, optionally filtered by name, slug, or ID."""
        return await tools.list_projects(query=query, limit=limit)

    @mcp.tool()
    async def resolve_project(reference: str, limit: int = 5) -> dict[str, Any]:
        """Resolve a human-readable project reference to candidates or one match."""
        return await tools.resolve_project(reference=reference, limit=limit)

    @mcp.tool()
    async def get_project_summary(project: str) -> dict[str, Any]:
        """Summarize a project by ID, slug, name, or fuzzy human reference."""
        return await tools.get_project_summary(project=project)

    @mcp.tool()
    async def list_recent_runs(
        project: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """List the most recent runs globally or within a project."""
        return await tools.list_recent_runs(project=project, limit=limit)

    @mcp.tool()
    async def list_project_runs(
        project: str,
        status: str | None = None,
        assay: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List runs for a project, optionally filtered by status or assay."""
        return await tools.list_project_runs(
            project=project,
            status=status,
            assay=assay,
            limit=limit,
        )

    @mcp.tool()
    async def list_project_samples(
        project: str,
        query: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List samples for a project, optionally filtered by sample text."""
        return await tools.list_project_samples(project=project, query=query, limit=limit)

    @mcp.tool()
    async def get_run(run_id: str, project: str | None = None) -> dict[str, Any]:
        """Fetch a run summary by run ID, optionally constrained to a project."""
        return await tools.get_run(run_id=run_id, project=project)

    @mcp.tool()
    async def list_run_samples(
        run_id: str, project: str | None = None
    ) -> dict[str, Any]:
        """List samples attached to a run."""
        return await tools.list_run_samples(run_id=run_id, project=project)

    @mcp.tool()
    async def list_run_metrics(
        run_id: str,
        project: str | None = None,
        metric_query: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """List scalar and analytics metrics for a run."""
        return await tools.list_run_metrics(
            run_id=run_id,
            project=project,
            metric_query=metric_query,
            limit=limit,
        )

    @mcp.tool()
    async def list_run_files(
        run_id: str,
        project: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List files attached to a run."""
        return await tools.list_run_files(
            run_id=run_id,
            project=project,
            kind=kind,
            limit=limit,
        )

    @mcp.resource("goodomics://runs/{run_id}")
    async def run_resource(run_id: str) -> dict[str, Any]:
        """Fetch a run by ID as an MCP resource."""
        return await tools.get_run(run_id=run_id)

    return mcp
