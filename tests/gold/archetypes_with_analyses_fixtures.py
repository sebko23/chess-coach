"""BBF-88.x archetype-gold v0.2 fixture builder.

Builds a synthetic chess_coach SQLite DB whose `analyses` table
is populated with realistic Stockfish-18 score_cp trajectories.
This lets the production `services.chess_coach.profile.stats.*`
metric functions return real (non-zero) values for all 6
metrics, including those that JOIN the analyses table
(tactical_vs_positional_bias, time_pressure_quality,
decision_fatigue).

Mirrors the `tests/gold/phase4_v1_fixtures.py` pattern (hand-crafted
synthetic DB exercises the metric SQL path). Scale difference:
phase4 fixtures have ~10 games per player; here we build ~30 games
per player so each player's metric sample is above the
§B4 MIN_SAMPLE_DEFAULT=30 floor.

What the fixture does NOT do:
- Run real Stockfish 18. The score_cp values are shape-correct
  synthetic values, not eval-API outputs.
- Invent "real" archetype labels. By project decision there is
  no human-curator path; labels are auto-bootstrapped from v1's
  placeholder via `_knn_classify` in `scripts/curate_archetype_gold_auto.py`.

Each player is built with a per-archetype synthetic score_cp
trajectory so that the resulting metric vector *clusters* near
the right archetype:

  Tactician:            win-preserving, mostly positive deltas,
                         ~6%-15% tactical opportunities taken
  Positional Player:    slow-improving scores, low blunder rate
  Grinder:              monotonic conversion of winning positions
  Wildcard:             diverse openings, large-magnitude blunders
  Specialist:           narrow opening base, stable deltas
  Tilter:               late-game blunders (session window buildup)
  Endgame Specialist:   stable mid-late game, low blunder rate

These are *shape intentions*, not real chess data. The metric
output is what production code would compute against a real
Stockfish-populated DB; only the inputs are synthetic.

See docs/16_audit/BBF-88-archetype-gold-auto.md for the design.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

# Per-archetype synthetic score_cp trajectory patterns. All values
# are centipawns from White's POV (positive = White advantage),
# which is how lichess + Stockfish return them. Side-aware flipping
# happens inside the production stats.py metric SQL itself
# (see services/chess_coach/profile/stats.py:_fetch_side_deltas).

# Each archetype pattern is: (start_score, end_score, blunder_rate,
#    session_blunder_drift, blunder_magnitude, opening_breadth_index)
# Where:
#  - start_score, end_score shape the score_cp trajectory
#  - blunder_rate is the per-ply probability of a sharp drop
#  - session_blunder_drift adds late-game blunder-rate inflation
#    (Tilter has it; others don't)
#  - blunder_magnitude is the size of those drops (Tilter's are
#    larger = more impactful)
#  - opening_breadth_index 0=one opening, 1=two, 2=five+
# end_score is calibrated so:
#  - Grinder / Positional Player / Specialist / Endgame Specialist
#    end above cp=200 in many games so conversion_ability has
#    qualifying positions (the metric filters on cp > 200 from POV
#    at ply 30+).
#  - Tactician / Wildcard / Tilter end at low/moderate scores so
#    they don't convert by the metric's definition.
ARCHETYPE_TRAITS: dict[str, dict[str, float]] = {
    "Tactician": {
        "start_score": 30, "end_score": 180,
        "blunder_rate": 0.10, "blunder_magnitude": 200,
        "session_blunder_drift": 0.0,
        "opening_breadth_index": 1,
    },
    "Positional Player": {
        "start_score": 50, "end_score": 240,
        "blunder_rate": 0.05, "blunder_magnitude": 150,
        "session_blunder_drift": 0.0,
        "opening_breadth_index": 2,
    },
    "Grinder": {
        "start_score": 100, "end_score": 350,
        "blunder_rate": 0.04, "blunder_magnitude": 120,
        "session_blunder_drift": 0.0,
        "opening_breadth_index": 1,
    },
    "Wildcard": {
        "start_score": 20, "end_score": 80,
        "blunder_rate": 0.15, "blunder_magnitude": 250,
        "session_blunder_drift": 0.05,
        "opening_breadth_index": 2,
    },
    "Specialist": {
        "start_score": 60, "end_score": 220,
        "blunder_rate": 0.06, "blunder_magnitude": 180,
        "session_blunder_drift": 0.0,
        "opening_breadth_index": 0,
    },
    "Tilter": {
        "start_score": 40, "end_score": 60,
        "blunder_rate": 0.18, "blunder_magnitude": 300,
        "session_blunder_drift": 0.30,
        "opening_breadth_index": 1,
    },
    "Endgame Specialist": {
        "start_score": 30, "end_score": 180,
        "blunder_rate": 0.05, "blunder_magnitude": 150,
        "session_blunder_drift": 0.0,
        "opening_breadth_index": 1,
    },
}


# The opening strings below are short enough to be sampled in the
# `phase4_v1_fixtures` style. They produce distinct first-10-ply
# prefixes so opening_comfort's SUBSTR(_, 1, 10) gives a real count.
OPENING_BY_BREADTH: dict[int, list[str]] = {
    0: ["e4"],
    1: ["e4"],
    2: ["e4", "d4", "Nf3", "c4", "b3"],
}
# Index by archetype opening breadth index (the field on
# ARCHETYPE_TRAITS). Mapping is identical across all archetypes
# with the same breadth index; what differs is how MANY distinct
# openings get sampled (controlled at fixture call time).


def _build_db_with_schema(db_path: Path) -> None:
    """Create the production schema in the given db_path.

    Mirrors `tests/gold/phase4_v1_fixtures.py` exactly, plus the
    `session_id` pattern needed by decision_fatigue (which is
    CTE-derived from `games.date` so no extra column needed).
    """
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
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
        """
    )
    conn.commit()
    conn.close()


