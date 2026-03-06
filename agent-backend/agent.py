import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession

from llm_provider import get_fallback_llm, get_llm
from mcp_client import create_mcp_session, get_mcp_tools
from prompts import WEATHER_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


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
                logger.warning(f"Primary LLM failed: {e}, trying fallback")
                fallback = get_fallback_llm()
                if fallback is None:
                    raise
                agent = create_react_agent(fallback, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)
                result = await agent.ainvoke({"messages": messages})
                return _extract_response(result)


async def run_agent_stream(user_message: str, chat_history: list[dict] | None = None) -> AsyncGenerator[str, None]:
    """Run the weather agent and stream the response token by token.

    Yields text chunks as they become available.
    """
    try:
        async with create_mcp_session() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await get_mcp_tools(session)

                llm = get_llm()
                agent = create_react_agent(llm, tools, prompt=WEATHER_AGENT_SYSTEM_PROMPT)

                messages = _build_messages(user_message, chat_history)

                async for event in agent.astream_events(
                    {"messages": messages},
                    version="v2",
                ):
                    kind = event.get("event")
                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                            yield chunk.content
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"\n\nSorry, something went wrong while generating the response: {e}"


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
            return msg.content
    return "I wasn't able to generate a response. Please try again."
