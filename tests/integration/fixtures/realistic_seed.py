"""Realistic integration-test fixture seed (BBF-84B).

Populates a freshly-migrated SQLite DB with:
  * 551 rows in `games` (373 owned by player 'ebassti',
    178 across other players). `created_at` is staggered 1
    second per row, most-recent first, so that the
    `ORDER BY created_at DESC` default in
    `services/chess_coach/gateway/routes/game_routes.py:44`
    produces a reproducible "first game" id (the most
    recent fixture row, `g_ebassti_0000`).
  * 3700+ rows in `training_cards` with `due <= now()` (mostly
    yesterday), spread across all players so the `default`
    aggregate satisfies due_count >= 3700.

Inserted via `aiosqlite.connect()` in a single transaction so the
whole fixture is atomic with respect to the surrounding
`_integration_db` autouse. Idempotent: starts every run with
`DELETE FROM` on the seeded tables, so a partially-populated
retry does not produce partial state.

Count values (551, 373, 3700) are deliberately pinned to the
`tests/integration/test_api_routes.py` and
`tests/integration/test_profile_analysis.py` assertion
contracts. A change to the seed counts is a deliberate test
contract change and must come with a corresponding test-body
change.

This file is the *fixture contract* for the 5 pre-existing
real-data integration failures (BBF-49 regression class). It is
not a copy of production data. Player names other than
`ebassti` are synthetic. PGN text is a 3-move Caro-Kann stub,
not real game records. The contract is row-count +
column-shape, not content.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

GAME_TOTAL: int = 551
EBASSTI_GAMES: int = 373
CARDS_DUE_TARGET: int = 3700  # must equal or exceed

PGN_STUB: str = (
    '[Event "Test fixture"]\n'
    '[Site "?"]\n'
    '[Date "2024.01.01"]\n'
    '[White "?"]\n'
    '[Black "?"]\n'
    '[Result "1/2-1/2"]\n'
    '\n'
    '1. e4 c6 2. d4 d5 1/2-1/2\n'
)


def _iso(dt: datetime) -> str:
    """Format `dt` as the project's ISO-8601 timestamp string."""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _pgn_with_players(white: str, black: str) -> str:
    # PGN headers are case-sensitive; the tests only require a
    # substring of "Event"/"[Event" so we keep the stub's
    # Event header intact and replace the player-name headers.
    lines = PGN_STUB.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith('[White '):
            out.append(f'[White "{white}"]')
        elif line.startswith('[Black '):
            out.append(f'[Black "{black}"]')
        else:
            out.append(line)
    return '\n'.join(out)


async def populate(db_path: Path) -> None:
    """Seed 551 games + 3700+ due training cards into `db_path`.

    Caller is responsible for ensuring the DB has been migrated
    first (this function does not call `migrate`). Safe to call
    multiple times against the same DB: each call wipes the
    previously-seeded rows first.
    """
    import aiosqlite

    other_players: list[str] = [f'player_{i:03d}' for i in range(1, 30)]
    other_game_count: int = GAME_TOTAL - EBASSTI_GAMES
    per_player: int = other_game_count // len(other_players)
    extra: int = other_game_count - per_player * len(other_players)
    rounds: list[int] = [
        per_player + (1 if i < extra else 0)
        for i in range(len(other_players))
    ]
    now: datetime = datetime.now(UTC).replace(microsecond=0)
    yesterday: datetime = now - timedelta(days=1)
    iso = _iso

    async with aiosqlite.connect(str(db_path)) as db:
        # Idempotent: wipe any previously-seeded rows so a
        # partially-populated retried test gets a clean fixture.
        await db.execute('DELETE FROM training_cards')
        await db.execute('DELETE FROM games')

        # Build the 551 game rows in memory first so we can
        # later iterate them in fixture order with descending
        # `created_at` (i=0 -> newest).
        fixture_rows: list[tuple[str, str, str, str]] = []
        for i in range(EBASSTI_GAMES):
            white = 'ebassti'
            black = other_players[i % len(other_players)]
            gid = f'g_ebassti_{i:04d}'
            fixture_rows.append(
                (gid, white, black, _pgn_with_players(white, black))
            )
        idx = 0
        for player, n in zip(other_players, rounds, strict=True):
            for _k in range(n):
                opponent = other_players[(idx + 3) % len(other_players)]
                gid = f'g_other_{idx:04d}'
                fixture_rows.append(
                    (
                        gid,
                        player,
                        opponent,
                        _pgn_with_players(player, opponent),
                    )
                )
                idx += 1
        assert len(fixture_rows) == GAME_TOTAL, (
            f'fixture rows: {len(fixture_rows)}, expected {GAME_TOTAL}'
        )

        for i, (gid, white, black, pgn) in enumerate(fixture_rows):
            ts = now - timedelta(seconds=i)
            await db.execute(
                'INSERT INTO games (id, pgn_raw, white, black, event, '
                'result, import_status, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    gid,
                    pgn,
                    white,
                    black,
                    'Test fixture',
                    '1/2-1/2',
                    'done',
                    iso(ts),
                    iso(ts),
                ),
            )

        # 3700+ due training cards. The /v1/training/queue/default
        # route aggregates across all players (player='default'
        # skips the player_name filter in training.py:124), so
        # the player_name distribution doesn't matter for that
        # `due_count >= 3700` assertion. The other tests in the
        # suite (e.g.
        # `test_training_schedule::TestTrainingReview::test_review_valid_rating_returns_200`)
        # ask for cards belonging to a specific player, so we
        # include some `ebassti`-owned rows as well as rows for
        # `other_players[i % N]`.
        gids: list[str] = [r[0] for r in fixture_rows]
        pool: list[str] = ['ebassti'] + other_players
        for i in range(CARDS_DUE_TARGET + 40):  # +40 buffer
            cid: str = uuid.uuid4().hex
            player: str = pool[i % len(pool)]
            gid: str = gids[i % len(gids)]
            ref: str = f'{gid}:{i:04d}'
            await db.execute(
                'INSERT INTO training_cards (id, player_name, '
                'card_type, reference_id, due, created_at, '
                'updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    cid,
                    player,
                    'position',
                    ref,
                    iso(yesterday),
                    iso(yesterday),
                    iso(yesterday),
                ),
            )

        await db.commit()
