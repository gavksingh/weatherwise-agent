import os
import logging

from dotenv import load_dotenv
from langchain_google_vertexai import ChatVertexAI
from langchain_groq import ChatGroq

load_dotenv(dotenv_path="../.env")

logger = logging.getLogger(__name__)

_GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
_VERTEX_PROJECT = os.getenv("VERTEX_PROJECT")
_VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
_GROQ_API_KEY = os.getenv("GROQ_API_KEY")

_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google").lower()

if _LLM_PROVIDER == "google" and (not _GOOGLE_APPLICATION_CREDENTIALS or not _VERTEX_PROJECT):
    raise ValueError(
        "LLM_PROVIDER is 'google' but GOOGLE_APPLICATION_CREDENTIALS and/or "
        "VERTEX_PROJECT are not set."
    )
if _LLM_PROVIDER == "groq" and not _GROQ_API_KEY:
    raise ValueError("LLM_PROVIDER is 'groq' but GROQ_API_KEY is not set.")

if not (_GOOGLE_APPLICATION_CREDENTIALS and _VERTEX_PROJECT) and not _GROQ_API_KEY:
    raise ValueError(
        "At least one LLM provider must be configured. "
        "Set GOOGLE_APPLICATION_CREDENTIALS + VERTEX_PROJECT and/or GROQ_API_KEY in your .env file."
    )

PROVIDERS = {
    "google": {
        "class": ChatVertexAI,
        "kwargs": {
            "model_name": "gemini-2.5-flash",
            "project": _VERTEX_PROJECT,
            "location": _VERTEX_LOCATION,
        },
    },
    "groq": {
        "class": ChatGroq,
        "kwargs": {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
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
