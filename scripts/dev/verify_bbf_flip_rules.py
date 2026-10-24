#!/usr/bin/env python3
"""Verify BBF flip process rules against a repository.

Background
----------
``docs/16_audit/BBF-FLIP-PROCESS-RULES.md`` records the verification
discipline for documentation BBFs: a self-consistency sweep, a
git-topology check, an anchor check, a preservation check, and a scope
check, all run before the first push.

Several of those checks are mechanical. This script enforces the
mechanical subset; the judgement calls (does this prose actually
describe what the code does? must this target-platform test run
before release?) remain policy, enforced by review and by the
author's own discipline.

What this script adds
----------------------
``scripts/dev/verify_commit_refs.py`` already validates ``file:line``
references in a commit body or PR body. It does **not** validate
cited SHAs: a body can name a commit that does not exist, or one that
is not an ancestor of the PR base, and the reference gate stays green.
That is the gap this script closes.

Usage
-----
Two modes.

1. Body mode — the universally-applicable CI check::

       python scripts/dev/verify_bbf_flip_rules.py \\
           --repo-root . \\
           --base <base-sha> \\
           --commit-body "$(git log -1 --format=%B HEAD)" \\
           [--pr-body "$PR_BODY"]

   Extracts every SHA-like token from the supplied bodies and requires
   that each one exists and is an ancestor of ``--base``.

2. Manifest mode — the per-flip checks an author runs before pushing::

       python scripts/dev/verify_bbf_flip_rules.py \\
           --repo-root . --base <base> --head <head> \\
           --expect-files docs/16_audit/OPEN-FOLLOWUPS.md \\
           --numstat docs/16_audit/OPEN-FOLLOWUPS.md=1,1 \\
           --require-ancestor ae543ea8 \\
           --anchor docs/16_audit/OPEN-FOLLOWUPS.md:1860=RESOLVED \\
           --preserve docs/16_audit/OPEN-FOLLOWUPS.md:1702-1721

Exit codes
----------
    0 = every requested check passed
    1 = one or more checks failed
    2 = usage or environment error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ruff: noqa: S603, S607
#
# S603 (subprocess call with untrusted input): every invocation below is
# a fixed `git` subcommand with arguments this module constructs itself
# (`rev-parse`, `merge-base`, `cat-file`, `diff`) or that come from this
# module's own CLI flags. No shell is involved (`shell=False`), so no
# argument can be interpreted by a shell.
#
# S607 (partial executable path): `git` is resolved via PATH, matching
# the pattern already used by the repo's other policy scripts
# (`scripts/curate_archetype_gold_auto.py`, `scripts/curate_narrative_gold_auto.py`).

# A SHA-like token: 7-40 hex characters. To avoid matching ordinary
# prose (a line count, a colour code, a hex id in an unrelated
# context) a token must either contain at least one hex letter
# (a-f) or be a full 40-character object id.
_SHA_TOKEN = re.compile(r"(?<![0-9a-zA-Z])([0-9a-f]{7,40})(?![0-9a-zA-Z])")

# Anchor spec: path:line=substring
_ANCHOR_SPEC = re.compile(r"^(?P<path>.+):(?P<line>\d+)=(?P<needle>.+)$")

# Preserve spec: path:start-end
_PRESERVE_SPEC = re.compile(r"^(?P<path>.+):(?P<start>\d+)-(?P<end>\d+)$")

# Numstat spec: path=add,del
_NUMSTAT_SPEC = re.compile(r"^(?P<path>.+)=(?P<add>\d+),(?P<del>\d+)$")


class RuleError(Exception):
    """A concise, user-actionable verification failure."""


def _run_git(repo_root: Path, *args: str) -> tuple[int, str]:
    """Run a git command in ``repo_root`` and return (returncode, output)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr)


def _git(repo_root: Path, *args: str) -> str:
    code, out = _run_git(repo_root, *args)
    if code != 0:
        raise RuleError(f"git {' '.join(args)} failed: {out.strip()}")
    return out


