"""Phase 4 golden fixtures v1.

Three hand-crafted scenarios that exercise the 6 Phase 4 metrics
+ the sequence_based_tilt detector. Each scenario builds a
synthetic SQLite DB (with the production schema) and provides
the expected metric values (computed by hand from the fixture
data).

The "gold" is the expected output. Tests that run these
fixtures assert that the chess_coach.profile implementations
produce the expected values within a tolerance.

The fixture design uses minimal game histories (2-3 positions
per game) to keep the math tractable. Most assertions are
RANGE assertions (e.g. "tactical > 0.5") rather than EXACT
assertions, because the bootstrap CI + Cohen's d math
doesn't produce exact values by hand.

The only EXACT assertions are:
  - opening_comfort: distinct count of opening prefixes
  - blunder_count: explicit count of |delta| > 150 blunders

Everything else uses range + structural assertions.

This file follows the L-2 gold v1 pattern (BBF-51): a single
file in tests/gold/ with build_* functions and a constants
table. The test file tests/unit/test_phase4_golden.py is
the loader.

## Schema reminder

Production schema (migrations/0001..0007):
  games(id, white, black, result, date, ...)
  positions(id, game_id, fen, move_san, ply, is_mainline)
  analyses(id, position_id, engine_id, depth, score_cp,
           score_mate, best_move, pv_moves, result_json,
           created_at, classification, cp_delta)

NOTE: positions has NO score_cp column. The score lives
on analyses.score_cp. This is the BBF-57 follow-up fix
(before BBF-57, conversion_ability incorrectly queried
po.score_cp; the test schema also had a fictional
positions.score_cp column that masked the bug).
"""
from __future__ import annotations

import sqlite3


def _build_db_with_schema(db_path: str) -> None:
    """Create the production schema in the given db_path."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE games (
            id TEXT NOT NULL PRIMARY KEY,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result TEXT NOT NULL,
            date TEXT,
            white_elo INTEGER,
            black_elo INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE positions (
            id TEXT NOT NULL PRIMARY KEY,
            game_id TEXT NOT NULL,
            parent_id TEXT,
            fen TEXT NOT NULL,
            move_uci TEXT,
            move_san TEXT,
            ply INTEGER NOT NULL DEFAULT 0,
            is_mainline INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE analyses (
            id TEXT NOT NULL PRIMARY KEY,
            position_id TEXT NOT NULL,
            engine_id TEXT NOT NULL,
            depth INTEGER NOT NULL,
            score_cp INTEGER,
            score_mate INTEGER,
            best_move TEXT,
            pv_moves TEXT,
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            classification TEXT,
            cp_delta REAL
        );
    """)
    conn.commit()
    conn.close()


def _insert_game(conn, gid, white, black, result, date="2026-01-01",
                white_elo=1500, black_elo=1500):
    conn.execute(
        "INSERT INTO games(id, white, black, result, date, white_elo, black_elo) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (gid, white, black, result, date, white_elo, black_elo),
    )