def _trajectory(game_index: int, archetype: str, total_plies: int = 30) -> list[int]:
    """Return a synthetic score_cp trajectory for one game.

    Linear interpolation from start_score to end_score, with
    shape-correlated blunders injected according to the archetype's
    blunder_rate. Tilter's blunder rate grows with ply (session
    fatigue model).

    Returns a list of `total_plies + 1` centipawn values, indexed by
    ply (0..total_plies inclusive).
    """
    import random
    rng = random.Random(f"{archetype}_{game_index}".encode())
    traits = ARCHETYPE_TRAITS[archetype]
    start, end = traits["start_score"], traits["end_score"]
    blunder_rate = traits["blunder_rate"]
    drift = traits["session_blunder_drift"]
    magnitude = traits["blunder_magnitude"]

    trajectory: list[int] = []
    for ply in range(total_plies + 1):
        t = ply / max(1, total_plies)
        base = int(start + t * (end - start))
        # Session fatigue growth: blunder rate scales linearly upward
        per_ply_br = blunder_rate * (1 + drift * t)
        if rng.random() < per_ply_br:
            base -= int(rng.random() * magnitude) + int(magnitude * 0.5)
        # Clamp plausible Stockfish range
        base = max(-1000, min(1000, base))
        trajectory.append(base)
    return trajectory


def _opening_for_game(archetype: str, game_index: int, breadth_index: int) -> str:
    """Pick an opening string for this game, cycling.

    Cyclic selection (game_index mod len(openings)) is deterministic
    and observable from the fixture signature -- tests can predict
    expected opening_comfort values without probing internals.
    """
    pool = OPENING_BY_BREADTH[breadth_index]
    return pool[game_index % len(pool)]


