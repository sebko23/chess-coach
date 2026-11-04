"""Storage primitives for the per-player Polyglot book slots.

BBF-FU-11 remediation (2026-11-04). Two concerns live here so that
PUT, GET, DELETE and the recommendations fallback cannot diverge:

  - :func:`atomic_replace_bytes` — write bytes to the destination
    atomically, so an interrupted or failed replacement can never
    destroy the previous valid file.
  - :func:`resolve_book_path` — one canonical, symlink-safe resolver
    for the player name and destination path.

Both are deliberately narrow. This module does not know about HTTP,
auth, or the gateway; it is a storage primitive the route layer and
the writer compose.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# A Polyglot entry is 16 bytes: 8-byte key, 2-byte move, 2-byte
# weight, 4-byte learn. The public format (https://hgm.nubati.net/
# book_format.html) defines a book as a headerless series of such
# entries, so a file whose length is not a multiple of 16 is malformed.
ENTRY_SIZE: int = 16


class MalformedBookBytesError(ValueError):
    """Raised when a stored book's bytes are not a valid Polyglot book.

    Distinct from the writer's ``ValueError`` (which signals an
    invalid *input* entry) so the route layer can map a malformed
    STORED file to its own deterministic response without catching
    every validation error the same way.

    Named ``MalformedBookBytesError`` to avoid colliding with the
    typed ``chess_coach.errors.exceptions.MalformedBookError``, which
    is the ADR-0002 error the route raises in response.
    """


def atomic_replace_bytes(destination: Path, payload: bytes) -> int:
    """Write ``payload`` to ``destination`` atomically.

    The sequence:

      1. Write the complete payload to a unique temporary file in the
         SAME directory as ``destination`` (same filesystem, so
         :func:`os.replace` is atomic).
      2. ``flush`` + ``fsync`` the temporary file, so the bytes are
         durable before the name is swapped.
      3. ``os.replace`` the temporary file onto ``destination``. This
         is an atomic rename of the directory entry: a reader sees
         either the old file or the new one, never a partial write.
      4. On ANY failure, remove the temporary artifact and leave the
         previous ``destination`` bytes untouched.

    Because the replacement is a directory-entry swap, a pre-existing
    symlink at ``destination`` is REPLACED, not followed — the symlink
    itself is removed and a regular file takes its place.

    Returns the number of bytes written.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(destination.parent),
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic directory-entry swap. Never follows a symlink at the
        # destination: it replaces it.
        os.replace(tmp_path, destination)
        tmp_path = None  # ownership transferred by the rename
    finally:
        if tmp_path is not None:
            # Failure path: remove the temporary artifact. The previous
            # destination bytes were never touched.
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return len(payload)


def resolve_book_path(books_root: Path, player: str) -> Path:
    """Resolve ``player`` to a canonical destination path under ``books_root``.

    This is the SINGLE resolver used by PUT, GET, DELETE and the
    recommendations fallback. It enforces, in order:

      1. The player name is a plain name — no path separators, no
         ``.``/``..`` components, no NUL. (The route layer applies its
         own richer validation first; this is the storage-level backstop.)
      2. ``books_root`` is resolved (symlinks followed) to its canonical
         location, so a symlinked books directory is handled correctly.
      3. The destination is built inside the canonical root.
      4. The destination's PARENT is resolved. If the destination itself
         is an existing symlink, its resolved target must still be
         inside the canonical root — otherwise the call raises rather
         than reading or writing through an escaping symlink.

    Returns the resolved destination path.

    Raises:
        ValueError: if the player name is not a safe single path
            component, or if the destination escapes ``books_root``
            through a symlink.
    """
    books_root = Path(books_root)
    name = validate_player_component(player)
    canonical_root = books_root.resolve()
    destination = canonical_root / f"{name}.bin"

    # The destination's PARENT is the canonical root by construction.
    # The only escape vector is a pre-existing symlink AT the
    # destination itself. Resolve it and require it to stay inside.
    if destination.is_symlink():
        resolved_target = destination.resolve()
        if not _is_within(resolved_target, canonical_root):
            raise ValueError(
                f"Book path for player {name!r} escapes the books directory."
            )
    return destination


def validate_player_component(player: str) -> str:
    """Return ``player`` if it is a safe single path component.

    A safe component is a non-empty string of ASCII letters, digits,
    underscore or hyphen, at most 64 characters. This rejects
    lexical traversal (``..``), separators (``/``, ``\\``), absolute
    paths, and encoded-separator attempts that survive URL decoding
    into a separator.

    Raises:
        ValueError: if the name is not a safe component.
    """
    if not player or len(player) > 64:
        raise ValueError(f"Invalid player name: {player!r}.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if not set(player) <= allowed:
        raise ValueError(f"Invalid player name: {player!r}.")
    return player


def entry_count_from_size(size_bytes: int) -> int:
    """Number of Polyglot entries implied by a file's byte length.

    Raises:
        MalformedBookBytesError: if the length is not a multiple of
            :data:`ENTRY_SIZE`. A malformed stored file must NOT be
            reported as an empty book.
    """
    if size_bytes % ENTRY_SIZE != 0:
        raise MalformedBookBytesError(
            f"Book file size {size_bytes} is not a multiple of {ENTRY_SIZE} bytes; "
            "the stored book is malformed."
        )
    return size_bytes // ENTRY_SIZE


def _is_within(candidate: Path, root: Path) -> bool:
    """True when ``candidate`` is ``root`` or lives beneath it."""
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "ENTRY_SIZE",
    "MalformedBookBytesError",
    "atomic_replace_bytes",
    "entry_count_from_size",
    "resolve_book_path",
    "validate_player_component",
]
