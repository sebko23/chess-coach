# CHESS COACH documentation

This directory is the documentation index for the chess-coach
project. **Start here** — every doc file has a clear purpose and a
suggested reading order.

## Reading order

If you're **just cloning** the repo and want to run it:

1. [BUILDING.md](../../BUILDING.md) (in the repo root) — clone,
   install, smoke test
2. [REPO-READINESS.md](REPO-READINESS.md) — the operational
   guide with the 8 common pitfalls

If you're **new to the codebase** and want to understand it:

1. [README.md](../../README.md) — 1-page overview plus
   "Architecture in 60 seconds"
2. [14_adrs/](14_adrs/README.md) — the ADRs that explain *why*
   each major design decision
3. [17_lazy_eval_graph/SPEC.md](17_lazy_eval_graph/SPEC.md) — the
   BBF-22 strategic pivot to lazy eval-graph
4. [17_lazy_eval_graph/RESULTS.md](17_lazy_eval_graph/RESULTS.md)
   — the 6000-game stress test that proved the pivot worked

If you're **looking up something specific**:

- "How do I close the verification gap?" →
  [VERIFICATION.md](VERIFICATION.md)
- "What's been done?" → [CHANGELOG.md](CHANGELOG.md)
- "What are the known bugs?" → [14_adrs/ADR-0006-engine-pool-failure-modes.md](14_adrs/ADR-0006-engine-pool-failure-modes.md)
  and look for `Findings 1-5`
- "How does the protocol work?" → [../specs/](../specs/)

## Doc files

| Path | Purpose | Read time |
|---|---|---|
| [REPO-READINESS.md](REPO-READINESS.md) | "I just cloned this repo, what do I do?" — quick start, common pitfalls, ops guide | 5 min |
| [VERIFICATION.md](VERIFICATION.md) | Step-by-step instructions for closing the BBF-28/30 verification gaps | 5 min |
| [CHANGELOG.md](CHANGELOG.md) | BBF-18 → current sprint history with commit SHAs | 10 min |
| [14_adrs/README.md](14_adrs/README.md) | Architecture Decision Records — *why*, not *what* | 15 min |
| [17_lazy_eval_graph/SPEC.md](17_lazy_eval_graph/SPEC.md) | The strategic pivot: lazy eval-graph architecture | 15 min |
| [17_lazy_eval_graph/RESULTS.md](17_lazy_eval_graph/RESULTS.md) | The 6000-game stress test that verified the pivot | 5 min |

## Doc conventions

- ADRs are immutable once accepted. To change a decision, write
  a new ADR that supersedes it.
- The CHANGELOG is append-only. Sprints are listed newest-first.
- All operations-doc timing claims ("5 min", "15 min") are
  estimates; your reading time will vary.
- All cross-references between docs are relative paths so the
  rendering works on GitHub and on a local clone.

## Contributing to docs

If you're adding a doc:

1. Use Markdown (`.md` extension).
2. Cross-link generously — every doc should reference at least
   2 other docs in this directory.
3. Use the ADR template (`14_adrs/ADR-NNNN-template.md`) if
   you're writing an architecture decision record.
4. Update this `README.md` index with a new row in the table.
5. If your doc addresses a real bug, reference
   `14_adrs/ADR-0006-engine-pool-failure-modes.md` (or similar)
   so the audit trail is preserved.

If you're fixing a doc:

- Small fixes (typos, broken links): commit directly.
- Large fixes (changing the structure): open a brief that
  explains the change, similar to a BBF-N sprint.
