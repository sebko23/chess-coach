"""Unit tests for ``services/chess_coach/llm_router/config.py``.

Per the BBF-FU-18-keyring-test decision brief
(``docs/16_audit/BBF-FU-18-keyring-test.md``): the refactored
``get_api_key()`` MUST delegate to ``chess_coach.secrets.get_secret``
so the A-F10 contract (OS-native keychain) is honored.
"""
from __future__ import annotations

from unittest.mock import patch

from chess_coach.llm_router import config


def test_get_api_key_delegates_to_secrets_module() -> None:
    """``get_api_key()`` calls ``chess_coach.secrets.get_secret`` with
    the correct name and forwards the ``dev_fallback`` argument.
    """
    with patch("chess_coach.llm_router.config.get_secret") as mock_get_secret:
        mock_get_secret.return_value = "sk-test-from-mock"
        result = config.get_api_key(dev_fallback=False)
    mock_get_secret.assert_called_once_with(
        "OPENROUTER_API_KEY", dev_fallback=False
    )
    assert result == "sk-test-from-mock"


def test_get_api_key_returns_empty_string_on_none() -> None:
    """``get_api_key()`` returns ``""`` when the secrets module returns
    ``None``. This preserves the existing contract (the route at
    ``services/chess_coach/llm_router/router.py:32`` checks for
    falsy and returns a 503 when the key is empty).
    """
    with patch("chess_coach.llm_router.config.get_secret") as mock_get_secret:
        mock_get_secret.return_value = None
        result = config.get_api_key(dev_fallback=False)
    assert result == ""


def test_get_api_key_dev_fallback_defaults_to_true() -> None:
    """The default ``dev_fallback=True`` preserves dev-mode convenience.

    Production code paths must pass ``dev_fallback=False`` explicitly
    to enforce the keyring-only contract (per the
    ``--dev-secrets`` CLI flag in
    ``services/chess_coach/gateway/__main__.py``).
    """
    with patch("chess_coach.llm_router.config.get_secret") as mock_get_secret:
        mock_get_secret.return_value = "sk-default-dev"
        config.get_api_key()
    mock_get_secret.assert_called_once_with(
        "OPENROUTER_API_KEY", dev_fallback=True
    )
