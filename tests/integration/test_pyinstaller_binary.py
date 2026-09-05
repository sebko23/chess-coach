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


def _wait_for_health(base_url: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Poll /v1/system/health until 200 or timeout. Returns the JSON body."""
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{base_url}/v1/system/health", timeout=2.0)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:  # noqa: BLE001 - intentional catch-all
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(
        f"Gateway did not become healthy within {timeout_s}s "
        f"(last error: {last_error!r})"
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

    proc = subprocess.Popen(
        [str(binary), "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Step 3 + 4: Wait for health endpoint
        body = _wait_for_health(f"http://127.0.0.1:{port}", timeout_s=30.0)

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
        # backend_version is asserted as a non-empty string per
        # protocol_types/system.py:SystemInfo field
        bv = payload.get("backend_version", "")
        assert isinstance(bv, str) and bv, (
            f"backend_version missing or empty: {payload!r}"
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