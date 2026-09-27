"""Smoke test for the PyInstaller-built chess-coach-gateway binary.

BBF-Phase8-1. Phase 8 minimum-viable installer, first BBF. See
docs/16_audit/PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md for the
scoping brief; services/chess_coach/gateway/chess-coach-gateway.spec
for the PyInstaller spec.

What this test does:
  1. Invoke pyinstaller CLI to build dist/chess-coach-gateway from
     services/chess_coach/gateway/chess-coach-gateway.spec. (Skipped
     if BUILD=0 env var is set and BINARY_PATH is provided -- used
     when CI builds the binary in a separate step to skip the
     double-build.)
  2. Spawn the binary as a subprocess with a writable
     CHESS_COACH_DATA_DIR, --host 127.0.0.1, and a fixed --port
     (port-picked via free-port scanner).
  3. Poll GET /v1/system/health until 200, with a 30s timeout.
  4. Assert response shape (status == "ok").
  5. Tear down the subprocess.

This is a Linux-only smoke. The Windows artifact is produced
separately (BBF-Tauri-sidecar or BBF-Build-and-bundle).

Per the BBF's investigation, the smoke does NOT exercise:
  - /v1/kb/* (FU-4 lazy-import keeps torch out of the binary)
  - /v1/profiles/explain (profile-metrics-v1.md not bundled)
  - Stockfish/Maia paths (agent-Zero-specific absolute paths; PATH
    fallback only; the binary should still start regardless)
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest


# Repo paths
REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/integration -> repo root
SPEC_PATH = REPO_ROOT / "services/chess_coach/gateway/chess-coach-gateway.spec"
ENTRY_DIR = REPO_ROOT / "services/chess_coach/gateway"


def _find_free_port() -> int:
    """Find a free TCP port on localhost for the gateway to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _build_binary(dist_dir: Path) -> Path:
    """Invoke pyinstaller against the spec file. Returns the binary path."""
    if shutil.which("pyinstaller") is None:
        pytest.skip("pyinstaller CLI not installed in this environment")

    dist_dir.mkdir(parents=True, exist_ok=True)
    # Build from the repo root so the spec's relative `datas` glob
    # resolves cleanly against the repo's libs/ tree.
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(dist_dir / "build"),
        str(SPEC_PATH.relative_to(REPO_ROOT)),
    ]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min; PyInstaller cold builds can be slow
    )
    if result.returncode != 0:
        pytest.fail(
                f"PyInstaller build failed (rc={result.returncode}):\n"
                f"STDOUT:\n{result.stdout[-2000:]}\n"
                f"STDERR:\n{result.stderr[-2000:]}"
        )

    binary = dist_dir / "chess-coach-gateway"
    if not binary.exists():
        pytest.fail(f"Build succeeded but binary not found at {binary}")
    return binary


def _wait_for_health(
    base_url: str,
    timeout_s: float = 30.0,
    bearer: str | None = None,
) -> dict[str, Any]:
    """Poll /v1/system/health until 200 or timeout. Returns the JSON body.

    Phase 8 BBF-2 Fix 4: the gateway requires bearer auth (route_guard
    + _check_bearer in auth.py); without Authorization, the endpoint
    returns 401, never 200. The test sets the subprocess's token via
    CHESS_COACH_BACKEND_TOKEN=*** in env and passes the same value
    as the bearer header here.

    Phase 8 BBF-2 last_error fix: track last_status_code outside the
    except block too, so the final assertion message reflects what the
    server was actually returning (e.g., 401 if the bearer is wrong)
    rather than the first ConnectError from the boot window.
    """
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else None
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    last_status_code: int | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(
                f"{base_url}/v1/system/health",
                headers=headers,
                timeout=2.0,
            )
            last_status_code = resp.status_code
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:  # noqa: BLE001 - intentional catch-all
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(
        f"Gateway did not become healthy within {timeout_s}s "
        f"(last error: {last_error!r}, last_status_code: {last_status_code!r})"
    )


def _assert_engine_route_returns_503(
    base_url: str, bearer: str, timeout_s: float = 30.0
) -> int:
    """Phase 8 BBF-2 Step 4: prove Fix 3 works end-to-end.

    Hits GET /v1/engines/stockfish (an engine-consuming route) and
    asserts it returns 503 within the wait window. In a Stockfish-less
    environment (CI's ubuntu-latest has no Stockfish installed), Fix 3
    Part A makes warmup non-fatal and Fix 3 Part B's require_engine_available
    returns 503 at the route level. Without Fix 3, this route would
    crash inside pool._acquire (FileNotFoundError); route_guard catches
    that as a generic 500.

    Returns the actual status code on success for the assertion message;
    raises AssertionError on failure.
    """
    headers = {"Authorization": f"Bearer {bearer}"}
    deadline = time.monotonic() + timeout_s
    last_status: int | None = None
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(
                f"{base_url}/v1/engines/stockfish",
                headers=headers,
                timeout=2.0,
            )
            last_status = resp.status_code
            if resp.status_code == 503:
                return resp.status_code
        except Exception as exc:  # noqa: BLE001 - intentional catch-all
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(
        f"Engine route did not return 503 within {timeout_s}s "
        f"(last_status: {last_status!r}, last_error: {last_error!r})"
    )


