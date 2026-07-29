# BBF-86.4 — Ruff strategy decision (repo-wide audit)

**Author:** Hermes session 2026-07-29 (post F3 + F4 + BBF-86.2 ship cluster).
**Parent:** BBF-86 release-readiness audit; addresses §13.3 Tier 2 #9.
**Brief scope:** "repo-wide Ruff audit decision".

---

## 0. The decision at hand

Three plausible strategies for closing the remaining **134-error**
Ruff baseline on `main@4cfd664` (after this session's BBF-86.2 removed
27 from `services/chess_coach/profile/`):

1. **Per-slice BBFs** (v2 handoff §13.3 default): BBF-86.1 /
   BBF-86.3 / BBF-86.x — each scope is one directory or one
   rule family.
2. **Mega-BBF** (folded into BBF-90): one large BBF covers all
   remaining debt.
3. **Auto-fix-only**: rely on `ruff check --fix --unsafe-fixes` +
   `# noqa` annotations. Defer manual edits to no time soon.

Decision below. Brief is required reading before resuming
gate-keeping on BBF-86.1 / BBF-86.3 / BBF-86.x.

---

## 1. Current state (audit on `main@4cfd664`)

### 1.1 Per-directory Ruff error count

```
119  services/chess_coach/gateway/        <-- 88% of remaining
 10  services/chess_coach/engine_orch/
  3  services/chess_coach/llm_router/
  2  services/chess_coach/kb/
  0  libs/
  0  apps/cli/
---
134 total (union of libs + services + apps/cli)
```

Footnote: ruff targeting the named sub-dirs `pdf_ingest/`,
`pgn_import/`, `backfill_analyses/` (per prior layout intent in
the v2 handoff) returns 3× E902 (file not found); those paths
do not physically exist on this branch. The recursive
parent walk `ruff check libs services apps/cli` skips
non-existent sub-dirs and returns 134. The per-directory
table above is the recursive-walk reading; the
`pdf_ingest/pgn_import/backfill_analyses` entries are
dropped accordingly. A future BBF may instantiate the
`pdf_ingest/` etc. sub-trees; BBF-86.x (engine_orch + misc
1-offs) covers only what currently exists.

### 1.2 Per-rule breakdown (134 errors)

| Rule | Count | Auto-fixable | Notes |
|---|---|---|---|
| E501 line-too-long | 24 | ✗ | manual wrap |
| E402 module-import-not-at-top-of-file | 22 | ✗ | inline `# noqa: E402` per site (precedent at `gateway/app.py:37`) |
| I001 unsorted-imports | 21 | ✅ | `--fix` |
| F401 unused-import | 12 | ✅ | `--fix` |
| B904 raise-without-from | 8 | ✗ | structural `raise … from err` |
| B008 function-call-in-default | 6 | ✗ | FastAPI `Depends()` is the intended pattern; file-level `# ruff: noqa: B008` |
| UP017 datetime-timezone-utc | 6 | ✅ | `--fix --unsafe-fixes` |
| S608 hardcoded-sql-expression | 5 | ✗ | per-site review; `# noqa: S608` + rationale (BBF-86.2 precedent) |
| S110 try-except-pass | 4 | ✗ | add `logger.warning(...)` |
| W292 missing-newline-at-end | 4 | ✅ | `--fix` |
| ASYNC240 blocking-path-in-async | 3 | ✗ | structural (move out of async) |
| SIM105 suppressible-exception | 3 | ✗ | `contextlib.suppress` rewrites |
| SIM108 if-else-instead-of-if-exp | 3 | ✗ | ternary rewrite |
| UP041 timeout-error-alias | 3 | ✅ | `--fix --unsafe-fixes` |
| B007 unused-loop-control | 2 | ✗ | rename to `_` |
| S104 hardcoded-bind-all | 2 | ✗ | `# noqa: S104` for config knobs |
| UP037 quoted-annotation | 2 | ✅ | `--fix --unsafe-fixes` |
| ASYNC110 async-busy-wait | 1 | ✗ | replace `await asyncio.sleep` with `asyncio.Event` |
| B905 zip-without-strict | 1 | ✅ | `--fix --unsafe-fixes` (BBF-86.2 lesson: emits `strict=False`, preserves silent-truncation) |
| SIM117 multiple-with | 1 | ✗ | combined `with` statement |
| UP042 replace-str-enum | 1 | ✅ | `--fix --unsafe-fixes` |
| **Total** | **134** | **50 auto** | **84 manual** |

