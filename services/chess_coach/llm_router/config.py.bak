"""OpenRouter configuration.

Reads OPENROUTER_API_KEY from environment (with dotenv support at app startup).
"""
import os

# Key is read lazily at call time via get_api_key() to avoid import-time capture
def get_api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")

OPENROUTER_API_KEY = ""  # deprecated — use get_api_key()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Change this single line to switch models during benchmarking.
PRIMARY_MODEL: str = "z-ai/glm-5.2"
# Within-family fallback: same prompt format, tokenizer, tagging conventions.
FALLBACK_MODEL: str = "z-ai/glm-4.5-air"
PRIMARY_TIMEOUT: float = 60.0
FALLBACK_TIMEOUT: float = 60.0
