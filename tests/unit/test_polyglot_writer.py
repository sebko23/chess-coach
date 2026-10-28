"""Tests for the Polyglot ``.bin`` writer (FU-7 P2d implementation).

The round-trip property is the load-bearing assertion: any book we
write via ``write_polyglot_book`` MUST be readable back via
``chess.polyglot.open_reader`` and yield the same entries. The
file is a flat array of 16-byte entries sorted by zobrist key —
no separate header, no magic bytes at offset 0. Empty books are
0 bytes (the library's ``_EmptyMmap`` fallback handles this).
"""
from __future__ import annotations

import chess
import pytest
from chess.polyglot import open_reader

from chess_coach.repertoire.polyglot_writer import (
    BookEntry,
    write_polyglot_book,
)

# Test FENs (standard opening positions).
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
AFTER_E4_E5_FEN = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"


def test_polyglot_writer_magic_is_correct(tmp_path) -> None:
    """Empty book: 0 bytes. The library's _EmptyMmap fallback returns
    an empty iterator for a 0-byte file, which is the documented
    "no book" semantics. There is no separate magic header in the
    Polyglot format the python-chess library reads.
    """
    path = str(tmp_path / "book.bin")
    size = write_polyglot_book([], path)
    assert size == 0
    assert (tmp_path / "book.bin").read_bytes() == b""


def test_polyglot_writer_single_entry(tmp_path) -> None:
    """Single-entry book: exactly 16 bytes (no header, just the entry).

    The library's size check ``size % 16 == 0`` passes because
    ``16 % 16 == 0``. The single entry's zobrist hash becomes the
    first (and only) key in the file, so ``find_all`` finds it
    via bisect.
    """
    path = str(tmp_path / "book.bin")
    entries = [
        BookEntry(fen=STARTING_FEN, uci_move="e2e4", weight=100, learn=0),
    ]
    size = write_polyglot_book(entries, path)
    assert size == 16  # one entry, no header

    # Open back via python-chess and verify the entry.
    with open_reader(path) as reader:
        found = list(reader.find_all(chess.Board(STARTING_FEN)))
    assert len(found) == 1
    assert found[0].move.uci() == "e2e4"
    assert found[0].weight == 100
    assert found[0].learn == 0


def test_polyglot_writer_multiple_entries_round_trip(tmp_path) -> None:
    """Multiple-entry book: N*16 bytes (no header)."""
    path = str(tmp_path / "book.bin")
    entries = [
        BookEntry(fen=STARTING_FEN, uci_move="e2e4", weight=100, learn=0),
        BookEntry(fen=STARTING_FEN, uci_move="d2d4", weight=50, learn=0),
        BookEntry(fen=AFTER_E4_FEN, uci_move="e7e5", weight=75, learn=10),
        BookEntry(fen=AFTER_E4_E5_FEN, uci_move="g1f3", weight=200, learn=0),
    ]
    size = write_polyglot_book(entries, path)
    assert size == 16 * len(entries)  # N entries, no header

    # Round-trip: read back, group by position, verify each entry.
    with open_reader(path) as reader:
        # Position 1 (starting): expect e2e4 and d2d4.
        starting_entries = list(reader.find_all(chess.Board(STARTING_FEN)))
        assert len(starting_entries) == 2
        starting_moves = sorted(e.move.uci() for e in starting_entries)
        assert starting_moves == ["d2d4", "e2e4"]
        starting_weights = sorted(e.weight for e in starting_entries)
        assert starting_weights == [50, 100]

        # Position 2 (after e4): expect e7e5.
        after_e4_entries = list(reader.find_all(chess.Board(AFTER_E4_FEN)))
        assert len(after_e4_entries) == 1
        assert after_e4_entries[0].move.uci() == "e7e5"
        assert after_e4_entries[0].weight == 75
        assert after_e4_entries[0].learn == 10

        # Position 3 (after e4 e5): expect g1f3.
        after_e4_e5_entries = list(reader.find_all(chess.Board(AFTER_E4_E5_FEN)))
        assert len(after_e4_e5_entries) == 1
        assert after_e4_e5_entries[0].move.uci() == "g1f3"
        assert after_e4_e5_entries[0].weight == 200


def test_polyglot_writer_rejects_illegal_move(tmp_path) -> None:
    """Writing an entry with an illegal move raises a clear ValueError.

    This is a guard against silent data corruption: a caller passing
    the wrong FEN+UCI combination should fail loudly, not produce a
    .bin file with a junk key that no reader can match.
    """
    path = str(tmp_path / "book.bin")
    bad_entries = [
        # e2e4 is NOT legal from the "after e4" position
        # (it's white to move and the e2 pawn has already moved).
        BookEntry(fen=AFTER_E4_FEN, uci_move="e2e4", weight=100, learn=0),
    ]
    with pytest.raises(ValueError, match="not legal"):
        write_polyglot_book(bad_entries, path)


def test_polyglot_writer_rejects_out_of_range_weight(tmp_path) -> None:
    """Weight must be in 0..65535 per the Polyglot spec."""
    path = str(tmp_path / "book.bin")
    bad_entries = [
        BookEntry(fen=STARTING_FEN, uci_move="e2e4", weight=100000, learn=0),
    ]
    with pytest.raises(ValueError, match="Weight.*out of range"):
        write_polyglot_book(bad_entries, path)


def test_polyglot_writer_learn_field_round_trips(tmp_path) -> None:
    """The learn field (4 bytes) is preserved across round-trip.

    Per the Polyglot spec, the learn field is engine learning data
    (depth + eval). The default is 0; this test verifies that
    non-zero learn values are preserved.
    """
    path = str(tmp_path / "book.bin")
    entries = [
        # Test the 4-byte learn boundary: 0x00000000, 0xFFFFFFFF, mid.
        BookEntry(fen=STARTING_FEN, uci_move="e2e4", weight=100, learn=0x00000000),
        BookEntry(fen=STARTING_FEN, uci_move="d2d4", weight=100, learn=0xFFFFFFFF),
        BookEntry(fen=AFTER_E4_FEN, uci_move="e7e5", weight=100, learn=0xDEADBEEF),
    ]
    write_polyglot_book(entries, path)
    with open_reader(path) as reader:
        starting = list(reader.find_all(chess.Board(STARTING_FEN)))
        after_e4 = list(reader.find_all(chess.Board(AFTER_E4_FEN)))
    # Group learn by move.
    learn_by_move = {e.move.uci(): e.learn for e in starting + after_e4}
    assert learn_by_move["e2e4"] == 0x00000000
    assert learn_by_move["d2d4"] == 0xFFFFFFFF
    assert learn_by_move["e7e5"] == 0xDEADBEEF