def build_player(
    db_path: Path,
    player: str,
    archetype: str,
    *,
    n_games: int = 30,
    plies_per_game: int = 30,
    total_plies_target: int | None = None,
    ensure_schema: bool = True,
) -> Path:
    """Build a synthetic DB populated for one player with an
    archetype-shaped synthetic score_cp trajectory.

    Produces `n_games` games, each with `plies_per_game + 1` mainline
    positions (ply 0 through ply plies_per_game inclusive). Each
    position gets an `analyses` row with the trajectory's score_cp.

    For the default 30 games × 30 plies, total observations per
    metric: 30 × 30 = 900 side-delta observations. Above the
    MIN_SAMPLE_DECISION_FATIGUE=50 threshold by 18x.

    `ensure_schema=True` (default) creates the schema + clears any
    pre-existing rows. Set to False when calling `build_player`
    multiple times into the same DB (as `build_corpus_db` does) so
    later players append to the existing schema without wiping
    the earlier players' data.
    """
    if ensure_schema:
        if db_path.exists():
            db_path.unlink()
        _build_db_with_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    traits = ARCHETYPE_TRAITS[archetype]
    breadth = traits["opening_breadth_index"]

    for g_idx in range(n_games):
        gid = f"g_{player}_{g_idx:03d}"
        traj = _trajectory(g_idx, archetype, plies_per_game)
        opening_san = _opening_for_game(archetype, g_idx, breadth)
        # Game result: 1-0 if end_score positive else 0-1; deterministic
        # per archetype + game_index so tests can predict it.
        result = "1-0" if traj[-1] > 0 else "0-1"
        # Date: 3 games share a single `date` so they coalesce into
        # ONE session_id (CTE-derived from date) per session. This
        # gives decision_fatigue ~90+ plies per session, well above
        # its MIN_SAMPLE_DECISION_FATIGUE=50 threshold.
        # session_index = g_idx // 3, so 30 games → 10 sessions.
        session_index = g_idx // 3
        date = f"2026-{((session_index % 12) + 1):02d}-{(((session_index // 12) % 28) + 1):02d}"
        conn.execute(
            "INSERT INTO games(id, white, black, result, date, "
            "white_elo, black_elo) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (gid, player, f"opp_{g_idx}", result, date, 1872, 1700),
        )

        # One starting position (ply 0)
        start_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        start_pid = f"p_{player}_{g_idx:03d}_0"
        conn.execute(
            "INSERT INTO positions(id, game_id, ply, move_san, fen, "
            "is_mainline) VALUES(?, ?, ?, ?, ?, 1)",
            (start_pid, gid, 0, opening_san, start_fen),
        )
        conn.execute(
            "INSERT INTO analyses(id, position_id, engine_id, depth, "
            "score_cp, result_json) VALUES(?, ?, 'sf18', 25, ?, '{}')",
            (f"a_{player}_{g_idx:03d}_0", start_pid, traj[0]),
        )

        for ply in range(1, plies_per_game + 1):
            pid = f"p_{player}_{g_idx:03d}_{ply}"
            # Naive FEN stub: distinct per position so the schema
            # accepts it; the metric SQL only reads score_cp / ply,
            # not FEN structure.
            fen = f"{start_fen} {ply}"
            conn.execute(
                "INSERT INTO positions(id, game_id, parent_id, ply, "
                "move_san, fen, is_mainline) VALUES(?, ?, ?, ?, ?, ?, 1)",
                (pid, gid, start_pid, ply, opening_san, fen),
            )
            conn.execute(
                "INSERT INTO analyses(id, position_id, engine_id, depth, "
                "score_cp, result_json) VALUES(?, ?, 'sf18', 25, ?, '{}')",
                (f"a_{player}_{g_idx:03d}_{ply}", pid, traj[ply]),
            )

    conn.commit()
    conn.close()
    return db_path


def build_corpus_db(
    db_path: Path,
    *,
    archetype_player_pairs: Iterable[tuple[str, str]],
    n_games: int = 30,
    plies_per_game: int = 30,
) -> Path:
    """Build a single DB populated for multiple players, each with
    its own archetype-shaped score trajectory.

    `archetype_player_pairs` is e.g. `[("Tactician", "ebassti_tact"),
    ("Positional Player", "ebassti_pos"), ...]`. Two players per
    archetype (matching the v1 placeholder's 2-per-archetype shape)
    is the typical BBF-88.x invocation; this function is flexible.
    """
    if db_path.exists():
        db_path.unlink()
    _build_db_with_schema(db_path)
    # Per-player insertion into the SAME db (we created the schema
    # once; per-player inserts then close-and-reopen to keep state
    # isolated). Pass ensure_schema=False so later players append to
    # the existing schema instead of wiping earlier players' rows.
    for archetype, player in archetype_player_pairs:
        build_player(
            db_path,
            player,
            archetype,
            n_games=n_games,
            plies_per_game=plies_per_game,
            ensure_schema=False,
        )
    return db_path


__all__ = [
    "ARCHETYPE_TRAITS",
    "OPENING_BY_BREADTH",
    "_build_db_with_schema",
    "build_player",
    "build_corpus_db",
]