### 1.3 Latent-bug scan (`--select F821,F841,E402,A002`)

The 22 latent-bug findings are **all E402** at `services/chess_coach/gateway/app.py:20-44` plus one at `app.py:65` (`from .routes.system import build_system_router`) -- the contiguous post-`load_dotenv()` import cluster at the top of the file.
**Zero F821, zero F841, zero A002.** No real latent-bug trap;
the E402 cluster is purely stylistic / docs / `# noqa` work.

### 1.4 BBF-86.2 (profile/) as a comparable pilot

Per-session data point: cleaning 27 errors (a homogeneous
profile/ slice) took one BBF cycle (~30 tool calls) with
identical shape to what's needed elsewhere: `--fix --unsafe-fixes`
+ per-site `# noqa: S<reason>` annotations + manual per-file
edits for the structural subset. The same recipe scales.

---

## 2. Decision: **Per-slice (Option 1)**

### 2.1 Why Option 1 wins

- **Option 2 (mega-BBF):** 134 errors in one BBF is ~5× the size of
  BBF-86.2. The session that just shipped BBF-86.2 already saw
  the tool-budget struggle when BBF-86.1 hit ~70 errors.
  Mega-BBF is tooling-budget suicide per the
  chess-coach-bbf-sprint skill recommendations.

