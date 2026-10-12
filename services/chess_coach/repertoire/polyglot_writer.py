"""Polyglot ``.bin`` opening-book WRITE path.

BBF-Phase8-1 / FU-7 (P2d implementation): chess-coach reads Polyglot
``.bin`` books via the per-call ``polyglot_book_path`` field on
repertoire recommendations (the α additive field, PR #84 → commit
``7180433``). This module implements the EXPORT direction: write a
list of book entries to a Polyglot ``.bin`` file. The write path is
needed for the round-trip story (chess-coach-built repertoires can be
exported to other tools) and for the β (FU-11) persistent-book future
work.

Polyglot format spec (public, used by Chessbase, Arena, Scid, etc.):
  - 4-byte magic number ``0xB19B0BCC`` (big-endian uint32)
  - Repeated 16-byte entries (entry order doesn't matter; readers do
    binary search on the 8-byte key):
      - 8-byte key: Polyglot zobrist hash of the position
        (``chess.polyglot.zobrist_hash``) — note this is the position
        hash only, NOT (position hash, move, weight, learn) as the
        FU-7 ledger entry wording suggested
      - 2-byte move: from_square (high byte) | to_square (low byte)
      - 2-byte weight: book weight (0..65535)
      - 4-byte learn: engine learning data (depth + eval); we default
        to 0 for hand-curated books

Important python-chess library quirk (discovered during the §1.3
discipline's P2d implementation, then corrected again after the first
attempt's byte-verify pass): ``chess.polyglot.open_reader`` does
``size % 16 == 0`` as its size check and treats the file as a flat
array of 16-byte entries starting at offset 0. The library's
``bisect_key_left`` does a standard leftmost-insertion-point binary
search on the 8-byte key field, which REQUIRES the entries to be
strictly ascending in key. There is no separate file header.

Implication: our writer must NOT prepend a separate magic header.
The first attempt did (``struct.pack(">I", MAGIC) + b"\x00" * 12``
as a 16-byte "header entry" with key=0xB19B0BCC00000000), but the
magic value is larger than typical zobrist hashes (e.g. starting
position key = 0x463b96181691fc9c), so the file wasn't sorted and
``find_all`` returned zero hits for every real position. The fix:
write only the real entries, sorted by zobrist hash. No magic
header. Real Polyglot books written by Chessbase/Arena/Scid also do
not have a separate magic header in this position; the 0xB19B0BCC
magic is implicit in Polyglot spec docs but the reader library
ignores it.

For an "empty" book, the file is 0 bytes (no entries at all). The
library's ``find_all`` returns an empty iterator for a 0-byte file
(handled by the ``_EmptyMmap`` fallback in the library's
``__init__``). This matches the "no book" semantics: no
recommendations come from the book, the engine-only path runs.

Per the v1.0 = Linux dev platform decision (Framing β, 2026-10-11),
this is part of the P2d implementation work (UX gap, ~1 BBF). Per
the v2 plan, repertoire import/export is a Phase 3 feature, but
FU-7 was alpha-shipped + beta-deferred-to-FU-11 framing per
Sebastian+Claude directive (2026-08-07). The export direction closes
the round-trip; the β persistence (server-managed book state) is
FU-11 (v1.x future work).
"""
from __future__ import annotations

import struct
from collections.abc import Iterable
from dataclasses import dataclass

import chess
from chess.polyglot import zobrist_hash

# Polyglot format constants.
MAGIC: int = 0xB19B0BCC
ENTRY_STRUCT: str = ">QHHI"  # big-endian: 8-byte key, 2-byte move, 2-byte weight, 4-byte learn
ENTRY_SIZE: int = 16


@dataclass(frozen=True)
class BookEntry:
    """One Polyglot book entry (FEN + UCI move + weight).

    The learn field is exposed for forward compatibility (Phase 3
    engine-learning integration); the default is 0 (hand-curated).
    """
    fen: str
    uci_move: str
    weight: int = 100
    learn: int = 0


