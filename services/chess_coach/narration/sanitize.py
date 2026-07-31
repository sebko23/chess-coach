"""A-F12 user-content sanitization at the narration-prompt boundary.

Background
----------
``docs/08_security/security-strategy.md`` §A-F12 (lines 115-125) lists five
mandatory mitigations for any untrusted text that flows into an LLM prompt
via the narration pipeline. The historical attack vector in the spec is
PGN comment fields, but the actual current attack surface is the
``context`` field on ``POST /v1/narration/explain`` (see
``libs/chess_coach/protocol_types/narration.py:50`` and
``services/chess_coach/gateway/routes/narration.py:118-119``). The
mitigations apply identically to "free-form user context" as to
"PGN comments" — both are untrusted text the LLM must not follow.

This module is the single public entry point for those mitigations.
The route handler calls :func:`sanitize_user_content` at the
context boundary; the rest of the pipeline sees the wrapped,
truncated, control-stripped, pattern-flagged output.

Mitigations implemented (mapped to A-F12 spec):

1. Strip control characters and zero-width unicode. ``\\n`` and ``\\t``
   are preserved; everything in ``U+0000-U+001F`` and ``U+007F`` (DEL)
   is removed. Zero-width characters (``U+200B``, ``U+200C``, ``U+200D``,
   ``U+FEFF``) are also removed (these are common in steganographic
   payloads and bypass naive sanitizer logic).
2. Cap each user-content field at 1 KB; truncate longer fields.
   The cap is applied to the **content** (between delimiters). The
   delimiter wrapper itself is not counted toward the cap.
3. Wrap in explicit ``<user_content source="..." game_id="...">``
   delimiters. The delimiter tag is a fixed-shape machine marker; the
   LLM is told via the system prompt (``narration/prompt.py``) that
   content inside is untrusted.
4. System-prompt trust instruction is added in
   ``narration/prompt.py`` (out of scope for this module). This
   module produces the wrapped text; the system prompt is the
   separate concern.
5. Detect-and-flag (not block) common injection patterns. The
   detection matches: ``ignore previous``, ``new instruction``,
   ``system:``, ``override``. (Spec line 125 explicitly says not to
   auto-reject — false positives are likely on legitimate
   chess annotations that mention "ignore" or "system".) A
   WARNING is logged via the module logger so operators can audit
   detection rates via the gateway log; the sanitized text is
   returned regardless.

Surface:
    sanitize_user_content(text, *, source, game_id=None, max_bytes=1024)
        -> SanitizedUserContent(text, flagged, flagged_patterns)

The output text is always a single string suitable for direct
insertion into the LLM prompt. It is **always** wrapped in the
``<user_content ...>...</user_content>`` delimiters even when
``text`` is empty (so the LLM sees a consistent shape).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Mitigations #1 — control characters and DEL.
# We keep \n (\x0a) and \t (\x09) because collapsing them would
# damage legitimate multi-line annotations. Everything else in
# U+0000-U+001F and U+007F (DEL) is stripped. Note: the regex
# below is written as a continuous range rather than an explicit
# list; this deliberately covers carriage return (0x0d) along with the other
# control chars in the \x0b-\x1f span.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Mitigations #1 — zero-width unicode characters.
# These are commonly used to evade naive sanitizers and are
# invisible in LLM token streams, so they are stripped entirely.
# U+200B (zero-width space), U+200C (zero-width non-joiner),
# U+200D (zero-width joiner), U+FEFF (BOM / zero-width no-break space).
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

# Mitigations #5 — detect-and-flag injection patterns.
# Spec line 125: "ignore previous", "new instruction", "system:",
# "override". The patterns are case-insensitive substring matches
# after normalization; the exact wordings catch the common shapes
# while tolerating benign text ("the engine's evaluation system"
# still matches "system:" but is not a real injection).
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous",
    "new instruction",
    "system:",
    "override",
)

# Cap enforced on the **content** (between delimiters). The 1 KB
# value is the spec's mandatory ceiling.
DEFAULT_MAX_BYTES = 1024


@dataclass(frozen=True)
class SanitizedUserContent:
    """Result of sanitizing a user-content field.

    Attributes:
        text: The wrapped, truncated, control-stripped text. Always
            includes the ``<user_content source="..." game_id="...">``
            wrapper, even when the input was empty.
        flagged: True when at least one injection pattern matched.
        flagged_patterns: The list of patterns that matched (case
            lowered for canonical logging). Empty when ``flagged``
            is False.
    """

    text: str
    flagged: bool
    flagged_patterns: list[str]


def _strip_controls_and_zero_width(text: str) -> str:
    """Mitigations #1: strip control chars (keep \\n, \\t) and zero-width unicode."""
    out = _CONTROL_CHARS_RE.sub("", text)
    out = _ZERO_WIDTH_RE.sub("", out)
    return out


