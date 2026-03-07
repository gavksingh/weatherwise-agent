# WeatherWise Agent

An AI-powered weather assistant built with LangGraph, MCP (Model Context Protocol), and Next.js. Ask natural language questions about weather and get real-time answers powered by OpenWeatherMap.

## Features

- Natural language weather queries (current conditions, forecasts, air quality, alerts)
- Streaming responses via Server-Sent Events
- LLM provider fallback (Google Gemini / Groq)
- MCP-based tool architecture with 5 weather tools
- Dark-mode chat UI with example query chips
- Dockerized with isolated internal networking

## Prerequisites

- **Docker & Docker Compose** (recommended) or Python 3.12+ and Node.js 22+
- **OpenWeatherMap API key** - [get one free](https://openweathermap.org/appid)
- **LLM provider** - at least one of:
  - [Google Cloud / Vertex AI](https://console.cloud.google.com/) — a service account JSON key with Vertex AI API enabled (`GOOGLE_APPLICATION_CREDENTIALS` + `VERTEX_PROJECT`)
  - [Groq](https://console.groq.com/keys) (`GROQ_API_KEY`)

## Quick Start (Docker)

```bash
# 1. Clone and configure
git clone <your-repo-url> weatherwise-agent
cd weatherwise-agent
cp .env.example .env
# Edit .env with your API keys

# 2. Build and run
docker compose up --build

# 3. Open http://localhost:3000
```

The MCP server runs on an internal network with no exposed ports. Only the agent backend (`:8000`) and frontend (`:3000`) are accessible from the host.

## Local Development

### MCP Server

```bash
cd mcp-server
pip install -r requirements.txt
python server.py  # runs via stdio transport
```

### Agent Backend

```bash
cd agent-backend
pip install -r requirements.txt
python main.py  # starts on http://localhost:8000
```

The agent spawns the MCP server as a subprocess (stdio) automatically when `MCP_SERVER_URL` is not set.

### Frontend

```bash
cd frontend
npm install
npm run dev  # starts on http://localhost:3000
```

API calls are proxied to `http://localhost:8000` by default (configurable via `API_URL` env var).

## Testing

### MCP Server

```bash
cd mcp-server
pip install -r requirements.txt
pytest
```

### Agent Backend

```bash
cd agent-backend
pip install -r requirements.txt
pytest
```

Tests use `pytest-asyncio` for async test support. All tests use mocks and dummy API keys (set automatically via `conftest.py`), so no real credentials are needed.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENWEATHER_API_KEY` | Yes | - | OpenWeatherMap API key |
| `LLM_PROVIDER` | No | `google` | LLM provider: `google` or `groq` |
| `GOOGLE_APPLICATION_CREDENTIALS` | If provider=google | - | Path to GCP service account JSON |
| `VERTEX_PROJECT` | If provider=google | - | GCP project ID |
| `VERTEX_LOCATION` | No | `us-central1` | Vertex AI region |
| `GROQ_API_KEY` | If provider=groq | - | Groq API key |
| `MCP_SERVER_URL` | Docker only | - | SSE URL for MCP server (e.g., `http://mcp-server:8001/sse`) |
| `MCP_TRANSPORT` | Docker only | `stdio` | MCP server transport: `stdio` or `sse` |
| `API_URL` | Docker only | `http://localhost:8000` | Backend URL for frontend proxy |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a message, get a complete response |
| `GET` | `/api/chat/stream?message=...` | Stream a response via SSE |
| `GET` | `/api/health` | Health check |

## Project Structure

```
weatherwise-agent/
  agent-backend/       # FastAPI + LangGraph ReAct agent
    app.py             # API routes
    agent.py           # Agent orchestration and streaming
    mcp_client.py      # MCP client (stdio + SSE transport)
    llm_provider.py    # LLM configuration with fallback
    prompts.py         # System prompt
    main.py            # Uvicorn entrypoint
  mcp-server/          # FastMCP weather tools server
    server.py          # 5 MCP tools (geocode, weather, forecast, air quality, alerts)
    config.py          # OpenWeatherMap client configuration
    schemas.py         # Pydantic response models
  frontend/            # Next.js chat UI
    src/app/page.tsx   # Chat interface with SSE streaming
  Dockerfile.mcp       # MCP server image
  Dockerfile.agent     # Agent backend image
  Dockerfile.frontend  # Frontend multi-stage image
  docker-compose.yml   # All 3 services with network isolation
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and system overview.
