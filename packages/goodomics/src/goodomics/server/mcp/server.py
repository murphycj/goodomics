from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any

from mcp.server.fastmcp import FastMCP

from goodomics.server.query_tools import GoodomicsQueryTools, QueryToolContext

logger = logging.getLogger(__name__)


def create_mcp_server(context: QueryToolContext) -> FastMCP:
    """Create the read-only Goodomics MCP server for the FastAPI app.

    The MCP server and REST/AI chat surfaces share `GoodomicsQueryTools`, so all
    project resolution and query behavior stays consistent across entry points.
    `streamable_http_path="/"` is intentional because the parent FastAPI app
    mounts this ASGI app at `/mcp`.
    """

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
    logger.debug("Created Goodomics MCP server mounted at streamable_http_path=/")

    @mcp.tool()
    async def list_projects(
        query: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        """List Goodomics projects, optionally filtered by name, slug, or ID."""
        return await _logged_tool_call(
            "list_projects",
            {"query": query, "limit": limit},
            tools.list_projects(query=query, limit=limit),
        )

    @mcp.tool()
    async def list_data_contracts(
        project: str | None = None,
        query: str | None = None,
        limit: int = 20,
        field_limit: int = 25,
    ) -> dict[str, Any]:
        """List semantic data contracts and their queryable fields."""
        return await _logged_tool_call(
            "list_data_contracts",
            {
                "project": project,
                "query": query,
                "limit": limit,
                "field_limit": field_limit,
            },
            tools.list_data_contracts(
                project=project,
                query=query,
                limit=limit,
                field_limit=field_limit,
            ),
        )

    @mcp.tool()
    async def search_datasets(
        project: str,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search the project semantic runtime catalog."""

        return await _logged_tool_call(
            "search_datasets",
            {"project": project, "query": query, "limit": limit, "offset": offset},
            tools.search_datasets(
                project=project, query=query, limit=limit, offset=offset
            ),
        )

    @mcp.tool()
    async def describe_dataset(project: str, data_contract_id: str) -> dict[str, Any]:
        """Describe a semantic dataset, fields, joins, and capabilities."""

        return await _logged_tool_call(
            "describe_dataset",
            {"project": project, "data_contract_id": data_contract_id},
            tools.describe_dataset(project=project, data_contract_id=data_contract_id),
        )

    @mcp.tool()
    async def search_fields(
        project: str,
        query: str | None = None,
        query_kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search canonical fields by typed-query compatibility."""

        return await _logged_tool_call(
            "search_fields",
            {
                "project": project,
                "query": query,
                "query_kind": query_kind,
                "limit": limit,
                "offset": offset,
            },
            tools.search_fields(
                project=project,
                query=query,
                query_kind=query_kind,
                limit=limit,
                offset=offset,
            ),
        )

    @mcp.tool()
    async def find_dataset_joins(
        project: str, data_contract_id: str | None = None
    ) -> dict[str, Any]:
        """Find project-visible joins by logical identity."""

        return await _logged_tool_call(
            "find_dataset_joins",
            {"project": project, "data_contract_id": data_contract_id},
            tools.find_dataset_joins(
                project=project, data_contract_id=data_contract_id
            ),
        )

    @mcp.tool()
    async def list_field_values(
        project: str, field: str, limit: int = 20
    ) -> dict[str, Any]:
        """List bounded observed categorical values for a canonical field."""

        return await _logged_tool_call(
            "list_field_values",
            {"project": project, "field": field, "limit": limit},
            tools.list_field_values(project=project, field=field, limit=limit),
        )

    @mcp.tool()
    async def read_field_profile(project: str, field: str) -> dict[str, Any]:
        """Read an optional disposable profile for one canonical field."""

        return await _logged_tool_call(
            "read_field_profile",
            {"project": project, "field": field},
            tools.read_field_profile(project=project, field=field),
        )

    @mcp.tool()
    async def list_query_families(project: str) -> dict[str, Any]:
        """List valid query families, views, and provider requirements."""

        return await _logged_tool_call(
            "list_query_families",
            {"project": project},
            tools.list_query_families(project=project),
        )

    @mcp.tool()
    async def validate_insight_draft(
        project: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate and explain a complete shared version 2 insight draft."""

        return await _logged_tool_call(
            "validate_insight_draft",
            {"project": project, "definition": definition},
            tools.validate_insight_draft(project=project, definition=definition),
        )

    @mcp.tool()
    async def preview_insight_draft(
        project: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a bounded preview without saving the insight draft."""

        return await _logged_tool_call(
            "preview_insight_draft",
            {"project": project, "definition": definition},
            tools.preview_insight_draft(project=project, definition=definition),
        )

    @mcp.tool()
    async def resolve_project(reference: str, limit: int = 5) -> dict[str, Any]:
        """Resolve a human-readable project reference to candidates or one match."""
        return await _logged_tool_call(
            "resolve_project",
            {"reference": reference, "limit": limit},
            tools.resolve_project(reference=reference, limit=limit),
        )

    @mcp.tool()
    async def get_project_summary(project: str) -> dict[str, Any]:
        """Summarize a project by ID, slug, name, or fuzzy human reference."""
        return await _logged_tool_call(
            "get_project_summary",
            {"project": project},
            tools.get_project_summary(project=project),
        )

    @mcp.tool()
    async def list_recent_runs(
        project: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """List the most recent runs globally or within a project."""
        return await _logged_tool_call(
            "list_recent_runs",
            {"project": project, "limit": limit},
            tools.list_recent_runs(project=project, limit=limit),
        )

    @mcp.tool()
    async def list_project_runs(
        project: str,
        status: str | None = None,
        analysis_type_id: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List runs filtered by status or controlled analysis type."""
        return await _logged_tool_call(
            "list_project_runs",
            {
                "project": project,
                "status": status,
                "analysis_type_id": analysis_type_id,
                "limit": limit,
            },
            tools.list_project_runs(
                project=project,
                status=status,
                analysis_type_id=analysis_type_id,
                limit=limit,
            ),
        )

    @mcp.tool()
    async def list_project_samples(
        project: str,
        query: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List samples for a project, optionally filtered by sample text."""
        return await _logged_tool_call(
            "list_project_samples",
            {"project": project, "query": query, "limit": limit},
            tools.list_project_samples(project=project, query=query, limit=limit),
        )

    @mcp.tool()
    async def get_run(run_id: str, project: str | None = None) -> dict[str, Any]:
        """Fetch a run summary by run ID, optionally constrained to a project."""
        return await _logged_tool_call(
            "get_run",
            {"run_id": run_id, "project": project},
            tools.get_run(run_id=run_id, project=project),
        )

    @mcp.tool()
    async def list_run_samples(
        run_id: str, project: str | None = None
    ) -> dict[str, Any]:
        """List samples attached to a run."""
        return await _logged_tool_call(
            "list_run_samples",
            {"run_id": run_id, "project": project},
            tools.list_run_samples(run_id=run_id, project=project),
        )

    @mcp.tool()
    async def list_run_metrics(
        run_id: str,
        project: str | None = None,
        metric_query: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """List analytics metrics for a run."""
        return await _logged_tool_call(
            "list_run_metrics",
            {
                "run_id": run_id,
                "project": project,
                "metric_query": metric_query,
                "limit": limit,
            },
            tools.list_run_metrics(
                run_id=run_id,
                project=project,
                metric_query=metric_query,
                limit=limit,
            ),
        )

    @mcp.tool()
    async def list_run_files(
        run_id: str,
        project: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List files attached to a run."""
        return await _logged_tool_call(
            "list_run_files",
            {
                "run_id": run_id,
                "project": project,
                "kind": kind,
                "limit": limit,
            },
            tools.list_run_files(
                run_id=run_id,
                project=project,
                kind=kind,
                limit=limit,
            ),
        )

    @mcp.resource("goodomics://runs/{run_id}")
    async def run_resource(run_id: str) -> dict[str, Any]:
        """Fetch a run by ID as an MCP resource."""
        return await _logged_tool_call(
            "resource:run",
            {"run_id": run_id},
            tools.get_run(run_id=run_id),
        )

    return mcp


async def _logged_tool_call(
    name: str,
    arguments: dict[str, Any],
    call: Awaitable[dict[str, Any]],
) -> dict[str, Any]:
    """Log MCP tool execution without dumping large result payloads."""

    logger.debug(
        "MCP tool started: name=%s arguments=%s", name, _debug_arguments(arguments)
    )
    try:
        result = await call
    except Exception:
        logger.exception(
            "MCP tool failed: name=%s arguments=%s",
            name,
            _debug_arguments(arguments),
        )
        raise
    logger.debug(
        "MCP tool completed: name=%s result=%s", name, _debug_result_summary(result)
    )
    return result


def _debug_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: _truncate_debug_value(value) for key, value in arguments.items()}


def _truncate_debug_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 120 else f"{value[:117]}..."
    return value


def _debug_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, list):
            summary[key] = f"list[{len(value)}]"
        elif isinstance(value, dict):
            summary[key] = f"dict[{len(value)}]"
        else:
            summary[key] = _truncate_debug_value(value)
    return summary
