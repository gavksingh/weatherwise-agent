# Prompts Used to Build WeatherWise Agent

## Prompt 1: Project Scaffolding

> Read the current project structure. I need a complete scaffolding for WeatherWise Agent.
> Make sure these ALL exist:
> mcp-server/__init__.py, server.py, config.py, schemas.py, requirements.txt, tests/__init__.py, tests/conftest.py, tests/test_server.py
> agent-backend/__init__.py, app.py, agent.py, llm_provider.py, mcp_client.py, prompts.py, requirements.txt, tests/__init__.py, tests/test_app.py, tests/test_agent.py
> frontend/ (empty dir)
> .env, .env.example, .gitignore, README.md, PROMPTS.md, ARCHITECTURE.md
> Dockerfile.mcp, Dockerfile.agent, Dockerfile.frontend, docker-compose.yml

### What I modified
- Created 22 missing files across all directories
- Set up `.env` with placeholder keys, `.env.example` with descriptive comments
- `.gitignore` covering Python, Node.js, env files, IDE configs, and OS artifacts
- Empty `__init__.py` files making packages importable
- Skeleton test directories with `conftest.py` for mcp-server

## Prompt 2: MCP Server Implementation

> Read mcp-server/server.py and fix/complete it. Here are the exact API endpoints:
> Tool 1 geocode_location, Tool 2 get_current_weather, Tool 3 get_forecast,
> Tool 4 get_air_quality, Tool 5 get_weather_alerts
> All tools: async with httpx.AsyncClient(), try/except returning {"error": str(e)}.
> Bottom: mcp.run(transport="stdio"). Also make sure schemas.py has Pydantic models
> and config.py loads env vars properly.

### What I modified
- `server.py`: Implemented 5 async MCP tools wrapping OpenWeatherMap API endpoints with full error handling
- `schemas.py`: Created Pydantic models (GeoLocation, CurrentWeather, Forecast, ForecastEntry, AirQuality, AirQualityComponents, WeatherAlert, WeatherAlerts)
- `config.py`: Environment variable loading with `load_dotenv(dotenv_path="../.env")`, httpx client factory, AQI label mapping
- Transport set to `stdio` for local development

## Prompt 3: Agent Backend Code Audit and Fixes

> Read all files in agent-backend/. Audit and report on error handling,
> missing validation, hardcoded secrets, and production crash risks.
> Then fix: mcp_client.py connection handling and dead code removal,
> app.py input validation.

### What I modified
- `mcp_client.py`: Removed unused `subprocess` import and dead `args_schema_dict` code block. Added `ConnectionError` with clear messages when MCP server script is missing or connection fails. Later updated to support dual transport (stdio for local, SSE via `MCP_SERVER_URL` for Docker)
- `app.py`: Added `field_validator` on `ChatRequest.message` rejecting empty/whitespace strings and enforcing 2000-character max length. Added `Query(...)` validation on the stream endpoint with matching empty/length checks
- `llm_provider.py` (IDE fix): Added module-level validation raising `ValueError` if both API keys are missing, and per-provider key checks
- `prompts.py` (IDE fix): Added 3 multi-step reasoning few-shot examples (outdoor exercise, weekend forecast, severe weather)
- `agent.py` (IDE fix): Added try/except with error message in `run_agent_stream`

## Prompt 4: Test Suite

> Read agent-backend/tests/ and agent-backend/ code. Fix all failing tests.
> Make sure mocks match actual function signatures. Add pytest, pytest-asyncio,
> httpx to requirements.txt. Run: cd agent-backend && python -m pytest tests/ -v
> All must pass.

### What I modified
- `tests/conftest.py`: Created with dummy env vars (`GOOGLE_API_KEY`, `GROQ_API_KEY`, `LLM_PROVIDER`) set before test imports, preventing `llm_provider.py` module-level validation from failing
- `requirements.txt`: Added `pytest`, `pytest-asyncio`, `httpx` as test dependencies
- All 17 tests passing: 7 in `test_agent.py` (message building, response extraction), 10 in `test_app.py` (health, validation, success/error mocking)

## Prompt 5: Frontend Audit and Fixes

> Read all files in frontend/src/. Audit SSE streaming, auto-scroll, typing indicator,
> input validation, dark mode, accessibility, hardcoded URLs, error handling,
> keyboard submit, and dead code.
> Then fix: Remove unused inputRef, add aria-hidden="true" to all SVG icons.

### What I modified
- `page.tsx`: Added `aria-hidden="true"` to both SVG elements (welcome cloud icon and send button arrow icon). The `inputRef` removal and other accessibility fixes (aria-labels, `role="log"`, `aria-live="polite"`, mid-stream error handling) were already applied by the IDE
- `next.config.ts` (pre-existing): Confirmed `/api/*` rewrite proxy to backend is correctly configured
- `globals.css` (pre-existing): Custom dark color palette with scrollbar styling

## Prompt 6: Docker and Documentation Audit

> Read docker-compose.yml, all Dockerfiles, README.md, and ARCHITECTURE.md.
> Audit networking, depends_on, layer caching, .dockerignore, security, and docs.
> Then fix: Add healthcheck to agent-backend, update frontend depends_on
> to use condition: service_healthy.

### What I modified
- `docker-compose.yml`: Added healthcheck on `agent-backend` service hitting `/api/health` endpoint. Changed frontend `depends_on` from simple dependency to `condition: service_healthy` so it waits for the backend to be fully ready
- `Dockerfile.mcp`, `Dockerfile.agent`, `Dockerfile.frontend` (pre-existing): Confirmed layer caching (requirements first, then source), multi-stage build for frontend with non-root user
- `README.md`, `ARCHITECTURE.md` (pre-existing): Confirmed step-by-step instructions, env var table, project structure, design decision rationale
