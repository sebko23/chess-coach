"""Advisory corpus-version validation shared by gold corpus loaders."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def warn_on_version_mismatch(
    raw: dict[str, Any],
    requested_version: str,
    corpus_path: Path,
    *,
    corpus_name: str,
) -> None:
    """Warn when corpus metadata does not match the requested version.

    BBF-86.7 deliberately uses advisory validation. A mismatch is a
    deployment diagnostic, not a refusal: production callers may still
    need the available corpus, and refusing would turn version drift into
    an availability failure.
    """
    metadata = raw.get("_metadata")
    if not isinstance(metadata, dict):
        logger.warning(
            "%s version is unverifiable: requested %r but %s has no "
            "_metadata object",
            corpus_name,
            requested_version,
            corpus_path,
        )
        return

    corpus_version = metadata.get("version")
    if corpus_version is None:
        logger.warning(
            "%s version is missing: requested %r but %s has no "
            "_metadata.version",
            corpus_name,
            requested_version,
            corpus_path,
        )
        return
    if not isinstance(corpus_version, str):
        logger.warning(
            "%s version is malformed: requested %r but %s reports "
            "_metadata.version=%r",
            corpus_name,
            requested_version,
            corpus_path,
            corpus_version,
        )
        return
    if corpus_version != requested_version:
        logger.warning(
            "%s version mismatch: requested %r but %s reports "
            "_metadata.version=%r",
            corpus_name,
            requested_version,
            corpus_path,
            corpus_version,
        )


__all__ = ["warn_on_version_mismatch"]