def _insert_pos_with_score(conn, pid, gid, ply, score_cp, move_san="e4"):
    """Insert a position with a mainline analysis containing score_cp."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    conn.execute(
        "INSERT INTO positions(id, game_id, ply, move_san, fen, is_mainline) "
        "VALUES(?, ?, ?, ?, ?, 1)",
        (pid, gid, ply, move_san, fen),
    )
    conn.execute(
        "INSERT INTO analyses(id, position_id, engine_id, depth, score_cp, result_json) "
        "VALUES(?, ?, 'sf18', 25, ?, '{}')",
        (pid * 10, pid, score_cp),
    )


def build_clean_player(db_path: str) -> str:
    """Scenario 1: clean player, no blunders, no tactical opportunities.

    10 games, all wins. Each game has 2 mainline positions
    with small positive deltas (10-20cp). No |delta| > 80,
    so no tactical opportunities. No delta < -100, so no
    blunders. All positions use the same move_san
    "e4 Nf3 Nc6" so SUBSTR(_, 1, 10) is identical for all
    20 positions -> 1 distinct prefix.

    10 games (20 positions) is the minimum to pass
    MIN_SAMPLE_OPENING = 20 in the opening_comfort
    metric (which requires >= 20 first-10-ply positions).
    """
    _build_db_with_schema(db_path)
    conn = sqlite3.connect(db_path)
    for i in range(1, 11):
        gid = f"g{i}"
        _insert_game(conn, gid, "clean_player", f"opp{i}", "1-0")
        # 2 positions per game. Score 30 -> 50 (delta +20).
        # Same move_san for all positions -> 1 distinct prefix.
        for j, score in enumerate([30, 50], start=1):
            _insert_pos_with_score(
                conn, f"p{i}_{j}", gid, j, score, "e4 Nf3 Nc6"
            )
    conn.commit()
    conn.close()
    return db_path


def build_tactical_player(db_path: str) -> str:
    """Scenario 2: tactical player with 3 of 5 opportunities taken.

    5 games. Each game has 2 mainline positions.
      - Games 1, 2, 3: pos 2 score = 130 (delta = +100, TOOK)
      - Games 4, 5: pos 2 score = -60 (delta = -90, MISSED,
        in (-100, -80] so it's an opportunity, not a blunder)

    With 2 positions per game and LAG filtering out pos 1
    (no LAG partner), there is exactly 1 LAG-able position
    per game. 5 opportunities total, 3 taken = 3/5 = 0.6.

    All games use the same opening ("e4 Nf3") so
    opening_comfort = 1.
    """
    _build_db_with_schema(db_path)
    conn = sqlite3.connect(db_path)
    # 10 games with the same opening. 10 games * 2 positions
    # = 20 positions = MIN_SAMPLE_OPENING (the opening_comfort
    # metric requires >= 20 first-10-ply positions).
    # 6 took + 4 missed = 6/10 = 0.6 point_estimate.
    games_data = [
        # (gid, opp, result, pos2_score, opening)
        ("g1", "opp1", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g2", "opp2", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g3", "opp3", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g4", "opp4", "0-1", -60, "e4 Nf3 Nc6"),   # missed
        ("g5", "opp5", "0-1", -60, "e4 Nf3 Nc6"),   # missed
        ("g6", "opp6", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g7", "opp7", "0-1", -60, "e4 Nf3 Nc6"),   # missed
        ("g8", "opp8", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g9", "opp9", "1-0", 130, "e4 Nf3 Nc6"),   # took
        ("g10", "opp10", "0-1", -60, "e4 Nf3 Nc6"),  # missed
    ]
    for gid, opp, result, pos2, _ in games_data:
        _insert_game(conn, gid, "tactical_player", opp, result)
        # 2 positions per game. Same move_san for all
        # positions -> 1 distinct prefix.
        for j, score in enumerate([30, pos2], start=1):
            _insert_pos_with_score(
                conn, f"p{gid}_{j}", gid, j, score, "e4 Nf3 Nc6"
            )
    conn.commit()
    conn.close()
    return db_path


def build_blundering_player(db_path: str) -> str:
    """Scenario 3: blundering player.

    10 games. Game 1: clean (e4 opening). Games 2, 3:
    blunders in pos 2 (d4 opening). 8 more games: pattern
    alternates between clean and blunder, 50/50. 2 distinct
    openings total. 10 games * 2 positions = 20 positions =
    MIN_SAMPLE_OPENING.

    Total blunders: games 2, 3, 5, 7, 9 = 5 blunders out
    of 20 positions = 5/20 = 0.25 blunder rate.
    """
    _build_db_with_schema(db_path)
    conn = sqlite3.connect(db_path)
    # 10 games: game 1 clean (e4), games 2,3 blunder (d4),
    # then alternating
    game_specs = [
        # (gid, opp, result, pos2_score, move_san, blunder?)
        ("g1", "opp1", "1-0", 50, "e4 Nf3 Nc6", False),    # clean e4
        ("g2", "opp2", "0-1", -150, "d4 c4 Nf3", True),   # blunder d4
        ("g3", "opp3", "0-1", -200, "d4 c4 Nf3", True),   # blunder d4
        ("g4", "opp4", "1-0", 50, "e4 Nf3 Nc6", False),   # clean e4
        ("g5", "opp5", "0-1", -180, "d4 c4 Nf3", True),   # blunder d4
        ("g6", "opp6", "1-0", 50, "e4 Nf3 Nc6", False),   # clean e4
        ("g7", "opp7", "0-1", -160, "d4 c4 Nf3", True),   # blunder d4
        ("g8", "opp8", "1-0", 50, "e4 Nf3 Nc6", False),   # clean e4
        ("g9", "opp9", "0-1", -170, "d4 c4 Nf3", True),   # blunder d4
        ("g10", "opp10", "1-0", 50, "e4 Nf3 Nc6", False), # clean e4
    ]
    for gid, opp, result, pos2, san, _blunder in game_specs:
        _insert_game(conn, gid, "blundering_player", opp, result)
        for j, score in enumerate([30, pos2], start=1):
            _insert_pos_with_score(
                conn, f"p{gid}_{j}", gid, j, score, san
            )
    conn.commit()
    conn.close()
    return db_path


# --- Expected metric values (the "gold") ---
# These are computed by hand from the fixture data. The tests
# use a mix of EXACT assertions (for opening_comfort and
# blunder counts) and RANGE assertions (for ratios + sample
# sizes + gate results).

EXPECTED = {
    "clean_player": {
        # Exact values
        "opening_comfort_distinct_prefixes": 1,
        # Range assertions
        "tactical_opportunities": 0,
        "blunder_count": 0,
        # Sample size expectations: 10 games * 2 positions = 20
        # (passes MIN_SAMPLE_OPENING = 20)
        "min_observations": 20,
    },
    "tactical_player": {
        "opening_comfort_distinct_prefixes": 1,
        "tactical_opportunities": 10,  # 10 games, 1 each
        "tactical_taken": 6,            # 6 of 10
        "blunder_count": 0,
        "min_observations": 20,  # 10 games * 2 positions
    },
    "blundering_player": {
        "opening_comfort_distinct_prefixes": 2,
        # The 5 blunders (in games 2, 3, 5, 7, 9) have
        # |delta| > 80, so they count as "opportunities" in
        # the tactical metric (with value 0.0 = missed).
        "tactical_opportunities": 5,
        "tactical_taken": 0,            # all 5 are missed (blunders)
        "blunder_count": 5,             # 5 blunders total
        "min_observations": 20,  # 10 games * 2 positions
    },
}


__all__ = [
    "build_clean_player",
    "build_tactical_player",
    "build_blundering_player",
    "EXPECTED",
]