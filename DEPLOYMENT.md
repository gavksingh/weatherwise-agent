# WeatherWise — GCP Cloud Run Deployment Guide

## Overview

WeatherWise is a three-service application deployed on Google Cloud Platform using Cloud Run:

| Service | Description | Port |
|---|---|---|
| `mcp-server` | FastMCP weather tools server (SSE transport) | 8001 |
| `agent-backend` | FastAPI + LangChain AI agent | 8000 |
| `frontend` | Next.js chat interface | 3000 |

**Live URLs:**
- Frontend: https://weatherwise-agent-frontend-ybn6xfzrsa-uc.a.run.app
- Agent Backend: https://weatherwise-agent-backend-ybn6xfzrsa-uc.a.run.app
- MCP Server: https://weatherwise-agent-mcp-ybn6xfzrsa-uc.a.run.app

---

## Architecture

```
User Browser
    │
    ▼
┌─────────────────────────────┐
│  frontend (Cloud Run)       │  Next.js — serves UI, proxies /api/* to backend
│  port 3000                  │
└──────────┬──────────────────┘
           │ HTTP (rewrites via next.config.ts)
           ▼
┌─────────────────────────────┐
│  agent-backend (Cloud Run)  │  FastAPI + LangChain agent
│  port 8000                  │
└──────────┬──────────────────┘
           │ MCP over SSE
           ▼
┌─────────────────────────────┐
│  mcp-server (Cloud Run)     │  FastMCP — weather tool implementations
│  port 8001                  │  (geocoding, current weather, forecast, AQI, alerts)
└─────────────────────────────┘
           │ HTTPS
           ▼
     OpenWeatherMap API
```

**Auth model:** All services run under a dedicated service account (`weatherwise-run`). Vertex AI (Gemini) authentication uses Application Default Credentials (ADC) automatically — no JSON key file required on Cloud Run.

---

## GCP Resources

| Resource | Name/Value |
|---|---|
| GCP Project | `project-cf964f7d-d79b-4b69-81c` |
| Region | `us-central1` |
| Artifact Registry | `us-central1-docker.pkg.dev/project-cf964f7d-d79b-4b69-81c/weatherwise` |
| Service Account | `weatherwise-run@project-cf964f7d-d79b-4b69-81c.iam.gserviceaccount.com` |
| IAM Roles | `roles/aiplatform.user`, `roles/secretmanager.secretAccessor` |
| Secrets | `weatherwise-openweather-api-key`, `weatherwise-groq-api-key` |

---

## Code Changes Made for Cloud Run

Only two files were modified. Local Docker Compose behavior is completely unchanged.

### 1. `agent-backend/llm_provider.py`

**Problem:** The original code required `GOOGLE_APPLICATION_CREDENTIALS` (a JSON key file path) to be set, or it would raise an error on startup.

**Why this breaks on Cloud Run:** Cloud Run authenticates to Google APIs via Application Default Credentials (ADC) using the service account attached to the service. There is no JSON key file — it's handled automatically by the metadata server. So `GOOGLE_APPLICATION_CREDENTIALS` is always absent on Cloud Run.

**Fix:** Removed `GOOGLE_APPLICATION_CREDENTIALS` from the required-field validation. Only `VERTEX_PROJECT` is required for the Google provider. When `GOOGLE_APPLICATION_CREDENTIALS` is set (local dev), `langchain_google_vertexai` uses it automatically. When it's absent (Cloud Run), ADC kicks in.

```python
# Before
if _LLM_PROVIDER == "google" and (not _GOOGLE_APPLICATION_CREDENTIALS or not _VERTEX_PROJECT):
    raise ValueError("LLM_PROVIDER is 'google' but GOOGLE_APPLICATION_CREDENTIALS and/or VERTEX_PROJECT are not set.")

# After
if _LLM_PROVIDER == "google" and not _VERTEX_PROJECT:
    raise ValueError("LLM_PROVIDER is 'google' but VERTEX_PROJECT is not set.")
```

### 2. `agent-backend/main.py`

**Problem:** Port was hardcoded to `8000`.

**Why this matters on Cloud Run:** Cloud Run injects a `PORT` environment variable and expects the container to listen on it. While we use `--port=8000` which aligns with the hardcoded value, reading `PORT` is Cloud Run best practice and makes the service more flexible.