- **Option 3 (auto-fix-only):** Removes only 50 errors; leaves 84
  manual edits as perpetual debt. Per the v2 handoff §13.3 ("per-file
  Ruff slices (BBF-86.1, .2, .3) are the path forward"), the
  project expects to land these as a strategic decision.

- **Option 1 (per-slice):** Same rhythm as BBF-86.2 for each
  sub-scope; each sub-BBF has well-defined scope; each
  leaf-review cycle sees a manageable commit; no surprises.

### 2.2 Sequencing (modified §13.3 Tier 2)

| Tier | BBF | Scope | Errors | Risk | Tool budget |
|---|---|---|---|---|---|
| 1 | **BBF-86.4 (this)** | decision brief | n/a | n/a | shipped |
| 1 | **BBF-86.1** | gateway/ slice | 119 | medium-high | split into 86.1a + 86.1b below |
| 1.1 | BBF-86.1a | gateway/ --fix --unsafe-fixes + `# noqa: E402` cluster at app.py:20-44 + file-level `# ruff: noqa: B008` for the 4 affected route files | ~50 of the 119 | low | ~25 calls; smoke test of the BBF-86.2 pattern at scale |
| 1.2 | BBF-86.1b | gateway/ manual structural: B904, E501, ASYNC240, S110 | ~30 edits across 8 files | medium | ~50 calls; whole-file writes per the v0.7.100 patch-tool footgun memory |
| 1.3 | BBF-86.1c | gateway/ S608 (5 sites) + remaining SIM + W292 etc. | ~30 | medium | ~30 calls; SQL review per site |
| 2 | **BBF-86.3** | engine_orch/ Ruff slice | 10 | low | one BBF, ~15 calls |
| 2 | **BBF-86.x** | misc 1-offs: kb/ + llm_router/ + pdf_ingest/ + pgn_import/ + backfill_analyses/ | 8 total | low | one BBF, ~10 calls |

The split-86.1 into a/b/c is **the scaling lesson from this
session**: BBF-86.1 proved that 70+ edits in one BBF burns the
tool budget and risks per-edit latent-bug mistakes (the F821
pattern caught). Splitting 86.1 into a mechanical-86.1a and
structural-86.1b+86.1c earns its overhead.

### 2.3 What BBF-86.4 changes in the held-back queue

Old (v2 handoff §13.3):
- Tier 2: BBF-86.4 repo-wide Ruff audit decision
- (Subsequent BBFs 86.1, 86.2, 86.3 implicit)

New:
- **Tier 1**: BBF-86.4 (this brief; ships before any slice work)
- **Tier 1**: BBF-86.1a, BBF-86.1b, BBF-86.1c (gateway/ split)
- **Tier 2**: BBF-86.3, BBF-86.x (engine_orch + 1-offs)

### 2.4 What was tried and rejected (for posterity)

- **Single BBF-86.1 (rejected this session):** 70+ edits, latent-bug
  regression caught (`F821` introduced by patch-tool on import
  block at `gateway/routes/analysis.py`), tool budget burned.
  Reverted; the branch was deleted.
- **Path B mini-BBF split rejected**: 3 BBF briefs + 3 leaf reviews
  + 3 squash-merge cycles for a 30-error sub-scope is overhead
  without payoff. Path C (skip and ship decision) is the
  user-endorsed path here; Path B was an over-engineering trap.

---

## 3. Honest disclosures

1. **This BBF was authored by Hermes (AI agent) under explicit
   user instruction** to skip BBF-86.1 and ship the strategic
   decision first. The user surfaced the v0.7.93 dependency-graph
   pattern: BBF-86.4 is upstream of BBF-86.1's right answer.

2. **Net ruff baseline after BBF-86.2:** 134 errors (down from
   the 166 at original BBF-86 audit time, ~19% reduced). The
   remaining 88% is concentrated in `gateway/` (89% of remaining).

3. **The `services/chess_coach` total reads 134** while per-dir
   sum reads 134 too (`profile/` is 0 after BBF-86.2). The 119 in
   `gateway/` plus the 10 + 3 + 2 = 134, exactly. (Earlier
   draft listed `pdf_ingest/pgn_import/backfill_analyses`
   sub-dirs as 1+1+1; leaf review caught that those paths
   do not physically exist on this branch -- 3× E902
   file-not-found from standalone `ruff check <path>`. The
   recursive parent walk `ruff check libs services apps/cli`
   skips non-existent sub-dirs and returns 134. Footnote in
   §1.1 documents the discrepancy.)

4. **The 22 E402 in `app.py` have an existing precedent** at
   line 37 (`# noqa: E402  (BBF-87.1; follows existing app.py
   E402 pattern)`). BBF-86.1a lands the same shape uniformly.

5. **BBF-86.1a is the next BBF after this one. Per the user-endorsed
   path, BBF-86.1a should be the next `go` prompt target, then
   BBF-86.1b, then BBF-86.1c. The three-BBF split is part of
   this decision, not a future re-decision.**

6. **The brief assumes the BBF-86.2 / F3 / F4 ships cluster's
   process discipline carries forward**: every BBF gets a
   leaf review before squash-merge, with explicit `--fix
   --unsafe-fixes` + post-fix latent-bug audit.

---

## 4. Cross-references

- BBF-86 release-readiness audit (the parent): held back per
  §13.3.
- v2 handoff §13.3 Tier 2 #9: "BBF-86.4 — repo-wide Ruff audit
  decision."
- v2 handoff §13.3 Tier 1: BBF-86.1 / 86.2 are tier 1 by mistake
  of ordering; the right reading per the v0.7.93 dependency-graph
  recipe is that BBF-86.4 is the upstream tier-1 BBF and BBF-86.1
  is dependent.
- chess-coach-bbf-sprint skill v0.7.93: Multi-BBF dependency-graph
  verification, "go X and then the rest" trap.
- Skill `lint-sweep-f821-f841-audit`: latent-bug audit recipe that
  BBF-86.2 followed.
- Memory: BBF-84A prose-claim inversion trap (relevant for
  commit-body writing on 86.1a/b/c).
- Memory: patch-tool footgun at import regions / multi-line
  constructs (relevant for any structural subset edits in
  86.1b/c).
