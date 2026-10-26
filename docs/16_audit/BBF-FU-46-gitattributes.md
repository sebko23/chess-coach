# BBF-FU-46 — repository line-ending policy (`.gitattributes`)

**Date:** 2026-10-26
**Branch:** `bbf-fu-46-gitattributes`
**Base:** `6b6eb94992e12a810a42988d2025e89a7f5bc9ad` (`main`)

## Objective

The repository has no `.gitattributes`, so git's line-ending behaviour is
governed entirely by each developer's `core.autocrlf`. Seventeen tracked files
are committed with CRLF in the object store, and a checkout on a
CRLF-configured host produces hundreds of spurious modifications.

This BBF adds an explicit, audited line-ending policy and normalises the
committed CRLF text blobs to LF. Binary assets are protected by rule and are
never transformed.

## Why two commits

The work is split so each diff is independently reviewable:

1. **Policy commit** — adds the root `.gitattributes` and nothing else. Zero
   source-content changes.
2. **Renormalization commit** — `git add --renormalize .`, changing only the
   16 CRLF text blobs. Every changed blob differs from its predecessor by
   CRLF-to-LF only.

Combining them would hide the policy review behind a 16-file normalization
diff and make rollback and `git blame` less precise.

## Current-main evidence

Every figure below was measured by the authenticated host against
`6b6eb94992e12a810a42988d2025e89a7f5bc9ad`, classifying blobs from **git object
bytes** rather than working-tree bytes.

| Classification | Count |
|---|---:|
| Tracked entries | 868 |
| Known binary assets | 91 |
| Text-family paths | 777 |
| Unknown / review-required | 0 |
| Committed-CRLF files | 17 |

The binary inventory is exactly 32 `.png`, 32 `.jpg`, 24 `.mp3`, 2 `.ico`,
1 `.icns` — 91 files, all containing NUL bytes.

The 17 committed-CRLF files are:

```
CHANGELOG.md
CONTRIBUTING.md
apps/desktop/src/components/panels/coach/CoachPanel.tsx.bak_1780860511
docs/10_roadmap/phase-plan-v2.md
docs/15_methodology/profile-metrics-v1.md
docs/CHANGELOG.md
libs/chess_coach/datasets/__init__.py
services/chess_coach/llm_router/config.py
services/chess_coach/profile/__init__.py
tests/gold/phase4_v1_fixtures.py
tests/integration/test_profile_archetypes_integration.py
tests/unit/test_keychain.py
tests/unit/test_pdftomd_metrics.py
tests/unit/test_phase4_golden.py
tests/unit/test_profile_skeleton.py
tests/unit/test_profile_stats.py
tests/unit/test_profile_tilt_archetypes.py
```

`docs/CHANGELOG.md` is **mixed** (1,052 CRLF and 1,599 LF lines);
`CHANGELOG.md` is CRLF-only (657 lines, no bare LF).

## The policy

`.gitattributes` — 3,030 bytes, LF-only, SHA-256
`c37388d05352206784c2690c534cf5e4a0d8fff0372282f81e4a39dae3687629`, 76 lines, 39 active rules:

| Class | Rules | Effect |
|---|---|---|
| Binary | 6 (`*.png`, `*.jpg`, `*.jpeg`, `*.mp3`, `*.ico`, `*.icns`) | never transformed |
| Text | 23 extensions | `text eol=lf` |
| Dotfile / extensionless | 8 (`.gitignore`, `.gitattributes`, `.dockerignore`, `.editorconfig`, `.upstream-ref`, `.gitkeep`, `Dockerfile`, `LICENSE`) | `text eol=lf` |
| Frozen orphans | 2 exact paths | `-text` |

> **Correction (2026-10-26, FU-47):** the two exact-path `-text`
> freezes were removed with the files they protected. FU-47 deleted both
> orphan `.bak` files; the policy now has 37 active rules and no
> exact-path `-text` freeze.

Design decisions:

- **No broad `* text=auto eol=lf` fallback.** `text=auto` delegates the
  decision to git's content sniffing, which is the nondeterminism that produced
  this problem. Every path is classified explicitly.