def _blob_lines(repo_root: Path, rev: str, path: str) -> list[str]:
    """Return the lines of ``path`` at ``rev``.

    Uses ``git cat-file`` rather than the working tree so the check is
    against committed content rather than whatever is on disk. This
    matters for line-ending configuration: the working tree and the
    blob can differ (this repo sets ``core.autocrlf=false`` and has no
    ``.gitattributes``, so they currently agree, but the check must not
    depend on that).
    """
    code, out = _run_git(repo_root, "cat-file", "-p", f"{rev}:{path}")
    if code != 0:
        raise RuleError(f"cannot read {path} at {rev}: {out.strip()}")
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _extract_shas(text: str) -> list[str]:
    """Extract SHA-like tokens from a body.

    Filters out tokens that are plausibly ordinary prose. A token is
    accepted only when it is a full 40-character object id, OR when it
    contains BOTH a hex letter and a digit.

    The digit requirement is load-bearing: English words made only of
    the letters a-f collide with the hex alphabet and would otherwise
    be treated as cited SHAs ("defaced", "effaced", "facaded",
    "deadbeef", "cafebabe"). A real 7-character git short SHA is
    all-letters with probability ~0.1%, so requiring a digit rejects
    prose at the cost of an occasional missed short-SHA.

    This keeps the gate from failing on ordinary prose, which matters
    more than the rare false negative: a gate that cries wolf gets
    disabled.
    """
    found: list[str] = []
    for match in _SHA_TOKEN.finditer(text):
        token = match.group(1)
        if len(token) == 40 or (re.search(r"[a-f]", token) and re.search(r"[0-9]", token)):
            found.append(token)
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for token in found:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _check_sha_ancestry(repo_root: Path, base: str, shas: list[str]) -> list[str]:
    """Every SHA must exist and be an ancestor of ``base``."""
    errors: list[str] = []
    for sha in shas:
        code, _ = _run_git(repo_root, "rev-parse", "--verify", f"{sha}^{{commit}}")
        if code != 0:
            errors.append(f"cited SHA {sha} is not a commit in this repository")
            continue
        code, _ = _run_git(repo_root, "merge-base", "--is-ancestor", sha, base)
        if code != 0:
            errors.append(f"cited SHA {sha} is not an ancestor of base {base}")
    return errors


def _check_scope(
    repo_root: Path, base: str, head: str, expect_files: list[str]
) -> list[str]:
    """The changed-file set must equal ``expect_files`` exactly."""
    changed = [
        line
        for line in _git(
            repo_root, "diff", "--name-only", f"{base}..{head}"
        ).split("\n")
        if line.strip()
    ]
    errors: list[str] = []
    if not expect_files:
        errors.append(
            "--expect-files was given but no files were listed; an empty "
            "expectation set would pass vacuously"
        )
        return errors
    if sorted(changed) != sorted(expect_files):
        unexpected = sorted(set(changed) - set(expect_files))
        missing = sorted(set(expect_files) - set(changed))
        if unexpected:
            errors.append(f"unexpected file(s) changed: {', '.join(unexpected)}")
        if missing:
            errors.append(f"expected file(s) not changed: {', '.join(missing)}")
        if not unexpected and not missing:
            errors.append(
                f"changed file set differs (order/case): {changed} != {expect_files}"
            )
    return errors


def _check_numstat(
    repo_root: Path, base: str, head: str, specs: list[str]
) -> list[str]:
    """Each ``path=add,del`` spec must match the real numstat."""
    actual: dict[str, tuple[int, int]] = {}
    for line in _git(
        repo_root, "diff", "--numstat", f"{base}..{head}"
    ).split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        try:
            actual[parts[2]] = (int(parts[0]), int(parts[1]))
        except ValueError:
            continue
    errors: list[str] = []
    for spec in specs:
        match = _NUMSTAT_SPEC.match(spec)
        if not match:
            errors.append(f"malformed --numstat spec: {spec!r}")
            continue
        path = match.group("path")
        want = (int(match.group("add")), int(match.group("del")))
        if path not in actual:
            errors.append(f"numstat spec names a file with no diff: {path}")
            continue
        got = actual[path]
        if got != want:
            errors.append(
                f"numstat mismatch for {path}: expected {want[0]}/{want[1]}, "
                f"actual {got[0]}/{got[1]}"
            )
    return errors


def _check_anchors(
    repo_root: Path, head: str, specs: list[str]
) -> list[str]:
    """Each ``path:line=substring`` spec must hold at the head tree.

    This is the semantic-containment check, not an existence check: the
    cited line must actually contain the content the prose claims.
    """
    errors: list[str] = []
    for spec in specs:
        match = _ANCHOR_SPEC.match(spec)
        if not match:
            errors.append(f"malformed --anchor spec: {spec!r}")
            continue
        path = match.group("path")
        line_no = int(match.group("line"))
        needle = match.group("needle")
        try:
            lines = _blob_lines(repo_root, head, path)
        except RuleError as exc:
            errors.append(str(exc))
            continue
        if line_no < 1 or line_no > len(lines):
            errors.append(
                f"anchor {path}:{line_no} is out of range "
                f"(file has {len(lines)} lines)"
            )
            continue
        content = lines[line_no - 1]
        if needle not in content:
            errors.append(
                f"anchor {path}:{line_no} does not contain {needle!r}; "
                f"line reads: {content.strip()[:120]!r}"
            )
    return errors


