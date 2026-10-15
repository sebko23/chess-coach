"""Unit tests for ``services/chess_coach/log_redaction.py`` (A-F10 contract).

Per ``docs/08_security/security-strategy.md:55``:
"Secrets are NEVER logged. A redaction filter wraps the logger
and replaces matched key patterns with ``***``."

These tests verify the redactor handles the secret patterns we
actually emit in this codebase (OpenRouter, OpenAI, GitHub PAT,
Lichess PAT, xAI) and does NOT redact benign strings that happen
to share a prefix.
"""
from __future__ import annotations

import logging

from chess_coach.log_redaction import SecretRedactionFilter


def test_redactor_replaces_sk_prefix() -> None:
    """An OpenAI/OpenRouter-style ``sk-...`` key in a log message
    is replaced with the redaction marker.
    """
    redactor = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Loaded API key sk-abc123def456ghi789jkl012mno",
        args=(),
        exc_info=None,
    )
    redactor.filter(record)
    assert record.getMessage() == "Loaded API key ***REDACTED***"
    assert "sk-abc123" not in record.getMessage()


def test_redactor_replaces_github_pat_prefix() -> None:
    """A ``ghp_...`` GitHub PAT is replaced."""
    redactor = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Authorizing with ghp_abc123def456ghi789jkl",
        args=(),
        exc_info=None,
    )
    redactor.filter(record)
    assert "ghp_abc123" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_redactor_replaces_lichess_pat_prefix() -> None:
    """A ``lip_...`` Lichess PAT is replaced."""
    redactor = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Lichess auth: lip_abc123def456ghi789jkl",
        args=(),
        exc_info=None,
    )
    redactor.filter(record)
    assert "lip_abc123" not in record.getMessage()


def test_redactor_does_not_redact_benign_strings() -> None:
    """A normal string that happens to contain ``sk-`` as a substring
    is NOT redacted if the surrounding pattern doesn't match a
    known secret format.

    Example: a comment that mentions "sketch" or "skate" or a
    short prefix ``sk-`` followed by fewer than 20 characters.
    """
    redactor = SecretRedactionFilter()
    # Short prefix (not a real key) — should NOT be redacted.
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="User typed 'sk-' to start sketching",
        args=(),
        exc_info=None,
    )
    redactor.filter(record)
    assert record.getMessage() == "User typed 'sk-' to start sketching"


def test_redactor_handles_args_substitution() -> None:
    """A secret passed via ``logger.info("...%s", secret)`` is
    redacted in the formatted output.

    Per A-F10: secrets are NEVER logged. The redactor runs on the
    ``getMessage()`` output, which performs the ``%s``
    substitution, so secrets that arrive via args are still
    caught.
    """
    redactor = SecretRedactionFilter()
    secret = "sk-test-arg12345abcdef678901234"
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Loaded key: %s",
        args=(secret,),
        exc_info=None,
    )
    redactor.filter(record)
    assert secret not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()
