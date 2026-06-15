"""OpenRouter configuration.

Reads OPENROUTER_API_KEY from environment (with dotenv support at app startup).
"""
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Change this single line to switch models during benchmarking.
PRIMARY_MODEL: str = "nousresearch/hermes-3-llama-3.1-405b:free"
# Within-family fallback: same prompt format, tokenizer, tagging conventions.
FALLBACK_MODEL: str = "nousresearch/hermes-3-llama-3.1-405b:free"
PRIMARY_TIMEOUT: float = 60.0
FALLBACK_TIMEOUT: float = 60.0