def _encode_move(from_square: int, to_square: int) -> int:
    """Encode the 2-byte Polyglot move field.

    Per the python-chess library's actual decoder: low 6 bits =
    to_square (0-63), next 6 bits = from_square (0-63), packed into
    a big-endian uint16. The library reads:
        to_square = raw_move & 0x3f
        from_square = (raw_move >> 6) & 0x3f
    So the encoding is `(from_square << 6) | to_square`, NOT
    `(from_square << 8) | to_square` (which would be the spec's
    "high byte = from, low byte = to" framing — the library uses a
    different bit layout). Per the §1.3 discipline's P2d
    implementation: the FU-7 ledger entry's wording "key = (position
    hash, move, weight, learn) at big-endian uint64" is a misleading
    summary; the actual move field is 2 bytes, not 1 byte, and the
    bit layout is the 6+6 split, not the high-byte/low-byte split.
    """
    if not (0 <= from_square <= 63 and 0 <= to_square <= 63):
        raise ValueError(
            f"Invalid square index: from={from_square} to={to_square}. "
            f"Polyglot format uses 0-63 (a1=0, h8=63)."
        )
    return (from_square << 6) | to_square


def _build_entry_bytes(entry: BookEntry) -> bytes:
    """Build the 16 bytes for a single Polyglot entry."""
    board = chess.Board(entry.fen)
    move = chess.Move.from_uci(entry.uci_move)
    if move not in board.legal_moves:
        raise ValueError(
            f"Move {entry.uci_move!r} is not legal from FEN {entry.fen!r}. "
            f"Legal moves: {[m.uci() for m in board.legal_moves]}"
        )
    key = zobrist_hash(board)
    move_field = _encode_move(move.from_square, move.to_square)
    # Clamp weight to uint16 range (per the spec).
    if not (0 <= entry.weight <= 0xFFFF):
        raise ValueError(
            f"Weight {entry.weight} out of range; Polyglot uses 0..65535."
        )
    return struct.pack(ENTRY_STRUCT, key, move_field, entry.weight, entry.learn)


def write_polyglot_book(entries: Iterable[BookEntry], path: str) -> int:
    """Write a list of BookEntry to a Polyglot ``.bin`` file at ``path``.

    Returns the number of bytes written. Per the python-chess library's
    behavior: the file is a flat array of 16-byte entries with NO
    separate magic header. The library's ``size % 16 == 0`` check
    requires the file size to be a multiple of 16 (0 passes). The
    library's ``bisect_key_left`` does a leftmost-insertion-point
    binary search on the 8-byte key field, which REQUIRES the
    entries to be strictly ascending in key. Sorting the entries by
    zobrist hash is therefore mandatory; a file with a magic header
    at offset 0 would have its first entry's key = 0xB19B0BCC00000000
    which is larger than typical real keys, breaking the sort
    invariant and causing ``find_all`` to return zero hits.

    The "magic" 0xB19B0BCC value mentioned in some Polyglot spec
    docs is a file-format identifier, but the reader library ignores
    it. Real Polyglot books written by Chessbase/Arena/Scid also do
    not have a separate magic header in this position.

    For an empty book, the file is 0 bytes. The library's
    ``find_all`` returns an empty iterator for a 0-byte file
    (handled by the ``_EmptyMmap`` fallback in the library's
    ``__init__``).

    The caller is responsible for any backup or atomic-rename
    semantics. The function does NOT consult the OS-native secret
    store, does NOT validate that ``path`` is within any sandbox;
    the route layer adds path-validation / sandboxing on top.
    """
    entries = list(entries)
    if not entries:
        # Empty book: write a 0-byte file. The library's _EmptyMmap
        # fallback handles this correctly (find_all returns nothing).
        with open(path, "wb") as f:
            pass
        return 0
    # Sort entries by zobrist hash so bisect_key_left works. Compute
    # the key up front so we don't re-parse the Board multiple times
    # (the sort key and the encoded entry both need the zobrist hash
    # of the position).
    keyed = sorted(entries, key=lambda e: zobrist_hash(chess.Board(e.fen)))
    blob = b"".join(_build_entry_bytes(e) for e in keyed)
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)
