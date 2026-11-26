# BBF: `i18next` advisory remediation — `GHSA-6jcc-5g8w-32mx` (production gate)

**Date:** 2026-11-26
**Branch:** `bbf/i18next-advisory-remediation`
**Base:** `7d19b44278948d92f855e03b494507162df532c9` (`main`)
**Scope:** 4 files — 2 dependency files (`apps/desktop/package.json`,
`apps/desktop/pnpm-lock.yaml`), this brief, and the FU-50 ledger entry.

## Objective

The `pnpm audit (JS dep vulnerability scan)` job in
`.github/workflows/security-audit.yml` is red on `main`. It reports one
moderate-severity finding against the **direct** dependency `i18next`, on the
production dependency graph. This BBF clears that gate by moving the two
affected direct declarations to their patched versions.

`picomatch` is **not** addressed here: its advisory is withdrawn and no
patched release exists upstream. That is recorded as a standing condition in
FU-49 and restated under *Scope excluded* below.

## Root cause: the wrong floor, in a DIRECT dependency

`i18next` is declared directly in `apps/desktop/package.json`. Its declared
range `^25.8.11` excludes every patched version, so no lockfile refresh could
have fixed this — the declaration itself had to move.

| Package | Classification | Declared before | Resolved before | Fix floor | Declared after | Resolved after |
|---|---|---|---|---|---|---|
| `i18next` | **direct** (`dependencies`) | `^25.8.11` | 25.10.10 | `>= 26.3.4` | `26.3.4` (exact) | 26.3.4 |
| `react-i18next` | **direct** (`dependencies`) | `^16.5.4` | 16.6.6 | peer requires `i18next >= 26.2.0` | `17.0.11` (exact) | 17.0.11 |

Both floors are **exact pins**, not carets. A caret on `i18next` would resolve
past the version that was reviewed here; an exact pin is deterministic and
cannot drift into a future advisory range. `26.3.4` is the advisory's own
per-package fix floor, and it satisfies `react-i18next@17.0.11`'s peer
constraint (`i18next >= 26.2.0`).

**Why the two declarations move together.** `react-i18next@16.6.6` pins
`i18next: '>= 25.10.9'` and would have continued to resolve the vulnerable
25.x line, so bumping `react-i18next` alone would leave the production graph
red through the parent. Both direct declarations move.

**What was deliberately NOT taken.** `i18next@27.2.9` is the current npm
`latest` and also clears the advisory, but it is a major bump of a library
used across 73 desktop source files and adds no value to this gate. `26.7.2`,
the newest 26.x, also clears it, but is a later minor than the floor requires.
`26.3.4` is the smallest change that clears the gate.

## The advisory, re-derived at the time of this change

Read live from the GitHub advisory API on 2026-11-26, not carried over from
an earlier diagnosis:

| Property | Value |
|---|---|
| Advisory | `GHSA-6jcc-5g8w-32mx` |
| Summary | `i18next deepExtend recurses into inherited built-ins, allowing corruption of shared built-in objects (DoS)` |
| Severity | medium |
| Vulnerable range | `< 26.3.4` |
| `withdrawn_at` | **null** — the advisory is LIVE, not withdrawn |
| `published_at` | 2026-11-23T20:53:00Z |

Two other `i18next` advisories exist (`GHSA-f89g-whpf-6q9m`, affecting
`<= 1.10.2`, and `GHSA-cmh5-qc8w-xvcq`, affecting `>= 2.0.0, < 3.4.4`).
Neither applies to the 25.x/26.x versions in this graph, so the binding floor
for this graph is `26.3.4`.

## The gate, before and after

Reproduced locally with the CI's exact command and working directory
(`working-directory: apps/desktop`, `pnpm audit --audit-level moderate --prod`),
not read from CI logs.

**Before:** exit 1 — one vulnerability.

```
│ moderate            │ i18next deepExtend recurses into inherited built-ins,  │
│ Package             │ i18next                                                │
│ Vulnerable versions │ <26.3.4                                                │
│ Patched versions    │ >=26.3.4                                               │
│ Paths               │ .>i18next                                              │
│                     │ .>react-i18next>i18next                                │
```

**After:** exit 0 — `No known vulnerabilities found`.

The production graph now resolves a single `i18next` version:

```
$ pnpm why i18next --prod
i18next@26.3.4
├── chess-coach@0.1.0 (dependencies)
└─┬ react-i18next@17.0.11
  └── chess-coach@0.1.0 (dependencies)

Found 1 version of i18next
```

## The gate is still armed

The remediation is a real fix, not a false green:

- **The workflow is not modified at all.** `git diff
  7d19b442 -- .github/workflows/security-audit.yml` produces **no output** —
  the file is byte-identical to the base, so the job's `run:` line is
  unchanged: still `pnpm audit --audit-level moderate --prod`, still
  `working-directory: apps/desktop`.
- **No suppression mechanism was introduced.** A tree-wide search for
  `ignoreCves|ignore-vuln|ignoreGhsas|auditConfig|auditLevel|--no-audit|PIP_AUDIT_IGNORE|allowedVersions|ignoreAdvisories`
  returns no match.
- **The audit level was not lowered** and the `--prod` scope was not dropped.

## Migration surface: measured, not assumed

