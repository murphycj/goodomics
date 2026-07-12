from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from goodomics.server.query_tools import GoodomicsQueryTools, QueryToolContext
from goodomics.server.settings import Settings

logger = logging.getLogger(__name__)


# Pydantic models here are API-facing payloads used by the dashboard chat route.
class ChatMessage(BaseModel):
    role: str
    content: str


class ToolEvidence(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class ChatResult(BaseModel):
    conversation_id: str | None = None
    message: ChatMessage
    tool_calls: list[ToolEvidence] = Field(default_factory=list)


@dataclass(frozen=True)
class ProviderToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    content: str = ""
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class AIProvider(Protocol):
    # Structural interface for model backends (OpenAI-compatible or future providers).
    def is_configured(self) -> bool: ...

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse: ...


class AIProviderNotConfigured(RuntimeError):
    # Raised when Ask AI is requested but provider credentials/config are missing.
    pass


class OpenAICompatibleProvider:
    """OpenAI-compatible chat/completions adapter.

    This keeps the rest of the server provider-neutral: the chat loop depends on
    `AIProvider`, while this adapter handles the current HTTP wire format.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.ai_api_key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ProviderResponse:
        if not self.settings.ai_api_key:
            logger.debug("AI provider requested but no API key is configured.")
            raise AIProviderNotConfigured("AI provider is not configured.")
        payload: dict[str, Any] = {
            "model": self.settings.ai_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.settings.ai_base_url.rstrip('/')}/chat/completions"
        logger.debug(
            "Calling AI provider: model=%s base_url=%s messages=%d tools=%d",
            self.settings.ai_model,
            self.settings.ai_base_url,
            len(messages),
            len(tools),
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]

        # Normalize provider-specific tool call payloads into a stable internal shape.
        tool_calls = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            arguments = function.get("arguments") or "{}"
            tool_calls.append(
                ProviderToolCall(
                    id=str(raw_call.get("id") or function.get("name") or "tool_call"),
                    name=str(function.get("name") or ""),
                    arguments=_parse_arguments(arguments),
                )
            )
        logger.debug(
            "AI provider response received: content_chars=%d tool_calls=%s",
            len(message.get("content") or ""),
            [call.name for call in tool_calls],
        )
        return ProviderResponse(
            content=message.get("content") or "", tool_calls=tool_calls
        )


class GoodomicsChatService:
    """Bounded, read-only AI chat loop for dashboard Ask AI.

    The model receives tool schemas and may request Goodomics query tools. The
    server executes those tools, appends structured evidence, and stops at the
    configured round limit so chat remains auditable and non-mutating.
    """

    def __init__(
        self,
        context: QueryToolContext,
        *,
        provider: AIProvider | None = None,
    ) -> None:
        self.context = context
        self.provider = provider or OpenAICompatibleProvider(context.settings)
        self.query_tools = GoodomicsQueryTools(context)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        project_id: str | None = None,
        conversation_id: str | None = None,
    ) -> ChatResult:
        if not self.provider.is_configured():
            logger.debug("Ask AI chat rejected because provider is not configured.")
            raise AIProviderNotConfigured(
                "Configure GOODOMICS_AI_API_KEY to enable Ask AI."
            )

        provider_messages: list[dict[str, Any]] = [
            {"role": "system", "content": _system_prompt(project_id=project_id)}
        ] + [
            # Only replay chat roles the provider should see; tool evidence is
            # generated below from trusted server-side executions.
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in {"user", "assistant"} and message.content.strip()
        ]
        evidence: list[ToolEvidence] = []
        tools = tool_schemas()
        max_rounds = max(0, self.context.settings.ai_max_tool_rounds)
        logger.debug(
            "Ask AI chat started: conversation_id=%s project_id=%s "
            "user_messages=%d max_tool_rounds=%d",
            conversation_id,
            project_id,
            len(provider_messages) - 1,
            max_rounds,
        )

        for round_index in range(max_rounds + 1):
            response = await self.provider.complete(provider_messages, tools)
            logger.debug(
                "Ask AI provider round completed: round=%d content_chars=%d "
                "tool_calls=%s",
                round_index,
                len(response.content),
                [call.name for call in response.tool_calls],
            )
            if not response.tool_calls:
                # Final assistant turn with no further tool requests.
                linked_content = _link_response_content(response.content, evidence)
                logger.debug(
                    "Ask AI final response: conversation_id=%s evidence_items=%d "
                    "content_chars=%d linked_content_chars=%d",
                    conversation_id,
                    len(evidence),
                    len(response.content),
                    len(linked_content),
                )
                return ChatResult(
                    conversation_id=conversation_id,
                    message=ChatMessage(
                        role="assistant",
                        content=linked_content,
                    ),
                    tool_calls=evidence,
                )
            if len(evidence) >= max_rounds:
                # Bound tool execution rounds to keep chat auditable and predictable.
                logger.debug(
                    "Ask AI stopped at tool round limit: conversation_id=%s "
                    "evidence_items=%d pending_tool_calls=%s",
                    conversation_id,
                    len(evidence),
                    [call.name for call in response.tool_calls],
                )
                return ChatResult(
                    conversation_id=conversation_id,
                    message=ChatMessage(
                        role="assistant",
                        content=(
                            "I stopped after reaching the configured Goodomics tool "
                            "round limit. Try narrowing the question or asking about "
                            "one project, run, or sample at a time."
                        ),
                    ),
                    tool_calls=evidence,
                )

            provider_messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            # Execute each requested tool and append a tool-role message so the
            # provider can continue reasoning with structured evidence.
            for call in response.tool_calls:
                logger.debug(
                    "Ask AI executing Goodomics tool: name=%s arguments=%s",
                    call.name,
                    _debug_arguments(call.arguments),
                )
                result = await self._call_tool(call)
                logger.debug(
                    "Ask AI Goodomics tool completed: name=%s result=%s",
                    call.name,
                    _debug_result_summary(result),
                )
                evidence.append(
                    ToolEvidence(
                        name=call.name,
                        arguments=call.arguments,
                        result=result,
                    )
                )
                provider_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )

        return ChatResult(
            conversation_id=conversation_id,
            message=ChatMessage(
                role="assistant",
                content=(
                    "I could not complete the request within the configured tool limit."
                ),
            ),
            tool_calls=evidence,
        )

    async def _call_tool(self, call: ProviderToolCall) -> dict[str, Any]:
        """Dispatch a model-requested function call to the read-only query layer."""

        arguments = call.arguments
        if call.name == "list_projects":
            return await self.query_tools.list_projects(**arguments)
        if call.name == "list_data_contracts":
            return await self.query_tools.list_data_contracts(**arguments)
        if call.name == "resolve_project":
            return await self.query_tools.resolve_project(**arguments)
        if call.name == "get_project_summary":
            return await self.query_tools.get_project_summary(**arguments)
        if call.name == "list_recent_runs":
            return await self.query_tools.list_recent_runs(**arguments)
        if call.name == "list_project_runs":
            return await self.query_tools.list_project_runs(**arguments)
        if call.name == "list_project_samples":
            return await self.query_tools.list_project_samples(**arguments)
        if call.name == "get_run":
            return await self.query_tools.get_run(**arguments)
        if call.name == "list_run_samples":
            return await self.query_tools.list_run_samples(**arguments)
        if call.name == "list_run_metrics":
            return await self.query_tools.list_run_metrics(**arguments)
        if call.name == "list_run_files":
            return await self.query_tools.list_run_files(**arguments)
        logger.debug("Ask AI received unknown tool call: name=%s", call.name)
        return {"error": f"Unknown tool: {call.name}"}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        _tool(
            "list_projects",
            "List Goodomics projects.",
            {"query": _string(), "limit": _int()},
        ),
        _tool(
            "list_data_contracts",
            "List semantic data contracts and queryable fields before "
            "using raw tables.",
            {
                "project": _string(),
                "query": _string(),
                "limit": _int(),
                "field_limit": _int(),
            },
        ),
        _tool(
            "resolve_project",
            "Resolve a project reference to a project or candidate list.",
            {"reference": _string(required=True), "limit": _int()},
        ),
        _tool(
            "get_project_summary",
            "Summarize a project by ID, slug, name, or fuzzy reference.",
            {"project": _string(required=True)},
        ),
        _tool(
            "list_recent_runs",
            "List recent runs globally or for a project.",
            {"project": _string(), "limit": _int()},
        ),
        _tool(
            "list_project_runs",
            "List project runs with optional status or analysis-type filters.",
            {
                "project": _string(required=True),
                "status": _string(),
                "analysis_type_id": _string(),
                "limit": _int(),
            },
        ),
        _tool(
            "list_project_samples",
            "List samples for a project.",
            {"project": _string(required=True), "query": _string(), "limit": _int()},
        ),
        _tool(
            "get_run",
            "Fetch a run summary by run ID.",
            {"run_id": _string(required=True), "project": _string()},
        ),
        _tool(
            "list_run_samples",
            "List samples attached to a run.",
            {"run_id": _string(required=True), "project": _string()},
        ),
        _tool(
            "list_run_metrics",
            "List analytics metrics for a run.",
            {
                "run_id": _string(required=True),
                "project": _string(),
                "metric_query": _string(),
                "limit": _int(),
            },
        ),
        _tool(
            "list_run_files",
            "List files attached to a run.",
            {
                "run_id": _string(required=True),
                "project": _string(),
                "kind": _string(),
                "limit": _int(),
            },
        ),
    ]


def _tool(
    name: str, description: str, properties: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    # `_string(required=True)` marks required fields with a private sentinel so
    # call sites stay compact while the emitted schema remains provider-friendly.
    required = [
        key for key, schema in properties.items() if schema.pop("__required", False)
    ]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _string(*, required: bool = False) -> dict[str, Any]:
    return {"type": "string", "__required": required}


def _int() -> dict[str, Any]:
    return {"type": "integer", "minimum": 1, "maximum": 50}


def _parse_arguments(arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError:
        # Invalid JSON from provider should not crash the chat loop.
        return {}
    return value if isinstance(value, dict) else {}


def _system_prompt(*, project_id: str | None) -> str:
    project_context = (
        f"The dashboard is currently scoped to project_id {project_id}."
        if project_id
        else "The dashboard is not currently scoped to a project."
    )
    return (
        "You are Goodomics Ask AI, an evidence-grounded assistant for omics run "
        "history. Use read-only Goodomics tools when answering questions about "
        "projects, runs, samples, files, or metrics. Do not invent data. If a "
        "project reference is ambiguous, explain the candidate projects and ask "
        "the user to choose. When tool results include app_path or markdown_link "
        "for projects, runs, or samples, present those items as Markdown links "
        "using the app path, such as [Sample name](/project/prj_id/samples/sample_id) "
        "or [Run ID](/project/prj_id/runs/run_id). "
        "Agents can query, summarize, compare, draft, and suggest; scientists "
        "and teams make final QC and scientific decisions. "
        f"{project_context}"
    )


def _link_response_content(content: str, evidence: list[ToolEvidence]) -> str:
    """Link entity names in a model response using structured tool evidence.

    Providers do not always follow the Markdown-link instruction. This pass keeps
    app navigation reliable by turning exact project/run/sample labels into app
    links when the corresponding tool result included an `app_path`.
    """

    links = _evidence_entity_links(evidence)
    if not links:
        return content

    # Prefer longest labels first so "project-123" wins over "project".
    pattern = re.compile(
        r"(?<![A-Za-z0-9_%/-])("
        + "|".join(re.escape(label) for label in sorted(links, key=len, reverse=True))
        + r")(?![A-Za-z0-9_%/-])",
        flags=re.IGNORECASE,
    )
    segments: list[str] = []
    last_index = 0
    for match in re.finditer(
        r"\[[^\]\n]+\]\([^) \n]*(?:%20[^)\n]*)?[^)\n]*\)", content
    ):
        # Do not rewrite text already inside Markdown links.
        if match.start() > last_index:
            segments.append(
                _link_plain_text(content[last_index : match.start()], pattern, links)
            )
        segments.append(match.group(0))
        last_index = match.end()
    if last_index < len(content):
        segments.append(_link_plain_text(content[last_index:], pattern, links))
    return "".join(segments)


def _link_plain_text(
    content: str,
    pattern: re.Pattern[str],
    links: dict[str, str],
) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(0)
        path = links.get(label.lower())
        if path is None:
            return label
        return f"[{_escape_markdown_label(label)}]({path.replace(' ', '%20')})"

    return pattern.sub(replace, content)


def _evidence_entity_links(evidence: list[ToolEvidence]) -> dict[str, str]:
    """Build an unambiguous label-to-app-path map from nested tool results."""

    links: dict[str, str] = {}
    conflicts: set[str] = set()

    def add_link(label: Any, path: str) -> None:
        if not isinstance(label, str):
            return
        clean_label = label.strip()
        if len(clean_label) < 2:
            return
        key = clean_label.lower()
        if key in conflicts:
            return
        if key in links and links[key] != path:
            # Drop ambiguous labels so we only auto-link unambiguous entities.
            links.pop(key, None)
            conflicts.add(key)
            return
        links[key] = path

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            app_path = value.get("app_path")
            if isinstance(app_path, str) and app_path.startswith("/"):
                # Tool results can nest entities under summaries or lists, so
                # collect labels wherever an app path appears.
                for label in _entity_link_labels(value):
                    add_link(label, app_path)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for item in evidence:
        visit(item.result)
    return links


def _entity_link_labels(value: dict[str, Any]) -> list[Any]:
    if "sample_id" in value:
        return [value.get("sample_name"), value.get("sample_id")]
    if "run_id" in value:
        return [value.get("name"), value.get("run_id")]
    if "project_id" in value:
        return [value.get("name"), value.get("project_id"), value.get("slug")]
    return []


def _escape_markdown_label(label: str) -> str:
    return label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _debug_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return bounded tool arguments for debug logs without dumping full prompts."""

    return {key: _truncate_debug_value(value) for key, value in arguments.items()}


def _truncate_debug_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 120 else f"{value[:117]}..."
    return value


def _debug_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Summarize a tool result shape without logging entire evidence payloads."""

    summary: dict[str, Any] = {}
    for key, value in result.items():
        if isinstance(value, list):
            summary[key] = f"list[{len(value)}]"
        elif isinstance(value, dict):
            summary[key] = f"dict[{len(value)}]"
        else:
            summary[key] = _truncate_debug_value(value)
    return summary