- **Binary rules come last.** Gitattributes applies each attribute
  independently: `text` is decided by the last rule matching `text`,
  `binary` by the last rule matching `binary`.

  The binary rules are listed **last** deliberately. `binary` is a shorthand
  for `-text -diff`, so a later binary rule wins the `text` attribute and
  clears it. A path matching both a binary and a text rule would keep
  `text: set` if the text rule came last, and git would then rewrite its
  bytes — the exact outcome the binary rules exist to prevent.

  Verified in a throwaway repository with a CRLF payload in a `.png` file:

  | Rule order | `check-attr text` | Stored blob | Bytes protected? |
  |---|---|---|---|
  | `*.png binary` first, `*.png text eol=lf` last | `text: set` | `AAA\nBBB\n` | **No — converted** |
  | `*.png text eol=lf` first, `*.png binary` last | `text: unset` | `AAA\r\nBBB\r\n` | **Yes — preserved** |

  No tracked path matches both rule classes today (0 of 870), so the shipped
  policy is correct either way — but the order is set so that a future rule
  added in the wrong place cannot silently rewrite binary bytes.
- **No `.bat`/`.cmd` rules.** The current tree contains no such paths, so
  rules for them would be speculative.
- **The two orphan `.bak` files are pinned by EXACT path**, not by a `*.bak`
  glob. A glob would also match any future orphan backup file added to the
  tree and silently freeze a file that has not been reviewed. The leading `/`
  anchors the rule to the repository root.

### Why the two `.bak` files were frozen rather than normalized

Both are unreferenced leftovers, scheduled for deletion in a separate
cleanup BBF. **Correction (2026-10-26, FU-47):** they were added by a 2026-06-13 commit titled "backup: pre-player-atom state snapshot before shared atom migration",
not by `cd43906c` (2026-07-13) — `cd43906c` merely carried them forward, and
the original attribution came from a shallow clone whose history boundary was
`cd43906c`. That cleanup BBF has since landed:
both files are deleted and the two exact-path `-text` freezes are removed
with them. Normalizing a file that is about to be deleted is
churn, and the `.tsx.bak` one is the only CRLF-containing file that would
still be CRLF after this BBF. `-text` guarantees no conversion is applied in
either direction and their committed bytes stay exactly as they are.

## Verification

All checks were run in a throwaway clone at the pinned commit, with
`core.autocrlf=false` and `core.eol=lf` set before any checkout. The audited
repository was not used as the experiment surface.

### Policy coverage

`git check-attr text eol binary` over **every** tracked path, read via
`--pathspec-from-file --pathspec-file-nul` (or `--stdin -z`; plain `--stdin`
mangles paths on Windows):

- **base: 868 of 868 paths matched; 0 unspecified.**
- **head: 870 of 870 paths matched; 0 unspecified** — head adds `.gitattributes`
  and the brief to the base's 868.

### The exact-path rules resolve

```
apps/desktop/src/components/panels/coach/CoachPanel.tsx.bak_1780860511
    -> text: unset
services/chess_coach/gateway/routes/repertoire_recommendations.py.bak
    -> text: unset
apps/desktop/src/components/panels/coach/CoachPanel.tsx
    -> text: set, eol: lf
services/chess_coach/gateway/routes/repertoire_recommendations.py
    -> text: set, eol: lf
```

At this commit the two orphans are frozen; their live siblings are
normalised. **Correction (2026-10-26, FU-47):** both orphan files were
subsequently deleted, so the freezes no longer exist.

### Renormalization result

`git add --renormalize .` changed **16** files — the 17 minus the frozen
`.bak`:

| Property | Result |
|---|---|
| Files renormalized | 16 |
| Binary assets changed | **0** of 91 |
| `.bak` blobs changed | **0** (both byte-identical) |
| Every changed blob CRLF-only | **True**, verified byte-by-byte |
| `git diff --check` | clean |

### Post-commit state of the object store

After the renormalization, the tracked blobs that still contain the CRLF byte
pair are:

| Class | Count | Note |
|---|---:|---|
| Binary assets | 49 | image/audio data where the byte pair is not a line ending; bytes unchanged |
| Text files | **1** | the frozen orphan `CoachPanel.tsx.bak_1780860511` |

> **Correction (2026-10-26, FU-47):** that orphan was deleted on
> 2026-10-26, so the current tree has **0** tracked text files containing a
> CRLF sequence.

So **no tracked text file other than the frozen orphan contains a CRLF
sequence**.