def _check_preservation(
    repo_root: Path, base: str, head: str, specs: list[str]
) -> list[str]:
    """Each ``path:start-end`` spec must be byte-identical base vs head."""
    errors: list[str] = []
    for spec in specs:
        match = _PRESERVE_SPEC.match(spec)
        if not match:
            errors.append(f"malformed --preserve spec: {spec!r}")
            continue
        path = match.group("path")
        start = int(match.group("start"))
        end = int(match.group("end"))
        try:
            base_lines = _blob_lines(repo_root, base, path)
            head_lines = _blob_lines(repo_root, head, path)
        except RuleError as exc:
            errors.append(str(exc))
            continue
        if end > len(base_lines) or end > len(head_lines):
            errors.append(
                f"preserve range {path}:{start}-{end} exceeds file length "
                f"(base {len(base_lines)}, head {len(head_lines)})"
            )
            continue
        base_slice = base_lines[start - 1 : end]
        head_slice = head_lines[start - 1 : end]
        if base_slice != head_slice:
            errors.append(
                f"preserve range {path}:{start}-{end} changed between "
                f"{base[:8]} and {head[:8]}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify BBF flip process rules against a repository."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--base", required=True, help="Base commit SHA.")
    parser.add_argument("--head", default=None, help="Head commit SHA (manifest mode).")
    parser.add_argument("--commit-body", default="", help="Commit body to check.")
    parser.add_argument("--pr-body", default="", help="PR body to check.")
    parser.add_argument(
        "--expect-files",
        nargs="*",
        default=None,
        help="Exact set of files that must change between base and head.",
    )
    parser.add_argument(
        "--numstat",
        nargs="*",
        default=None,
        help="Exact numstat assertions, as path=add,del.",
    )
    parser.add_argument(
        "--require-ancestor",
        nargs="*",
        default=None,
        help="SHAs that must exist and be ancestors of base.",
    )
    parser.add_argument(
        "--anchor",
        nargs="*",
        default=None,
        help="Semantic anchor assertions, as path:line=substring.",
    )
    parser.add_argument(
        "--preserve",
        nargs="*",
        default=None,
        help="Byte-preservation assertions, as path:start-end.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"ERROR: not a git repository: {repo_root}", file=sys.stderr)
        return 2

    errors: list[str] = []
    checked: list[str] = []

    # --- SHA ancestry, from bodies and/or explicit specs -----------------
    shas = list(args.require_ancestor or [])
    body_shas = _extract_shas(args.commit_body) + _extract_shas(args.pr_body)
    for sha in body_shas:
        if sha not in shas:
            shas.append(sha)
    if shas:
        errors.extend(_check_sha_ancestry(repo_root, args.base, shas))
        checked.append(f"sha-ancestry ({len(shas)} SHA(s))")

    # --- Manifest-mode checks --------------------------------------------
    if args.head:
        if args.expect_files is not None:
            errors.extend(
                _check_scope(repo_root, args.base, args.head, args.expect_files)
            )
            checked.append(f"scope ({len(args.expect_files)} expected file(s))")
        if args.numstat:
            errors.extend(_check_numstat(repo_root, args.base, args.head, args.numstat))
            checked.append(f"numstat ({len(args.numstat)} spec(s))")
        if args.anchor:
            errors.extend(_check_anchors(repo_root, args.head, args.anchor))
            checked.append(f"anchors ({len(args.anchor)} spec(s))")
        if args.preserve:
            errors.extend(
                _check_preservation(repo_root, args.base, args.head, args.preserve)
            )
            checked.append(f"preservation ({len(args.preserve)} spec(s))")
    elif any(
        x is not None for x in (args.expect_files, args.numstat, args.anchor, args.preserve)
    ):
        print("ERROR: --head is required for manifest-mode checks", file=sys.stderr)
        return 2

    if errors:
        print(f"Found {len(errors)} rule violation(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    if checked:
        print(f"OK: BBF flip rules verified ({'; '.join(checked)}).")
    else:
        print("OK: nothing to verify.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
