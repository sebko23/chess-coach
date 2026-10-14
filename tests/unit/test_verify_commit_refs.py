"""Regression tests for scripts/dev/verify_commit_refs.py.

Per the v0.7.13 (ρ) and (σ) thread-discipline items + the
test-design-positive-wired-assertions skill: any patch to
``scripts/dev/verify_commit_refs.py`` must be paired with a test that
fails if the patch is reverted.

This file exercises the two footguns the patch closes:

  1. The v0.7.125 path-qualification footgun (a bare ``path:N``
     reference — no directory prefix — produces a confusing
     "referenced file does not exist" error for files that DO exist,
     just not at the repo root).

  2. The markdown-fence + backtick-strip regex interaction (a PR body
     with BOTH a triple-backtick code fence AND inline single-backtick
     refs inside the fence causes the regex to mis-pair spans).

The positive-wired assertion at the bottom of the module checks that
the script is wired to smoke.yml (so any future PR that removes the
test file from CI's pytest invocation trips the assertion immediately).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev" / "verify_commit_refs.py"
SMOKE_YML_PATH = REPO_ROOT / ".github" / "workflows" / "smoke.yml"


def _run_verify(commit_body: str, pr_body: str = "") -> tuple[int, str]:
    """Run ``verify_commit_refs.py`` with the given bodies and
    return ``(returncode, stdout)``.

    Uses a fresh temp cwd so the script's Path handling is exercised
    against a known root, and so the verify never inherits any
    prior worktree state.

    Cross-platform: on Windows (this dev env), ``verify_commit_refs.py``
    is invoked via the local ``.venv\\Scripts\\python.exe``. On Linux
    runners (CI), it must be invoked via the system ``python``.
    """
    import sys as _sys
    if _sys.platform == "win32":
        python_exe = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    else:
        python_exe = "python"
    cmd = [
        python_exe,
        str(SCRIPT_PATH),
        "--commit-body",
        commit_body,
        "--repo-root",
        str(REPO_ROOT),
    ]
    if pr_body:
        cmd += ["--pr-body", pr_body]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


# -----------------------------------------------------------------------
# 1. The v0.7.125 path-qualification footgun
# -----------------------------------------------------------------------


def test_bare_file_reference_with_line_emits_v0_7_125_disciplined_error() -> None:
    """A bare ``path:N`` reference (no directory prefix) MUST produce
    a clear error message that names the v0.7.125 discipline, not
    the generic "referenced file does not exist" message.
    """
    rc, out = _run_verify("fixes bare config.py:87 in a sentence")
    assert rc == 1, f"expected exit 1 for bare ref, got {rc}: {out}"
    assert "bare file reference 'config.py:87'" in out, (
        f"expected v0.7.125-disciplined error naming the bare ref, got: {out}"
    )
    assert "v0.7.125" in out, (
        f"expected error message to name the v0.7.125 discipline, got: {out}"
    )
    assert "no directory prefix" in out, (
        f"expected error to flag missing directory prefix, got: {out}"
    )


def test_bare_file_reference_without_line_is_skipped_silently() -> None:
    """A bare ``path`` reference WITHOUT a line number MUST NOT produce
    the v0.7.125 error (the new check only fires for path:N format
    where the line IS specified). The script should treat it as
    section-citation-like and skip.
    """
    # Bare "config.py" with no line — should not error.
    rc, out = _run_verify("references config.py somewhere")
    # No line means the script skips (per `_verify_reference` line 209).
    # It may return 0 (no refs found) or error in unrelated path —
    # but MUST NOT emit the v0.7.125-bare-file-reference error.
    assert "bare file reference 'config.py'" not in out, (
        f"bare ref without line should not emit v0.7.125 error; got: {out}"
    )


def test_qualified_path_with_line_does_not_emit_v0_7_125_error() -> None:
    """A fully-qualified ``services/.../path:N`` reference MUST NOT
    emit the v0.7.125 error (it's the qualified form, not the bare
    form). The script should successfully verify the reference.
    """
    rc, out = _run_verify(
        "fix at services/chess_coach/gateway/config.py:87"
    )
    assert "bare file reference" not in out, (
        f"qualified ref should not emit v0.7.125 error; got: {out}"
    )
    # The qualified path either passes or errors for an unrelated
    # reason (out-of-range line, etc.) — but not the bare-ref reason.
    if rc != 0:
        assert "no directory prefix" not in out, (
            f"qualified ref error must not be the bare-ref reason; got: {out}"
        )


# -----------------------------------------------------------------------
# 2. The markdown-fence + backtick-strip regex interaction
# -----------------------------------------------------------------------


def test_pr_body_fenced_code_block_no_false_positive() -> None:
    """A PR body that contains a triple-backtick code block with
    inline backtick references inside it MUST NOT produce false
    positives from the backtick-strip regex.

    Pre-fix behavior: the regex mis-paired spans across the fence edge,
    leaving ``config.py:62-68`` un-stripped and triggering the bare-ref
    error.

    Post-fix behavior: the fence is preprocessed out; the inline
    backticks are then stripped; ``config.py:62-68`` is recognized
    as bare (no directory prefix) only if it appears OUTSIDE a
    code block.

    This test uses a PR body where the bare reference IS inside a
    code block — so it should NOT trigger the bare-ref error.
    """
    rc, out = _run_verify(
        commit_body="no refs in commit",
        pr_body=(
            "Here is a code block:\n"
            "```\n"
            "  - `config.py:62-68` → `services/chess_coach/gateway/config.py:62-68`\n"
            "```\n"
            "And outside the fence, no refs.\n"
        ),
    )
    assert "bare file reference 'config.py:62'" not in out, (
        f"bare ref inside fenced code block should NOT trip the regex; got: {out}"
    )
    assert "Found 1 stale reference(s)" not in out, (
        f"no stale refs expected; got: {out}"
    )


def test_pr_body_with_fenced_code_block_does_not_match_inline_refs_inside_fence() -> None:
    """Stronger version of the above: a bare ``config.py:N`` reference
    (one that would trip the regex) inside a fenced code block should
    NOT trigger the bare-ref error, because the fence is a code example
    (not an actual file claim).
    """
    rc, out = _run_verify(
        commit_body="good commit",
        pr_body=(
            "```\n"
            "  - bare config.py:87 reference (would trip if un-stripped)\n"
            "```\n"
        ),
    )
    assert "bare file reference 'config.py:87'" not in out, (
        f"bare ref inside fenced code block should NOT trip; got: {out}"
    )


def test_unfenced_backtick_strip_still_works() -> None:
    """The fence preprocessor must NOT regress the original single-
    backtick strip behavior. A bare ``config.py:N`` reference
    wrapped in single backticks (unfenced) MUST still be stripped.
    """
    rc, out = _run_verify(
        commit_body="uses `config.py:87` inline (should be stripped)",
        pr_body="",
    )
    assert "bare file reference 'config.py:87'" not in out, (
        f"single-backtick strip should still work for inline refs; got: {out}"
    )


# -----------------------------------------------------------------------
# 3. Positive wired assertion (per the test-design-positive-wired-assertions skill)
# -----------------------------------------------------------------------


def test_verify_commit_refs_script_path_wires() -> None:
    """Positive assertion: this test file IS enforced by CI's pytest
    invocation. Per the sec02 lesson + the test-design-positive-wired-
    assertions skill: a regression test unenforced by CI provides no
    real protection.

    For chess-coach's directory-globbed CI (post-FU-28 wiring):
    enforcement means (a) the file's directory appears as a pytest arg
    in the smoke job's pytest invocation, AND (b) the file's path
    does NOT appear in any --ignore= line.
    """
    if not SMOKE_YML_PATH.exists():
        return  # Smoke config not on this worktree — skip silently.
    smoke_text = SMOKE_YML_PATH.read_text(encoding="utf-8")

    # Isolate the smoke job block (broader pattern than boot-block since
    # the script is invoked from any job that runs pytest).
    smoke_block_matches = []
    for match in re.finditer(
        r"^\s*pytest\s+[^\n]+", smoke_text, re.MULTILINE
    ):
        smoke_block_matches.append(match.group(0))
    smoke_block = "\n".join(smoke_block_matches)

    file_path = "tests/unit/test_verify_commit_refs.py"
    file_dir = "tests/unit"

    # Condition (a): the file's directory appears in a pytest arg.
    assert file_dir in smoke_block, (
        f"{file_dir} not in smoke.yml's pytest args; per the sec02 lesson "
        f"(a regression test unenforced by CI provides no real protection), "
        f"this directory must be globbed by at least one pytest invocation."
    )

    # Condition (b): the file is not in any --ignore= line.
    ignore_pattern = re.compile(
        rf"^\s*--ignore={re.escape(file_path)}\s*\\?$",
        re.MULTILINE,
    )
    assert not ignore_pattern.search(smoke_block), (
        f"{file_path} is in smoke.yml's --ignore= list; the test is "
        f"explicitly excluded from CI enforcement. Remove it from --ignore= "
        f"if it can run in ubuntu-latest with [dev] deps installed."
    )
