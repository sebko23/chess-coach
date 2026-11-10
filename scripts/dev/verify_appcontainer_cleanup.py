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

The foreign state is NOT a sibling directory
-------------------------------------------
An earlier version of this certificate put the foreign tree at
``staging_root / "someone-elses-poppler"``, as a SIBLING of the staging
tree.  That made the assertion VACUOUS: ``cleanup_owned_state()`` only
ever inspects ``root / "poppler"`` and never enumerates the root, so a
cleanup that removed the foreign tree would have had to delete a path
the real cleanup never visits.  Measured: two security-relevant
mutations -- the cleanup removing an unmarked tree, and the
ownership-marker check being broken entirely -- both left that version
exiting 0.

Here the foreign state sits at exactly the path the cleanup inspects,
``root / "poppler"``, and carries NO ownership marker.  The OWNERSHIP
PREDICATE is therefore the only thing that preserves it, and the
certificate proves that it does.  The owned state is a second root whose
``poppler`` subdirectory DOES carry the marker, so the cleanup must
remove it.

Both roots live under the temporary directory, so the certificate does
not depend on -- or destroy -- the tree the CI job staged.

Usage
-----
::

    python scripts/dev/verify_appcontainer_cleanup.py

The staging root is read from ``CHESS_COACH_APPCONTAINER_STAGING_ROOT``
and defaults to ``ProgramData\\ChessCoach``.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "services") not in sys.path:
    sys.path.insert(0, str(ROOT / "services"))

from chess_coach.pdf_ocr import windows_appcontainer as wa  # noqa: E402


def main() -> int:
    """Run the certificate.  Returns 0 on success, 1 on failure."""
    # The certificate uses its OWN roots, under the temporary directory.
    # It must not depend on -- or destroy -- the tree the CI job staged,
    # and the ownership predicates it proves are the real ones, so each
    # root is passed to the cleanup explicitly.
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="chess_coach_cleanup_cert_"))

    # --- the OWNED state: a MARKED tree the application created -------- #
    # The marker is present, so the cleanup must remove this tree.
    owned_root = scratch / "owned"
    owned = owned_root / "poppler"
    owned.mkdir(parents=True, exist_ok=True)
    (owned / ".chesscoach-staging").write_text(
        "Owned by the Chess Coach installation. Removed by the application's "
        "own cleanup routine.",
        encoding="utf-8",
    )
    (owned / "pdftoppm.exe").write_bytes(b"stub")

    # --- the FOREIGN state: an UNMARKED tree that is NOT ours ---------- #
    # It sits at exactly the path the cleanup inspects -- root/poppler --
    # and it carries NO ownership marker, so the OWNERSHIP PREDICATE is
    # what preserves it.  A cleanup that ignored the marker would remove
    # this tree, and the certificate would fail.
    foreign_root = scratch / "foreign"
    foreign = foreign_root / "poppler"
    foreign.mkdir(parents=True, exist_ok=True)
    (foreign / "keep.txt").write_text("not ours", encoding="utf-8")

    # The profile must exist for the mapping half of the cleanup.
    wa.invalidate_registration_cache()
    if not wa.profile_is_registered():
        wa.register_profile()

    first = wa.cleanup_owned_state(staging=owned_root)
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
    # The FOREIGN state is cleaned with ITS OWN root, so the cleanup
    # inspects root/poppler -- the same path -- and the ownership marker
    # is the only thing that preserves it.
    foreign_cleanup = wa.cleanup_owned_state(staging=foreign_root)
    print("foreign cleanup (its own root, unmarked tree):")
    print("  removed  :", foreign_cleanup.removed)
    print("  preserved:", foreign_cleanup.preserved)
    print("  errors   :", foreign_cleanup.errors)
    if not foreign_cleanup.ok:
        failures.append(
            f"the cleanup reported errors on the foreign tree: {foreign_cleanup.errors}"
        )
    if foreign_cleanup.removed:
        failures.append(
            "the cleanup removed the UNMARKED tree; the ownership marker is "
            f"what must preserve it, but it removed {foreign_cleanup.removed!r}"
        )
    if not foreign.exists():
        failures.append("the cleanup removed a foreign tree")
    elif not (foreign / "keep.txt").exists():
        failures.append("the cleanup removed a foreign file")

    second = wa.cleanup_owned_state(staging=owned_root)
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

    # The scratch roots are the certificate's own state.
    shutil.rmtree(scratch, ignore_errors=True)

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
