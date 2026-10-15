"""OpenRouter configuration.

Reads ``OPENROUTER_API_KEY`` from the OS-native keychain via
``chess_coach.secrets.get_secret()``. The keyring path is the
production code path (A-F10 contract per
``docs/08_security/security-strategy.md:50-55``). A plaintext
environment-variable fallback is enabled by default for dev-mode
convenience; production code paths should pass
``dev_fallback=False`` to enforce the keyring-only contract.
"""
from __future__ import annotations

from chess_coach.keychain import get_secret


# Key is read lazily at call time via get_api_key() to avoid import-time capture
def get_api_key(*, dev_fallback: bool = True) -> str:
    return get_secret("OPENROUTER_API_KEY", dev_fallback=dev_fallback) or ""

OPENROUTER_API_KEY = ""  # deprecated — use get_api_key()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Change this single line to switch models during benchmarking.
PRIMARY_MODEL: str = "z-ai/glm-5.2"
# Within-family fallback: same prompt format, tokenizer, tagging conventions.
FALLBACK_MODEL: str = "z-ai/glm-4.5-air"
PRIMARY_TIMEOUT: float = 60.0
FALLBACK_TIMEOUT: float = 60.0