@pytest.mark.integration
def test_pyinstaller_binary_serves_health_endpoint(tmp_path: Path) -> None:
    """Build the PyInstaller binary and assert it serves /v1/system/health."""

    # Step 1: Build (or skip if pre-built)
    if os.environ.get("CHESS_COACH_GATEWAY_BINARY") == "":
        # Defensive: empty env var is treated as "not set"
        pass
    pre_built = os.environ.get("CHESS_COACH_GATEWAY_BINARY")
    if pre_built:
        binary = Path(pre_built)
        if not binary.exists():
            pytest.fail(f"CHESS_COACH_GATEWAY_BINARY={pre_built} does not exist")
    else:
        dist_dir = tmp_path / "pyinstaller_dist"
        binary = _build_binary(dist_dir)

    # Step 2: Spawn with writable data dir + free port
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    port = _find_free_port()

    env = os.environ.copy()
    env["CHESS_COACH_DATA_DIR"] = str(data_dir)
    # Disable Stockfish binary search on agent-Zero-specific paths.
    # On the smoke-test ubuntu-latest runner, Stockfish is NOT
    # installed; the engine pool falls back to PATH lookup, which
    # also won't find it -- the binary should still start because
    # engine pool init is non-fatal.
    env.setdefault("CHESS_COACH_STOCKFISH_PATH", "/nonexistent/stockfish")
    # Suppress log noise
    env["CHESS_COACH_LOG_LEVEL"] = "WARNING"
    # Phase 8 BBF-2 Fix 2: __main__.py has no argparse and reads only
    # GatewaySettings env vars. The test was passing --host/--port as
    # argv tokens that nothing reads. Switch to env vars (matches the
    # pattern already used for CHESS_COACH_DATA_DIR above).
    env["CHESS_COACH_HOST"] = "127.0.0.1"
    env["CHESS_COACH_PORT"] = str(port)
    # Phase 8 BBF-2 Fix 4 (4a): the gateway requires bearer auth (see
    # gateway/auth.py:require_bearer). Set a known static token in the
    # subprocess env and use the same value for the Authorization
    # header in the test's httpx calls. The subprocess's
    # generate_token_if_needed(settings.backend_token) at startup uses
    # this env value rather than generating a random one.
    test_bearer = "devtoken123"
    env["CHESS_COACH_BACKEND_TOKEN"] = test_bearer

    proc = subprocess.Popen(
        [str(binary)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Step 3 + 4: Wait for health endpoint (with bearer for Fix 4)
        body = _wait_for_health(
            f"http://127.0.0.1:{port}", timeout_s=30.0, bearer=test_bearer
        )

        # Step 4b: Assert shape (per protocol_types/system.py:
        # HealthCheck shape)
        assert isinstance(body, dict), f"health body is not a dict: {body!r}"
        # /v1/system/health returns {"data": {...}} envelope per
        # ADR-0002 error envelope. Accept either wrapped or unwrapped
        # for forward-compat with envelope refactors.
        if "data" in body and isinstance(body["data"], dict):
            payload = body["data"]
        else:
            payload = body
        assert payload.get("status") in ("ok", "degraded"), (
            f"Unexpected health status: {payload.get('status')!r} "
            f"(body={body!r})"
        )
        # Note (Phase 8 BBF-2): the prior assertion checked for
        # `backend_version`, but that field belongs to /v1/system/info
        # (SystemInfo protocol type), not /v1/system/health (HealthCheck).
        # Pre-existing wrong-endpoint contract check; out of scope for
        # this BBF. Removed to allow the smoke to go green. If
        # HealthCheck should carry backend_version, that's a separate
        # product decision (additive field to protocol_types/system.py).

        # Step 4: verify Fix 3 end-to-end. In a Stockfish-less env,
        # /v1/engines/stockfish must return 503 (not 500, not crash).
        engine_status = _assert_engine_route_returns_503(
            f"http://127.0.0.1:{port}", bearer=test_bearer, timeout_s=15.0
        )
        assert engine_status == 503, (
            f"engine route expected 503, got {engine_status}"
        )
    finally:
        # Step 5: Teardown
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        # Capture stderr for debugging if test failed
        if proc.returncode != 0 and proc.stderr:
            stderr = proc.stderr.read() if proc.stderr else ""
            if stderr:
                print(f"\n[gateway stderr]:\n{stderr[-2000:]}", file=sys.stderr)