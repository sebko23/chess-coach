# Chess-Coach — Project Progress Report

**Recorded:** 2026-11-25  |  **Prior report:** `docs/16_audit/PROGRESS_REPORT_2026-09-03.md` (276 lines, HEAD `4aa2d645`)

**Source basis:** figures re-derived from `origin/main` at `7eef904e443a44df624fd63a51f90d518dee6c44` (the landed flip-23 squash) and from the GitHub API. The pre-flight ran first: remote `https://github.com/sebko23/chess-coach.git`; local `HEAD` == `origin/main` (`0 0` ahead/behind); working tree clean. Quantitative comparisons use explicit, like-for-like denominators; analyst estimates and normalizations are labeled.
**Repo root:** `C:\Users\i3\verify_chess_coach\chess-coach\`

---

## 1. Headline

| Metric | 2026-09-03 (prior) | 2026-11-25 (now) | Δ |
|---|---|---|---|
| **Plan completion (equal-weight)** | **59.5%** | **61.0%** | +1.5 pts |
| **Plan completion (effort-weighted)** | **53.1%** | **54.6%** | +1.5 pts |
| Commits on `main` | baseline `4aa2d645` | 474 total; **125 after the prior-report baseline** | +125 after baseline |
| PRs merged | baseline PR #115 | **93 after PR #115** (94 including it) | +93 including baseline |
| Ledger FU entries | 34 | **47** | +13 |
| Ledger status lines (**raw marker counts**) | — | **66** plain `**Status:**` lines (59 RESOLVED, 4 OPEN, 1 PARTIAL, 1 TRACKING, **1 document-level LIVING**) + **8** clarification lines (6 RESOLVED, 1 PARTIALLY RESOLVED, 1 alpha-shipped/beta-deferred); clarification markers **overlap** plain status lines | — |
| Test files (Python files under `tests/unit` + `tests/integration`, excluding `__init__.py`) | 59 (37 unit + 22 integration) | **77** (51 unit + 26 integration) | **+18** |
| Test functions | 570 | 839 | +269 |
| Route Python files / `@router.*` decorators | 21 / 29 | 22 / 32 | +1 / +3 |
| Backend LOC — **like-for-like** (gateway routes + `libs/chess_coach/*/*.py` — the prior report's own `wc -l` scope) | 6,677 | **7,565** | **+888** |
| Backend LOC — broad (`services` + `libs` + `apps/cli`) | 12,430 | 19,530 | +7,100 |
| Numbered ADRs | 9 | **9** | 0 |
| Files in `docs/14_adrs/` | 11 (9 ADRs + template + README) | 11 (9 ADRs + template + README) | 0 |
| `docs/16_audit/` tracked files | 22 | 97 | +75 |
| CI check runs green on `main` | 10 of 11 (`pnpm audit` red) | 19 of 20 (`pnpm audit` red — **different cause**) | +9 check runs |

> **Note on the LOC comparison.** The prior report's row was labelled "Backend LOC (libs + services + cli)" but its stated command was `wc -l services/chess_coach/gateway/routes/*.py libs/chess_coach/*/*.py` — a *narrower* scope than its own label. This report compares **like-for-like against that command's scope** (6,677 → 7,565, +888) and states the broad scope separately (`services` + `libs` + `apps/cli`: 12,430 → 19,530, +7,100). The apparent "+12.9k" in the first draft of this report was a scope mismatch, not a growth claim. All LOC figures are `wc -l` (newline counts); a trailing-empty-line method over-counts by one per file.

**The honest one-liner:** the plan is roughly **55–61% complete**, up from **53.1–59.5%** (the prior report's own effort-weighted and equal-weight figures) on 2026-09-03; the remaining work is concentrated in **Phase 6 (OCR ML), Phase 7 (sync/research), and Phase 8 (packaging)** — not in the core engine, analysis, profile, repertoire, or training paths, which are largely shipped.

---

## 2. Phase-by-phase completion, and the comparison

Baseline = `docs/10_roadmap/phase-plan-v2.md:272-280` (the plan's own table). Current = re-derived from the tree on 2026-11-25.

| Phase | Prior % | Now % | Δ | What changed |
|---|---|---|---|---|
| Gate 0 — Legal + Planning | 100% | **100%** | 0 | Nothing. ADRs 0001–0009 (9 numbered ADRs; `docs/14_adrs/` also holds a template and a README), CLA family, licensing, protocol spec all committed. |
| Phase 1 — Foundation | 100% | **100%** | 0 | Nothing to do. Redis still deferred per v2; Qdrant sidecar shipped and CI-smoked. |
| Phase 2 — Engine + Analysis | 90% | **90%** | 0 | Unchanged. Stockfish 18 + depth-22 + blunder classification + lazy eval-graph ship; Leela/Maia adapters and WS streaming still deferred per v2. |
| Phase 3 — Memory + KB + LLM | 75% | **75%** | 0 | Unchanged. Engine-wired narration shipped; real-LLM production wiring still held back. The LLM router has **no stub markers** in `libs/chess_coach/llm_router/router.py` — the hold-back is a wiring/key decision, not a stub. |
| Phase 4 — Playing Style Patterns | 85% | **85%** | 0 | Unchanged. **7 metrics**: 6 in `services/chess_coach/profile/stats.py` (`tactical_vs_positional_bias`, `time_pressure_quality`, `opening_comfort`, `conversion_ability`, `blunder_rate_vs_rating`, `decision_fatigue`) plus `sequence_based_tilt` in `services/chess_coach/profile/tilt.py`. kNN classifier with 7 archetypes, dashboard + `/profiles/explain`. *(The prior report attributed all 7 to `stats.py`; the count was right, the file attribution was not.)* |
| Phase 5 — Repertoire + Training | 90% | **90%** | 0 | Unchanged. FSRS training, repertoire tree, 15 routes, typed client. |
| Phase 6 — PDF/Vision | 15% | **15%** | 0 | Unchanged. **0 references** to YOLOv8 or PaddleOCR in any tracked `.py`. The chessvision.ai API path ships; the local-ML fallback does not exist. |
| Phase 7 — Cloud Sync + Research | 15% | **15%** | 0 | Unchanged. Lichess import ships (`routes/lichess_import.py`); **no Chess.com route** (only a logo asset), **no research agent**, **no PDF export**. |
| Phase 8 — Packaging + Hardening | 25% | **40%** *(analyst re-estimate, not a roadmap value)* | +15 | **+15.** `services/chess_coach/gateway/chess-coach-gateway.spec` now exists and a `PyInstaller binary smoke` CI job is **green**. Still missing: `externalBin` in `tauri.conf.json`, `tauri build --no-bundle` (no MSI/NSIS), `tests/perf/budgets.yaml`. |
| Phase 9 — v2 candidates | 0% | **0%** | 0 | Unchanged. Uncommitted candidates by plan. |

**The arithmetic, both models, recomputed:**

```
equal-weight (as the prior report did):
  prior: (100 + 100 + 90 + 75 + 85 + 90 + 15 + 15 + 25 + 0) / 10 = 59.5%
  now:   (100 + 100 + 90 + 75 + 85 + 90 + 15 + 15 + 40 + 0) / 10 = 61.0%

