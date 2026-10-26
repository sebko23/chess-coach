"""FU-45 tests for the UTF-8 mojibake guard.

The guard (`apps/desktop/scripts/lint-utf8.mjs`) was written in BBF-17 to
catch the classic "UTF-8 bytes decoded as Latin-1 and re-encoded as UTF-8"
mistake that damaged `CoachPanel.tsx`, `GameDetailPage.tsx`, and
`ProfileDashboard.tsx` during the BBF-4 / BBF-5 sprints.

It sat at the repository root (`scripts/lint-utf8.mjs`) and was ORPHANED: no
`package.json` script invoked it, no CI job ran it, and its own header
claimed otherwise. FU-45 moved it beside `check-i18n-keys.mjs` and wired it
into `pnpm lint:ci`, which the `frontend lint + test` CI job runs.

These tests lock in three things:

1. the guard is WIRED -- a `lint:utf8` script exists, `lint:ci` invokes it,
   and a CI job actually runs `pnpm lint:ci` (the positive wired-assertion
   pattern, so unwiring the guard trips this test instead of silently
   disabling it);
2. the guard DETECTS mojibake (a regression guard on the detection logic);
3. the guard ALLOWS legitimate non-ASCII (so wiring it in cannot break the
   tree on real Unicode such as em-dashes and arrows).

The test lives in the Python suite rather than the frontend suite because the
guard is a Node script: `apps/desktop/src/` is browser-only by design (no
`@types/node`, and no file under it imports a Node builtin), and `vitest`'s
`include` glob is `src/**/*.{test,spec}.{ts,tsx}`. The precedent for testing
a frontend scanner from this suite is `tests/unit/test_check_frontend_imports.py`.

NOTE: this file must not contain literal mojibake. The offending byte
sequences are constructed at runtime from codepoints.
"""

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = REPO_ROOT / "apps" / "desktop"
GUARD = DESKTOP / "scripts" / "lint-utf8.mjs"
PACKAGE_JSON = DESKTOP / "package.json"
SMOKE_YML = REPO_ROOT / ".github" / "workflows" / "smoke.yml"

# The mojibake form of a rightwards arrow (UTF-8 bytes read as Latin-1).
MOJIBAKE_ARROW = "\u00e2\u2020'"
# Real Unicode that must never be flagged.
REAL_UNICODE = "\u2192\u2014\u2026"


def _run_guard(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the guard with `cwd` as its project root."""
    return subprocess.run(
        ["node", str(GUARD)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_guard_detects_mojibake_and_exits_nonzero(tmp_path: Path) -> None:
    """A file containing the mojibake arrow must fail the guard."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.ts").write_text(f'const x = "a{MOJIBAKE_ARROW}b";\n', encoding="utf-8")

    result = _run_guard(tmp_path)

    assert result.returncode != 0, (
        "the guard must exit non-zero when it finds mojibake"
    )
    combined = result.stdout + result.stderr
    assert "mojibake site(s) found" in combined
    assert "src/bad.ts:1" in combined


def test_guard_allows_legitimate_non_ascii(tmp_path: Path) -> None:
    """Real Unicode must NOT be flagged -- wiring the guard in must not
    break the tree on em-dashes, arrows, and ellipses."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.ts").write_text(f'const x = "{REAL_UNICODE}";\n', encoding="utf-8")

    result = _run_guard(tmp_path)

    assert result.returncode == 0, (
        f"the guard must not flag legitimate Unicode; got: {result.stdout}{result.stderr}"
    )
    assert "0 mojibake sites" in result.stdout


def test_guard_scans_the_scripts_directory_too(tmp_path: Path) -> None:
    """The guard's scan scope includes `scripts/`, not only `src/`."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bad.mjs").write_text(f'const x = "{MOJIBAKE_ARROW}";\n', encoding="utf-8")

    result = _run_guard(tmp_path)

    assert result.returncode != 0
    assert "scripts/bad.mjs:1" in result.stdout + result.stderr


def test_guard_lives_beside_the_frontend_scripts() -> None:
    """FU-45: the guard used to live at the REPOSITORY ROOT. From there it
    could not scan what it claimed to scan, because `PROJECT_ROOT` is
    `process.cwd()` and `lint:ci` runs from `apps/desktop`."""
    assert not (REPO_ROOT / "scripts" / "lint-utf8.mjs").exists(), (
        "the guard must not remain at the repository root; it has to sit "
        "beside check-i18n-keys.mjs so `pnpm lint:ci` can invoke it"
    )
    assert GUARD.exists(), f"guard not found at {GUARD}"


