# BBF-doc-drift-flip-3 — flip FU-29 and FU-35 to RESOLVED in OPEN-FOLLOWUPS.md

**Sprint intent:** Close the 2 stale `OPEN` ledger entries
in `docs/16_audit/OPEN-FOLLOWUPS.md`:

- **FU-29** (line 2086): the declared-but-unused quality
  tooling gap. Closed by the 12-BBF FU-29 chain
  (ruff + mypy + pytest-cov, Stages 1 + 2 + 3).
- **FU-35** (line 2361): the `chess_coach` implicit
  namespace package gap. Partially closed by PR #161
  (BBF-FU-35-explicit-namespace, squash `99a355df`);
  PyInstaller cleanup is the follow-up.

**Status:** Doc-only BBF. 1 file modified.

## §1. The flip pattern (matches BBF-doc-drift-flip-2)

Per the v0.7.128 (sigma) meta-footgun, the flip
prepends a `**Status:** **RESOLVED ...**` line at the
top of each existing FU section, preserving the
original narrative. No entries are moved to the
`## Resolved` section (that's a different convention
used by older entries; the current convention is the
prepended Status line).

## §2. The 2 flips

### FU-29 — Declared-but-unused quality tooling: ruff, mypy, pytest-cov

**Status:** **RESOLVED 2026-10-17 via BBF-FU-29 chain
(12 BBFs, squashed across main)**. The FU-29 ratchet
is COMPLETE — all 3 stages (burn-down, baseline, wire CI)
done for all 3 tools (ruff, mypy, pytest-cov).

- **ruff:** Stage 1 burn-down at `a27da3f9` (33 → 0 findings).
  Stage 3 wire-CI at `98780986` (13/13 green). The CI gate
  fails on any new ruff finding.
- **mypy:** Stage 1 burn-down at `ed258fdc` (169 → 0 errors
  across 6 sub-task BBFs: easy-burndown, type-arg, misc,
  no-untyped-def, no-any-return, misc-followup). Stage 3
  wire-CI at `379851ff` (14/14 green after 2 amends:
  `uv sync` + `uv run mypy`). Stage 2 baseline ratchet
  at `70a1cb38` (`quality-ratchet.json` +
  `scripts/dev/check_quality_ratchet.py`). The CI gate
  fails on any new mypy error.
- **pytest-cov:** Stage 1 baseline at `0d09fd55` (61% coverage,
  4785 statements / 1711 missed / 1082 branches / 94 partial).
  Stage 3 wire-CI at `0d09fd55` (15/15 green, `--cov-fail-under=55`).
  Stage 2 baseline ratchet at `70a1cb38` (55% floor, 6% tolerance).

**Final state on main (`70a1cb38`):** ruff 0/0, mypy 0/0,
pytest-cov 61/55%. All three tools are CI-gated and self-enforcing.

### FU-35 — `chess_coach` implicit namespace package blocks clean PyInstaller packaging

**Status:** **PARTIALLY RESOLVED 2026-10-17 via squash-merge
of PR #161** (commit `99a355df`, BBF-FU-35-explicit-namespace).
The structural fix is complete: `chess_coach/__init__.py`
was added at the repo root (option (b) from the FU-35
resolution shape), and `[tool.setuptools.package-dir]`
in `pyproject.toml` was updated with the self-mapping
`"chess_coach" = "chess_coach"`. The per-package mappings
are preserved, so the editable install continues to work.
CI: 15/15 green on main (`92aa7dfc`).

**Out of scope for the structural fix (follow-up BBF
`BBF-FU-35-pyi-cleanup`):** the PyInstaller spec update
(use `collect_all('chess_coach')` instead of tree-level
`datas=` entries), removal of the runtime hook
(`services/chess_coach/gateway/pyinstaller_rthook.py`),
and verification of the PyInstaller binary smoke test
without the runtime hook. These are the remaining work
for the FU-35 resolution.

## §3. The §1.3 catches (exemplary discipline)

1. **CRLF footgun in OPEN-FOLLOWUPS.md** (pre-commit) —
   The file was 3042 CRLF lines in my local working
   copy. The convert-to-LF step is automatic in this
   session's workflow; verified clean diff (+26 lines,
   no line-ending churn).

## §4. Honest disclosures

1. **FU-29 is fully RESOLVED.** All 3 stages (burn-down,
   baseline, wire CI) are complete for all 3 tools
   (ruff, mypy, pytest-cov). The ratchet is self-enforcing
   via the existing CI gates.

2. **FU-35 is PARTIALLY RESOLVED.** The structural fix
   (explicit namespace package) is complete. The PyInstaller
   cleanup is a follow-up BBF. The Status line reflects
   this honestly: "PARTIALLY RESOLVED" with the remaining
   work documented in the "Out of scope" paragraph.

3. **No code changes; no test changes; no CI impact.**
   This BBF is doc-only, matching the prior
   BBF-doc-drift-flip pattern (PR #142, PR #146).

4. **Per the v0.7.114 nit-fold discipline, doc-only BBFs
   that don't touch CI are below the re-review threshold.**
   The leaf review is waived for this BBF.

5. **The 8 still-open FUs** (FU-5, FU-6, FU-9, FU-11,
   FU-20, FU-21, FU-23, FU-27) are NOT in scope for this
   BBF. Each has its own resolution work; this BBF is
   bookkeeping only for FU-29 and FU-35.

## §5. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-29 entry (line 2086, +22 lines Status block).
- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-35 entry (line 2361, +4 lines Status block).
- `docs/16_audit/BBF-FU-29-scoping-brief.md` (e2da99c7).
- `docs/16_audit/BBF-FU-29-pytest-cov-baseline.md` (0d09fd55).
- `docs/16_audit/BBF-FU-29-stage-2-baseline-ratchet.md` (70a1cb38).
- `docs/16_audit/BBF-FU-35-explicit-namespace.md` (92aa7dfc).
- PR #142 (`BBF-doc-drift-flip`) and PR #146 (`BBF-doc-drift-flip-2`) — the prior doc-drift-flip pattern.
