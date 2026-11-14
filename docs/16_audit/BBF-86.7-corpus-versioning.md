# BBF-86.7 — corpus versioning and coupled production selection

**Sprint intent:** make the shipped archetype and narrative gold corpora
self-describing, select the same corpus version for packaging and runtime,
and preserve availability when version metadata drifts.

**Status:** Code, data, tests, audit-truth corrections, and this tracked
per-flip brief. This BBF replaces the July untracked draft rather than
landing PR #48's stale branch unchanged.

**Base:** `main @ 882972de8728bf4c36355dbf438aaf986bc8e093`.

**Historical reference:** PR #48 carried an early implementation of corpus
version metadata and Dockerfile arguments. Its branch is far behind current
main, its loaders predate current typed signatures and hand-curated corpus
support, and its build flags could select a packaged corpus different from
the runtime-selected corpus. The implementation here is adapted to current
main and adds the production-selection and durability work that PR #48 did
not contain.

---

## §1. Decision: advisory validation, never refusal

A corpus-version mismatch is a deployment diagnostic, not a reason to make
the service unavailable.

The shared loader helper in
`libs/chess_coach/datasets/corpus_version.py` checks `_metadata.version` and
logs a warning when:

- the requested and reported versions differ;
- `_metadata.version` is missing;
- `_metadata.version` is malformed or non-string; or
- `_metadata` itself is absent.

The helper never raises for a version mismatch. Existing structural failures
remain strict: a missing corpus file, malformed JSON, missing `entries`, and
an unsupported `schema_version` still raise as before.

This is deliberately different from the July draft's proposed strict
`raise ValueError(...)`. A strict refusal would turn deployment drift into an
availability failure and would break valid deployments that intentionally
carry a corpus under a different version token.

---

## §2. Production archetype default: v0

BBF-88.2 explicitly assigned the archetype default flip from v1 to v0 to
BBF-86.7. Current main contradicted that assignment:

- `services/chess_coach/profile/archetypes.py` loaded v1 explicitly;
- the Dockerfile copied only `tests/gold/archetypes/v0/`; and
- the archetype route therefore attempted to load a corpus absent from the
  production image.

This BBF makes the production selection explicit and configurable:

- `CHESS_COACH_ARCHETYPE_GOLD_VERSION` selects the corpus;
- an unset or empty value defaults to v0;
- the production classifier uses v0 by default; and
- the Dockerfile packages and selects the same version by default.

The v1 corpus remains loadable for backward compatibility. Existing callers
of `_knn_classify` remain source-compatible because the new optional
`corpus_version` parameter is appended after the existing positional
parameters.

The production v0 feature space now includes `sequence_based_tilt`. Two
synthetic shape-curated Tilter references are derived from the repository's
existing v1 Tilter vectors and cross-checked against
`ARCHETYPE_TRAITS[Tilter]`; their provenance states that the vectors are
synthetic rather than player-measured. The two historical auto-derived Tilter
rows retain the underpowered/no-sample sentinel tilt value 0.0 and record why.
Vote shares are normalized by the effective neighbor count, so the
two-entry hand-curated corpus produces shares summing to 1.0 rather than
`2/3`.

The auto-curator remains semantically stable: its documented bootstrap
labels are derived from the v1 placeholder, so its call explicitly requests
v1 rather than inheriting the new production default.

---

## §3. Durable, self-describing corpus metadata

The checked-in corpora and their generators now persist the version:

- `tests/gold/archetypes/v0/corpus.json` declares `_metadata.version = "v0"`;
- `tests/gold/narrative/v2/corpus.json` declares `_metadata.version = "v2"`;
- `scripts/curate_archetype_gold_auto.py` writes the canonical `int_version`;
  and
- `scripts/curate_narrative_gold_auto.py` writes the canonical `version`.

This prevents a later regeneration from silently dropping the field.
Advisory loaders tolerate a missing field for backward compatibility, but
newly generated corpora remain self-describing by construction.

Canonical v0 regeneration also preserves existing
`synthetic_shape_curated` rows. It seeds generated IDs from the preserved
IDs, merges the preserved rows after the newly generated entries, and
records the preserved-row count in metadata. This prevents a routine
regeneration from silently deleting the Tactician, Wildcard, Specialist, and
Tilter shape references.

---

## §4. Coupled Docker packaging and runtime selection

PR #48 parameterized the two `COPY` paths but did not couple those paths to
runtime selection. A custom build could therefore package one corpus and
run against another.

This BBF defines two build arguments with production defaults:

