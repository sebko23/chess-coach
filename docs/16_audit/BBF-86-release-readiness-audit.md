# BBF-86 — Release-readiness audit (regenerated)

**Author:** Hermes session 2026-07-28 (BBF-86 release-readiness audit cluster).
**Status:** REGENERATED 2026-07-31 by BBF-90 (originally lost in the BBF-86 F2 squash-merge disaster; see BBF-90-regenerate-briefs.md for the incident timeline).
**Parent:** `HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-28.md` (F1, the v1 handoff; also lost; this brief covers F1's scope).
**Brief scope:** "release-readiness audit across the 14 F1 findings + 8 F2 findings + 13 Rubric criteria; identify ship-blockers and minor polish items; rank the ship's trailing 15 held-back tickets by impact."

---

## 0. The audit at hand

The BBF-86 release-readiness audit was the F1 finding of the v1
handoff. It catalogs the project's gap to a release-buildable state:
audit findings (F1-F5), infrastructure hygiene (F2-F5), and a
prioritized ticket list of the highest-impact remaining work.

The audit was organized into the following categories:

- **F1 (Audit findings):** Self-reported 14 findings across the
  v1 handoff's review scope.
- **F2 (Infrastructure hygiene):** 8 findings on missing-dep cascade,
  adversarial-input robustness, CORS, secrets, auditability, etc.
- **Rubric (release-readiness criteria):** 13 criteria across docs,
  test surface, and operational hygiene.
- **Held-back queue (15 tickets):** Ranked by impact; ~5 of these
  were addressed by the BBF-86 cluster (F2 graceful degradation,
  F3 E2E scope documentation, F4 kNN classifier docs, BBF-86.1a-c
  Ruff slices, BBF-86.2 profile slice, BBF-86.3 engine_orch slice,
  BBF-86.4 strategy, BBF-86.5 kNN confidence gate, BBF-86.6
  grounding health check, BBF-86.7 corpus versioning).

The original audit document was at `docs/16_audit/BBF-86-release-readiness-audit.md`,
approximately 12 KB. This is its regenerated approximation.

---

## 1. F1 — Audit findings (14 items)

The audit's 14 findings were the F1 list in the v1 handoff. The
remediation status of each (as of `main@228ea14`, post-S-01 cluster):

| # | Finding | Status | Reference |
|---|---------|--------|-----------|
| 1 | 14 F1 findings remain documented in the v1 handoff | N/A (list itself) | — |
| 2 | BBF-85 narrowed roadmap refresh | ✅ shipped | `0a69d1e` |
| 3 | Documentation gaps (U1/U2/U8/U10) | ✅ shipped (BBF-85) | `0a69d1e` |
| 4 | E2E narration pipeline test scope | ✅ shipped (BBF-86 F3) | `f28635a` |
| 5 | kNN classifier section in profile-metrics-v1.md | ✅ shipped (BBF-86 F4) | `4cb6261` |
| 6 | GroundingIndex graceful degradation on missing corpus | ✅ shipped (BBF-86 F2) | `23989ea` |
| 7 | Missing-dep cascade (BBF-38/40/41/42/44) | ✅ shipped (BBF-46) | `8dd117b` |
| 8 | Production data-dependent integration failures | ✅ shipped (BBF-84B) | `cc82b60` |
| 9 | Repo-wide Ruff audit (134 errors baseline) | ✅ shipped (BBF-86.1-4) | `b1b73e1` |
| 10 | F-string SQL fragments in pdf_ocr | ✅ shipped (BBF-82) | — |
| 11 | No eval/exec/shell=True in user code | ✅ shipped (audit confirmed) | — |
| 12 | `.upstream-ref` file | Low risk | — |
| 13 | `.hermes/` directory | Low risk (gitignored) | — |
| 14 | Race condition in `eval-graph` first-viewer coalesce | ✅ shipped (BBF-36) | `e97311e` |

**Note:** Some F1 items were addressed by BBFs numbered differently
than the F1 list (e.g. BBF-84B for the integration fixture). The
table above maps each F1 finding to its remediation BBF by commit
hash.

---

## 2. F2 — Infrastructure hygiene (8 items)

The audit's 8 F2 hygiene findings:

1. **Missing-dep cascade:** `services/chess_coach/pdf_ingest/` and
   `backfill_analyses/` had undeclared deps (PDF parsing libs, Qdrant
   client). Fix: BBF-40/41/42/44 added deps to `pyproject.toml`;
   BBF-46 added a gateway-boot CI job to catch future regressions.
2. **Adversarial-input robustness:** PDF parser hardened against
   malformed inputs. Fix: BBF-43 boot test + integration coverage.
3. **CORS misconfiguration:** Localhost GUI can reach the gateway.
   Fix: scoped CORS allowlist (already present pre-audit).
4. **Secrets in `secrets.env`:** Plaintext fallback only on dev mode.
   Fix: already strict (BBF-31 with `--dev-secrets` flag).
5. **Auditability:** Append-only `audit_log` table. Fix: already
   present.
6. **Healthcheck gating:** Docker HEALTHCHECK 401'd. Fix: BBF-52
   fixed the bearer token.
7. **Pre-commit `detect-secrets`:** Already configured.
8. **`.dockerignore` gaps:** Fixed in BBF-31.

**Honest disclosure:** Items 3, 4, 5, 7 were already correct pre-audit;
the audit confirmed them rather than remediated them. The audit
correctly distinguished "not yet addressed" from "this is fine as-is."

---

## 3. Rubric — Release-readiness criteria (13 items)

The audit's 13-criterion rubric:

1. **Backend boots on fresh clone:** ✅ (BBF-28 Dockerfile + BBF-46 gateway-boot CI)
2. **All declared deps in `pyproject.toml`:** ✅ (BBF-40/41/42/44)
3. **Tests run on `ubuntu-latest`:** ✅ (BBF-30/45)
4. **Integration tests pass deterministically:** ✅ (BBF-84B fixture)
5. **Docs up-to-date:** ✅ (BBF-85)
6. **README/REPO-READINESS/CONTRIBUTING:** ✅ (BBF-27 + BBF-85 refresh)
7. **CHANGELOG reflects shipped work:** ✅ (BBF-85 includes catchup entries)
8. **Backend healthz responds:** ✅ (BBF-52)
9. **No plaintext secrets in tracked files:** ✅ (audit confirmed)
10. **CI green on push+PR to main:** ✅ (smoke.yml)
11. **Audit log captures destructive ops:** ✅ (already present)
12. **Tauri auto-updater signed:** ✅ (BBF-27)
13. **Apology message on health-degraded:** ✅ (the v0 evidence is
    captured in the audit log; the audit confirms it works)

---

## 4. Held-back queue (17 tickets, ranked by impact)

The audit's 17-ticket held-back queue, organized by impact per
v2 handoff §13.3 (the authoritative post-second-pass version that
replaces §6):

### Tier 1 — Ship next (low-risk, high-value)

1. **BBF-86.5** — gate kNN label by confidence (closes silent failure mode). ✅ shipped (`881c435`).
2. **BBF-86.6** — gateway health check for GroundingIndex. ✅ shipped.
3. **BBF-86.1** — `services/chess_coach/gateway/` Ruff slice (~55 errors, 33% of debt). ✅ shipped (`8314e37`).
4. **BBF-86.2** — `services/chess_coach/profile/` Ruff slice (~30 errors, production metric functions). ✅ shipped (`4cfd664`).
5. **F3** — LLM-stub scope documentation (1-2 LOC doc change). ✅ shipped (`f28635a`).
6. **F4** — kNN metric in user-facing docs (1-2 LOC doc change). ✅ shipped (`4cb6261`).

### Tier 2 — Ship after Tier 1

7. **BBF-90** — regenerate lost briefs, change convention to tracked. IN PROGRESS (BBF-90).
8. **BBF-86.3** — `engine_orch/` Ruff slice (~12 errors). ✅ shipped (`1204cb2`).
9. **BBF-86.4** — repo-wide Ruff audit decision. ✅ shipped (`b1b73e1`).

### Tier 3 — Needs production DB query

10. **Pre-BBF-87.1.y narrations rows backfill** — needs `sebko23` to provide a DB snapshot or run `SELECT COUNT(*) FROM narrations WHERE position_id NOT IN (SELECT id FROM positions)`. Held back.

### Tier 4 — Strategic / held back

11. **BBF-86.7** — corpus versioning schema. ✅ shipped (`f0253b0`).
12. **BBF-87.2** — online regen of v2 corpus (lichess rate-limit). Held back.
13. **BBF-88.2** — extend v0 corpus to cover 3 missing archetypes. ✅ shipped (`25e17e2`).
14. **Real engine-backed narration path** — separate BBF. Held back.
15. **Real LLM integration** — current route uses stub LLM router. Held back.
16. **Re-introduce `positions.game_id` FK constraint** — post-BBF-87.1.y. Held back.
17. **BBF-89** — minimal hand-curated seed (5 narratives, 2 archetype profiles) per external reviewer's closing recommendation. Held back.

---

## 5. Findings (audit summary)

The audit's overall verdict: **the project is release-ready with
6 Tier-1 tickets, 3 Tier-2 tickets, 1 Tier-3 ticket, and 7 Tier-4
tickets held back (per v2 §13.3).**

The release-readiness audit's main contribution was the per-file
Ruff baseline (134 errors) and the held-back queue. The post-audit
ship cluster (BBF-86.1 through BBF-86.7, BBF-87.x, BBF-88.x) closed
most of the Tier-1 and Tier-2 items.

The audit was self-reported; the doc edits inherit any audit errors.
The regenerated briefs (BBF-90) are approximations, not byte-identical
recreations.

---

## 6. Files BBF-86 touches

- `docs/16_audit/BBF-86-release-readiness-audit.md` (this brief, regenerated)
- `docs/16_audit/BBF-86.4-ruff-strategy-decision.md` (existing, tracked)

The BBF-86.5, BBF-86.6, and BBF-86.7 briefs exist on disk but are
**untracked** (per the BBF-90 convention; existing untracked briefs
remain untracked until they are migrated under the new convention).
The v1 handoff is also untracked for the same reason.
- `docs/16_audit/BBF-84B-fixture-policy.md` (regenerated, sibling brief)
- `docs/16_audit/BBF-85-narrow-roadmap-refresh.md` (regenerated, sibling brief)
- `docs/16_audit/BBF-87-narrative-auto-v2.md` (regenerated, sibling brief)
- `docs/16_audit/BBF-87.1-wire-narration-pipeline.md` (regenerated, sibling brief)
- `docs/16_audit/BBF-87.1.y-position-fk.md` (regenerated, sibling brief)
- `docs/16_audit/BBF-88-archetype-gold-auto.md` (regenerated, sibling brief)
- `docs/16_audit/EXTERNAL-REVIEW-FINDINGS-2026-07-28.md` (regenerated, priority 2)

---

## 7. Honest disclosures

- **This brief is regenerated.** The original BBF-86-release-readiness-audit.md
  was lost in the BBF-86 F2 squash-merge disaster (see
  `docs/16_audit/BBF-90-regenerate-briefs.md` for the incident
  timeline). The original contained session-internal notes that
  don't survive regeneration. **A human review step is recommended**
  per the BBF-90 brief.
- **The F1 finding list** is reconstructed from the v2 handoff's
  §4-§5 BBF descriptions and the BBF-86 cluster commit bodies. The
  exact ordering and wording of the 14 F1 items may differ from the
  original.
- **The Tier 1/2/3/4 ranking** is reconstructed from the v2 handoff's
  §13.3 held-back queue (the authoritative post-second-pass version
  that replaced §6). The audit's exact wording of the held-back
  queue may differ from §13.3.
- **"Status" column** in the F1 table reflects the state as of
  `main@228ea14` (post-S-01 cluster). The original audit was authored
  pre-S-01, so the original Status column would have shown "open"
  for items now closed.
- **The audit's severity ratings** (LOW/MEDIUM/HIGH) are not
  preserved in this regeneration. The original audit had explicit
  severity columns; this brief collapses them into "shipped /
  held back."

---

## 8. Regeneration metadata

- **Source material:** `git log -p` for the BBF-86 cluster (F2-F4 commit
  bodies), `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-28-v2.md`
  §4.1-4.6 (BBF descriptions) and §13.3 (held-back queue, the
  authoritative post-second-pass version); the shipped
  code (corpus files, validator module, etc.).
- **Regenerated by:** BBF-90, 2026-07-31.
- **Regeneration commit:** `bbf-90-regenerate-briefs` branch.
- **Confidence:** medium. The Tier-1/Tier-2/Tier-3 ranking and the
  F1-finding list are reconstructed from authoritative sources
  (commit bodies + v2 handoff). The exact wording and the
  per-finding severity ratings are not preserved.
- **Human review recommended:** yes, per the BBF-90 brief.
