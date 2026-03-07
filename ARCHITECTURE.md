# Architecture

## System Overview

```
                         +-------------------+
                         |   OpenWeatherMap  |
                         |       API         |
                         +--------^----------+
                                  |
+----------+    +----------+    +----------+
|          | -> |  Agent   | -> |   MCP    |
| Frontend |    | Backend  |    |  Server  |
| (Next.js)|    | (FastAPI)|    | (FastMCP)|
+----------+    +----------+    +----------+
  :3000           :8000           :8001

  Browser          SSE            stdio (local)
  <-------->    streaming         SSE (Docker/Cloud Run)
  HTTP/SSE      + proxy
```

Users interact with the Next.js frontend, which proxies API requests to the agent backend. The agent uses LangGraph's ReAct loop to reason about the query and call weather tools exposed by the MCP server.

**Deployment modes:**
- **Local (Docker Compose)**: All 3 services on an internal Docker network. MCP server has no exposed ports.
- **Cloud Run (GCP)**: Each service is an independent Cloud Run service. The frontend proxies to the agent backend via its Cloud Run URL (baked in at build time). The agent backend connects to the MCP server via its Cloud Run URL.

## Components

### MCP Server (`mcp-server/`)

A FastMCP server exposing 5 weather tools that wrap the OpenWeatherMap API:

| Tool | Purpose |
|---|---|
| `geocode_location` | Convert city name to lat/lon (must be called first) |
| `get_current_weather` | Current temperature, humidity, wind, conditions |
| `get_forecast` | 5-day / 3-hour interval forecast |
| `get_air_quality` | AQI index and pollutant concentrations |
| `get_weather_alerts` | Severe weather warnings (requires OneCall 3.0) |

**Dual transport**: Runs via stdio for local development (agent spawns it as a subprocess) or SSE over HTTP for Docker (separate container on an internal network).

### Agent Backend (`agent-backend/`)

A FastAPI service that orchestrates an LLM-powered weather agent:

- **LangGraph ReAct agent**: Iteratively reasons and calls MCP tools until it has enough information to answer
- **LLM providers**: Google Gemini via Vertex AI (primary) or Groq with automatic fallback. Instances are cached per-provider with `temperature=0` and `max_output_tokens=2048` for fast, deterministic responses
- **MCP client**: Connects to the MCP server via stdio (local) or SSE (Docker), converts MCP tools to LangChain `StructuredTool` instances with Pydantic args models and type coercion for cross-provider compatibility
- **Streaming**: Token-level SSE streaming via `astream(stream_mode="messages")` with `_extract_text()` to handle Vertex AI's list-of-parts content format

### Frontend (`frontend/`)

A Next.js app with a ChatGPT-style dark-theme interface:

- **SSE streaming**: `EventSource` connected to `/api/chat/stream`, tokens rendered as they arrive
- **Markdown rendering**: Assistant responses render bold, lists, headers, and code blocks via `react-markdown`
- **API proxy**: Next.js rewrites forward `/api/*` to the backend, avoiding CORS in production
- **Accessibility**: ARIA labels, `role="log"`, `aria-live="polite"` for screen readers
- **Dark theme only**: The UI uses a fixed dark color scheme. This is a deliberate design choice — weather dashboards are frequently checked throughout the day, and a dark theme reduces eye strain during extended use while providing better contrast for numerical weather data (temperatures, percentages, wind speeds). There is no light mode toggle.

## Communication Flow

1. User types a question or clicks an example chip
2. Frontend opens an SSE connection to `/api/chat/stream?message=...`
3. Next.js rewrites proxy the request to the agent backend
4. Agent backend creates an MCP session and loads tools
5. LangGraph ReAct loop:
   - LLM decides which tool to call (e.g., `geocode_location` then `get_current_weather`)
   - Tool call is forwarded to MCP server, which calls OpenWeatherMap
   - Result is returned to the LLM for further reasoning or final answer
6. Final answer tokens are streamed back via SSE
7. Frontend appends each token to the assistant message bubble

## Design Decisions

### Why MCP?

The Model Context Protocol decouples tool implementation from the agent. The MCP server can be developed, tested, and versioned independently. Other agents or LLM applications can reuse the same weather tools without duplicating API integration code.

### Why dual transport (stdio + SSE)?

- **stdio** for local dev: zero configuration, agent spawns the server as a subprocess, no ports to manage
- **SSE** for Docker: enables proper container isolation. The MCP server runs on an internal Docker network with no exposed ports, only reachable by the agent backend

### Why LangGraph ReAct?

The ReAct pattern lets the agent chain multiple tool calls autonomously. A weather query like "should I go hiking in Denver?" requires geocoding, current weather, air quality, and possibly alerts. LangGraph handles this multi-step reasoning loop with built-in support for tool calling and streaming.