- `NARRATIVE_VERSION=v2`;
- `ARCHETYPE_VERSION=v0`.

The same arguments feed both the corpus `COPY` paths and the runtime
environment variables:

- `CHESS_COACH_NARRATIVE_GOLD_VERSION`;
- `CHESS_COACH_ARCHETYPE_GOLD_VERSION`.

The packaged corpus and the runtime-selected corpus therefore share one
source of truth in the image definition.

The coupling is guaranteed for the image defaults. A runtime override of
either `CHESS_COACH_*_GOLD_VERSION` can select a corpus absent from that
image. Operators must keep the runtime value equal to the corresponding
build ARG, or build/package the selected corpus. The archetype loader
raises `FileNotFoundError` for an absent selected corpus; narrative
grounding degrades to an empty index with a warning.

---

## §5. Test coverage

The focused BBF-86.7 suite covers:

- archetype and narrative mismatch warnings;
- absent `_metadata`, missing `_metadata.version`, and malformed/non-string version warnings;
- no warning for matching versions;
- non-refusal in every advisory case;
- shipped corpus version fields;
- archetype runtime default and override behavior;
- Docker build/runtime version coupling;
- narrative generator metadata durability; and
- archetype generator metadata durability through the real generator
  function with controlled metrics, including an explicit assertion that
  archetype bootstrap uses `corpus_version="v1"` while emitted metadata is `"v0"`;
- preservation of existing `synthetic_shape_curated` rows during canonical
  v0 regeneration, including their data, provenance, and reserved IDs;
- normalized vote shares for the two-entry hand-curated corpus;
- restored `sequence_based_tilt` production feature space and sensitivity to
  changing only that field; and
- the shipped v0 corpus's mixed auto-derived and shape-curated composition.

The exact-reference self-match case remains a separate contract. The
representative Tactician, Specialist, Wildcard, Tilter, confidence-floor,
effect-size, and B4-gate tests use fixed, reviewed v0-range vectors that
are not exact corpus rows. They preserve explicit label, confidence,
effect-size, and gate expectations rather than becoming label-agnostic.

---

## §6. Audit-truth corrections

The July and regenerated audit documents described BBF-86.7 as already
shipped even though its implementation was absent from main and the PR #48
branch was unmerged. This BBF corrects every identified false-claim
location in:

- `docs/16_audit/BBF-86-release-readiness-audit.md`;
- `docs/16_audit/EXTERNAL-REVIEW-FINDINGS-2026-07-28.md`; and
- `docs/16_audit/PROGRESS_REPORT_2026-09-03.md`.

Every correction is line-count neutral so existing line-number citations in
`tier-3-backfill-record.md` and the progress report remain valid. The
corrections do not cite PR #48's descendant commit as a landed SHA.

---

## §7. Verification

Local verification on the pinned base:

- affected suite (`pytest` over the BBF-86.7 loader, generator, classifier,
  profile, and narrative-generator tests): **118 passed**;
- CI-equivalent unit suite (`pytest tests/unit` with the smoke workflow's
  `test_keychain.py` and `test_sec01_https_chessvision.py` exclusions):
  **679 passed, 16 capability-gated skips**;
- Ruff on all touched Python files: **pass**;
- mypy on the changed implementation modules: **pass**;
- JSON parsing and metadata-field checks: **pass**;
- `git diff --check`: **pass**.

The complete unit command initially stopped during collection because the
reusable container environment lacks the optional `keyring` dependency used
by `test_keychain.py`; no assertion failed. The CI-equivalent command then
used the same exclusions as the repository smoke workflow and passed.

A real Docker build could not run in the Agent Zero container: the Docker
client is installed, but no daemon is available, and no alternative image
builder is installed. No local image-build pass is claimed. The PR's
Docker-capable CI remains the load-bearing build verification before merge.

---

## §8. Explicit exclusions and limitations

- This BBF does not implement real human-curated corpus content.
- It does not claim that auto-derived labels are human ground truth.
- It does not change the kNN distance function, distance threshold,
  confidence floor, or B4 gate semantics. It does normalize vote shares by
  the effective neighbor count so a corpus smaller than k still sums to 1.0.
- It does not delete the v1 placeholder corpus.
- It does not make malformed or missing corpus files graceful; only version
  metadata drift is advisory.
- It does not land PR #48's stale branch or claim that branch's commits are
  ancestors of main.

## §9. Merge boundary

This BBF may be published as a dedicated PR after independent review. A
squash merge requires a separate explicit merge authorization; the brief's
historical July wording that a user-named command implied merge is not used
as authorization in this cycle.
