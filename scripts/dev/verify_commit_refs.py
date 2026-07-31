"""Verify file:line references in a commit body and PR body.

Background
----------
BBF-sec-04's leaf reviewer flagged a disclosure-accuracy defect that
recurred 5 times in the BBF-sec-04 amend chain. The defect class: a
commit body (or PR body) cites file:line references that are stale,
point to the wrong section, or have changed since the body was
written. The reviewer recommended a CI check that parses every
file:line reference and verifies the file exists + the line number is
within range. This is that check.

Usage
-----
    python scripts/dev/verify_commit_refs.py \\
        --commit-body "$(git log -1 --format=%B HEAD)" \\
        [--pr-body "$PR_BODY"]

Exits 0 if all references are valid, 1 if any are stale.

What counts as a reference
--------------------------
The script parses references in two formats:

1. ``path/to/file.ext:NNN`` — a file followed by a colon and a line
   number. Examples: ``services/foo.py:42``, ``docs/audit.md §13``.

2. Markdown section citations: ``§N``, ``§N.M``, ``§N.M.K`` followed
   by an optional ``line NN``. For markdown files, the script
   resolves the section number to the actual line range and verifies
   the cited line number falls within that range.

What the script does NOT do
---------------------------
- It does not check the meaning of the citation (e.g. "the citation
  is supposed to be about pip-audit but the section is about gitleaks").
  That's a semantic check, beyond what a CI gate should do.
- It does not verify PR body self-references (e.g. "the previous
  commit"). Those are handled by the BBF-sec-04 R5 fix (commit body
  describes final state only; round-history in PR body).
- It does not check the audit's section naming against the BBF-86
  cluster's section naming. The audit file is the source of truth.

Why this is durable
-------------------
The disclosure-accuracy defect class is hard to avoid via commit-body
discipline alone. Every amend of a commit body is a fresh opportunity
to introduce stale references. The CI check makes the references
verifiable at amend time, not at code-review time.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Reference patterns:
# 1. `path/to/file.ext:NNN` — file followed by colon and line number.
#    The path can include alphanumerics, dots, slashes, underscores,
#    dashes, and tilde (for paths like `services/chess_coach/narration/`).
#    Capture groups: (1) path, (2) line number.
#
# 2. `§N` or `§N.M` or `§N.M.K` — markdown section heading markers.
#    Optionally followed by `line NN`. Capture groups: (3) section
#    number, (4) optional line number.
#
# Note: the regex is intentionally permissive on the path side
# (no path traversal protection). The script runs in a CI sandbox
# where the input is the commit body. A malicious commit body could
# include arbitrary characters; the worst case is a false negative
# (unmatched reference), not a security exploit.
_REF_PATTERN = re.compile(
    r"""(?x)
    (?:
        # Format 1: path:NNN. The path must either:
        #   - contain at least one / (directory separator), OR
        #   - end with a known file extension (.md, .py, .yml, .yaml,
        #     .json, .txt, .toml, .sh, .js, .ts, .tsx, .css, .html)
        # This avoids matching bare prose words like "valid" or
        # "invalid" while still accepting top-level files like
        # BUILDING.md and README.md.
        (?P<path>(?:[A-Za-z0-9._/\-~]+/)[A-Za-z0-9._\-~]+|(?:[A-Za-z0-9._/\-~]*[A-Za-z0-9_\-]+\.(?:md|py|yml|yaml|json|txt|toml|sh|js|ts|tsx|css|html))):(?P<line>\d+)
        |
        # Format 2: path §N[.M[.K]] (optional "line NNN"). Same path
        # requirement as Format 1.
        (?P<path2>(?:[A-Za-z0-9._/\-~]+/)[A-Za-z0-9._\-~]+|(?:[A-Za-z0-9._/\-~]*[A-Za-z0-9_\-]+\.(?:md|py|yml|yaml|json|txt|toml|sh|js|ts|tsx|css|html)))\s+§(?P<section>\d+(?:\.\d+){0,2})(?:\s+line\s+(?P<line2>\d+))?
    )
    """
)

# Markdown section heading pattern. Matches lines like:
#   ## 1. Executive Summary
#   ### 9.1 [LOW] Large corpus of session-internal documentation
_SECTION_HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)$"
)


def _parse_references(text: str) -> list[tuple[str, str | None, int | None]]:
    """Parse all references from a text.

    Returns a list of (path, section, line) tuples. Section is None
    for path:NNN formats; line is None for `§N` formats without
    `line NNN`.

    Both formats require a path; standalone `§N` references (no path)
    are not verifiable and are skipped.

    Inline code spans (backticks) are stripped before parsing, so
    prose examples of `path:NNN` syntax inside backticks (which is
    how the documentation explains the pattern) are not treated as
    actual references.
    """
    # Strip inline code spans (single and double backticks). This is
    # a regex-based on the markdown inline code syntax. We replace
    # the contents of the backticks with whitespace so that line
    # numbers elsewhere in the document are not shifted.
    stripped = re.sub(r"`[^`]+`", lambda m: " " * len(m.group()), text)
    matches: list[tuple[str, str | None, int | None]] = []
    for m in _REF_PATTERN.finditer(stripped):
        if m.group("path"):
            matches.append((m.group("path"), None, int(m.group("line"))))
        elif m.group("path2") and m.group("section"):
            line = int(m.group("line2")) if m.group("line2") else None
            matches.append((m.group("path2"), m.group("section"), line))
    return matches


def _resolve_section(path: Path, section: str) -> tuple[int, int] | None:
    """Resolve a section number to a (start, end) line range in a markdown file.

    Returns None if the file isn't markdown or the section isn't found.
    """
    if path.suffix not in (".md", ".markdown"):
        return None
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    # Find the first line whose leading hashes + section number match.
    start: int | None = None
    level: int | None = None
    for i, line in enumerate(lines, start=1):
        m = _SECTION_HEADING_RE.match(line)
        if not m:
            continue
        hashes = m.group("hashes")
        title = m.group("title")
        cur_level = len(hashes)
        # Check if this heading matches the section number.
        # Parse section prefix from the title: "1. ...", "9.1 ...", "1.2.3 ..."
        # Some headings (e.g. "### 9.1 [LOW] ...") don't have a period
        # after the section number, so we match on either "1.2.3." or
        # "1.2.3 " (with whitespace) or "1.2.3" followed by end-of-string.
        match = re.match(
            r"^(?P<sec>\d+(?:\.\d+){0,2})(?:\.|\s|$|[\[\]])",
            title,
        )
        if not match:
            continue
        cur_section = match.group("sec")
        if start is None and cur_section == section:
            start = i
            level = cur_level
        elif start is not None and cur_level <= level:
            # End of the section range.
            return start, i - 1
    if start is not None:
        return start, len(lines)
    return None


def _verify_reference(
    repo_root: Path, path: str, section: str | None, line: int | None
) -> str | None:
    """Verify a single reference. Returns an error message or None."""
    if section is not None:
        # Section-citation format. We need a path to resolve against.
        # If the path is empty, we can't verify (skip).
        if not path:
            return None
        # Resolve the section to a line range.
        full_path = repo_root / path
        if not full_path.exists():
            return f"referenced file does not exist: {path}"
        if line is None:
            # §N without "line NNN" — just verify the section exists.
            range_ = _resolve_section(full_path, section)
            if range_ is None:
                return f"section §{section} not found in {path}"
            return None
        # §N line NNN — verify the section exists and the line is within it.
        range_ = _resolve_section(full_path, section)
        if range_ is None:
            return f"section §{section} not found in {path}"
        start, end = range_
        if not (start <= line <= end):
            return (
                f"line {line} not in section §{section} of {path} "
                f"(section spans lines {start}-{end})"
            )
        return None
    # path:NNN format.
    if not path:
        return None
    full_path = repo_root / path
    if not full_path.exists():
        return f"referenced file does not exist: {path}"
    if line is None:
        return None
    total_lines = sum(1 for _ in full_path.open(encoding="utf-8"))
    if line < 1 or line > total_lines:
        return (
            f"line {line} out of range for {path} "
            f"(file has {total_lines} lines)"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify file:line references in a commit body or PR body."
    )
    parser.add_argument(
        "--commit-body",
        required=True,
        help="The commit body to verify.",
    )
    parser.add_argument(
        "--pr-body",
        default="",
        help="The PR body to verify (optional).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the repository root (default: current directory).",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()

    # Parse references from both bodies.
    commit_refs = _parse_references(args.commit_body)
    pr_refs = _parse_references(args.pr_body) if args.pr_body else []

    # Deduplicate (a reference may appear in both bodies).
    all_refs = list(commit_refs) + list(pr_refs)
    if not all_refs:
        print("No file:line references found in commit body or PR body.")
        return 0

    # Verify each reference.
    errors: list[str] = []
    seen: set[tuple[str, str | None, int | None]] = set()
    for path, section, line in all_refs:
        key = (path, section, line)
        if key in seen:
            continue
        seen.add(key)
        err = _verify_reference(repo_root, path, section, line)
        if err is not None:
            errors.append(err)

    if errors:
        print(f"Found {len(errors)} stale reference(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"All {len(seen)} reference(s) verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
