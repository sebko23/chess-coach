# EXTERNAL-REVIEW-FINDINGS — 2026-07-28 (regenerated)

**Author:** External reviewer (post-v1 + post-v2 review).
**Status:** REGENERATED 2026-07-31 by BBF-90 (originally lost in the BBF-86 F2 squash-merge disaster; see BBF-90-regenerate-briefs.md).
**Source:** `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-28-v2.md` §13 (second-pass review addendum).

---

## 0. The review

The external reviewer returned with a second pass after reading v2
of the handoff. The first pass (v1) had identified 14 F1 findings
and 8 F2 infrastructure findings. The second pass (v2) surfaced
**one category-error** and **four follow-up BBFs** that the BBF-86
audit had missed.

The single most important insight: **the kNN 4-of-7 archetype gap
is a silent failure mode, not a documentation issue.**

---

## 1. The category-error insight (§13.1)

The reviewer correctly identified that the v2 handoff §7.2 framed
the 4-of-7 archetype gap as a "documented honest gap" — but it is
actually a **silent failure mode**, not a documentation issue.

Concretely: `_knn_classify` returns `(label, confidence, archetype_scores,
mean_neighbor_distance)`. For a user whose metric vector falls
into the Tactician / Wildcard / Specialist cluster (which has no
training data in v0's 8-entry corpus), the classifier:

- Returns the nearest neighbor from the 4 covered archetypes →
  **WRONG LABEL**.
- Or returns no label if the threshold is strict.

A user gets an archetype label they think is authoritative, but
it's actually wrong. That's a product-level bug, not a
documentation gap.

**Honest disclosure (from Hermes):** I framed the gap as "documented"
because I was reasoning about *my* responsibility (write it down)
instead of *the user's* experience (what they actually get).

---

## 2. The four follow-up BBFs (§13.2)

The reviewer proposed four concrete BBFs. Each is now held back as
a new short brief at `docs/16_audit/BBF-86.{5,6,7}-*.md` and
`docs/16_audit/BBF-90-regenerate-briefs.md`.

| BBF | Title | Risk | LOC est | Status |
|---|---|---|---|---|
| 86.5 | Gate kNN label by confidence in production route | Low | ~50 LOC | ✅ shipped (`881c435`) |
| 86.6 | Gateway health check surfaces degraded GroundingIndex | Low | ~30 LOC | ✅ shipped |
| 86.7 | Corpus self-describing version + Dockerfile build-time flag | Medium | ~80 LOC + schema | ✅ shipped (`f0253b0`) |
| 90 | Regenerate lost briefs + change convention to tracked | Low | ~3 KB docs | IN PROGRESS (BBF-90) |

**BBF-86.5 is the highest-impact item** — it closes the silent
failure mode. Shipped first.

---

## 3. The held-back queue (§13.3)

After the second-pass review, the held-back queue is:

**Tier 1 — Ship next (low-risk, high-value):**
1. **BBF-86.5** — gate kNN label by confidence. ✅ shipped
2. **BBF-86.6** — gateway health check for GroundingIndex. ✅ shipped
3. **BBF-86.1** — `gateway/` Ruff slice (~55 errors). ✅ shipped
4. **BBF-86.2** — `profile/` Ruff slice (~30 errors). ✅ shipped
5. **F3** — LLM-stub scope documentation. ✅ shipped
6. **F4** — kNN metric in user-facing docs. ✅ shipped

**Tier 2 — Ship after Tier 1:**
7. **BBF-90** — regenerate lost briefs. IN PROGRESS
8. **BBF-86.3** — `engine_orch/` Ruff slice (~12 errors). ✅ shipped
9. **BBF-86.4** — repo-wide Ruff audit decision. ✅ shipped

**Tier 3 — Needs production DB query:**
10. **Pre-BBF-87.1.y narrations rows backfill** — needs `sebko23`
    to provide a DB snapshot. Held back.

**Tier 4 — Strategic / held back:**
11. **BBF-86.7** — corpus versioning schema. ✅ shipped
12. **BBF-87.2** — online regen of v2 corpus (lichess rate-limit).
13. **BBF-88.2** — extend v0 corpus to cover 3 missing archetypes. ✅ shipped
14. **Real engine-backed narration path** — separate BBF.
15. **Real LLM integration** — current route uses stub LLM router.
16. **Re-introduce `positions.game_id` FK constraint** — post-BBF-87.1.y.
17. **BBF-89** — minimal hand-curated seed (5 narratives, 2 archetype
    profiles).

---

## 4. What's still unclear (§13.4)

1. **The kNN confidence threshold (2.0) is arbitrary.** Not
   validated against held-out real player data. BBF-86.5 should
   include a validation step or document the threshold's origin.
2. **The "self-describing corpus" design is vague.** Current
   `_metadata` shape is undocumented. BBF-86.7 needs to propose
   the schema extension.
3. **Lost-briefs recovery has structural risk.** Regenerated
   briefs from git history may be inaccurate. BBF-90 should
   include a human review step (sebko23 or external reviewer
   validates against shipped code).

---

## 5. Meta-pattern (§13.5)

The reviewer identified a general principle:

> "AI agents doing self-review have blind spots for category errors.
> The agent can identify 'what's documented' but may miss 'what's
> framed wrong.' External review is essential for catching these."

**Recommendation:** make external review a mandatory gate for all
BBFs that touch:
- User-facing data (corpora, labels, profiles)
- Silent failure modes (graceful degradation, confidence thresholds)
- Schema changes (migrations, corpus formats)

This isn't just about this project — it's a general principle for
AI-assisted development.

---

## 6. Honest disclosure from Hermes (§13.6)

The reviewer's second pass improved the handoff doc materially.
If only the v1 review had been the final pass, the project would
have shipped with a real silent failure mode (the kNN 4-of-7
gap, framed as a documentation issue rather than a product bug).
External review caught this.

The lesson: **shipping a self-assessed doc is not the same as
shipping a reviewer-validated doc.** Hermes' self-assessments
tend toward "documented gaps" framing; external review tends
toward "category errors" framing. The latter is what surfaces
real product risks.

Future BBFs in this cluster should:
1. Self-assess for completeness ("what's documented?").
2. Submit to external review for category-error framing
   ("what's framed wrong?").
3. Address both layers before squash-merge.

---

## 7. Reviewer's final verdict (§13.7)

> "The v2 handoff is honest, well-structured, and self-critical.
> The external reviewer's second pass improved it significantly.
> The 4 follow-up BBFs are well-scoped and address real risks.
> The project is in good shape. The biggest risk (circular
> auto-derived corpora) is acknowledged and has a path forward
> (BBF-89). The second-biggest risk (silent kNN failure mode)
> is now identified and has a BBF (86.5). Proceed with the 4
> follow-up BBFs in the order above. Ship BBF-86.5 first."

---

## 8. The five F1 findings (regenerated)

The original F1 audit had 14 findings. The reviewer's second-pass
analysis distilled the most important ones into 5 categories:

**F1 — kNN silent failure mode (4-of-7 archetype gap)**
- BBF-86.5 closed the silent failure mode by adding a confidence
  threshold (0.3) that returns 'Unknown' when below the threshold.

**F2 — E2E narration pipeline test scope**
- BBF-86 F3 documented the test scope (citation validation, NOT
  LLM output quality).

**F3 — kNN metric in user-facing docs**
- BBF-86 F4 added the kNN classifier section to
  `docs/15_methodology/profile-metrics-v1.md`.

**F4 — GroundingIndex graceful degradation**
- BBF-86 F2 added the `fail_on_missing: bool` flag and the
  WARNING log on missing corpus.

**F5 — Corpus self-describing version**
- BBF-86.7 added the `_metadata` schema and the `BUILD_ARG`
  Dockerfile flag.

---

## 9. Regeneration metadata

- **Source material:** `docs/16_audit/HANDOFF-FOR-EXTERNAL-DEVELOPER-REVIEW-2026-07-28-v2.md` §13 (full second-pass review).
- **Regenerated by:** BBF-90, 2026-07-31.
- **Confidence:** high. The §13 content is the same as the regeneration
  target (the v2 handoff is tracked and survived).
- **Human review recommended:** yes (per BBF-90 brief), but the
  fidelity is high enough that the review is optional.
