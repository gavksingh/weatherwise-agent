import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sse_starlette.sse import EventSourceResponse

from agent import run_agent, run_agent_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WeatherWise Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_MESSAGE_LENGTH = 2000


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None

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
    response: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the weather agent and get a complete response."""
    try:
        response = await run_agent(request.message, request.history)
        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/stream")
async def chat_stream(message: str = Query(...)):
    """Stream a response from the weather agent via Server-Sent Events.

    Query params:
        message: The user's question.
    """
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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "weatherwise-agent"}
