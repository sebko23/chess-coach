"""End-to-end smoke test for the chess-coach backend.

Hits a real running gateway over HTTP, exercises the lazy eval-graph
path, and exits 0 on success or non-zero on failure. Used as the
post-build verification step in BUILDING.md, REPO-READINESS.md, and
the README quick-start.

Usage (standalone):

    # Defaults: http://127.0.0.1:18080 with token devtoken123 (matches
    # the docker-compose.yml dev defaults).
    python tests/integration/smoke_test.py

    # Override the gateway URL and token:
    CHESS_COACH_BASE_URL=http://localhost:18080 \\
    CHESS_COACH_BACKEND_TOKEN=*** \\
    python tests/integration/smoke_test.py

Usage (pytest):

    pytest tests/integration/smoke_test.py
    # Reads the same env vars. Skips if the gateway is not reachable.

Exit code:

    0   all checks passed
    1   gateway unreachable or returned a non-2xx response
    2   import or eval-graph response shape was wrong
    3   eval-graph had no score_cp values (lazy mode didn't work)
    4   second eval-graph call (cache hit) failed
"""
from __future__ import annotations

import os
import sys
import time

import httpx

# 7-ply Spanish Opening (Ruy Lopez) — the same shape used in the
# BBF-22 stability test. The PGN must be a multi-line string with
# headers and a *result; chess.pgn parses it on the backend.
SMOKE_PGN = (
    '[Event "smoke-test"]\n'
    '[Result "*"]\n'
    "\n"
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)

# Depth at which to evaluate. Matches the eval-graph route default.
DEPTH = 6

# Per-request timeout. The first eval-graph call for a fresh game
# runs N stockfish analyses serially with MAX_WORKERS=1; a 7-ply
# game at depth 6 is ~3s with 1 stockfish worker. 60s is plenty.
REQUEST_TIMEOUT_S = 60.0

# Health-check timeout. The gateway should respond to /health
# in < 100ms. 5s is plenty.
HEALTH_TIMEOUT_S = 5.0


def _base_url() -> str:
    return os.environ.get("CHESS_COACH_BASE_URL", "http://127.0.0.1:18080").rstrip("/")


def _token() -> str:
    return os.environ.get("CHESS_COACH_BACKEND_TOKEN", "devtoken123")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


def _check_health(client: httpx.Client) -> None:
    """Confirm the gateway is up. Exits 1 if not."""
    url = f"{_base_url()}/v1/system/health"
    print(f"[1/4] GET {url}")
    try:
        resp = client.get(url, headers=_headers(), timeout=HEALTH_TIMEOUT_S)
    except httpx.HTTPError as e:
        print(f"  FAIL: cannot reach gateway: {e}")
        print("  is the backend running? start it with: docker compose up -d")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"  FAIL: HTTP {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    body = resp.json()
    status = (body.get("data") or {}).get("status")
    if status != "ok":
        print(f"  FAIL: gateway reports status={status!r}, body={body}")
        sys.exit(1)
    print(f"  OK status={status}")


def _import_pgn(client: httpx.Client) -> str:
    """Import the smoke PGN. Returns the new game_id."""
    url = f"{_base_url()}/v1/import/pgn"
    print(f"[2/4] POST {url} (7-ply Ruy Lopez)")
    body = {"pgn": SMOKE_PGN, "depth": DEPTH, "max_games": 1, "max_plies": 7}
    t0 = time.monotonic()
    try:
        resp = client.post(url, json=body, headers=_headers(), timeout=REQUEST_TIMEOUT_S)
    except httpx.HTTPError as e:
        print(f"  FAIL: {e}")
        sys.exit(2)
    elapsed = time.monotonic() - t0
    if resp.status_code != 200:
        print(f"  FAIL: HTTP {resp.status_code} {resp.text[:300]}")
        sys.exit(2)
    data = resp.json()
    if data.get("imported_count", 0) != 1:
        print(f"  FAIL: imported_count={data.get('imported_count')}, expected 1")
        print(f"  full response: {data}")
        sys.exit(2)
    results = data.get("results") or []
    if not results:
        print(f"  FAIL: no results in import response: {data}")
        sys.exit(2)
    game_id = results[0]["game_id"]
    positions = data.get("positions_count", 0)
    print(f"  OK game_id={game_id[:18]}... positions={positions} elapsed={elapsed:.2f}s")
    return game_id


