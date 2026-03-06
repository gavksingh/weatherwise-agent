import os
import logging

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

load_dotenv(dotenv_path="../.env")

logger = logging.getLogger(__name__)

_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
_GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not _GOOGLE_API_KEY and not _GROQ_API_KEY:
    raise ValueError(
        "At least one LLM API key is required. "
        "Set GOOGLE_API_KEY and/or GROQ_API_KEY in your .env file."
    )

_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google").lower()
if _LLM_PROVIDER == "google" and not _GOOGLE_API_KEY:
    raise ValueError("LLM_PROVIDER is 'google' but GOOGLE_API_KEY is not set.")
if _LLM_PROVIDER == "groq" and not _GROQ_API_KEY:
    raise ValueError("LLM_PROVIDER is 'groq' but GROQ_API_KEY is not set.")

PROVIDERS = {
    "google": {
        "class": ChatGoogleGenerativeAI,
        "kwargs": {
            "model": "gemini-2.5-flash",
            "google_api_key": _GOOGLE_API_KEY,
        },
    },
    "groq": {
        "class": ChatGroq,
        "kwargs": {
            "model": "llama-3.3-70b-versatile",
            "groq_api_key": _GROQ_API_KEY,
        },
    },
}

FALLBACK_ORDER = {
    "google": "groq",
    "groq": "google",
}


def _create_llm(provider_name: str):
    """Create an LLM instance for the given provider."""
    config = PROVIDERS[provider_name]
    return config["class"](**config["kwargs"])


def get_llm():
    """Get an LLM instance based on LLM_PROVIDER env var.

    Returns the primary provider. If it fails at call time, use get_llm_with_fallback
    to automatically try the fallback.
    """
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Must be one of: {list(PROVIDERS.keys())}")
    return _create_llm(provider)


def get_fallback_llm():
    """Get the fallback LLM (the other provider)."""
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    fallback = FALLBACK_ORDER.get(provider)
    if not fallback:
        return None
    try:
        return _create_llm(fallback)
    except Exception as e:
        logger.warning(f"Could not create fallback LLM ({fallback}): {e}")
        return None


async def invoke_with_fallback(primary_llm, messages, fallback_llm=None, **kwargs):
    """Invoke the primary LLM; if it fails, try the fallback."""
    try:
        return await primary_llm.ainvoke(messages, **kwargs)
    except Exception as e:
        if fallback_llm is None:
            raise
        logger.warning(f"Primary LLM failed ({e}), falling back to secondary provider")
        return await fallback_llm.ainvoke(messages, **kwargs)
