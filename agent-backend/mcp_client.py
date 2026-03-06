import json
import logging
import sys
from pathlib import Path

from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

MCP_SERVER_SCRIPT = str(Path(__file__).resolve().parent.parent / "mcp-server" / "server.py")


def _make_langchain_tool(name: str, description: str, input_schema: dict, session: ClientSession) -> StructuredTool:
    """Create a LangChain StructuredTool that calls an MCP tool via the session."""

    async def _call_tool(**kwargs):
        result = await session.call_tool(name, arguments=kwargs)
        text_parts = [block.text for block in result.content if hasattr(block, "text")]
        text = "\n".join(text_parts)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    return StructuredTool.from_function(
        coroutine=_call_tool,
        name=name,
        description=description,
        args_schema=None,
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


MCP_CONNECT_TIMEOUT = 30

async def create_mcp_session():
    """Create and return an MCP stdio client context and session.

    Usage:
        async with create_mcp_session() as (read, write):
            async with ClientSession(read, write) as session:
                ...

    Raises:
        ConnectionError: If the MCP server process fails to start.
    """
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
