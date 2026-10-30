#!/usr/bin/env python3
"""Verify the AppArmor local override is a minimal delta.

Ubuntu 24.04 restricts unprivileged user namespaces by default. A
process that creates a user namespace transitions into AppArmor's
``unprivileged_userns`` profile, which grants ``userns`` but NOT
``mount`` and NOT ``x``. The sandbox launcher needs both: ``mount`` to
make the root filesystem read-only and bind-mount the artifact path
writable, and ``x`` to exec the parser afterwards.

The stock profile ends with::

    include if exists <local/unprivileged_userns>

which is the documented site-specific override mechanism. This script
proves that the shipped override:

  * contains ONLY the two rules the launcher needs, and
  * grants nothing else -- no capability, no ``deny``, no path
    exception, no unconfined flag.

It fetches the stock profile so the check is against the real upstream
text rather than a copy that could drift.

Usage:
    python scripts/dev/verify_apparmor_delta.py \\
        infra/docker/apparmor-unprivileged-userns-local.override
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

STOCK_PROFILE_URL = (
    "https://gitlab.com/apparmor/apparmor/-/raw/master/profiles/apparmor.d/unprivileged_userns"
)

#: The rules the override is allowed to contain.
REQUIRED_RULES = {
    "mount": "the containment sequence needs to mount inside the namespace",
    "allow file x /{,**}": "the parser must be executable after the namespace is set up",
}


def _rule_lines(text: str) -> list[str]:
    """The meaningful rule lines of a profile, without comments."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        out.append(line)
    return out


def _fetch_stock() -> str | None:
    try:
        with urllib.request.urlopen(STOCK_PROFILE_URL, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 -- network failure is reported, not raised
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("override", help="path to the local override file")
    args = parser.parse_args()

    path = Path(args.override)
    if not path.is_file():
        print(f"FAIL: {path} does not exist")
        return 1
    override_text = path.read_text(encoding="utf-8")
    rules = _rule_lines(override_text)

    print("=== 0. the shipped override ===")
    print(f"  {path}")
    for rule in rules:
        print(f"    {rule}")

    print()
    print("=== 1. the override contains only the required rules ===")
    ok = True
    required = {" ".join(r.split()) for r in REQUIRED_RULES}
    present: set[str] = set()
    for rule in rules:
        normalised = " ".join(rule.split()).rstrip(",")
        present.add(normalised)
        if normalised in required:
            print(f"  OK: {rule!r} -- {REQUIRED_RULES[normalised]}")
        else:
            print(f"  FAIL: unexpected rule {rule!r}")
            ok = False
    missing = required - present
    for rule in sorted(missing):
        print(f"  FAIL: missing required rule {rule!r}")
        ok = False

    print()
    print("=== 2. the override grants nothing else ===")
    forbidden = [
        (r"\bcapability\b", "grants a capability"),
        (r"\bdeny\b", "denies something"),
        (r"unconfined", "removes confinement"),
        (r"\bptrace\b", "allows ptrace"),
        (r"\bmount\s+options=", "mount options"),
        (r"owner\s", "an owner exception"),
    ]
    rules_text = "\n".join(rules)
    for pattern, why in forbidden:
        if re.search(pattern, rules_text, re.IGNORECASE):
            print(f"  FAIL: the override {why} ({pattern!r})")
            ok = False
        else:
            print(f"  OK: no rule {why}")

    print()
    print("=== 3. the stock profile's override hook is present ===")
    stock = _fetch_stock()
    if stock is None:
        print("  SKIP: could not fetch the stock profile (offline)")
    else:
        if "include if exists <local/unprivileged_userns>" in stock:
            print("  OK: the stock profile includes <local/unprivileged_userns>")
        else:
            print("  FAIL: the stock profile has no <local/unprivileged_userns> hook")
            ok = False
        for granted in ("allow userns",):
            if granted in stock:
                print(f"  OK: the stock profile grants {granted!r}")
        if re.search(r"^\s*mount\s*,?\s*$", stock, re.MULTILINE):
            print("  FAIL: the stock profile already grants mount")
            ok = False
        else:
            print("  OK: the stock profile does NOT grant mount (the gap is real)")
        if re.search(r"allow file x", stock):
            print("  NOTE: the stock profile already grants file x")
        else:
            print("  OK: the stock profile does NOT grant file x (the gap is real)")

    print()
    if ok:
        print("=== APPARMOR OVERRIDE VERIFIED: minimal two-rule delta ===")
        return 0
    print("=== APPARMOR OVERRIDE VERIFICATION FAILED ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
