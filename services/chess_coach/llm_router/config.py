"""OpenRouter configuration.

Reads OPENROUTER_API_KEY from environment (with dotenv support at app startup).
"""
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Change this single line to switch models during benchmarking.
PRIMARY_MODEL: str = "anthropic/claude-sonnet-4-5"
FALLBACK_MODEL: str = "openai/gpt-4o-mini"
PRIMARY_TIMEOUT: float = 60.0
FALLBACK_TIMEOUT: float = 60.0