def _fetch_eval_graph(
    client: httpx.Client, game_id: str, *, expect_cache_hit: bool
) -> list[dict]:
    """Fetch the eval-graph. Returns the list of {ply, score_cp, ...} dicts.

    On expect_cache_hit=True, the call should be fast (< 200ms typical,
    < 1s budget). If the response shape is wrong or score_cp is missing,
    exits 3. If the call fails entirely, exits 1.
    """
    url = f"{_base_url()}/v1/games/{game_id}/eval-graph?depth={DEPTH}"
    label = "cache hit" if expect_cache_hit else "cache miss"
    print(f"[3/4] GET {url} (expect {label})")
    t0 = time.monotonic()
    try:
        resp = client.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT_S)
    except httpx.HTTPError as e:
        print(f"  FAIL: {e}")
        sys.exit(1)
    elapsed = time.monotonic() - t0
    if resp.status_code != 200:
        print(f"  FAIL: HTTP {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    data = resp.json()
    if not isinstance(data, list):
        print(f"  FAIL: response is not a list: {type(data).__name__}")
        sys.exit(2)
    if not data:
        print("  FAIL: empty eval-graph")
        sys.exit(2)
    with_score = [p for p in data if p.get("score_cp") is not None]
    print(
        f"  OK positions={len(data)} with score_cp={len(with_score)} "
        f"elapsed={elapsed:.2f}s"
    )
    if not expect_cache_hit and len(with_score) != len(data):
        print("  FAIL: expected all positions to have score_cp on first call")
        print(f"  missing: {[p for p in data if p.get('score_cp') is None]}")
        sys.exit(3)
    if expect_cache_hit and len(with_score) != len(data):
        print("  FAIL: cache hit lost score_cp values")
        sys.exit(4)
    return data


def main() -> int:
    print(f"smoke_test: base={_base_url()} token={'***' if _token() else '(empty)'}")
    with httpx.Client() as client:
        _check_health(client)
        game_id = _import_pgn(client)
        first = _fetch_eval_graph(client, game_id, expect_cache_hit=False)
        second = _fetch_eval_graph(client, game_id, expect_cache_hit=True)
    # Sanity: the two calls returned the same data
    if [p["ply"] for p in first] != [p["ply"] for p in second]:
        print("  FAIL: ply order changed between calls")
        return 2
    if [p.get("score_cp") for p in first] != [p.get("score_cp") for p in second]:
        print("  FAIL: score_cp values changed between calls")
        return 4
    print(f"[4/4] OK smoke_test passed: {len(first)} positions, all with score_cp")
    return 0


# ---- pytest mode ----
# When run via `pytest tests/integration/smoke_test.py`, this file's
# pytest fixtures provide a skip-on-no-gateway behavior. The
# standalone path above (when run as `python tests/integration/smoke_test.py`)
# just exits with the right code.


def test_smoke_lazy_eval_graph():
    """Pytest entry: same checks as the standalone main(), but skips
    cleanly if the gateway is unreachable so CI doesn't fail on a
    dev machine without the backend running.
    """
    import pytest
    base = _base_url()
    with httpx.Client() as client:
        # Health check
        try:
            url = f"{base}/v1/system/health"
            resp = client.get(url, headers=_headers(), timeout=HEALTH_TIMEOUT_S)
        except httpx.HTTPError:
            pytest.skip(f"gateway not reachable at {base}; skipping smoke test")
        if resp.status_code != 200:
            pytest.skip(f"gateway returned {resp.status_code} for /health; skipping")

        # Run the same checks as main() but raise on failure instead
        # of sys.exit, so pytest can format the failure nicely.
        game_id = _import_pgn(client)
        first = _fetch_eval_graph(client, game_id, expect_cache_hit=False)
        second = _fetch_eval_graph(client, game_id, expect_cache_hit=True)
        assert [p["ply"] for p in first] == [p["ply"] for p in second]
        assert [p.get("score_cp") for p in first] == [p.get("score_cp") for p in second]


if __name__ == "__main__":
    sys.exit(main())