def test_guard_is_wired_into_package_json_and_ci() -> None:
    """Positive wired-assertion.

    Per the sec02 / FU-19 lesson: a guard that exists in the repo but is not
    invoked by CI provides no protection. This test FAILS if the guard is
    unwired, so unwiring cannot pass silently.
    """
    assert PACKAGE_JSON.exists(), f"package.json not found at {PACKAGE_JSON}"
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get("scripts", {})

    # (a) a dedicated script exists and invokes the guard
    lint_utf8 = scripts.get("lint:utf8")
    assert lint_utf8 is not None, (
        "package.json defines no `lint:utf8` script; the guard must be "
        "invocable on its own, not only as part of lint:ci"
    )
    assert "scripts/lint-utf8.mjs" in lint_utf8, (
        f"the `lint:utf8` script must invoke the guard; got: {lint_utf8!r}"
    )

    # (b) lint:ci invokes it (not merely defines it)
    lint_ci = scripts.get("lint:ci")
    assert lint_ci is not None, "package.json defines no `lint:ci` script"
    assert "scripts/lint-utf8.mjs" in lint_ci, (
        f"`lint:ci` must invoke the guard; got: {lint_ci!r}"
    )

    # (c) a CI job actually runs lint:ci
    assert SMOKE_YML.exists(), f"smoke.yml not found at {SMOKE_YML}"
    smoke = SMOKE_YML.read_text(encoding="utf-8")
    assert "pnpm lint:ci" in smoke, (
        "no CI job runs `pnpm lint:ci`; the guard is wired to a script that "
        "nothing executes, which is the exact orphan condition FU-45 fixed"
    )


def test_this_test_file_is_enforced_by_ci() -> None:
    """Positive wired-assertion for THIS file.

    The CI pytest invocation is directory-globbed (`pytest tests/unit`), so
    enforcement means (a) `tests/unit` appears as a pytest argument in the
    coverage job, AND (b) this file's path does not appear in any
    `--ignore=` line. Both conditions must hold.
    """
    smoke = SMOKE_YML.read_text(encoding="utf-8")

    # Isolate the coverage job's pytest invocation so we do not
    # false-positive on the boot job's or the qdrant job's pytest args.
    match = re.search(
        r"coverage:.*?Run pytest with coverage.*?(?=^  [a-z]|\Z)",
        smoke,
        re.S | re.M,
    )
    assert match, "coverage job 'Run pytest with coverage' block not found in smoke.yml"
    block = match.group(0)

    file_path = "tests/unit/test_lint_utf8_guard.py"
    file_dir = "tests/unit"

    # Condition (a): the file's directory is in the pytest args.
    assert file_dir in block, (
        f"{file_dir} not in the coverage job's pytest args; per the sec02 "
        "lesson (a regression test unenforced by CI provides no real "
        "protection), this directory must be globbed by the pytest invocation."
    )

    # Condition (b): the file is not in any --ignore= flag.
    #
    # The two jobs format their pytest invocation differently -- the coverage
    # job puts the whole invocation on ONE long line, while the boot job
    # uses backslash line-continuations -- so a line-anchored regex would
    # silently miss an --ignore= in the coverage job (the FU-31
    # comment-noise / false-positive caveat). Scan the whole invocation
    # instead, after stripping YAML comment lines so a commented-out flag
    # cannot produce a false positive.
    code_only = "\n".join(
        line for line in block.split("\n") if not line.lstrip().startswith("#")
    )
    ignore_flags = re.findall(r"--ignore=(\S+)", code_only)
    assert file_path not in ignore_flags, (
        f"{file_path} is in the coverage job's --ignore= list ({ignore_flags}); "
        "the test is explicitly excluded from CI enforcement."
    )


def test_no_literal_mojibake_in_this_file() -> None:
    """This file lives in `tests/`, which the guard does NOT scan -- but it
    still must not contain literal mojibake. The strings it builds ARE the
    guard's own needles, so a literal copy would be indistinguishable from a
    real hit."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert MOJIBAKE_ARROW not in source, (
        "this file must not contain literal mojibake; construct it from "
        "codepoints instead (see MOJIBAKE_ARROW)"
    )
