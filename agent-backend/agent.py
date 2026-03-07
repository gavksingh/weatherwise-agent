import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession

from llm_provider import get_fallback_llm, get_llm
from mcp_client import create_mcp_session, get_mcp_tools
from prompts import WEATHER_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _unwrap_exception(exc: Exception) -> Exception:
    """Recursively unwrap ExceptionGroup to extract the root-cause exception."""
    if hasattr(exc, "exceptions") and exc.exceptions:
        return _unwrap_exception(exc.exceptions[0])
    return exc


def _extract_text(content) -> str:
    """Extract text from AIMessageChunk content (str or list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return ""


async def _stream_agent_chunks(agent, messages) -> AsyncGenerator[str, None]:
    """Yield only final AI text chunks from an agent stream."""
    async for chunk_msg, metadata in agent.astream(
        {"messages": messages},
        stream_mode="messages",
    ):
        if (
            isinstance(chunk_msg, AIMessageChunk)
            and metadata.get("langgraph_node") == "agent"
        ):
            text = _extract_text(chunk_msg.content)
            if text:
                yield text


async def run_agent(user_message: str, chat_history: list[dict] | None = None) -> str:
    """Run the weather agent and return the final response.

    Args:
        user_message: The user's question.
        chat_history: Optional list of {"role": "user"|"assistant", "content": "..."} dicts.

    Returns:
        The agent's text response.
    """
    async with create_mcp_session() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await get_mcp_tools(session)

            llm = get_llm()
            agent = create_react_agent(llm, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)

            messages = _build_messages(user_message, chat_history)

            try:
                result = await agent.ainvoke({"messages": messages})
                return _extract_response(result)
            except Exception as e:
                cause = _unwrap_exception(e)
                logger.warning(f"Primary LLM failed: {cause}, trying fallback")
                fallback = get_fallback_llm()
                if fallback is None:
                    raise
                agent = create_react_agent(fallback, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)
                result = await agent.ainvoke({"messages": messages})
                return _extract_response(result)


async def run_agent_stream(user_message: str, chat_history: list[dict] | None = None) -> AsyncGenerator[str, None]:
    """Run the weather agent and stream the response token by token.

    Only streams tokens from the final answer, not intermediate tool-calling steps.
    Yields text chunks as they become available. Falls back to a secondary LLM on failure.
    """
    try:
        async with create_mcp_session() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await get_mcp_tools(session)

                llm = get_llm()
                agent = create_react_agent(llm, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)

                messages = _build_messages(user_message, chat_history)

                try:
                    async for chunk in _stream_agent_chunks(agent, messages):
                        yield chunk
                    return
                except Exception as e:
                    cause = _unwrap_exception(e)
                    logger.warning(f"Primary LLM stream failed: {cause}, trying fallback")

                fallback = get_fallback_llm()
                if fallback is None:
                    yield f"\n\nSorry, something went wrong while generating the response: {cause}"
                    return

                logger.info("Switching to fallback model for this request")
                agent = create_react_agent(fallback, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)
                async for chunk in _stream_agent_chunks(agent, messages):
                    yield chunk
    except Exception as e:
        cause = _unwrap_exception(e)
        logger.error(f"Stream error: {cause}")
        yield f"\n\nSorry, something went wrong while generating the response: {cause}"


def _build_messages(user_message: str, chat_history: list[dict] | None) -> list:
    """Convert chat history + new message into LangChain message objects."""
    messages = []
    if chat_history:
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_message))
    return messages


def _extract_response(result: dict) -> str:
    """Extract the final text response from the agent result."""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return _extract_text(msg.content)
    return "I wasn't able to generate a response. Please try again."
