"""Unit tests for the UCI parser (no engine subprocess required)."""
from __future__ import annotations

import pytest

from chess_coach.uci.engine import InfoEvent, _parse_info
from chess_coach.protocol_types.analysis import Score


class TestParseInfo:
    def test_standard_info_line(self):
        line = "info depth 18 seldepth 24 multipv 1 score cp 32 nodes 12345 nps 123450 time 100 pv d2d4 d7d5 g1f3"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.depth == 18
        assert ev.seldepth == 24
        assert ev.multipv == 1
        assert ev.score == Score(kind="cp", value=32)
        assert ev.nodes == 12345
        assert ev.nps == 123450
        assert ev.time_ms == 100
        assert ev.pv == ["d2d4", "d7d5", "g1f3"]

    def test_mate_score(self):
        line = "info depth 12 score mate 5"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.score == Score(kind="mate", value=5)

    def test_negative_cp(self):
        line = "info depth 10 score cp -55 pv e7e5"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.score == Score(kind="cp", value=-55)

    def test_multipv_line(self):
        line = "info depth 20 multipv 3 score cp 10 pv b1c3"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.multipv == 3

    def test_no_pv(self):
        line = "info depth 8 score cp 0"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.pv == []

    def test_no_score(self):
        line = "info depth 5 pv e2e4"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.score is None

    def test_not_info_line(self):
        ev = _parse_info("bestmove e2e4")
        assert ev is None

    def test_no_multipv_defaults_to_1(self):
        line = "info depth 10 score cp 10"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.multipv == 1

    def test_only_depth(self):
        line = "info depth 99"
        ev = _parse_info(line)
        assert ev is not None
        assert ev.depth == 99
        assert ev.multipv == 1
        assert ev.score is None
        assert ev.pv == []
