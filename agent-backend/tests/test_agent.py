import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from agent import _build_messages, _extract_response, _unwrap_exception, run_agent_stream

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup


# ── _build_messages ──


def test_build_messages_no_history():
    msgs = _build_messages("Hello", None)
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "Hello"


def test_build_messages_with_history():
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "How are you?"},
    ]
    msgs = _build_messages("Fine thanks", history)
    assert len(msgs) == 4
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert isinstance(msgs[2], HumanMessage)
    assert isinstance(msgs[3], HumanMessage)
    assert msgs[3].content == "Fine thanks"


def test_build_messages_empty_history():
    msgs = _build_messages("Test", [])
    assert len(msgs) == 1


# ── _extract_response ──


def test_extract_response_finds_last_ai_message():
    result = {
        "messages": [
            HumanMessage(content="Hi"),
            AIMessage(content="First response"),
            AIMessage(content="Final response"),
        ]
    }
    assert _extract_response(result) == "Final response"


def test_extract_response_skips_empty_ai_messages():
    result = {
        "messages": [
            AIMessage(content="Good answer"),
            AIMessage(content=""),
        ]
    }
    assert _extract_response(result) == "Good answer"


def test_extract_response_no_ai_messages():
    result = {"messages": [HumanMessage(content="Hi")]}
    assert "wasn't able to generate" in _extract_response(result)


def test_extract_response_empty_messages():
    result = {"messages": []}
    assert "wasn't able to generate" in _extract_response(result)


# ── _unwrap_exception ──


def test_unwrap_exception_plain():
    exc = ValueError("plain error")
    assert _unwrap_exception(exc) is exc


def test_unwrap_exception_single_group():
    root = ValueError("root cause")
    group = ExceptionGroup("group", [root])
    assert _unwrap_exception(group) is root


def test_unwrap_exception_nested_groups():
    root = RuntimeError("deep cause")
    inner = ExceptionGroup("inner", [root])
    outer = ExceptionGroup("outer", [inner])
    assert _unwrap_exception(outer) is root


# ── run_agent_stream fallback ──


def _make_mock_mcp_session():
    """Create mocked MCP session context manager."""
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    return mock_session


def _make_chunk(content, tool_calls=None, tool_call_chunks=None):
    """Create an AIMessageChunk for testing."""
    return AIMessageChunk(
        content=content,
        tool_calls=tool_calls or [],
        tool_call_chunks=tool_call_chunks or [],
    )


@pytest.mark.asyncio
async def test_run_agent_stream_fallback_on_primary_failure():
    """When primary LLM raises, stream falls back to secondary LLM."""
    primary_error = ExceptionGroup("tasks", [ValueError("429 rate limit")])

    async def failing_astream(*args, **kwargs):
        raise primary_error
        yield  # make it an async generator  # noqa: unreachable

    fallback_chunk = _make_chunk("fallback response")
    fallback_metadata = {"langgraph_node": "agent"}

    async def success_astream(*args, **kwargs):
        yield fallback_chunk, fallback_metadata

    primary_agent = MagicMock()
    primary_agent.astream = failing_astream

    fallback_agent = MagicMock()
    fallback_agent.astream = success_astream

    call_count = 0

    def mock_create_react_agent(llm, tools, prompt=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return primary_agent
        return fallback_agent

    with patch("agent.create_mcp_session") as mock_mcp, \
         patch("agent.get_mcp_tools", new_callable=AsyncMock, return_value=[]), \
         patch("agent.get_llm", return_value=MagicMock()), \
         patch("agent.get_fallback_llm", return_value=MagicMock()), \
         patch("agent.create_react_agent", side_effect=mock_create_react_agent):
        mock_session = _make_mock_mcp_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_mcp.return_value = mock_ctx
        with patch("agent.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            chunks = []
            async for chunk in run_agent_stream("test"):
                chunks.append(chunk)

    assert "fallback response" in chunks
    assert not any("Switching" in c for c in chunks)


@pytest.mark.asyncio
async def test_run_agent_stream_both_llms_fail():
    """When both LLMs fail, stream yields error message."""
    async def failing_astream(*args, **kwargs):
        raise ValueError("primary down")
        yield  # noqa: unreachable

    async def fallback_failing_astream(*args, **kwargs):
        raise ValueError("fallback also down")
        yield  # noqa: unreachable

    primary_agent = MagicMock()
    primary_agent.astream = failing_astream

    fallback_agent = MagicMock()
    fallback_agent.astream = fallback_failing_astream

    call_count = 0

    def mock_create_react_agent(llm, tools, prompt=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return primary_agent
        return fallback_agent

    with patch("agent.create_mcp_session") as mock_mcp, \
         patch("agent.get_mcp_tools", new_callable=AsyncMock, return_value=[]), \
         patch("agent.get_llm", return_value=MagicMock()), \
         patch("agent.get_fallback_llm", return_value=MagicMock()), \
         patch("agent.create_react_agent", side_effect=mock_create_react_agent):
        mock_session = _make_mock_mcp_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_mcp.return_value = mock_ctx
        with patch("agent.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock(return_value=False))):
            chunks = []
            async for chunk in run_agent_stream("test"):
                chunks.append(chunk)

    assert any("sorry" in c.lower() or "wrong" in c.lower() for c in chunks)


@pytest.mark.asyncio
async def test_run_agent_stream_no_fallback_available():
    """When primary fails and no fallback configured, yields error."""
    async def failing_astream(*args, **kwargs):
        raise ValueError("rate limited")
        yield  # noqa: unreachable

    primary_agent = MagicMock()
    primary_agent.astream = failing_astream

    with patch("agent.create_mcp_session") as mock_mcp, \
         patch("agent.get_mcp_tools", new_callable=AsyncMock, return_value=[]), \
         patch("agent.get_llm", return_value=MagicMock()), \
         patch("agent.get_fallback_llm", return_value=None), \
         patch("agent.create_react_agent", return_value=primary_agent):
        mock_session = _make_mock_mcp_session()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_mcp.return_value = mock_ctx
        with patch("agent.ClientSession", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
            chunks = []
            async for chunk in run_agent_stream("test"):
                chunks.append(chunk)

    assert any("sorry" in c.lower() or "wrong" in c.lower() for c in chunks)
    assert not any("Switching" in c for c in chunks)