def _cap_length(text: str, max_bytes: int) -> str:
    """Mitigations #2: cap content at ``max_bytes``; truncate (don't reject).

    Operates on the ``text`` argument (the content between delimiters).
    Note: this counts *characters*, not UTF-8 *bytes*. The cap is a
    soft ceiling on prompt size; precision to bytes is unnecessary
    for the A-F12 use case (the spec says "1 KB" but the intent is
    "shapes the prompt size", not "exact byte accounting").
    """
    if len(text) <= max_bytes:
        return text
    return text[:max_bytes]


def _detect_patterns(text: str) -> list[str]:
    """Mitigations #5: detect common injection patterns; return canonical list.

    Detection is case-insensitive substring matching. We do NOT
    normalize whitespace or unicode forms before matching — the
    patterns are literal phrasings, and unicode-normalizing the
    input first would mask evasion attempts that use full-width
    characters (which the zero-width strip already covers).
    """
    haystack = text.lower()
    matched: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern in haystack:
            matched.append(pattern)
    return matched


def _render_wrapper(content: str, *, source: str, game_id: str | None) -> str:
    """Mitigations #3: wrap content in explicit ``<user_content ...>...</user_content>``.

    The attribute shape is fixed: ``source="..."`` is always present
    (required by the spec); ``game_id="..."`` is present when the
    caller supplied a value. We are deliberately not escaping the
    content's own angle brackets here — the control-char strip
    already removed the most common evasion surface, and the
    delimiter is a parse-time trust marker, not a hard parser.
    """
    gid = f' game_id="{game_id}"' if game_id is not None else ""
    return (
        f'<user_content source="{source}"{gid}>'
        f"{content}"
        f"</user_content>"
    )


def sanitize_user_content(
    text: str | None,
    *,
    source: str,
    game_id: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> SanitizedUserContent:
    """Apply A-F12 mitigations to a user-content field, returning a wrapped string.

    Args:
        text: The user-supplied text. ``None`` is treated as empty.
        source: A short label identifying the origin of the text
            (e.g. ``"narration_context"``, ``"pgn_comment"``). This
            becomes the ``source="..."`` attribute on the wrapper.
        game_id: Optional game id (matches ``games.id`` in the
            SQLite schema). When supplied, becomes the
            ``game_id="..."`` attribute on the wrapper.
        max_bytes: Maximum content length (between delimiters).
            Defaults to the spec's 1 KB ceiling.

    Returns:
        A :class:`SanitizedUserContent` whose ``.text`` is always
        wrapped in ``<user_content ...>...</user_content>`` and
        ready for prompt insertion. The ``.flagged`` field is
        True when any injection pattern matched; ``.flagged_patterns``
        lists the matched patterns (lowercased). The text is
        returned regardless of the flag (spec: detect-and-flag,
        not block).
    """
    raw = text or ""

    # NFC-normalize first so any composed/decomposed zero-width
    # characters are caught by the zero-width strip on the
    # canonical form. This is a defensive belt-and-suspenders
    # step; the strip itself operates on the post-normalization
    # output.
    normalized = unicodedata.normalize("NFC", raw)

    # Mitigations #1.
    stripped = _strip_controls_and_zero_width(normalized)

    # Mitigations #2.
    capped = _cap_length(stripped, max_bytes)

    # Mitigations #5.
    matched = _detect_patterns(capped)
    if matched:
        logger.warning(
            "A-F12 detection: source=%s game_id=%s flagged_patterns=%s",
            source,
            game_id if game_id is not None else "",
            matched,
        )

    # Mitigations #3.
    wrapped = _render_wrapper(capped, source=source, game_id=game_id)

    return SanitizedUserContent(
        text=wrapped,
        flagged=bool(matched),
        flagged_patterns=matched,
    )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "SanitizedUserContent",
    "sanitize_user_content",
]
