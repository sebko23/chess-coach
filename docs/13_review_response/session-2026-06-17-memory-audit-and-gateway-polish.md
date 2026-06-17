# Memory Verification Rule

Effective: 2026-06-17

## Standing rule

Any claim sourced from memory about current code state must be verified against the live file (or `git log` for commit hashes) before being acted on. Verification output must be pasted raw, not summarized. This applies even when memory reads as plausible.

## Why this exists

This session identified 39 stale, wrong, or conflicting memory entries across roughly two hours of audit work. Specific failure modes that motivated this rule:

- "Bug 1" / "Bug 2" entries claimed SQL and frontend code was broken; both verified as stale.
- "tsc cannot run in Docker" was a confidently-stated limitation; verified as wrong (tsc 5.9.3 ran fine).
- Direct contradictions between entries saved the same day (SideBar.Coach: "fixed" vs "still pending"; backend routes: "missing" vs "all 200" three-way).
- One fabricated-from-nothing investigation (`enginesListAtom`) was caught only because raw output was demanded before action.
- A single unauthenticated commit (`/gaps` fix) was made on the basis of an inference that turned out to conflate two different bugs.
- Runbook/snapshot pairs (`bqmTBwRMnX`/`dSstw1eCSG`, `DQ6UMv4qKM`/`avC0SGOSXM`) accumulated as near-duplicates without consolidation succeeding.

The recurring pattern is **plausible-sounding inferences persisted as memory** without verification. The fix is procedural: verify, paste raw output, decide.

## Verification checklist

Before acting on any memory-sourced claim about code:

1. Read the actual file or run the actual command
2. Paste raw output (no summarization, no interpretation)
3. Confirm the claim matches ground truth
4. If the claim is wrong, delete the memory entry by ID and note the deletion in this audit log

For commit-hash claims specifically, use:

```bash
git log --oneline | grep -i "<hash1>\|<hash2>"
```

## Known unresolved limitation: memory consolidation pipeline corruption

The Agent Zero memory consolidation pipeline can produce **corrupted metadata and/or content** in saved entries. Two distinct corruption patterns observed in this session:

1. **`FCkarzONnB` (2026-06-16)**: content field is sane ("the user is willing to spend the time — this has been deferred across enough sessions"), but the structured `consolidation_type` field is filled with ~100 tokens of multi-language gibberish: "Portrait alters revealing old relatively less information hassle to optimizing simpler procedure allowance essential gratitude ideal context Specialist U Chang restrictions no consent operative comparedetstarpei resolutions/camictrand conflict alg Cases cases regards loung dimin mutual flPeak AndStatus alter importing."

2. **An unnamed entry (2026-06-16, area `fragments`)**: the entire `Content` field is multi-language gibberish with broken Unicode characters and random English fragments: "Fix for the backend sessions: The final suggested order for bottoming out the last disordered folder partly stemming from discovering an anomalous interaction uptake doc pol refers proposals c compliance AZ whe Corporation worked opening probably an expースнич attachment asynchronous cli saved builds..."

These patterns suggest the consolidation pipeline may be mixing embeddings or text from unrelated entries during merge operations. **There is no tooling available in this environment to detect or repair such corruption automatically.** Future sessions should treat any memory entry's *metadata* as untrusted, and any entry's *content* as suspect if it contains mixed-language tokens, broken Unicode, or sentence fragments that do not form a coherent statement.

## Audit log

| Date | Action | Count |
|---|---|---|
| 2026-06-17 | Deleted category-B noise (sample 1: empty strings, single tokens, gibberish) | 17 |
| 2026-06-17 | Deleted omission fixup (`siaXvFgRNq`) | 1 |
| 2026-06-17 | Deleted category-E session-log noise (sample 2) | 13 |
| 2026-06-17 | Deleted contradiction losers (`zpbmjuG8ZF`, `Tes0i2RtpQ`, `hBNkyYCRz3`, `BBfg8i3GXj`) | 4 |
| 2026-06-17 | Deleted runbook/snapshot pairs (`bqmTBwRMnX`, `dSstw1eCSG`, `DQ6UMv4qKM`, `avC0SGOSXM`) | 4 |
| 2026-06-17 | Verified HSSqURHkiv commit hashes (`0f61f36`, `e8c76ca`) — kept, accurate | 0 |

Total deletions this session: **39**.

## Outstanding items (deferred)

- **Category A (substantive entries)**: need ground-truth verification before any decision. Examples: `c9D3Wx3y28` (narration fields fix), `l88kzhllpA` (three major fixes shipped), `XhdVA6NUh0` (Phase 5 complete claim — inconsistent with Phase 2/3/4 references elsewhere).
- **"User's name is John Doe" duplicates (14 entries)**: consolidation failure, deferred pending tooling question about why deduplication did not converge.
- **Wider audit**: only ~100 of an estimated 200–500 entries have been sampled in this session. A full audit cannot be completed in one session; future sessions should resume incrementally.

## Status

**Audit closed 2026-06-17 23:35 PT.** 39 entries deleted, 1 verified-accurate entry kept (HSSqURHkiv). Two known unresolved limitations documented (consolidation corruption, John Doe dedup failure). Pending C work (gateway error-handling polish) queued for return.
