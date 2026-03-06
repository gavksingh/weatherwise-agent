import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app import app, MAX_MESSAGE_LENGTH

client = TestClient(app)


# ── Health ──


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "weatherwise-agent"


# ── POST /api/chat validation ──


def test_chat_empty_message():
    resp = client.post("/api/chat", json={"message": "   "})
    assert resp.status_code == 422


def test_chat_too_long_message():
    resp = client.post("/api/chat", json={"message": "x" * (MAX_MESSAGE_LENGTH + 1)})
    assert resp.status_code == 422


def test_chat_missing_message():
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 422


# ── GET /api/chat/stream validation ──


def test_stream_empty_message():
    resp = client.get("/api/chat/stream", params={"message": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_stream_too_long_message():
    resp = client.get("/api/chat/stream", params={"message": "x" * (MAX_MESSAGE_LENGTH + 1)})
    assert resp.status_code == 400
    assert "maximum length" in resp.json()["detail"].lower()


def test_stream_missing_message():
    resp = client.get("/api/chat/stream")
    assert resp.status_code == 422


# ── POST /api/chat success ──


@patch("app.run_agent", new_callable=AsyncMock)
def test_chat_success(mock_run_agent):
    mock_run_agent.return_value = "It's 22°C and sunny in London."
    resp = client.post("/api/chat", json={"message": "Weather in London"})
    assert resp.status_code == 200
    assert resp.json()["response"] == "It's 22°C and sunny in London."
    mock_run_agent.assert_called_once_with("Weather in London", None)


@patch("app.run_agent", new_callable=AsyncMock)
def test_chat_with_history(mock_run_agent):
    mock_run_agent.return_value = "Tomorrow will be rainy."
    history = [
        {"role": "user", "content": "Weather in London"},
        {"role": "assistant", "content": "It's sunny."},
    ]
    resp = client.post("/api/chat", json={"message": "What about tomorrow?", "history": history})
    assert resp.status_code == 200
    mock_run_agent.assert_called_once_with("What about tomorrow?", history)


@patch("app.run_agent", new_callable=AsyncMock)
def test_chat_agent_error(mock_run_agent):
    mock_run_agent.side_effect = RuntimeError("LLM connection failed")
    resp = client.post("/api/chat", json={"message": "Weather in London"})
    assert resp.status_code == 500
    assert "LLM connection failed" in resp.json()["detail"]
