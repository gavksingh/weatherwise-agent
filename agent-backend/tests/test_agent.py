import pytest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agent import _build_messages, _extract_response


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
