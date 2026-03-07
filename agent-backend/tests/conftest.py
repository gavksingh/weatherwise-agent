import os

# Set dummy credentials BEFORE any test module imports trigger
# llm_provider.py's module-level validation.
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/test-credentials.json")
os.environ.setdefault("VERTEX_PROJECT", "test-project")
os.environ.setdefault("VERTEX_LOCATION", "us-central1")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("LLM_PROVIDER", "google")
