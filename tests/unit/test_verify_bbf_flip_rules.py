"""Regression tests for scripts/dev/verify_bbf_flip_rules.py.

Per the ``test-design-positive-wired-assertions`` convention, any patch
to ``scripts/dev/verify_bbf_flip_rules.py`` must be paired with a test
that fails if the patch is reverted, and the test file itself must
assert that it is enforced by CI.

The script enforces the mechanical subset of
``docs/16_audit/BBF-FLIP-PROCESS-RULES.md``:

- cited SHAs exist and are ancestors of the base (the gap left open by
  ``verify_commit_refs.py``, which checks ``file:line`` refs but not
  SHAs);
- the changed-file set matches the expected set exactly (scope check);
- each ``path=add,del`` numstat assertion matches reality;
- each ``path:line=substring`` anchor holds the content its prose
  claims (semantic containment, not line existence);
- each ``path:start-end`` range is byte-identical between base and head
  (preservation check).

The judgement calls in the rules document — does this prose describe
what the code actually does, must a target-platform test run before
release — are NOT automated here. They remain policy, enforced by
review.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev" / "verify_bbf_flip_rules.py"
SMOKE_YML_PATH = REPO_ROOT / ".github" / "workflows" / "smoke.yml"
SECURITY_AUDIT_PATH = REPO_ROOT / ".github" / "workflows" / "security-audit.yml"


def _python_exe() -> str:
    if sys.platform == "win32":
        candidate = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _run(*args: str) -> tuple[int, str]:
    """Run the verifier with the given arguments."""
    proc = subprocess.run(
        [_python_exe(), str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def _head_sha() -> str:
    return _git("rev-parse", "HEAD")


def _base_sha() -> str:
    """The merge-base of HEAD and origin/main, or HEAD's first parent.

    NOTE: CI checks out with the default ``actions/checkout@v6``
    depth-1, so ``origin/main`` and ``HEAD~1`` may not resolve. This
    helper returns "" when the history needed is unavailable, and every
    caller skips rather than failing -- the tests must not depend on
    git history depth that CI does not provide.
    """
    merge_base = _git("merge-base", "HEAD", "origin/main")
    if merge_base:
        return merge_base
    parent = _git("rev-parse", "HEAD~1")
    # A depth-1 clone echoes the unresolvable name back; treat that as absent.
    if parent and parent not in ("HEAD~1", "origin/main"):
        return parent
    return ""


def _history_available() -> bool:
    """True when the clone has enough history for the git-history checks."""
    return bool(_base_sha())


# --- SHA ancestry -------------------------------------------------------


def test_fabricated_sha_is_rejected() -> None:
    """A SHA that was never a commit must fail the gate.

    This is the gap ``verify_commit_refs.py`` leaves open: a body can
    name a plausible-looking 7-hex token that was never committed and
    the file:line reference check stays green.
    """
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        _head_sha(),
        "--require-ancestor",
        "deadbee1",
    )
    assert code == 1, f"expected exit 1 for a fabricated SHA, got {code}: {out}"
    assert "not a commit" in out, f"unexpected message: {out}"


def test_non_ancestor_sha_is_rejected() -> None:
    """A real commit that is NOT an ancestor of the base must fail.

    This is the flip-12 / FU-20 case: a brief that cites a SHA which
    exists but never landed on main.

    The base here is the merge-base of HEAD and origin/main (the branch
    point), and the candidate is picked from commits that are NOT
    ancestors of that base. Using HEAD as the base would let HEAD itself
    be chosen as the "non-ancestor" candidate, which is an ancestor of
    HEAD by definition and would make the assertion vacuous.
    """
    merge_base = _git("merge-base", "HEAD", "origin/main")
    if not merge_base or merge_base in ("origin/main",):
        return
    candidates = [
        sha
        for sha in _git("log", "--all", "--format=%H", "-50", "--not", merge_base).split("\n")
        if sha.strip() and sha.strip() != _head_sha()
    ]
    if not candidates:
        # No such commit available in this clone; the fabricated-SHA test
        # already covers the "cannot be a commit" branch.
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        merge_base,
        "--require-ancestor",
        candidates[0],
    )
    assert code == 1, f"expected exit 1 for a non-ancestor SHA, got {code}: {out}"
    assert "not an ancestor" in out, f"unexpected message: {out}"


def test_ancestor_sha_is_accepted() -> None:
    """A SHA that IS an ancestor of the base must pass."""
    base = _base_sha()
    if not base:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--require-ancestor",
        base,
    )
    assert code == 0, f"expected exit 0 for an ancestor SHA, got {code}: {out}"


def test_body_sha_is_extracted_and_checked() -> None:
    """A SHA cited in the commit body is checked, not just an explicit spec."""
    base = _base_sha()
    if not base:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--commit-body",
        f"Verified against commit {base}.",
    )
    assert code == 0, f"expected exit 0 for a body citing an ancestor, got {code}: {out}"

    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--commit-body",
        "Cited commit deadbee1 in the body.",
    )
    assert code == 1, f"expected exit 1 for a body citing a fabricated SHA, got {code}: {out}"
    assert "not a commit" in out, f"unexpected message: {out}"


# --- Scope --------------------------------------------------------------


def test_scope_rejects_unexpected_file() -> None:
    """A changed-file set beyond the expected set must fail."""
    base = _base_sha()
    head = _head_sha()
    if not base or base == head:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--head",
        head,
        "--expect-files",
        "docs/16_audit/OPEN-FOLLOWUPS.md",
    )
    assert code == 1, f"expected exit 1 for a scope mismatch, got {code}: {out}"
    assert "unexpected file" in out or "expected file" in out, f"unexpected: {out}"


def test_scope_accepts_exact_match() -> None:
    """The exact expected file set must pass."""
    base = _base_sha()
    head = _head_sha()
    if not base or base == head:
        return
    changed = [
        line
        for line in _git("diff", "--name-only", f"{base}..{head}").split("\n")
        if line.strip()
    ]
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--head",
        head,
        "--expect-files",
        *changed,
    )
    assert code == 0, f"expected exit 0 for an exact scope match, got {code}: {out}"


# --- Numstat ------------------------------------------------------------


def test_numstat_mismatch_is_rejected() -> None:
    """A wrong numstat claim must fail."""
    base = _base_sha()
    head = _head_sha()
    if not base or base == head:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--head",
        head,
        "--numstat",
        "docs/16_audit/OPEN-FOLLOWUPS.md=999,999",
    )
    assert code == 1, f"expected exit 1 for a numstat mismatch, got {code}: {out}"
    assert "numstat mismatch" in out, f"unexpected message: {out}"


def test_numstat_match_is_accepted() -> None:
    """The real numstat must pass."""
    base = _base_sha()
    head = _head_sha()
    if not base or base == head:
        return
    changed = [
        line
        for line in _git("diff", "--name-only", f"{base}..{head}").split("\n")
        if line.strip()
    ]
    specs = []
    for line in _git("diff", "--numstat", f"{base}..{head}").split("\n"):
        if not line.strip():
            continue
        add, dele, path = line.split("\t")
        specs.append(f"{path}={add},{dele}")
    if not specs:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--head",
        head,
        "--numstat",
        *specs,
    )
    assert code == 0, f"expected exit 0 for the real numstat, got {code}: {out}"
    assert changed  # sanity: the diff is non-empty


# --- Anchors (semantic containment) -------------------------------------


def test_anchor_requires_semantic_containment_not_existence() -> None:
    """A line that EXISTS but holds different content must fail.

    This is the flip-10 failure mode: an anchor check that only proves
    the line number is in range passes while every anchor is off by
    several lines.
    """
    ledger = "docs/16_audit/OPEN-FOLLOWUPS.md"
    head = _head_sha()
    # Line 1 of the ledger is the title; assert it contains something it
    # does not contain.
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        head,
        "--head",
        head,
        "--anchor",
        f"{ledger}:1=THIS_STRING_IS_NOT_IN_LINE_ONE",
    )
    assert code == 1, f"expected exit 1 for a non-matching anchor, got {code}: {out}"
    assert "does not contain" in out, f"unexpected message: {out}"


def test_anchor_accepts_real_content() -> None:
    """An anchor whose needle really is on that line must pass."""
    ledger = "docs/16_audit/OPEN-FOLLOWUPS.md"
    head = _head_sha()
    first_line = _git("show", f"{head}:{ledger}").split("\n")[0]
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        head,
        "--head",
        head,
        "--anchor",
        f"{ledger}:1={first_line[:24]}",
    )
    assert code == 0, f"expected exit 0 for a matching anchor, got {code}: {out}"


def test_anchor_out_of_range_is_rejected() -> None:
    """An anchor past the end of the file must fail."""
    ledger = "docs/16_audit/OPEN-FOLLOWUPS.md"
    head = _head_sha()
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        head,
        "--head",
        head,
        "--anchor",
        f"{ledger}:999999=anything",
    )
    assert code == 1, f"expected exit 1 for an out-of-range anchor, got {code}: {out}"
    assert "out of range" in out, f"unexpected message: {out}"


# --- Preservation -------------------------------------------------------


def test_preservation_detects_byte_drift() -> None:
    """A range that differs between base and head must fail."""
    ledger = "docs/16_audit/OPEN-FOLLOWUPS.md"
    base = _base_sha()
    head = _head_sha()
    # Compare the ledger against ITSELF at the same rev (identical), which
    # must pass; then compare across a range known to have changed.
    if not base:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        head,
        "--head",
        head,
        "--preserve",
        f"{ledger}:1-5",
    )
    assert code == 0, f"expected exit 0 for an identical range, got {code}: {out}"

    if not base or base == head:
        return
    # Find a line that actually differs, and assert the range covering it
    # is flagged as changed.
    base_lines = _git("show", f"{base}:{ledger}").split("\n")
    head_lines = _git("show", f"{head}:{ledger}").split("\n")
    diff_line = None
    for i in range(min(len(base_lines), len(head_lines))):
        if base_lines[i] != head_lines[i]:
            diff_line = i + 1
            break
    if diff_line is None:
        return
    code, out = _run(
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        base,
        "--head",
        head,
        "--preserve",
        f"{ledger}:{diff_line}-{diff_line}",
    )
    assert code == 1, f"expected exit 1 for a changed range, got {code}: {out}"
    assert "preserve range" in out, f"unexpected message: {out}"


# --- Positive wired assertion -------------------------------------------


def test_rule_script_is_wired_to_ci() -> None:
    """Positive assertion: this test file IS enforced by CI.

    Per the sec02 lesson (a regression test that exists in the repo but
    is unenforced by CI provides no real protection), this file must be
    inside the directory that CI's pytest invocation globs, and must not
    appear in any ``--ignore=`` clause in the same block.

    For directory-globbed CI the assertion encodes the INTENT (the file
    is enforced) rather than the MECHANISM (its name appears as a
    string), per the FU-31 lesson: a bare substring check can pass via a
    comment and would not fail closed.
    """
    assert SMOKE_YML_PATH.exists(), f"smoke.yml not found at {SMOKE_YML_PATH}"
    smoke_text = SMOKE_YML_PATH.read_text(encoding="utf-8")

    # Isolate the gateway-boot job's pytest invocation block so we don't
    # false-positive on another job's pytest args.
    import re

    boot_match = re.search(
        r"gateway-boot:.*?Run boot test.*?(?=^  [a-z]|\Z)",
        smoke_text,
        re.S | re.M,
    )
    assert boot_match, "gateway-boot 'Run boot test' block not found in smoke.yml"
    boot_block = boot_match.group(0)

    file_dir = "tests/unit"
    file_path = "tests/unit/test_verify_bbf_flip_rules.py"

    # Condition (a): the file's directory is a pytest arg in the boot job.
    pytest_lines = [
        line.lstrip()
        for line in boot_block.split("\n")
        if line.lstrip().startswith("pytest ")
    ]
    assert pytest_lines, "no pytest invocation line found in the gateway-boot block"
    arg_lines = " ".join(pytest_lines).split()
    assert file_dir in arg_lines, (
        f"{file_dir} not in gateway-boot's pytest args; per the sec02 lesson "
        f"(a regression test unenforced by CI provides no real protection), "
        f"this directory must be globbed by the boot job's pytest invocation."
    )

    # Condition (b): the file is not excluded by an --ignore= clause.
    ignore_pattern = re.compile(
        rf"^\s*--ignore={re.escape(file_path)}\s*\\?$", re.M
    )
    assert not ignore_pattern.search(boot_block), (
        f"{file_path} is in the boot job's --ignore= list; the test is "
        f"explicitly excluded from CI enforcement."
    )


def test_rule_script_is_referenced_by_a_ci_workflow() -> None:
    """Positive assertion: a CI workflow invokes the rule script.

    The script must be wired into the CI path, not merely present in the
    repo. This asserts the script is referenced by name in a tracked
    workflow file.
    """
    assert SECURITY_AUDIT_PATH.exists(), (
        f"security-audit.yml not found at {SECURITY_AUDIT_PATH}"
    )
    audit_text = SECURITY_AUDIT_PATH.read_text(encoding="utf-8")
    assert "verify_bbf_flip_rules.py" in audit_text, (
        "verify_bbf_flip_rules.py is NOT referenced by security-audit.yml; "
        "per the sec02 lesson (a check that exists in the repo but is "
        "unwired provides no real protection), the script must be invoked "
        "by a CI workflow."
    )
