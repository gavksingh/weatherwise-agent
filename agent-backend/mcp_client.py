import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

MCP_SERVER_SCRIPT = str(Path(__file__).resolve().parent.parent / "mcp-server" / "server.py")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")


JSON_TYPE_MAP = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _build_args_model(name: str, input_schema: dict) -> type[BaseModel]:
    """Build a Pydantic model from an MCP tool's JSON Schema so LangChain
    advertises the correct parameter names and types to the LLM."""
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    fields: dict[str, Any] = {}

    for prop_name, prop_info in properties.items():
        py_type = JSON_TYPE_MAP.get(prop_info.get("type", "string"), str)
        field_desc = prop_info.get("description", "")
        if prop_name in required:
            fields[prop_name] = (py_type, Field(description=field_desc))
        else:
            default = prop_info.get("default")
            fields[prop_name] = (
                Optional[py_type],
                Field(default=default, description=field_desc),
            )

    return create_model(f"{name}_args", **fields)


def _make_langchain_tool(name: str, description: str, input_schema: dict, session: ClientSession) -> StructuredTool:
    """Create a LangChain StructuredTool that calls an MCP tool via the session."""

    properties = input_schema.get("properties", {})

    async def _call_tool(**kwargs):
        coerced = {}
        for key, value in kwargs.items():
            expected = properties.get(key, {}).get("type")
            if expected == "number" and isinstance(value, str):
                coerced[key] = float(value)
            elif expected == "integer" and isinstance(value, str):
                coerced[key] = int(value)
            else:
                coerced[key] = value
        result = await session.call_tool(name, arguments=coerced)
        text_parts = [block.text for block in result.content if hasattr(block, "text")]
        text = "\n".join(text_parts)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    args_model = _build_args_model(name, input_schema)

    return StructuredTool.from_function(
        coroutine=_call_tool,
        name=name,
        description=description,
        args_schema=args_model,
        func=lambda **kw: None,  # sync placeholder, async is used
    )


async def get_mcp_tools(session: ClientSession) -> list[StructuredTool]:
    """List all tools from the MCP server and convert to LangChain tools."""
    tools_response = await session.list_tools()
    tools = []

    for tool in tools_response.tools:
        lc_tool = _make_langchain_tool(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
            session=session,
        )
        tools.append(lc_tool)

    logger.info(f"Loaded {len(tools)} tools from MCP server: {[t.name for t in tools]}")
    return tools


def get_server_params() -> StdioServerParameters:
    """Get the stdio server parameters to launch the MCP server."""
    return StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT],
    )


def create_mcp_session():
    """Create an MCP client context.

    Uses SSE transport when MCP_SERVER_URL is set (Docker), otherwise spawns
    the MCP server as a subprocess via stdio (local development).

    Usage:
        async with create_mcp_session() as (read, write):
            async with ClientSession(read, write) as session:
                ...
    """
    if MCP_SERVER_URL:
        from mcp.client.sse import sse_client

        logger.info(f"Connecting to MCP server via SSE at {MCP_SERVER_URL}")
        return sse_client(MCP_SERVER_URL)

    server_path = Path(MCP_SERVER_SCRIPT)
    if not server_path.exists():
        raise ConnectionError(
            f"MCP server script not found at {MCP_SERVER_SCRIPT}. "
            "Ensure the mcp-server directory is in the expected location."
        )

    try:
        return stdio_client(get_server_params())
    except Exception as e:
        raise ConnectionError(
            f"Failed to connect to MCP server: {e}. "
            "Check that mcp-server dependencies are installed and server.py is valid."
        ) from e
