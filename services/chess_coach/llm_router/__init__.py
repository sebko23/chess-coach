"""LLM routing and OpenAI-compatible client abstraction."""
from . import config
from .router import LLMRouter, LLMUnavailableError

__all__ = ["LLMRouter", "LLMUnavailableError", "config"]
