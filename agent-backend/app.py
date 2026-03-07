import logging
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from agent import run_agent, run_agent_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="WeatherWise Agent API",
    version="1.0.0",
    description=(
        "An AI-powered weather assistant API built with **LangGraph**, **MCP (Model Context Protocol)**, "
        "and **Google Vertex AI (Gemini 2.5 Flash)**.\n\n"
        "The agent reasons over real-time weather data from OpenWeatherMap via MCP tools and returns "
        "natural-language responses. Supports both single-shot and streaming (SSE) response modes.\n\n"
        "**Tools available to the agent:**\n"
        "- `geocode_location` — Resolve city names to coordinates\n"
        "- `get_current_weather` — Current temperature, conditions, wind, humidity\n"
        "- `get_forecast` — 5-day / 3-hour forecast\n"
        "- `get_air_quality` — AQI and PM2.5 levels\n"
        "- `get_weather_alerts` — Active NWS storm warnings\n\n"
        "**Fallback:** If the primary LLM (Vertex AI) fails, the agent automatically retries with Groq (Llama 4)."
    ),
    contact={
        "name": "Gaurav Singh",
        "url": "https://github.com/gavksingh/weatherwise-agent",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {
            "name": "Chat",
            "description": (
                "Send messages to the WeatherWise agent. Use **POST /api/chat** for a complete response "
                "or **GET /api/chat/stream** for token-by-token streaming via Server-Sent Events."
            ),
        },
        {
            "name": "System",
            "description": "Health and readiness checks for the agent backend.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_MESSAGE_LENGTH = 2000


class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: str
    content: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"role": "user", "content": "What's the weather in Tokyo?"},
                {"role": "assistant", "content": "Tokyo is currently 22°C with clear skies."},
            ]
        }
    }


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str
    history: list[ChatMessage] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Should I bring an umbrella in London today?",
                    "history": None,
                },
                {
                    "message": "What about tomorrow?",
                    "history": [
                        {"role": "user", "content": "What's the weather in London?"},
                        {"role": "assistant", "content": "London is currently 14°C with light rain."},
                    ],
                },
            ]
        }
    }

    @field_validator("message")
    @classmethod
    def message_must_be_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters")
        return v


class ChatResponse(BaseModel):
    """Response from the weather agent."""

    response: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "response": (
                        "Yes, bring an umbrella! London is currently 14°C with light rain "
                        "(2.1 mm/h) and 87% humidity. Rain is expected to continue through "
                        "the afternoon with 80% precipitation probability."
                    )
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    llm_provider: str
    version: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "service": "weatherwise-agent",
                    "llm_provider": "google (vertex ai)",
                    "version": "1.0.0",
                }
            ]
        }
    }


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Send a message to the weather agent",
    description=(
        "Send a natural-language question to the WeatherWise agent and receive a complete response.\n\n"
        "The agent will:\n"
        "1. Geocode any location mentioned in the message\n"
        "2. Call the relevant MCP weather tools (current weather, forecast, AQI, alerts)\n"
        "3. Synthesize the data into a clear, actionable response\n\n"
        "For real-time token streaming, use **GET /api/chat/stream** instead.\n\n"
        "**Validation:** Message must be non-empty and under 2000 characters."
    ),
    responses={
        200: {"description": "Agent response successfully generated"},
        422: {"description": "Validation error — message empty or too long"},
        500: {"description": "Agent or LLM error"},
    },
)
async def chat(request: ChatRequest):
    try:
        history = [m.model_dump() for m in request.history] if request.history else None
        response = await run_agent(request.message, history)
        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/api/chat/stream",
    tags=["Chat"],
    summary="Stream a response via Server-Sent Events",
    description=(
        "Stream the agent's response token by token using **Server-Sent Events (SSE)**.\n\n"
        "The response is delivered as a stream of SSE events:\n"
        "- `event: message` — A text chunk from the agent\n"
        "- `event: done` — Stream complete (empty data)\n"
        "- `event: error` — An error occurred (data contains the message)\n\n"
        "**Example (curl):**\n"
        "```bash\n"
        'curl -N "http://localhost:8000/api/chat/stream?message=What+is+the+AQI+in+Delhi"\n'
        "```\n\n"
        "**Validation:** Message must be non-empty and under 2000 characters."
    ),
    responses={
        200: {
            "description": "SSE stream of agent response chunks",
            "content": {
                "text/event-stream": {
                    "example": (
                        "event: message\ndata: The AQI in Delhi\n\n"
                        "event: message\ndata:  is currently 4 (Poor)\n\n"
                        "event: done\ndata: \n\n"
                    )
                }
            },
        },
        400: {"description": "Validation error — message empty or too long"},
    },
)
async def chat_stream(
    message: str = Query(
        ...,
        description="The weather question to ask the agent",
        examples=["What's the forecast for New York this weekend?"],
    ),
):
    message = message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters",
        )

    async def event_generator():
        try:
            async for chunk in run_agent_stream(message):
                yield {"event": "message", "data": chunk}
            yield {"event": "done", "data": ""}
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
    description=(
        "Returns the health status of the agent backend, the active LLM provider, and the API version.\n\n"
        "Use this to verify the service is running before making chat requests."
    ),
    responses={
        200: {"description": "Service is healthy"},
    },
)
async def health():
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    provider_label = "google (vertex ai)" if provider == "google" else provider
    return HealthResponse(
        status="healthy",
        service="weatherwise-agent",
        llm_provider=provider_label,
        version="1.0.0",
    )