`i18next` v26.0.0 is a major release. Its published breaking changes are the
removal of the `initImmediate` option, the legacy monolithic
`interpolation.format` function, the `showSupportNotice` option and
`simplifyPluralSuffix`. (`initAsync`, which replaced `initImmediate` back in
v24, is **not** among them — it still exists in i18next 26.3.4's
`typescript/options.d.ts`, and the same is true of the other three names
above in 25.10.10, so their absence here is a real removal rather than a
naming change.) A tree-wide search across the desktop source and
config files — every tracked file under `apps/desktop/` ending in `.ts`,
`.tsx`, `.js`, `.jsx`, `.mjs` or `.json`, **274** files — found:

| Removed in v26 | Occurrences in this repository |
|---|---|
| `initImmediate` | 0 |
| `simplifyPluralSuffix` | 0 |
| `showSupportNotice` | 0 |
| `interpolation.format` (the removed monolithic form) | 0 |

The repository's only `interpolation` use is
`apps/desktop/src/components/home/AccountCard.tsx:285` —
`interpolation: { escapeValue: false }` — which is not the removed API.

The application's i18n initialization (`apps/desktop/src/index.tsx`) uses
`resources`, `detection`, `fallbackLng` and `returnEmptyString`, none of which
changed in v26.

**The app's own gates, run against the change:** `pnpm run lint:ci` exit 0
(`tsgo --noEmit`, `oxfmt --check`, `oxlint` — 81 warnings, 0 errors, and the
i18n keygate reporting `OK: all 548 source-referenced keys exist in committed
en-US.json`); `pnpm run test` exit 0 — 7 test files, 44 tests passed.

`pnpm run i18n:status` exits 1 (`Incomplete translations detected`), but it
exits 1 identically on the base tree with the change stashed — it is a
pre-existing translation-coverage state, not a regression from this change,
and it is not a CI gate.

## The full dependency graph is outside the gate and is not clean

`pnpm audit --audit-level moderate` — the **full** graph, production and
development together, with no scope flag — exits 1 with **32
vulnerabilities** — 3 low, 16 moderate, 11 high, 2 critical — across **8
packages** (`tinypool`, `undici`, `brace-expansion`, `js-yaml`, `vitest`,
`@vitest/mocker`, `glob`, `minimatch`), itemised as **29 advisory rows**
carrying **25 distinct advisory ids**. Before this change the same graph
reported 33 vulnerabilities (3 low / 17 moderate / 11 high / 2 critical)
across 9 packages, 30 rows and 26 distinct ids; the one that left is the
`i18next` advisory this BBF fixes. `i18next` is a **production** dependency,
so that advisory was in the production graph and in this full graph.

**The `--dev`-only graph is a different graph, and this BBF does not change
it.** `pnpm audit --audit-level moderate --dev` reports 32 vulnerabilities,
25 distinct advisory ids, 29 rows and 8 packages on the base tree and on
this change's tree alike — the same advisory-id set in both — because
`i18next` is declared in `dependencies`, not `devDependencies`, so its
advisory is absent from the development-only graph either way.

None of these are in the `--prod` gate's scope, so the green production result
says nothing about them. They are not claimed as resolved.

## The CI comment needs no correction

The `pnpm-audit` job's comment block in `.github/workflows/security-audit.yml`
records the dev graph as 32 vulnerabilities (3 low | 16 moderate | 11 high |
2 critical) across 8 packages, "itemised as 25 distinct advisories". That
figure was re-measured on the base tree and on this change's tree and is
**accurate on both**: `pnpm audit --audit-level moderate --dev` reports 32
vulnerabilities and 25 distinct advisory ids (in 29 rows) across 8 packages
before and after this remediation, because `i18next` is a production
dependency and its advisory sits in the production graph, not the development
one. The comment's figures were already correct, so
`.github/workflows/security-audit.yml` is **not modified by this BBF**.

This matters because the two numbers are easy to confuse: pnpm prints one
row per module/range pair, so 29 rows carry 25 unique advisory ids (four ids
appear twice). The repo's own convention — commit `9b02ae5a` — records the
same graph as "29 advisory rows carrying 25 distinct advisory ids".

## Scope excluded

- **`picomatch`** — `GHSA-fc5q-39xc-vjpf` / `CVE-2026-112366` is **withdrawn**
  (`withdrawn_at: 2026-11-18T15:38:56Z`) — the advisory's current text reads
  *"This advisory has been withdrawn because it is **not** a security issue"* —
  and no patched release exists: npm
  `latest` is still `4.0.7` and there is no `4.0.8`. The two upstream items
  are not the same kind of thing: `micromatch/picomatch` **#235** is the
  proposed fix for the disputed repeated-extglob issue the advisory cites
  (**closed and unmerged**), while **#194** is a separate open
  wildcard-parser change whose own body states *"This is not a security fix
  and I am not claiming a vulnerability"* and that it *"does not fix #175
  generally"* (**open and unmerged**). The locked versions 4.0.5 and 4.0.7
  are unchanged. There is nothing to pin, and this BBF does not change
  `picomatch`'s resolution. Two *other* `picomatch` advisories
  (`GHSA-3v7f-55p6-f55p`, `GHSA-c2c7-rcm5-vvqj`) remain live but affect only
  `< 4.0.4`, `>= 3.0.0, < 3.0.2` and `< 2.3.2` — none of the locked versions.
  Standing condition: the production gate's green state for `picomatch` rests
  on the withdrawal, not on a code change.
- **The full dependency graph's 32 vulnerabilities** (29 advisory rows carrying
  25 distinct advisory ids, across 8 packages) — outside the `--prod` scope
  and not remediated here. The `--dev`-only graph is unchanged by this BBF.
- **The `pnpm run i18n:status` translation coverage** — pre-existing on the
  base tree.