### Why SSE streaming (not WebSocket)?

SSE is simpler for unidirectional server-to-client streaming. The chat pattern is request-response (user sends a message, agent streams back), which maps directly to SSE. No connection upgrade negotiation, works through HTTP proxies, and is natively supported by `EventSource` in browsers.

### Docker networking

The MCP server has no published ports and runs on an `internal` Docker network. Only the agent backend (on both `internal` and `default` networks) can reach it. This follows the principle of least privilege: the weather tool server has no reason to be accessible from outside the stack.

## Production Deployment (GCP Cloud Run)

### Cloud Run Architecture

All 3 services are deployed to Google Cloud Run in `us-central1`:

```
               Cloud Run (TLS managed by GCP)
                            |
               +────────────v────────────+
               | weatherwise-agent-      |
               |   frontend              |  Cloud Run service
               |   :3000                 |  min-instances: 1
               +────────────+────────────+
                            | Next.js rewrites (build-time URL)
               +────────────v────────────+
               | weatherwise-agent-      |
               |   backend               |  Cloud Run service
               |   :8000                 |  min-instances: 1
               +────────────+────────────+
                            | MCP over SSE
               +────────────v────────────+
               | weatherwise-agent-      |
               |   mcp                   |  Cloud Run service
               |   :8001                 |  min-instances: 1
               +────────────+────────────+
                            |
                      OpenWeatherMap
```

**Live URLs:**
- Frontend: `https://weatherwise-agent-frontend-ybn6xfzrsa-uc.a.run.app`
- Agent Backend: `https://weatherwise-agent-backend-ybn6xfzrsa-uc.a.run.app`
- MCP Server: `https://weatherwise-agent-mcp-ybn6xfzrsa-uc.a.run.app`
- Swagger Docs: `https://weatherwise-agent-backend-ybn6xfzrsa-uc.a.run.app/docs`

- **Frontend**: Serves the Next.js app. Backend URL is baked in at `docker build` time via `--build-arg API_URL=<backend-url>`, because Next.js `rewrites()` are compiled during `next build`.
- **Agent Backend**: Receives proxied traffic from the frontend. Connects to the MCP server via its Cloud Run URL. Authenticates to Vertex AI (Gemini) via ADC — no JSON key file needed.
- **MCP Server**: Runs FastMCP with SSE transport on port 8001. Only called by the agent backend.

### Authentication & Secrets

**Vertex AI auth**: Cloud Run uses Application Default Credentials (ADC) via a dedicated service account (`weatherwise-run@project-cf964f7d-d79b-4b69-81c.iam.gserviceaccount.com`). No JSON key file is needed — the metadata server handles auth automatically. The service account has `roles/aiplatform.user` and `roles/secretmanager.secretAccessor`.

**API keys**: Stored in GCP Secret Manager and injected into containers at runtime via `--set-secrets`:

| Secret | Used by |
|---|---|
| `weatherwise-openweather-api-key` | mcp-server, agent-backend |
| `weatherwise-groq-api-key` | agent-backend |

Secrets are never baked into images. The `deploy.sh` script reads values from the local `.env` and creates/updates Secret Manager versions. Rotation requires only updating the secret version and redeploying.

### Scaling

All services use Cloud Run's built-in autoscaling:

| Setting | Value | Rationale |
|---|---|---|
| `min-instances` | 1 | Eliminates cold starts — the first request works instantly |
| `max-instances` | 3 | Prevents runaway scaling and cost |

Cloud Run scales to zero by default, but this causes a **cold start chain**: the first request must wait for all 3 services to start sequentially (frontend → backend → mcp-server), which often times out. Setting `min-instances=1` keeps one container warm per service.

### Deployment Script

`deploy.sh` handles the full end-to-end deployment in the correct order:

```
1. Create Artifact Registry repo (idempotent)
2. Create service account + IAM roles
3. Store secrets in Secret Manager from .env
4. Build & push mcp-server and agent-backend images (linux/amd64)
5. Deploy weatherwise-agent-mcp → capture URL
6. Deploy weatherwise-agent-backend (with MCP_SERVER_URL) → capture URL
7. Build frontend image with --build-arg API_URL=<backend-url>
8. Push & deploy weatherwise-agent-frontend
9. Print all URLs
```

The frontend is built **after** the backend is deployed because Next.js `rewrites()` in `next.config.ts` are compiled at `next build` time — the backend URL must be known and baked into the image via `--build-arg`.

Images must be built with `--platform linux/amd64` when building on Apple Silicon Macs, as Cloud Run runs on `amd64`.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full deployment guide, challenges encountered, and troubleshooting.