effort-weighted (phase-plan-v2 week counts: 1=6w, 2=3w, 3=4w, 4=3w, 5=4w, 6=12w, 7=4w, 8=4w):
  prior: (0×1.0 + 100×6 + 90×3 + 75×4 + 85×3 + 90×4 + 15×12 + 15×4 + 25×4 + 0×0) / 40 = 53.1%
  now:   (0×1.0 + 100×6 + 90×3 + 75×4 + 85×3 + 90×4 + 15×12 + 15×4 + 40×4 + 0×0) / 40 = 54.6%
```

**Why the headline moved less than the raw metrics suggest:** the test surface grew from 570 → 839 functions, broad-scope backend LOC grew from 12,430 → 19,530, and the PyInstaller path now builds a tested binary — but none of that automatically maps to a phase's *stated exit criteria*. Phase 8 moved because a deliverable (the `.spec` + a green binary-smoke job) landed; Phases 6 and 7 did not move because no ML model, no Chess.com route, no research agent, and no PDF export exist. Reporting a percentage that rose on LOC alone would be the same class of error as the prior report's Qdrant correction: counting the wrong thing.

---

## 3. The CI gate — the one red job, and why it is not the same red as before

| | Prior (2026-09-03) | Now (2026-11-25) |
|---|---|---|
| Red job | `pnpm audit` — `@tiptap/core` `GHSA-cp6q-959q-f8rh` (FU-34) | `pnpm audit` — `GHSA-6jcc-5g8w-32mx`; direct `i18next@25.10.10` (also used by `react-i18next@16.6.6`) |
| Why | a real, fixable dependency vulnerability | **a newly-published advisory** (2026-11-23); the patched direct dependency is `i18next >=26.3.4` (the lockfile also contains safe `i18next 26.3.6` via `react-i18next@17.0.11`) |
| Blocking? | Yes — it blocked every PR's CI | **No** — `main` has no branch protection; `mergeable_state: unstable`, not `blocked` |
| Ledger | FU-34 RESOLVED 2026-09-04 via PR #117 | FU-44 RESOLVED 2026-10-25; FU-49 RESOLVED 2026-11-18 by the **withdrawal** of the `picomatch` advisory |

The `picomatch` situation is the one that needs stating plainly: **picomatch no longer reddens the production audit gate because its advisory was withdrawn, not because the vulnerable dependency was remediated.** The current production gate is nevertheless red on the separate i18next advisory described above. `picomatch` 4.0.5 and 4.0.7 are still in the lockfile; npm `latest` is still `4.0.7`; no `4.0.8` exists. The withdrawn advisory’s reference list includes upstream `micromatch/picomatch` PR **#194**, which remains open; a separate proposed fix, PR **#235**, was closed unmerged, and a comment on #235 documents the dispute that led to the withdrawal. The default graph reports **33 advisory records / 29 unique GHSAs / 9 packages** (`@vitest/mocker`, `brace-expansion`, `glob`, `i18next`, `js-yaml`, `minimatch`, `tinypool`, `undici`, `vitest`) — 3 low, 17 moderate, 11 high, 2 critical — while the `--prod` gate contains only the i18next advisory. Measured live with `pnpm audit --json` on 2026-11-25; the `i18next` package and one advisory count are new since the 2026-11-19 CI-job comment, which recorded 32/25/8.

**All 19 other CI jobs are green**, including gates that did not exist as gates before: `PyInstaller binary smoke`, `Windows AppContainer network isolation`, `Windows Job Object enforcement`, `linux network isolation (production container)`, `mypy strict`, `pytest-cov baseline`, `ruff lint`, `uv lock --check`, `gitleaks`, `qdrant sidecar smoke`, `lazy eval-graph smoke test`, `gold package clean-install gate`, `bbf flip rules verify`, `commit ref verify`.

---

## 4. Recommended order — author prioritization

**This ranking is the report author's judgment, not an inherited repository-defined queue.** The ledger's OPEN entries and the BBF-86 readiness tiers are real, but neither specifies an order; this section imposes one, ranked by (a) what unblocks the most downstream work, then (b) effort, then (c) risk.

### Tier 1 — close the red gate (1 PR, ~1 day)

1. **The `i18next` advisory (`GHSA-6jcc-5g8w-32mx`) — a DoS, not a ReDoS.** The advisory: `i18next deepExtend recurses into inherited built-ins, allowing corruption of shared built-in objects (DoS)`; affected range `< 26.3.4`, first patched `26.3.4`.
   The fix needs **three** steps, not one — the direct dependency is the vulnerable one:
   - `apps/desktop/package.json` declares **both** `i18next: ^25.8.11` and `react-i18next: ^16.5.4` as direct dependencies.
   - The lockfile resolves the direct `i18next` to **25.10.10** (vulnerable) *and* separately carries `i18next 26.3.6` (patched) via `react-i18next@17.0.11`.
   - Bumping only `react-i18next` to `17.0.11` would **not** clear the advisory: the application's own direct `i18next` resolution to 25.10.10 remains.
   - **Required:** raise direct `i18next` to a patched range (`>=26.3.4`), raise `react-i18next` to `17.0.11`, regenerate `pnpm-lock.yaml`, and prove the exact production CI command (`pnpm audit --audit-level moderate --prod`) is green on the result. The default/dev graph remains affected by other advisories.
   *Not a regression from any recent PR: `package.json` and `pnpm-lock.yaml` are byte-identical between PR #209's base and head, and base `main` reproduces the same failure.*

### Tier 2 — Phase 8: finish packaging (4–5 BBFs)

2. **`externalBin` + the Rust spawn command** in `apps/desktop/src-tauri/tauri.conf.json` and the JS layer — the sidecar exists and builds; nothing launches it yet.
3. **Drop `--no-bundle` from the Tauri build** (`apps/desktop/package.json`) so an MSI/NSIS installer is actually produced. Requires a Rust toolchain on Windows or a paid runner.
4. **A sidecar smoke test** that spawns the *bundled* artifact (not the dev tree) and asserts the backend goes healthy — `tests/e2e/` has 1 file and does not cover this.
5. **`tests/perf/budgets.yaml`** — the file the plan's Phase 8 exit criteria depend on does not exist, so no perf budget can be enforced at p95.
6. **Security checklist sign-off** — `docs/08_security/security-strategy.md` exists but is unsigned; the plan lists it as a Phase 8 exit criterion.

### Tier 3 — Phase 6: OCR ML (8–12 weeks per v2; the largest remaining block)

7. **YOLOv8 detector + piece classifier, PaddleOCR integration, figurine-notation recognition, manual-review queue, correction-feedback loop** — all absent (0 tracked references). **The plan's own recommended path is to NOT do this**: `PHASE-8-MINIMUM-VIABLE-SCOPING-2026-08-20.md` argues option (a) — keep the chessvision.ai API only and drop the local-fallback aspiration. **This is a product decision, not an engineering task — it needs an explicit call, and the prior report already recommended option (a).**

### Tier 4 — Phase 7: sync + research + reporting (~3–4 BBFs)

8. **Chess.com OAuth sync** — same shape as the shipped Lichess path. ~1–2 BBFs.
9. **Research agent** — curated-source monitor with an LLM relevance judge; Phase 7's exit criterion is a weekly digest. ~2 BBFs. Depends on item 11 (a real LLM path).
10. **PDF export / weekly progress reports** — Phase 7 deliverable; no implementation exists.

### Tier 5 — Phase 3: the real LLM path (~1 BBF)

11. **Wire the real OpenRouter route** with a budget cap and a smoke test. The router code has no stub markers, so this is a configuration/key/policy task rather than an implementation task — but nothing in production uses it, and the research agent (item 9) depends on it.

### Tier 6 — remaining ledger scope (4 items; FU-7 includes optional product work)

12. **FU-7** — Polyglot `.bin` import/export remains substantively **PARTIAL**. The α shipped 2026-08-08 and the α-ext persistent-book path shipped later, but the full external import/export surface — multi-book library, indexing layer, combine algorithm, user-identity model, CLI management surface, backup automation, and Phase 8 packaging support — remains explicitly open (`OPEN-FOLLOWUPS.md:378-380`). The mid-entry OPEN line at `OPEN-FOLLOWUPS.md:420` is **stale** and should be reconciled, but that documentation fix does **not** close the full product scope.
13. **FU-9** — long-term narrative-gold corpus growth. Awaiting a human curator by directive; **no session action**.
14. **FU-23** — data-dir migration `org.encroissant.app` → `org.chesscoach.app`, explicitly deferred until Phase 8 ships. **Blocked by items 2–4.**
15. **FU-27** — nested duplicate locale tree. Open by explicit directive; removing it needs §3.2-protected-file governance, so it is owner-gated.

---

## 5. What changed since the prior report

**93 PRs merged after PR #115** (94 including it), **125 commits after the prior-report baseline**, and **224 distinct changed files**: 66 product/source, 85 documentation, 42 test, 2 CI-workflow, and 29 other. Here, product/source means paths beginning `services/`, `libs/`, `apps/`, or `chess_coach/`; documentation means `docs/`; test means `tests/`; CI-workflow means `.github/workflows/`; all remaining paths are other.

**Security work landed and is now enforced in CI** — the prior report's Tier-1 item 22 ("FU-20 / FU-21 / FU-22 — A-F11 properties 2/3/4 — no implementation, no test") is the single biggest change:

- **FU-20 (A-F11 property 2, network isolation)** — Linux fail-closed namespace launcher (`services/chess_coach/pdf_ocr/linux_sandbox.py`, `unshare(CLONE_NEWUSER|CLONE_NEWNET|CLONE_NEWNS)`) landed 2026-11-02 via PR #192; Windows zero-capability AppContainer (`windows_appcontainer.py`, behind `CHESS_COACH_WINDOWS_APPCONTAINER=1`) landed 2026-11-11 via PR #195. Both have dedicated green CI jobs.
- **FU-21 (A-F11 property 3, read-only filesystem)** — Linux bind-mount + remount landed 2026-10-19 via PR #169.
- **FU-22 (A-F11 property 4, 2 GB memory cap)** — Windows Job Object enforcement landed 2026-10-29 via PR #190 (`windows_job.py`, ctypes, `JOB_OBJECT_LIMIT_PROCESS_MEMORY` at 2 GiB).
- The guard is now `ensure_network_isolation_supported()`, raising `NetworkIsolationUnsupportedError` (HTTP 501 `internal.not_implemented`) **before** any parser process or Job target is created. The shipped default remains the 501 refusal; the Windows path is opt-in; FU-20 stays open as the standing per-deployment enablement item (Decision A accepted generally 2026-11-17, Decision B not accepted).

**Also landed:** the FU-29 quality-tooling chain (ruff, mypy strict, pytest-cov — now green CI gates), the FU-44 dependency-CVE remediation (50 Python + 9 JS advisories), the FU-46 line-ending policy, the FU-45 UTF-8 guard, the FU-43 flip-rules migration, gitleaks v3, and a **23-event post-baseline doc-drift campaign** (9a, 9b, and 9c count as distinct events; flip-5 predates the baseline and there is no published flip-11 event; **22 total brief files**—21 numbered briefs plus the unnumbered base `BBF-doc-drift-flip.md`—because flip-2 had no separate brief) that retired stale current-state claims across the ledger and multiple audit briefs. In flip-23 alone, the landed diff corrected 15 existing briefs (7 non-flip briefs and 8 earlier flip briefs), plus the ledger, and added the new flip-23 brief.

---

## 6. What did NOT move, and why it is not a regression

| Item | Status | Why |
|---|---|---|
| Phase 6 OCR ML | **15%** for the phase as a whole; **0%** of the remaining local-ML subtasks | Deliberately deferred; the plan's recommended path is option (a) (API-only). Needs a product call. |
| Phase 7 Chess.com / research / PDF export | **15%** for the phase as a whole; **0%** of the three named Phase 7 deliverables | Not started; sequenced behind the real-LLM path. |
| Phase 2 WS streaming, Leela/Maia adapters | deferred | v2 scope reduction, consciously tracked. |
| Phase 1 Redis as a separate service | deferred | v2 committed to monolith-first; deferred to Phase 6+. |
| Phase 4 v0 corpus coverage (4 of 7 archetypes) | gap | Honest, documented in `_metadata`; Tactician/Wildcard/Specialist need a curator. |
| The `picomatch` code remediation | impossible today | No upstream release exists; the advisory was **withdrawn** instead. The gate is green by withdrawal, not by fix. |

---

## 7. Bottom line

**~55–61% of the v1+v2 plan is shipped** (54.6% effort-weighted, 61.0% equal-weight), up from ~53–60% on 2026-09-03 — a real but modest gain, because the work that landed since then (A-F11 properties 2/3/4, the quality-tooling chain, the dependency-CVE remediation, 23 doc-drift flips) is **security and hygiene work that strengthens shipped features rather than adding new phase deliverables**.

**Phases 0–5 are effectively done** (85–100%). The remaining work is three blocks: **Phase 8 packaging** (4–5 BBFs, the highest-leverage because it turns a working codebase into something a user can install), **Phase 7 sync/research/reporting** (3–4 BBFs), and **Phase 6 OCR ML** (the big one — and the one the plan says to *not* do).

**The cheapest win is Tier 1**: two dependency bumps (`i18next` to a patched range, plus `react-i18next` to `17.0.11`) and a lockfile regeneration clear the current production advisory and make the `--prod` audit gate green again. The non-production dependency graph remains affected by other advisories.

**The highest-leverage decision is Phase 6**: explicitly choosing option (a) removes ~12 weeks from the critical path and makes the plan's own percentages honest.

---

## 8. Verification and provenance

The quantitative figures in this report were re-derived from the tree or the GitHub API. An independent audit of the first draft found four quantitative errors and three wording problems; focused later audits found further denominator, chronology, method, and internal-consistency defects — including a **LOC-counting method error** (counting a trailing empty line over-counts by one per file), a **nonexistent path** (`apps/chess_coach_cli` for the real `apps/cli`), and **mixed denominators** between the test-file and route-file rows. Those corrections are applied above, and the provenance table records the final denominator and method for each figure rather than asserting unqualified correctness.

| Figure | Value | How it was derived |
|---|---|---|
| Plan completion, equal-weight | 61.0% | the sum of §2's ten rows ÷ 10 |
| Plan completion, effort-weighted | 54.6% | phase-plan-v2 week counts (1=6w, 2=3w, 3=4w, 4=3w, 5=4w, 6=12w, 7=4w, 8=4w) |
| Commits on `main` | 474 total; 125 since `4aa2d645` | `git rev-list --count` |
| PRs merged after the baseline | 93 (94 including PR #115) | the GitHub pulls API, `merged_at` after PR #115's `2026-09-03T20:26:15Z` |
| Test functions | 839 | `grep -rE "def test_\|async def test_"` over `tests/unit/` + `tests/integration/` |
| Backend LOC, like-for-like | 7,565 (from 6,677) | the prior report's own `wc -l` scope, at both trees; `wc -l` = newline count |
| Backend LOC, broad | 19,530 (from 12,430) | recursive `services` + `libs` + `apps/cli` at both trees |
| Numbered ADRs | 9 (unchanged) | `docs/14_adrs/ADR-\d{4}-*` minus the template |
| Ledger entries / marker lines | 47 entries; 66 plain status lines + 8 clarification lines | counted directly from the blob; marker categories overlap |
| Profile metrics | 7 (6 in `stats.py`, 1 in `tilt.py`) | the module-level `def` names at each location |
| Doc-drift flips | 23 events; 22 total brief files | post-baseline flip commits; 9a/9b/9c count separately; 22 briefs = 21 numbered briefs + the unnumbered base brief; flip-2 had no brief |
| Dev-graph audit | 33 advisory records / 29 unique GHSAs / 9 packages | `pnpm audit --json` (no `--prod`), measured 2026-11-25 |
| Prod-graph audit | 1 advisory record / 1 package (`i18next`) | `pnpm audit --audit-level moderate --prod` — the exact CI invocation |
| CI | 19/20, one failure | the check-runs API for `7eef904e` |
| Test files | 77 (51 unit + 26 integration) | `tests/unit` + `tests/integration` `.py`, excluding `__init__.py`, at both trees |
| Route files / decorators | 22 / 32 | `services/chess_coach/gateway/routes/*.py` and the `@router.*` decorators |
| `docs/16_audit/` files | 22 → 97 | `git ls-tree -r origin/main docs/16_audit/` at both trees |
| Changed files since the baseline | 224 (66 product/source, 85 docs, 42 test, 2 CI, 29 other) | `git diff --name-status 4aa2d645 origin/main`, deduplicated; path rules are defined in §5 |

```bash
git -C C:/Users/i3/verify_chess_coach/chess-coach rev-parse HEAD origin/main
git -C C:/Users/i3/verify_chess_coach/chess-coach rev-list --left-right --count origin/main...HEAD   # 0 0
git -C C:/Users/i3/verify_chess_coach/chess-coach rev-list --count origin/main                          # 474
git -C C:/Users/i3/verify_chess_coach/chess-coach rev-list --count 4aa2d645..origin/main              # 125
git -C C:/Users/i3/verify_chess_coach/chess-coach ls-tree -r --name-only origin/main docs/16_audit/ | wc -l  # 97
gh api repos/sebko23/chess-coach/commits/7eef904e443a44df624fd63a51f90d518dee6c44/check-runs
gh api repos/sebko23/chess-coach/advisories/GHSA-6jcc-5g8w-32mx
gh api repos/sebko23/chess-coach/advisories/GHSA-fc5q-39xc-vjpf
```

**On the ledger partition.** The 39 RESOLVED / 3 OPEN / 5 clarified split in the first draft was an **analyst-normalized** partition, not a native field. The ledger has 47 primary `## FU-N` entries and records **66 plain `**Status:**` lines** — 59 RESOLVED, 4 OPEN, 1 PARTIAL, 1 TRACKING, and **1 document-level LIVING marker** (the ledger's own preamble, not an entry) — plus **8 clarification lines**: 6 RESOLVED, 1 PARTIALLY RESOLVED, and 1 alpha-shipped/beta-deferred. The clarification markers **overlap** entries already represented by plain status lines and are **not** additional independent statuses, so the two counts must not be added together. The raw marker counts are now the reported figures.

**On the dev-graph audit.** The figure reported here — 33 advisory records / 29 unique GHSAs / 9 packages — is the live measurement from `pnpm audit --json` on 2026-11-25. The `i18next` package and the additional advisory count are **new since the 2026-11-19 CI-job comment**, which recorded 32 records / 25 advisories / 8 packages; that comment is therefore a stale snapshot of the pre-advisory graph, not a contradiction of the current measurement.