**Fix:**
```python
# Before
uvicorn.run(app, host="0.0.0.0", port=8000)

# After
port = int(os.getenv("PORT", 8000))
uvicorn.run(app, host="0.0.0.0", port=port)
```

---

## Deployment Script (`deploy.sh`)

A single script handles the full end-to-end deployment. Run it from the project root:

```bash
./deploy.sh
```

### What it does (in order):

1. **Creates Artifact Registry repo** — Docker image registry in `us-central1` (idempotent, safe to re-run)
2. **Configures Docker auth** — sets up `gcloud` as the credential helper for the registry
3. **Creates service account** — `weatherwise-run` with the minimum required IAM roles
4. **Stores secrets in Secret Manager** — reads `OPENWEATHER_API_KEY` and `GROQ_API_KEY` from `.env` and stores them as versioned secrets
5. **Builds and pushes `mcp-server` image** — `linux/amd64` platform (required for Cloud Run)
6. **Builds and pushes `agent-backend` image** — `linux/amd64` platform
7. **Deploys `mcp-server`** → captures its Cloud Run URL
8. **Deploys `agent-backend`** with `MCP_SERVER_URL` pointing to the live mcp-server → captures its URL
9. **Builds and pushes `frontend` image** — uses `--build-arg API_URL=<backend-url>` to bake the real backend URL into the Next.js build
10. **Deploys `frontend`** with the pre-baked backend URL

### Deployment order matters

The services have hard dependencies:
```
mcp-server → agent-backend (needs MCP_SERVER_URL) → frontend build (needs BACKEND_URL)
```
The script deploys them strictly in this order and captures each URL before proceeding.

---

## Challenges Encountered

### Challenge 1: Wrong Docker Image Architecture

**Symptom:**
```
terminated: Application failed to start: failed to load /usr/local/bin/python: exec format error
```

**Cause:** Docker Desktop on Apple Silicon (M1/M2/M3 Macs) builds images for `linux/arm64` by default. Cloud Run runs on `linux/amd64`. The binary format mismatch causes the container to fail immediately on startup — no code runs at all.

**Fix:** Added `--platform linux/amd64` to every `docker build` command:
```bash
docker build --platform linux/amd64 -f Dockerfile.mcp -t ...
```

**Lesson:** Always specify `--platform linux/amd64` when building images on Apple Silicon for any cloud deployment target.

---

### Challenge 2: `GOOGLE_APPLICATION_CREDENTIALS` Required on Cloud Run

**Symptom:** The `agent-backend` would crash at startup with:
```
ValueError: LLM_PROVIDER is 'google' but GOOGLE_APPLICATION_CREDENTIALS and/or VERTEX_PROJECT are not set.
```

**Cause:** The original validation check required both `GOOGLE_APPLICATION_CREDENTIALS` (a path to a local JSON key file) and `VERTEX_PROJECT`. On Cloud Run, ADC handles authentication transparently through the instance metadata server — there is no key file and no need to point to one.

**Fix:** Removed `GOOGLE_APPLICATION_CREDENTIALS` from the startup validation. Only `VERTEX_PROJECT` is required.

**Lesson:** Never require a JSON key file path in code that will run on Cloud Run. The service account attached to the Cloud Run service handles auth automatically via ADC.

---

### Challenge 3: Frontend Proxying to Docker Compose Hostname

**Symptom:**
```
Failed to proxy http://agent-backend:8000/api/chat/stream Error: getaddrinfo EAI_AGAIN agent-backend
```
The frontend could load, but every chat message returned a 500 error.

**Cause:** `next.config.ts` defines rewrites that proxy `/api/*` to the backend:
```typescript
destination: `${process.env.API_URL || "http://localhost:8000"}/api/:path*`
```
The `Dockerfile.frontend` sets a build-time default:
```dockerfile
ARG API_URL=http://agent-backend:8000
ENV API_URL=$API_URL
```
`agent-backend` is the Docker Compose service hostname — valid on a local Docker network, but not resolvable on Cloud Run.

