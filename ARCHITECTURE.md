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
  :3000           :8000         internal only

  Browser          SSE            stdio (local)
  <-------->    streaming         SSE (Docker)
  HTTP/SSE      + proxy
```

Users interact with the Next.js frontend, which proxies API requests to the agent backend. The agent uses LangGraph's ReAct loop to reason about the query and call weather tools exposed by the MCP server.

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
- **LLM providers**: Google Gemini (primary) or Groq with automatic fallback
- **MCP client**: Connects to the MCP server via stdio (local) or SSE (Docker), converts MCP tools to LangChain `StructuredTool` instances
- **Streaming**: Token-level SSE streaming via `astream_events` for real-time responses

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

## Production Deployment

### Kubernetes Architecture

Each service maps to a Kubernetes Deployment + Service:

```
                    Ingress (TLS)
                        |
               +--------v--------+
               |    Frontend     |  Deployment (2+ replicas)
               |    Service      |  ClusterIP :3000
               +--------+--------+
                        |
               +--------v--------+
               |  Agent Backend  |  Deployment (2+ replicas)
               |    Service      |  ClusterIP :8000
               +--------+--------+
                        |
               +--------v--------+
               |   MCP Server    |  Deployment (2+ replicas)
               |    Service      |  ClusterIP :8001 (no Ingress)
               +--------v--------+
                        |
                  OpenWeatherMap
```

- **Frontend**: Deployed behind an Ingress with TLS termination. The `API_URL` env var points to the agent backend's ClusterIP service (`http://agent-backend:8000`).
- **Agent Backend**: Internal ClusterIP service, not exposed via Ingress. Receives proxied traffic from the frontend only.
- **MCP Server**: Internal ClusterIP service with no Ingress route. Only reachable by the agent backend within the cluster. Apply a `NetworkPolicy` to restrict ingress to the agent backend namespace/labels only.

### Secrets Management

API keys (`OPENWEATHER_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`) must never be baked into images or stored in plain ConfigMaps.

- **Kubernetes Secrets**: Minimum viable approach. Create an opaque Secret and mount as env vars in the relevant Deployments. Encrypt etcd at rest.
- **External secrets operator**: For production, use External Secrets Operator to sync secrets from AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault into Kubernetes Secrets automatically.
- **Rotation**: LLM API keys and the OpenWeatherMap key should be rotatable without redeployment. External Secrets Operator handles this via periodic sync. The services read keys at startup (no hot-reload needed - a rolling restart picks up new values).

### Scaling Strategy

| Service | Scaling approach | Bottleneck | Notes |
|---|---|---|---|
| Frontend | HPA on CPU (target 70%) | Mostly static serving, low resource | Scales easily, stateless |
| Agent Backend | HPA on concurrent requests or CPU | LLM API latency, SSE connection hold time | Each SSE stream holds a connection open; scale on connection count, not just CPU |
| MCP Server | HPA on CPU (target 70%) | OpenWeatherMap API rate limits | Scale conservatively; add response caching to reduce upstream calls |

Key considerations:
- **Agent Backend connections**: SSE streams are long-lived. Set appropriate `keep-alive` timeouts on the Ingress/load balancer. Use connection-count-based scaling rather than pure CPU.
- **MCP Server caching**: Weather data doesn't change every second. Add a Redis/Valkey sidecar or shared cache to deduplicate identical geocode/weather lookups. Cache TTLs: geocode (24h), current weather (5min), forecast (15min), air quality (10min).
- **Rate limiting**: Apply per-user rate limits at the Ingress or agent backend level to prevent abuse and protect downstream API quotas.

### CI/CD Pipeline

```
Push to main
    |
    v
Lint + Type Check --> Unit Tests --> Build Images --> Push to Registry
                                                           |
                                                           v
                                                   Deploy to Staging
                                                           |
                                                     Smoke Tests
                                                           |
                                                           v
                                                 Deploy to Production
                                                  (rolling update)
```

1. **Lint & test**: Run `ruff`/`pytest` for Python services, `eslint`/`npm run build` for frontend. Gate merges on passing checks.
2. **Build**: Multi-platform Docker builds (`linux/amd64`, `linux/arm64`) via GitHub Actions or similar. Tag images with git SHA for traceability.
3. **Registry**: Push to a private container registry (ECR, GCR, GHCR). Scan images for vulnerabilities (Trivy, Snyk).
4. **Deploy**: Use Helm charts or Kustomize overlays per environment. Rolling updates with `maxSurge: 1, maxUnavailable: 0` for zero-downtime deploys.
5. **Rollback**: Keep previous image tags. Rollback via `kubectl rollout undo` or by reverting the Helm release.
