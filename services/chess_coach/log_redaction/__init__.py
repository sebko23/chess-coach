"""Log-output secret redaction.

Per A-F10 (``docs/08_security/security-strategy.md:55``):
"Secrets are NEVER logged. A redaction filter wraps the logger
and replaces matched key patterns with ``***``."

This module provides a ``logging.Filter`` that scans every log
record's formatted message for known secret-bearing patterns and
replaces the secret value with ``***REDACTED***``. The filter is
applied at the logger level (via ``addFilter`` on each logger that
might emit secrets) or at the handler level (via ``addFilter`` on
the StreamHandler that writes to stdout/stderr).

The pattern set is intentionally narrow: only the patterns we
actually emit in this codebase (OpenRouter-style API keys, Lichess
PATs, our own ``OPENROUTER_API_KEY=sk-...`` form) are redacted.
Wider pattern sets have false-positive costs (redacting strings
that are not secrets, e.g. a base64-encoded body of a Lichess game
that happens to start with ``sk-``).
"""
from __future__ import annotations

import logging
import re

# Patterns we redact:
#   - sk-... (OpenAI / OpenRouter / similar API key prefix)
#   - ghp_... / gho_... / ghu_... / ghs_... (GitHub PAT prefixes)
#   - lip_... (Lichess PAT prefix)
#   - xai-... (xAI API key prefix)
#
# The pattern is matched anywhere in the formatted log message.
# We replace the secret with `***REDACTED***` to make redaction
# visible (a literal `***` is more subtle and could be missed by
# an operator scanning logs).
_REDACT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"ghu_[A-Za-z0-9]{20,}"),
    re.compile(r"ghs_[A-Za-z0-9]{20,}"),
    re.compile(r"lip_[A-Za-z0-9]{20,}"),
    re.compile(r"xai-[A-Za-z0-9_-]{20,}"),
)
_REDACTION = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    """A ``logging.Filter`` that redacts known secret patterns in
    the formatted log message.

    Per A-F10 contract: secrets are NEVER logged. This filter is
    defense-in-depth: code that calls ``logger.info("...%s", key)``
    will still have the secret value rendered into the log record
    by Python's logging machinery, and the redactor strips it
    before the record reaches a handler.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the formatted message (after %-formatting).
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — logging filter must never raise
            return True
        redacted = msg
        for pattern in _REDACT_PATTERNS:
            redacted = pattern.sub(_REDACTION, redacted)
        if redacted != msg:
            # Replace the formatted message. The args are left alone
            # (they are still in record.args) but the formatted
            # output is now safe.
            record.msg = redacted
            record.args = ()
        return True  # always allow the record; we only mutate it


def install_default_redaction() -> None:
    """Install the redactor on the root logger.

    Idempotent: checks for the filter's identity before adding
    (logging.Filter does not define __eq__, so we use ``is``).
    """
    redactor = SecretRedactionFilter()
    root = logging.getLogger()
    for existing in root.filters:
        if isinstance(existing, SecretRedactionFilter):
            return  # already installed
    root.addFilter(redactor)