The critical nuance: **Next.js `rewrites()` are evaluated at `next build` time** and compiled into `.next/routes-manifest.json`. Passing `API_URL` as a Cloud Run runtime environment variable has no effect — the URL is already baked into the static build artifact.

**Initial attempt (wrong):** Passing `--set-env-vars="API_URL=<backend-url>"` to `gcloud run deploy`. This sets a runtime env var, but Next.js rewrites are not re-evaluated at runtime in standalone mode.

**Fix:** Changed the deploy script to build the frontend image *after* the agent-backend is deployed and its URL is known, passing the real URL as a Docker build argument:
```bash
docker build --platform linux/amd64 -f Dockerfile.frontend \
  --build-arg API_URL="${BACKEND_URL}" \
  -t "${REGISTRY}/frontend:latest" .
```

This bakes the correct Cloud Run URL into the Next.js build, replacing the Docker Compose hostname.

**Lesson:** Understand what is resolved at build time vs runtime in your framework. Next.js rewrites in `next.config.ts` are build-time artifacts. Any URL they reference must be known at `next build` time.

---

## Verifying the Deployment

### 1. GCP Console
Navigate to **Cloud Run** in the GCP Console under project `project-cf964f7d-d79b-4b69-81c`. You should see all 3 services with green status indicators.

### 2. Check the live app
Open https://frontend-ybn6xfzrsa-uc.a.run.app and send a weather query (e.g. "What's the weather in Tokyo?"). A successful response confirms the full stack is working.

### 3. Check service health via CLI
```bash
# List all services and their URLs
gcloud run services list \
  --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c

# Check mcp-server SSE endpoint (should stream events)
curl https://weatherwise-agent-mcp-ybn6xfzrsa-uc.a.run.app/sse
```

### 4. View logs
```bash
# agent-backend logs (most useful for debugging)
gcloud run services logs read weatherwise-agent-backend \
  --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c \
  --limit=50

# frontend logs
gcloud run services logs read weatherwise-agent-frontend \
  --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c \
  --limit=50
```

---

## Re-deploying After Code Changes

Run `./deploy.sh` again from the project root. The script is fully idempotent — it safely re-creates or updates all resources.

For faster iteration when only one service changed:

**Only mcp-server changed:**
```bash
REGISTRY="us-central1-docker.pkg.dev/project-cf964f7d-d79b-4b69-81c/weatherwise"
docker build --platform linux/amd64 -f Dockerfile.mcp -t "${REGISTRY}/mcp-server:latest" . && \
docker push "${REGISTRY}/mcp-server:latest" && \
gcloud run deploy mcp-server --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c \
  --image="${REGISTRY}/mcp-server:latest" --quiet
```

**Only agent-backend changed:**
```bash
REGISTRY="us-central1-docker.pkg.dev/project-cf964f7d-d79b-4b69-81c/weatherwise"
docker build --platform linux/amd64 -f Dockerfile.agent -t "${REGISTRY}/agent-backend:latest" . && \
docker push "${REGISTRY}/agent-backend:latest" && \
gcloud run deploy agent-backend --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c \
  --image="${REGISTRY}/agent-backend:latest" --quiet
```

**Only frontend changed** (must rebuild with `--build-arg`):
```bash
REGISTRY="us-central1-docker.pkg.dev/project-cf964f7d-d79b-4b69-81c/weatherwise"
BACKEND_URL="https://agent-backend-ybn6xfzrsa-uc.a.run.app"
docker build --platform linux/amd64 -f Dockerfile.frontend \
  --build-arg API_URL="${BACKEND_URL}" \
  -t "${REGISTRY}/frontend:latest" . && \
docker push "${REGISTRY}/frontend:latest" && \
gcloud run deploy frontend --region=us-central1 \
  --project=project-cf964f7d-d79b-4b69-81c \
  --image="${REGISTRY}/frontend:latest" --quiet
```

---

## Local Development (Unchanged)

The Cloud Run deployment has zero impact on local development:

```bash
docker compose up
```

- `docker-compose.yml` — untouched
- `.env` — untouched
- `Dockerfile.mcp`, `Dockerfile.agent`, `Dockerfile.frontend` — untouched
- `GOOGLE_APPLICATION_CREDENTIALS` in `.env` — still works locally as before