> **Correction (2026-10-26, FU-47):** the frozen orphan was deleted, so
> **no tracked text file at all** now contains a CRLF sequence. The binary
> hits are byte-value coincidences inside PNG, JPG, MP3, ICO and ICNS
> payloads; their blobs are unchanged by this BBF.

### The checkout noise this BBF eliminates, measured

The symptom this policy addresses is that a checkout materialised under a
CRLF-configured host and then compared with `core.autocrlf=false` reports
hundreds of files as modified, which has repeatedly been mistaken for real
content drift.

Reproduced in a throwaway clone, for each commit, by materialising every
tracked file under `core.autocrlf=true` and then switching that setting to
`false` before comparing:

| Commit | Files on disk containing CRLF | Files whose on-disk bytes differ from a pristine LF checkout |
|---|---:|---:|
| Base `6b6eb949` (no `.gitattributes`) | 804 | **738** |
| Head (with the policy) | 50 | **0** |

The 50 remaining are the 49 binary assets and the frozen orphan `.bak`.

> **Correction (2026-10-26, FU-47):** the orphan was deleted, so the
> current count is **49** — all binary assets.

The middle column counts files whose **on-disk bytes** differ from a pristine
LF checkout; it is a byte-level measurement, not a `git diff` count. The
`git diff` count is deliberately not quoted: it varies with git's stat cache
and with the command that last refreshed the index, so it is not a stable
figure to publish. What matters is that the byte-level count is exactly 738
at the base commit and exactly 0 with the policy in place, and that the
on-disk CRLF count drops from 804 to 50.

### Gates on the renormalized tree

| Gate | Command | Result |
|---|---|---|
| Python tests | CI coverage invocation (`--cov-fail-under=55`) | exit 0 — **540 passed**, 9 skipped (identical to baseline) |
| Python lint | `ruff check libs services apps/cli tests scripts` | exit 0 — all checks passed |
| Python types | `mypy libs services apps/cli --no-incremental --platform linux` | exit 0 — no issues in 86 source files |

### Two scratch failures that were environment artifacts, not regressions

Both were re-run with a control on pristine `main` in the same clone:

- **pytest exit 1** with 19% coverage instead of ~60%: pristine `main` in the
  same scratch also exited 1 with the same coverage figure. It is the scratch
  environment's coverage measurement. 540 tests passed in both cases.
- **`gen-api --check` exit 1** ("cannot find path"): the scratch has no
  `node_modules`, so `openapi-typescript` is absent. The same command in the
  real repository exits 0 with `api.ts is up-to-date with the backend schema`.

## Scope

Two commits, 19 paths in total:

| Commit | Paths | What |
|---|---:|---|
| 1 — policy | 3 | `.gitattributes` (new), this brief (new), the FU-46 ledger entry (one pure 36-line insertion) |
| 2 — renormalization | 16 | the CRLF text blobs, each CRLF-to-LF only |

The two orphan `.bak` blobs are **not** in either commit's file set: they are
frozen by the policy and are deleted by a separate cleanup BBF.

## Deliberately out of scope

- **The two orphan `.bak` files.** Deletion is a separate cleanup BBF; this
  BBF only freezes their bytes. **Correction (2026-10-26, FU-47):** that
  cleanup BBF has since landed — both files are deleted and the two
  exact-path `-text` freezes are removed with them.
- **Any change to the CRLF content of the 16 renormalized files beyond the
  line terminators.** Each changed blob differs from its predecessor by
  CRLF-to-LF only; no other byte differs.
- **Any change to `core.autocrlf` / `core.eol` in repository configuration.**
  Those are per-developer settings, not repository content. The policy file
  makes them irrelevant for every tracked path.
- **`.bat`/`.cmd` line-ending rules.** The tree contains no such paths.
- **The pre-existing checkout noise.** This BBF fixes the committed content;
  a developer's existing checkout may need a re-clone to pick up the new
  policy.

## Provenance

The policy file was built and validated by the authenticated host. The
container verified the transferred candidate's bytes and rule coverage
read-only and confirmed both exact-path `.bak` freezes, the binary rules, the
absence of a `* text=auto` fallback, and the absence of `.bat`/`.cmd` rules.

The first scratch candidate was destroyed by a control reset before it could be
committed, so the transferred file is a rebuilt candidate that was then
re-validated from scratch — it is not recovered original bytes. Its digest is
recorded above and in the commit message.
