#!/usr/bin/env python3
"""Verify the FU-20 Windows AppContainer cleanup certificate.

**BBF-FU-20-windows-appcontainer-network-isolation.**

Background
----------
The Windows AppContainer backend leaves three kinds of state behind:

1. the per-user AppContainer mapping registered under the product SID;
2. the marked parser-staging tree under the staging root;
3. the package moniker folder, which carries the container's private
   ``AC\\Temp`` area.

``cleanup_owned_state()`` removes exactly those three and nothing else:
a mapping that carries a different moniker, a staging tree without the
ownership marker, and a package folder named for another product are all
PRESERVED.

Why this is a script and not an inline command
-----------------------------------------------
The certificate used to be an inline ``python -c "..."`` inside the
workflow.  In a PowerShell DOUBLE-QUOTED string the backtick is the
escape character, so a backtick-n in the program becomes a NEWLINE.  One
comment line was silently corrupted that way, the step failed with a
``SyntaxError`` instead of a certificate result, and the ownership
property the certificate exists to prove was never actually checked on
the runner.

Running the program from a FILE removes the whole class of hazard: there
is no shell quoting between the program and the interpreter.  It also
matches the repository's existing convention -- the other gates are
``scripts/dev/verify_*.py`` programs invoked by path.

What it proves
--------------
* the cleanup removes the application-owned state it created;
* the cleanup PRESERVES a foreign, unmarked staging tree;
* a second cleanup is a successful no-op.

Usage
-----
::

    python scripts/dev/verify_appcontainer_cleanup.py

The staging root is read from ``CHESS_COACH_APPCONTAINER_STAGING_ROOT``
and defaults to ``ProgramData\\ChessCoach``.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "services") not in sys.path:
    sys.path.insert(0, str(ROOT / "services"))

from chess_coach.pdf_ocr import windows_appcontainer as wa  # noqa: E402


def main() -> int:
    """Run the certificate.  Returns 0 on success, 1 on failure."""
    staging_root = pathlib.Path(
        os.environ.get(wa.ENV_STAGING_ROOT)
        or (pathlib.Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ChessCoach")
    )

    # --- the OWNED state: a marked tree the application created -------- #
    owned = staging_root / "poppler"
    owned.mkdir(parents=True, exist_ok=True)
    (owned / ".chesscoach-staging").write_text(
        "Owned by the Chess Coach installation. Removed by the application's "
        "own cleanup routine.",
        encoding="utf-8",
    )
    (owned / "pdftoppm.exe").write_bytes(b"stub")

    # --- the FOREIGN state: an unmarked tree that is NOT ours ---------- #
    foreign = staging_root / "someone-elses-poppler"
    foreign.mkdir(parents=True, exist_ok=True)
    (foreign / "keep.txt").write_text("not ours", encoding="utf-8")

    # The profile must exist for the mapping half of the cleanup.
    wa.invalidate_registration_cache()
    if not wa.profile_is_registered():
        wa.register_profile()

    first = wa.cleanup_owned_state()
    print("first cleanup:")
    print("  removed  :", first.removed)
    print("  preserved:", first.preserved)
    print("  errors   :", first.errors)

    failures: list[str] = []
    if not first.ok:
        failures.append(f"the first cleanup reported errors: {first.errors}")
    # The FIRST pass must actually have removed the application-owned
    # state.  Asserting only that the second pass removed nothing would
    # be satisfied vacuously when the first pass removed nothing either.
    if not any("staging:" in entry for entry in first.removed):
        failures.append(
            "the owned staging tree was not removed: " + repr(first.removed)
        )
    if owned.exists():
        failures.append("the owned staging tree still exists")
    # The FOREIGN tree must survive: the cleanup is ownership-scoped.
    if not foreign.exists():
        failures.append("the cleanup removed a foreign tree")
    elif not (foreign / "keep.txt").exists():
        failures.append("the cleanup removed a foreign file")

    second = wa.cleanup_owned_state()
    print("second cleanup:")
    print("  removed  :", second.removed)
    print("  preserved:", second.preserved)
    print("  errors   :", second.errors)

    if not second.ok:
        failures.append(f"the second cleanup reported errors: {second.errors}")
    if second.removed:
        failures.append(
            "the cleanup is not idempotent; the second pass removed "
            f"{second.removed!r}"
        )

    # The foreign tree is the certificate's own scratch state.
    shutil.rmtree(foreign, ignore_errors=True)

    if failures:
        print()
        print("CLEANUP CERTIFICATE FAILED:")
        for failure in failures:
            print("  -", failure)
        return 1

    print()
    print(
        "AppContainer cleanup removes owned state, preserves foreign state, "
        "and is idempotent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
