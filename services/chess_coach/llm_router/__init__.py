"""LLM routing and OpenAI-compatible client abstraction."""
from .router import LLMRouter, LLMUnavailableError
from . import config

__all__ = ["LLMRouter", "LLMUnavailableError", "config"]
