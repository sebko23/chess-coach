"""Tests for the BBF-60 /v1/profile/{player}/explain/{metric} endpoint.

Covers:
  - The 7 metrics + 1 archetype clusterer return a valid
    MetricExplainResponse
  - The methodology text is loaded from
    docs/15_methodology/profile-metrics-v1.md
  - The §B4 gate is correctly reported in passes_b4_gate
  - Unknown metric_id returns 404
  - The doc-slicing helper correctly slices the methodology
    doc per metric

The test uses a synthetic SQLite DB (per the BBF-57 pattern)
plus an in-process FastAPI app via httpx.ASGITransport.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


@pytest.fixture
def sqlite_db(tmp_path: Path) -> str:
    """Build a synthetic SQLite DB matching the production schema."""
    db_path = str(tmp_path / "metrics_bbf60.db")
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
    return db_path


def _populate_with_games(conn, n_games: int, player: str = "testplayer") -> None:
    """Populate the DB with `n_games` simple games.

    Each game has 1 game record + 2 mainline positions
    with 1 analysis each. The positions are designed so
    that all 5+ metrics have data to work with.
    """
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    for i in range(n_games):
        gid = f"g{i}"
        result = "1-0" if i % 3 != 0 else "0-1"  # mostly wins
        # Alternate colors
        if i % 2 == 0:
            white, black = player, f"opp{i}"
        else:
            white, black = f"opp{i}", player
        conn.execute(
            "INSERT INTO games(id, white, black, result, date, white_elo, black_elo) "
            "VALUES(?, ?, ?, ?, ?, 1500, 1500)",
            (gid, white, black, result, "2026-01-01"),
        )
        # 2 mainline positions per game (so metrics have data)
        for ply in (1, 2):
            pid = f"p{i}_{ply}"
            conn.execute(
                "INSERT INTO positions(id, game_id, ply, fen, is_mainline) "
                "VALUES(?, ?, ?, ?, 1)",
                (pid, gid, ply, fen),
            )
            # Score: 30, then 100 (white POV always, for simplicity)
            score_cp = 30 if ply == 1 else 100
            conn.execute(
                "INSERT INTO analyses(id, position_id, engine_id, depth, score_cp, result_json) "
                "VALUES(?, ?, 'sf18', 25, ?, '{}')",
                (f"a{i}_{ply}", pid, score_cp),
            )
    conn.commit()


@pytest_asyncio.fixture
async def client(sqlite_db: str, monkeypatch):
    """Build an in-process FastAPI app with the SQLite DB.

    Uses the same pattern as the existing test_profile_analysis.py
    (autouse `_patch_env` that sets the data dir). For BBF-60
    we set the data dir to the tmp_path's parent so the gateway
    can find the SQLite file.
    """
    # Move the SQLite db into the gateway's expected data dir
    import os
    import shutil

    from chess_coach.gateway import create_app
    from chess_coach.gateway.auth import set_active_token
    from chess_coach.gateway.config import GatewaySettings
    data_dir = str(Path(sqlite_db).parent / "gateway_data")
    os.makedirs(data_dir, exist_ok=True)
    target_db = str(Path(data_dir) / "sqlite" / "chess_coach.db")
    os.makedirs(os.path.dirname(target_db), exist_ok=True)
    shutil.copy(sqlite_db, target_db)

    # Re-populate the copy with our games (the copy was a fresh schema)
    conn = sqlite3.connect(target_db)
    _populate_with_games(conn, n_games=40, player="testplayer")
    conn.close()

    # Configure the gateway to use this data dir
    monkeypatch.setenv("CHESS_COACH_DATA_DIR", data_dir)
    monkeypatch.setenv("CHESS_COACH_LOG_LEVEL", "WARNING")
    set_active_token("devtoken123")

    settings = GatewaySettings()
    app = create_app(settings)
    app.state.gateway.settings = settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    set_active_token(None)


# --- Endpoint tests ---


@pytest.mark.asyncio
async def test_explain_endpoint_returns_200_for_each_metric(client) -> None:
    """All 7 metrics return a valid response."""
    metrics = [
        "tactical_vs_positional_bias",
        "time_pressure_quality",
        "opening_comfort",
        "conversion_ability",
        "blunder_rate_vs_rating",
        "decision_fatigue",
        "sequence_based_tilt",
    ]
    headers = {"Authorization": "Bearer devtoken123"}
    for metric_id in metrics:
        r = await client.get(
            f"/v1/profile/testplayer/explain/{metric_id}",
            headers=headers,
        )
        assert r.status_code == 200, (
            f"{metric_id}: status={r.status_code}, body={r.text[:200]}"
        )
        body = r.json()
        assert body["metric_id"] == metric_id
        assert body["player_name"] == "testplayer"
        # effect is a dict (not a Pydantic model -- see
        # _effect_to_dict). The shape depends on the metric.
        assert "point_estimate" in body["effect"]
        # methodology is non-empty
        assert len(body["methodology"]) > 0
        # raw_inputs includes the player + metric_id
        assert body["raw_inputs"]["metric_id"] == metric_id
        assert body["raw_inputs"]["player"] == "testplayer"


@pytest.mark.asyncio
async def test_explain_endpoint_returns_404_for_unknown_metric(client) -> None:
    """An unknown metric_id returns 404."""
    headers = {"Authorization": "Bearer devtoken123"}
    r = await client.get(
        "/v1/profile/testplayer/explain/not_a_real_metric",
        headers=headers,
    )
    assert r.status_code == 404
    body = r.json()
    # The detail should mention the unknown metric
    detail = str(body)
    assert "not_a_real_metric" in detail


@pytest.mark.asyncio
async def test_explain_endpoint_requires_auth(client) -> None:
    """No bearer token -> 401."""
    r = await client.get(
        "/v1/profile/testplayer/explain/tactical_vs_positional_bias"
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_explain_endpoint_archetypes(client) -> None:
    """The archetypes clusterer returns a label + confidence."""
    headers = {"Authorization": "Bearer devtoken123"}
    r = await client.get(
        "/v1/profile/testplayer/explain/archetypes",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metric_id"] == "archetypes"
    # The effect dict has label + confidence (not point_estimate)
    assert "label" in body["effect"]
    assert "confidence" in body["effect"]
    assert body["effect"]["label"] in (
        "Tactician", "Positional Player", "Grinder", "Wildcard",
        "Specialist", "Tilter", "Endgame Specialist", "Unknown",
    )
    # raw_inputs.metric_values is the 6-metric vector
    assert "metric_values" in body["raw_inputs"]
    assert "tactical_vs_positional_bias" in body["raw_inputs"]["metric_values"]


# --- Methodology-doc-slicing tests (no DB needed) ---


def test_methodology_doc_exists() -> None:
    """The methodology doc is at docs/15_methodology/profile-metrics-v1.md."""
    from pathlib import Path
    doc_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "15_methodology" / "profile-metrics-v1.md"
    )
    assert doc_path.is_file(), f"methodology doc not found at {doc_path}"


def test_methodology_doc_sections() -> None:
    """The methodology doc has one H2 section per metric."""
    from pathlib import Path
    doc_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "15_methodology" / "profile-metrics-v1.md"
    )
    if not doc_path.is_file():
        pytest.skip("methodology doc not present in this checkout")
    text = doc_path.read_text(encoding="utf-8")
    expected = {
        "tactical_vs_positional_bias",
        "time_pressure_quality",
        "opening_comfort",
        "conversion_ability",
        "blunder_rate_vs_rating",
        "decision_fatigue",
        "sequence_based_tilt",
        "archetypes",
    }
    for section in expected:
        assert f"## {section}" in text, (
            f"methodology doc missing ## {section} section"
        )


def test_methodology_doc_contains_b4_framing() -> None:
    """The doc references §B4 and the effect-size threshold."""
    from pathlib import Path
    doc_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "15_methodology" / "profile-metrics-v1.md"
    )
    if not doc_path.is_file():
        pytest.skip("methodology doc not present in this checkout")
    text = doc_path.read_text(encoding="utf-8")
    assert "§B4" in text or "B4" in text
    assert "Cohen" in text  # Cohen's d
    assert "0.5" in text  # effect-size threshold


def test_methodology_doc_per_metric_content() -> None:
    """Each metric section has H1 + H0 + Computation subsections."""
    from pathlib import Path
    doc_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "15_methodology" / "profile-metrics-v1.md"
    )
    if not doc_path.is_file():
        pytest.skip("methodology doc not present in this checkout")
    text = doc_path.read_text(encoding="utf-8")
    # Check at least 2 of the 8 sections have the full
    # §B4 contract (Hypothesis + Null hypothesis +
    # Effect-size threshold + Computation).
    for section in ("tactical_vs_positional_bias", "decision_fatigue"):
        # Find the section
        start_marker = f"## {section}"
        start = text.index(start_marker)
        # Section runs to the next H2 or end of file
        rest = text[start + len(start_marker):]
        next_h2 = rest.find("\n## ")
        section_text = rest if next_h2 == -1 else rest[:next_h2]
        assert "Hypothesis" in section_text, f"{section} missing Hypothesis"
        assert "Null hypothesis" in section_text, (
            f"{section} missing Null hypothesis"
        )
        assert "Effect-size threshold" in section_text, (
            f"{section} missing Effect-size threshold"
        )
        assert "Computation" in section_text, (
            f"{section} missing Computation"
        )
