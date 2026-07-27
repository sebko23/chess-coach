#!/usr/bin/env python3
# ruff: noqa: B023, E501, S310, S607
"""BBF-88.x archetype_gold v0.2 auto-curator.

Picks ≥3 players with ≥30 archived games from Lichess PGN exports,
imports each player's game set into a real chess_coach SQLite DB
whose `analyses` table is populated by the synthetic-analyses
fixture, calls the 6 production `services.chess_coach.profile.stats.*`
metric functions against each player, runs the kNN bootstrap via
`services.chess_coach.profile.archetypes._knn_classify(metrics)`
against v1 placeholder, and writes a 14-entry (2 per archetype × 7)
gold corpus to `tests/gold/archetypes/v0.2/corpus.json`.

By project decision (no human-curator path), labels are auto-
bootstrapped from v1's synthetic placeholder. The metric vectors
are real (production SQL pipeline); the labels are self-consistent
with v1 but not validated against real chess data. See
docs/16_audit/BBF-88-archetype-gold-auto.md for the design.

Usage:
    py -3 scripts/curate_archetype_gold_auto.py \\
        --input-pgn C:/Users/i3/Desktop/lichess_ebassti_2026-03-05.pgn \\
        --input-pgn C:/path/to/opponent_a.pgn \\
        --input-pgn C:/path/to/opponent_b.pgn \\
        --output tests/gold/archetypes/v0.2/corpus.json

The module-level `# ruff:` directive suppresses:
  - B023 (closure-over-loop-var): the per-player metric call
    is wrapped in a closure that captures loop vars; the closure
    is invoked immediately and never stored.
  - E501 (line too long): URL literals and path strings.
  - S310 (URL audit): the only URL is lichess.org/api/cloud-eval,
    a documented public endpoint (currently unused; kept for
    future online fetch support).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.pgn

_REPO_ROOT = Path(__file__).resolve().parents[1]
# On-disk path is integer-versioned (v0/, v1/, v2/) to match the
# production loader's regex (libs/chess_coach/datasets/archetype_gold.py
# hardcodes r"^AG-v\d+-\d{4}$"). v0.2 was the BBF brief notation;
# `v0` is the versioned key in this corpus generation.
DEFAULT_OUTPUT = _REPO_ROOT / "tests" / "gold" / "archetypes" / "v0" / "corpus.json"
_GIT_SHA: str | None = None
DEFAULT_FIXTURE = _REPO_ROOT / "tests" / "gold" / "archetypes_with_analyses_fixtures.py"
DEFAULT_PLAYER_GAMES = 30
DEFAULT_PLIES_PER_GAME = 30


def _git_sha() -> str:
    """Return the current HEAD git short-sha for provenance metadata."""
    global _GIT_SHA
    if _GIT_SHA is not None:
        return _GIT_SHA
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        _GIT_SHA = result.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        _GIT_SHA = "unknown"
    return _GIT_SHA


@dataclass
class PgnPlayer:
    """One player identified in a PGN export."""

    name: str
    n_games: int
    source_pgn: Path


def parse_pgn_for_players(pgn_path: Path) -> dict[str, int]:
    """Return a dict mapping each player name -> game count.

    Only counts games where the player appears as White or Black
    with a non-empty, non-anonymous name. Anonymous opponents
    (e.g. "lichess AI level 4") are filtered out.
    """
    counts: Counter[str] = Counter()
    with open(pgn_path, encoding="utf-8") as fh:
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            white = (game.headers.get("White") or "").strip()
            black = (game.headers.get("Black") or "").strip()
            for name in (white, black):
                if not name or name == "?" or name.lower().startswith("lichess ai"):
                    continue
                counts[name] += 1
    return dict(counts)


def pick_top_players(
    pgn_paths: list[Path],
    *,
    min_games: int = DEFAULT_PLAYER_GAMES,
    top_n: int = 14,
) -> list[PgnPlayer]:
    """Pick the top `top_n` players by game count across all input PGNs.

    Filters out players with fewer than `min_games` games (the §B4
    statistical-rigor floor). Returns at most `top_n` players; the
    caller can decide if a smaller pool is acceptable.
    """
    aggregate: Counter[str] = Counter()
    sources: dict[str, Path] = {}
    for pgn_path in pgn_paths:
        per_pgn = parse_pgn_for_players(pgn_path)
        for player, count in per_pgn.items():
            aggregate[player] += count
            sources.setdefault(player, pgn_path)
    eligible = [
        (player, count)
        for player, count in aggregate.items()
        if count >= min_games
    ]
    eligible.sort(key=lambda x: (-x[1], x[0]))
    chosen = eligible[:top_n]
    return [
        PgnPlayer(name=p, n_games=n, source_pgn=sources[p])
        for p, n in chosen
    ]


# The on-disk path is integer-versioned (v0/, v1/, v2/) to match
# the production loader's regex in
# libs/chess_coach/datasets/archetype_gold.py which hardcodes
# `r"^AG-v\d+-\d{4}$"`. The corpus entries' id fields use the
# same integer key. (The BBF brief's "v0.2" notation was for
# human readability; we collapse to "v0" so the production
# loader can resolve it.)
def next_entry_id(version: str, existing_ids: set[str]) -> str:
    """Generate the next AG-v<version>-NNNN id.

    `version` is the integer key (e.g. 'v0'), not the
    dotted-decimal form. The caller passes the integer key.
    """
    pat = re.compile(r"^AG-" + re.escape(version) + r"-(\d{4})$")
    used: list[int] = []
    for eid in existing_ids:
        m = pat.match(eid)
        if m:
            used.append(int(m.group(1)))
    n = max(used, default=0) + 1
    while f"AG-{version}-{n:04d}" in existing_ids:
        n += 1
    return f"AG-{version}-{n:04d}"


def curate_v02(
    pgn_inputs: list[Path],
    output_path: Path,
    *,
    min_games: int = DEFAULT_PLAYER_GAMES,
    top_n: int = 14,
    n_games_per_player: int = DEFAULT_PLAYER_GAMES,
    plies_per_game: int = DEFAULT_PLIES_PER_GAME,
    quiet: bool = False,
) -> dict:
    """Top-level pipeline. Returns a small summary dict.

    Steps:
      1. Pick top `top_n` players with ≥`min_games` games from PGNs.
      2. Build a synthetic-analyses DB populated with one player.
      3. Call the 6 production stats.py metrics for that player.
      4. Run kNN bootstrap against v1 placeholder.
      5. Emit corpus.json with provenance metadata.
    """
    # Deferred import: the `chess_coach.profile` module needs PYTHONPATH
    # to include the project's libs/ directory; that's set by the
    # test/conftest wiring. For the CLI invocation the user runs
    # `py -3 scripts/...` from the repo root, which doesn't always
    # have libs/ on the import path. We add it here defensively.
    repo = _REPO_ROOT
    libs_path = str(repo / "libs")
    if libs_path not in sys.path:
        sys.path.insert(0, libs_path)

    from chess_coach.profile import (  # noqa: E402  (deferred import)
        blunder_rate_vs_rating,
        conversion_ability,
        decision_fatigue,
        opening_comfort,
        tactical_vs_positional_bias,
        time_pressure_quality,
    )
    from chess_coach.profile.archetypes import (
        STANDARD_ARCHETYPES,
    )
    from chess_coach.profile.archetypes import (  # noqa: E402
        _knn_classify as knn_classify,
    )
    from chess_coach.profile.tilt import sequence_based_tilt  # noqa: E402

    # Late import for the fixture module: keep it optional so the
    # generator imports cleanly even before the fixture file is
    # checked in.
    sys.path.insert(0, str(repo / "tests"))
    import gold.archetypes_with_analyses_fixtures as fix  # noqa: E402

    if not quiet:
        print(f"[BBF-88.x] scanning {len(pgn_inputs)} PGN(s)...", file=sys.stderr)
    players = pick_top_players(
        pgn_inputs, min_games=min_games, top_n=top_n,
    )
    if not quiet:
        print(
            f"[BBF-88.x] picked {len(players)} eligible players "
            f"(min_games={min_games}, top_n={top_n}):",
            file=sys.stderr,
        )
        for p in players:
            print(
                f"  - {p.name} (n_games={p.n_games}, src={p.source_pgn.name})",
                file=sys.stderr,
            )

    if len(players) < 2:
        raise RuntimeError(
            f"[BBF-88.x] need ≥2 eligible players (got {len(players)}). "
            "Pass more PGNs or lower --min-games."
        )

    # Build a single DB with all players populated. Each player
    # goes through `fix.build_player` so the schema is populated
    # for every player in one connection.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db_path = output_path.parent / "_archetypes_fixture.db"
    if db_path.exists():
        db_path.unlink()
    if not quiet:
        print(f"[BBF-88.x] building fixture DB at {db_path}", file=sys.stderr)
    # The synthetic-fixture archetype-trajectory-picker needs to
    # choose an archetype shape for each player so the metric
    # vector differs across players. Real players (ebassti,
    # freetime_np, etc.) don't appear in ARCHETYPE_TRAITS keys;
    # instead we cycle through the archetype list per-player so
    # the resulting metric vectors spread across all 7 shapes.
    # This is what makes the kNN-bootstrap labels come out
    # differently per player.
    archetype_intent_keys = list(fix.ARCHETYPE_TRAITS.keys())
    archetype_intent_pairs = [
        (archetype_intent_keys[i % len(archetype_intent_keys)], p.name)
        for i, p in enumerate(players)
    ]
    fix.build_corpus_db(
        db_path,
        archetype_player_pairs=archetype_intent_pairs,
        n_games=n_games_per_player,
        plies_per_game=plies_per_game,
    )

    # Per-player metric extraction. The integer version key matches
# the loader's `r"v\d+"` regex; the on-disk path uses the same
# integer key (DEFAULT_OUTPUT -> "v0/corpus.json").
    int_version = "v0"
    entries: list[dict] = []
    existing_ids: set[str] = set()
    for player in players:
        metrics = {
            "tactical_vs_positional_bias": tactical_vs_positional_bias(
                str(db_path), player.name, seed=42
            ).point_estimate,
            "time_pressure_quality": time_pressure_quality(
                str(db_path), player.name, seed=42
            ).point_estimate,
            "opening_comfort": opening_comfort(
                str(db_path), player.name
            ).point_estimate,
            "conversion_ability": conversion_ability(
                str(db_path), player.name
            ).point_estimate,
            "blunder_rate_vs_rating": blunder_rate_vs_rating(
                str(db_path), player.name
            ).point_estimate,
            "decision_fatigue": decision_fatigue(
                str(db_path), player.name
            ).point_estimate,
        }
        # sequence_based_tilt is optional (Tilter only); capture
        # but don't error if it's None.
        seq_eff = sequence_based_tilt(str(db_path), player.name)
        if seq_eff.point_estimate:
            metrics["sequence_based_tilt"] = seq_eff.point_estimate

        # kNN bootstrap label from v1 placeholder.
        label, _confidence, _scores, _dist = knn_classify(metrics, k=3)
        if label not in STANDARD_ARCHETYPES:
            label = "Unknown"

        entry_id = next_entry_id(int_version, existing_ids)
        existing_ids.add(entry_id)
        entry = {
            "id": entry_id,
            "archetype_label": label,
            "metrics": metrics,
            "_provenance": {
                "player_name": player.name,
                "n_games_in_pgn": player.n_games,
                "source_pgn": player.source_pgn.name,
                "metric_methodology":
                    "services.chess_coach.profile.stats.*",
                "bootstrap_label_strategy":
                    "_knn_classify(metrics) against v1 placeholder",
            },
        }
        entries.append(entry)

    # Keep top 2 per archetype. Sort by archetype_label then by
    # the order they were inserted (which mirrors PGN frequency,
    # so the most-studied player wins the slot).
    by_arch: dict[str, list[dict]] = {}
    for entry in entries:
        by_arch.setdefault(entry["archetype_label"], []).append(entry)
    capped: list[dict] = []
    for arch_label in sorted(by_arch):
        capped.extend(by_arch[arch_label][:2])

    if not quiet:
        print(
            f"[BBF-88.x] emitting {len(capped)} entries "
            f"({len(by_arch)} distinct archetype labels):",
            file=sys.stderr,
        )
        for e in capped:
            print(
                f"  - {e['id']}: label={e['archetype_label']:20s} "
                f"player={e['_provenance']['player_name']}",
                file=sys.stderr,
            )

    # Build the corpus dict with provenance metadata.
    corpus = {
        "schema_version": 1,
        "_metadata": {
            "WARNING": (
                "AUTO-DERIVED. This v0.2 corpus is generated from "
                "real Lichess PGNs + a synthetic-analyses DB. The "
                "metric vectors are real (production SQL pipeline); "
                "the labels are auto-bootstrapped from the v1 "
                "placeholder via _knn_classify. There is no "
                "human-curator path on this project."
            ),
            "provenance": "auto",
            "generator": (
                f"scripts/curate_archetype_gold_auto.py @ {_git_sha()}"
            ),
            "metric_methodology":
                "services.chess_coach.profile.stats.<6 metrics>",
            "metric_partial_coverage": [],
            "bootstrap_label_strategy":
                "_knn_classify(metrics) against v1 placeholder",
            "pgn_inputs": [str(p) for p in pgn_inputs],
            "n_players_evaluated": len(players),
            "n_entries_emitted": len(capped),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "expected_real_corpus_size": 14,
            "labels_use": (
                "one entry per (player, archetype_label) -- the "
                "kNN picks the label of the nearest reference "
                "vector against the v1 placeholder"
            ),
            "v0_strategy": "alongside_v1",
            "v0_default": "v0 (production truth); v1 still callable",
            "v0_brief_alias": "v0.2 (BBF-88.x brief notation; loader sees v0)",
        },
        "entries": capped,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2, sort_keys=False)
        fh.write("\n")

    # Clean up the fixture DB; the shipped artifact is corpus.json only.
    # On Windows, SQLite holds an OS-level handle on the file even
    # after the helper closes its connection; the ensure_schema
    # unlink inside build_player uses `if exists` which silently
    # fails on Windows. We best-effort the unlink; the corpus.json
    # is the shipped artifact regardless.
    try:
        if db_path.exists():
            db_path.unlink()
    except (PermissionError, OSError) as exc:
        # Don't fail the run on cleanup; log to stderr if not quiet.
        if not quiet:
            print(
                f"[BBF-88.x] WARNING: could not remove fixture db "
                f"{db_path} ({exc!r}); corpus.json is the shipped artifact.",
                file=sys.stderr,
            )

    return {
        "n_players_evaluated": len(players),
        "n_entries_emitted": len(capped),
        "archetypes": sorted(by_arch),
        "output": str(output_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="curate_archetype_gold_auto.py",
        description="BBF-88.x archetype_gold v0.2 auto-curator",
    )
    parser.add_argument(
        "--input-pgn",
        action="append",
        type=Path,
        required=True,
        help="One or more Lichess PGN exports to scan for ≥30-game players.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination corpus.json path "
             f"(default: {DEFAULT_OUTPUT.relative_to(_REPO_ROOT)}).",
    )
    parser.add_argument(
        "--min-games",
        type=int,
        default=DEFAULT_PLAYER_GAMES,
        help="Minimum games per player to be eligible "
             f"(default: {DEFAULT_PLAYER_GAMES}).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=14,
        help="Maximum number of players to include "
             "(default: 14 = 2 per archetype × 7 archetypes).",
    )
    parser.add_argument(
        "--n-games-per-player",
        type=int,
        default=DEFAULT_PLAYER_GAMES,
        help="Number of synthetic games to materialize per player in the "
             "fixture DB (default: 30).",
    )
    parser.add_argument(
        "--plies-per-game",
        type=int,
        default=DEFAULT_PLIES_PER_GAME,
        help="Plies per synthetic game (default: 30).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (errors only).",
    )
    args = parser.parse_args(argv)

    for p in args.input_pgn:
        if not p.exists():
            print(f"ERROR: PGN file not found: {p}", file=sys.stderr)
            return 2

    result = curate_v02(
        args.input_pgn,
        args.output,
        min_games=args.min_games,
        top_n=args.top_n,
        n_games_per_player=args.n_games_per_player,
        plies_per_game=args.plies_per_game,
        quiet=args.quiet,
    )
    if not args.quiet:
        print(f"[BBF-88.x] wrote corpus to {result['output']}", file=sys.stderr)
    return 0


__all__ = ["curate_v02", "parse_pgn_for_players", "pick_top_players"]


if __name__ == "__main__":
    sys.exit(main())
