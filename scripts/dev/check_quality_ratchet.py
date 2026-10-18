#!/usr/bin/env python3
"""FU-29 stage-2 baseline-and-no-regressions ratchet checker.

Reads `quality-ratchet.json` and verifies that the current
state of all three quality tools (ruff, mypy, pytest-cov)
is at or above the documented floor. Fails with exit 1 if
any tool is below its floor.

Usage:
    python scripts/dev/check_quality_ratchet.py

Exit codes:
    0 = all tools above their floors
    1 = one or more tools below their floor
    2 = configuration error (missing file, invalid JSON, etc.)

See BBF-FU-29-stage-2-baseline-ratchet.md for the full strategy.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RATCHET_FILE = REPO_ROOT / "quality-ratchet.json"


def load_ratchet() -> dict:
    """Load the ratchet config from quality-ratchet.json."""
    if not RATCHET_FILE.exists():
        print(f"ERROR: ratchet config not found: {RATCHET_FILE}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(RATCHET_FILE) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {RATCHET_FILE}: {e}", file=sys.stderr)
        sys.exit(2)


def check_ruff(config: dict) -> tuple[int, int]:
    """Run ruff and return (findings, floor)."""
    floor = config["tools"]["ruff"]["current_floor"]
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "libs", "services", "apps/cli", "tests", "scripts"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
    )
    # Parse ruff output: "Found N errors" or "All checks passed!"
    if r.returncode == 0:
        return 0, floor
    # Try to extract the count
    m = re.search(r"Found (\d+) error", r.stdout)
    if m:
        return int(m.group(1)), floor
    # Fallback: ruff failed but we can't parse the count
    print(f"WARNING: ruff failed but could not parse count: {r.stdout[:200]}", file=sys.stderr)
    return -1, floor


def check_mypy(config: dict) -> tuple[int, int]:
    """Run mypy and return (errors, floor)."""
    floor = config["tools"]["mypy"]["current_floor"]
    r = subprocess.run(
        [sys.executable, "-m", "mypy", "libs", "services", "apps/cli", "--no-incremental"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=180,
    )
    if r.returncode == 0:
        return 0, floor
    # Parse mypy output: "Found N errors in M files"
    m = re.search(r"Found (\d+) error", r.stdout)
    if m:
        return int(m.group(1)), floor
    print(f"WARNING: mypy failed but could not parse count: {r.stdout[:200]}", file=sys.stderr)
    return -1, floor


def check_pytest_cov(config: dict) -> tuple[float, float]:
    """Run pytest with coverage and return (coverage_pct, floor)."""
    floor = config["tools"]["pytest-cov"]["current_floor"]
    # Use --cov-fail-under to get the coverage number in the output
    r = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--cov=libs/chess_coach",
            "--cov=services/chess_coach",
            "--cov=apps/cli/chess_coach",
            "--cov-report=term",
            "--no-header", "--tb=no", "-q",
            "--ignore=tests/unit/test_keychain.py",
            "--ignore=tests/unit/test_sec01_https_chessvision.py",
            "tests/unit/",
        ],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=300,
    )
    # Parse the TOTAL line from coverage report
    m = re.search(r"TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)%", r.stdout)
    if m:
        return float(m.group(1)), floor
    # Truncate to keep the warning readable
    snippet = r.stdout[-500:] if len(r.stdout) > 500 else r.stdout
    print(f"WARNING: could not parse coverage from pytest output: {snippet}", file=sys.stderr)
    return -1.0, floor


def main() -> int:
    config = load_ratchet()
    print("=" * 60)
    print("FU-29 Stage 2: Baseline-and-no-regressions ratchet")
    print("=" * 60)
    print(f"Baseline commit: {config.get('baseline_commit', 'unknown')}")
    print(f"Last updated: {config.get('last_updated', 'unknown')}")
    print()

    results = []
    all_pass = True

    # Check ruff
    ruff_count, ruff_floor = check_ruff(config)
    ruff_pass = ruff_count <= ruff_floor
    status = "✓ PASS" if ruff_pass else "✗ FAIL"
    print(f"  ruff:       {ruff_count:>4} findings (floor: {ruff_floor})  [{status}]")
    results.append(("ruff", ruff_count, ruff_floor, ruff_pass))
    if not ruff_pass:
        all_pass = False

    # Check mypy
    mypy_count, mypy_floor = check_mypy(config)
    mypy_pass = mypy_count <= mypy_floor
    status = "✓ PASS" if mypy_pass else "✗ FAIL"
    print(f"  mypy:       {mypy_count:>4} errors   (floor: {mypy_floor})  [{status}]")
    results.append(("mypy", mypy_count, mypy_floor, mypy_pass))
    if not mypy_pass:
        all_pass = False

    # Check pytest-cov
    cov_pct, cov_floor = check_pytest_cov(config)
    cov_pass = cov_pct >= cov_floor
    status = "✓ PASS" if cov_pass else "✗ FAIL"
    print(f"  pytest-cov: {cov_pct:>4.1f}%        (floor: {cov_floor}%)  [{status}]")
    results.append(("pytest-cov", cov_pct, cov_floor, cov_pass))
    if not cov_pass:
        all_pass = False

    print()
    if all_pass:
        print("All tools are at or above their floors. ✓")
        return 0
    else:
        print("One or more tools are below their floors. ✗")
        print()
        print("To fix:")
        print("  - Add tests for uncovered code (not lower the floor)")
        print("  - If a tool's floor needs to be lowered, amend quality-ratchet.json")
        print("    with a justification in the tool's notes field.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
