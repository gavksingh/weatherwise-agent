import os

# Set dummy API keys BEFORE any test module imports trigger
# llm_provider.py's module-level validation.
os.environ.setdefault("GOOGLE_API_KEY", "test-google-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("LLM_PROVIDER", "google")
