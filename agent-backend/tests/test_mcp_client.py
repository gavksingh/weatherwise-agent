"""Tests for MCP client argument coercion."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_client import _make_langchain_tool


def _make_tool(input_schema: dict):
    """Helper: build a LangChain tool backed by a mock MCP session."""
    session = AsyncMock()
    tool = _make_langchain_tool(
        name="test_tool",
        description="A test tool",
        input_schema=input_schema,
        session=session,
    )
    return tool, session


SCHEMA = {
    "type": "object",
    "properties": {
        "lat": {"type": "number", "description": "Latitude"},
        "lon": {"type": "number", "description": "Longitude"},
        "name": {"type": "string", "description": "Location name"},
    },
    "required": ["lat", "lon"],
}


@pytest.fixture
def _mock_call_result():
    """Return a mock MCP call_tool result with a text block."""
    block = MagicMock()
    block.text = json.dumps({"temp": 20})
    result = MagicMock()
    result.content = [block]
    return result


@pytest.mark.asyncio
async def test_string_coerced_to_float(_mock_call_result):
    tool, session = _make_tool(SCHEMA)
    session.call_tool.return_value = _mock_call_result

    await tool.ainvoke({"lat": "51.5", "lon": "-0.1"})

    _, call_kwargs = session.call_tool.call_args
    assert call_kwargs["arguments"]["lat"] == 51.5
    assert call_kwargs["arguments"]["lon"] == -0.1
    assert isinstance(call_kwargs["arguments"]["lat"], float)
    assert isinstance(call_kwargs["arguments"]["lon"], float)


@pytest.mark.asyncio
async def test_string_coerced_to_int(_mock_call_result):
    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of results"},
        },
        "required": ["count"],
    }
    tool, session = _make_tool(schema)
    session.call_tool.return_value = _mock_call_result

    await tool.ainvoke({"count": "5"})

    _, call_kwargs = session.call_tool.call_args
    assert call_kwargs["arguments"]["count"] == 5
    assert isinstance(call_kwargs["arguments"]["count"], int)


@pytest.mark.asyncio
async def test_correct_types_unchanged(_mock_call_result):
    tool, session = _make_tool(SCHEMA)
    session.call_tool.return_value = _mock_call_result

    await tool.ainvoke({"lat": 51.5, "lon": -0.1, "name": "London"})

    _, call_kwargs = session.call_tool.call_args
    assert call_kwargs["arguments"] == {"lat": 51.5, "lon": -0.1, "name": "London"}


@pytest.mark.asyncio
async def test_non_numeric_string_raises():
    tool, session = _make_tool(SCHEMA)

    with pytest.raises((ValueError, TypeError)):
        await tool.ainvoke({"lat": "not_a_number", "lon": "0.0"})
