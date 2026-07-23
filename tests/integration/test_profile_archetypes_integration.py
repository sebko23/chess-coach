"""Integration tests for BBF-65 archetype cluster via the /v1/profile/{player}/explain/archetypes endpoint.

Uses httpx.ASGITransport + AsyncClient (matches the BBF-64.3 pattern) and
patches ``cluster_archetypes`` at the route module so the handler sees
deterministic results without real DB / engine calls beyond the metrics
that the route computes upstream.

The route is /v1/profile/{player}/explain/{metric_id}; metric_id=archetypes
takes the special-case path that calls cluster_archetypes(metric_values)
and returns the ArchetypeAssignment in the effect field plus the
passes_b4_gate top-level boolean (the BBF-65.2 field).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

# BBF-66: mark all tests in this file as slow (~3 min each due to real DB +
# 6 upstream metric computations per route invocation). Excluded from PR CI;
# runs nightly. See CONTRIBUTING.md for marker semantics.
pytestmark = pytest.mark.slow

from chess_coach.gateway.app import create_app
from chess_coach.profile import ArchetypeAssignment
from chess_coach.profile.effect_size import EffectSize


AUTH = {"Authorization": "Bearer devtoken123"}


@pytest.fixture
def _archetypes_sqlite(tmp_path: Path) -> Path:
    """Create the minimal schema the archetypes route's upstream metric
    computations need to read without erroring.

    The 6 metric computations in services/chess_coach/profile/stats.py
    all run SELECT queries against {games, positions, analyses}. The
    queries all tolerate empty result sets (returning
    EffectSize(sample_size=0, ...)), so an empty schema is enough for
    the route to reach the patched cluster_archetypes() call.

    Schema mirrors libs/chess_coach/storage/migrations/{0002,0004,0005}.sql
    STRICT-mode tables (SQLite STRICT enforces declared types).
    """
    db_path = tmp_path / "sqlite" / "chess_coach.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE games (
                id            TEXT NOT NULL PRIMARY KEY,
                pgn_raw       TEXT NOT NULL,
                white         TEXT,
                black         TEXT,
                date          TEXT,
                event         TEXT,
                site          TEXT,
                result        TEXT,
                import_status TEXT NOT NULL DEFAULT 'pending'
                                  CHECK(import_status IN ('pending','analyzing','done','failed')),
                job_id        TEXT,
                created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ) STRICT;

            CREATE TABLE positions (
                id          TEXT NOT NULL PRIMARY KEY,
                game_id     TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                parent_id   TEXT REFERENCES positions(id),
                fen         TEXT NOT NULL,
                move_uci    TEXT,
                move_san    TEXT,
                ply         INTEGER NOT NULL DEFAULT 0,
                is_mainline INTEGER NOT NULL DEFAULT 1
            ) STRICT;

            CREATE TABLE analyses (
                id             TEXT NOT NULL PRIMARY KEY,
                position_id    TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
                engine_id      TEXT NOT NULL,
                depth          INTEGER NOT NULL,
                score_cp       INTEGER,
                score_mate     INTEGER,
                best_move      TEXT,
                pv_moves       TEXT,
                result_json    TEXT NOT NULL,
                created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                classification TEXT,
                cp_delta       REAL
            ) STRICT;
            """
        )
    return db_path


@pytest.fixture
def fastapi_app(tmp_path: Path, _archetypes_sqlite: Path):
    """FastAPI app with CHESS_COACH_DATA_DIR pointing at a tmp_path
    containing the minimal schema.

    The top-level tests/conftest.py autouse _isolate_env fixture
    already sets CHESS_COACH_DATA_DIR=<tmp_path>; this fixture relies
    on that plus _archetypes_sqlite to populate the SQLite DB the
    gateway reads from.

    Also activates the dev bearer token (and resets on teardown) so the
    route's auth path is exercised end-to-end. Mirrors the original
    _patch_env autouse behavior.
    """
    from chess_coach.gateway.auth import set_active_token
    set_active_token("devtoken123")
    app = create_app()
    yield app
    set_active_token(None)


def _fake_assignment(label="Tactician", confidence=0.7,
                     passes_gate=True) -> ArchetypeAssignment:
    return ArchetypeAssignment(
        label=label,
        confidence=confidence,
        archetype_scores={
            "Tactician": 0.85, "Positional Player": 0.20, "Grinder": 0.15,
            "Wildcard": 0.10, "Specialist": 0.05, "Tilter": 0.05,
            "Endgame Specialist": 0.05, "Unknown": 0.0,
        },
        effect_size=EffectSize(
            point_estimate=confidence,
            d=0.6,
            ci_low=0.5,
            ci_high=0.9,
            sample_size=8,
            null_value=0.4,
        ),
        passes_b4_gate=passes_gate,
    )


@pytest.mark.asyncio
async def test_archetypes_route_surfaces_label_and_gate(fastapi_app):
    """The route must surface label + passes_b4_gate (the BBF-65.2 field)
    in its response body."""
    with patch("chess_coach.profile.cluster_archetypes",
               return_value=_fake_assignment(label="Tactician", passes_gate=True)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/profile/ebassti/explain/archetypes",
                                 headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"]["label"] == "Tactician"
    assert body["passes_b4_gate"] is True


@pytest.mark.asyncio
async def test_archetypes_route_subthreshold_label_can_still_surface(fastapi_app):
    """A subthreshold archetype assignment should still include the label
    (the route surfaces the raw data; the UI decides whether to render
    'Inconclusive' based on passes_b4_gate).

    The mocked assignment has passes_b4_gate=False; the route must surface
    that exact boolean (not re-derive it from the EffectSize).
    """
    with patch("chess_coach.profile.cluster_archetypes",
               return_value=_fake_assignment(label="Wildcard", confidence=0.4,
                                             passes_gate=False)):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/profile/ebassti/explain/archetypes",
                                 headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"]["label"] == "Wildcard"
    assert body["passes_b4_gate"] is False
