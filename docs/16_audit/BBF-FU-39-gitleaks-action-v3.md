# BBF-FU-39-gitleaks-action-v3 — bump gitleaks-action @v2 to @v3 (Node 20 → 24)

**Sprint intent:** Bump
`gitleaks/gitleaks-action@v2` to
`gitleaks/gitleaks-action@v3` (and the companion
`actions/checkout@v5` → `@v6`) in
`.github/workflows/security-audit.yml`, closing the
Node-20 deprecation risk before the upstream hard
cutover (per the gitleaks-action README: Node 20
removed from GitHub-hosted runners Sep 2026; v2
silently broke on Jun 2, 2026 without the
`ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`
opt-out).

**Identified:** 2026-10-15, session-close
follow-up audit. The `.github/workflows/security-audit.yml`
workflow's `gitleaks` job is the only remaining
`@v2` action in the file; the other jobs already
use Node-24-era pins (`actions/setup-python@v6`,
`actions/setup-node@v6`, `pnpm/action-setup@v6`).
The v3 migration is a one-line action-version bump
+ a sibling checkout bump (per the v2→v3 migration
section of the upstream README).

**The gap this BBF closes:**

- The `gitleaks` job in `security-audit.yml` will
  start failing on Jun 2, 2026 (or earlier) when
  GitHub forces Node 24 on v2 actions unless
  `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true`
  is set as an opt-out.
- After Sep 16, 2026, the v2 action stops working
  entirely (Node 20 removed from runners). At that
  point, the `gitleaks (secret scan)` CI job fails
  with no actionable diagnostic — the workflow just
  doesn't run, and secrets stop being scanned.
- Bumping to `@v3` is a 2-line YAML change that
  adopts Node 24 natively and matches the rest of
  the workflow file's already-Node-24-era pins.

**Investigation-first pass (re-derive, pre-flight):**

- The current pin is `gitleaks/gitleaks-action@v2`
  (line 96 of `security-audit.yml`).
- The companion `actions/checkout@v5` must bump to
  `@v6` (the v3 action requires Node 24, and the
  Node 20 checkout is incompatible).
- The other 3 actions in the same file already
  use the v6 / Node 24 line: `actions/setup-python@v6`,
  `actions/setup-node@v6`, `pnpm/action-setup@v6`.
- The `.gitleaks.toml` config is unchanged by the
  bump (the gitleaks CLI binary version may change,
  but the config syntax + `[[allowlists]]` /
  `[allowlist]` semantics are the same).
- Post-merge CI on `main` was 12/12 green at
  `9cb7d84b`; the gitleaks job passed with the
  current `[[allowlists]]` config (now fixed to
  `[allowlist]` per amend #2 of PR #136).

**Work product:**

This BBF produces exactly one file change:
`.github/workflows/security-audit.yml` with two
line-level edits:

1. `actions/checkout@v5` → `actions/checkout@v6`
   (the gitleaks job's checkout step)
2. `gitleaks/gitleaks-action@v2` → `gitleaks/gitleaks-action@v3`
   (the gitleaks job's "Run gitleaks" step)

Plus a doc-only ledger entry: this BBF adds a
`## FU-39` section to `docs/16_audit/OPEN-FOLLOWUPS.md`
mirroring the FU-18 doc-drift pattern (so the
ledger has a dedicated entry for this follow-up
that can be flipped to RESOLVED on squash-merge).

**Out of scope (separate BBFs):**

- **FU-38** — 29 pre-existing historical gitleaks
  findings (visible in a local full-history scan,
  not in the diff-scoped SARIF). Not in scope for
  this BBF; the action bump is independent of the
  leak cleanup.
- **The 4-amend chain from PR #136** — the
  `[[allowlists]]` → `[allowlist]` fix and the
  3 other amend fixes. The v3 bump is a separate
  concern from the config-syntax fix; this BBF
  does not re-touch `.gitleaks.toml`.
- **Workflow-action Node-20 audit across other
  workflows** (`smoke.yml` and any others). The
  initial scan shows that `smoke.yml` is NOT yet
  on the Node-24 line; per the leaf review's
  empirical scan on the live `main` HEAD,
  `smoke.yml` still uses Node-20-era pins
  (`actions/checkout@v4`, `actions/setup-python@v5`,
  `actions/setup-node@v4`, `pnpm/action-setup@v4`).
  The audit + bump of those pins is a separate BBF
  (or set of BBFs); the same Node-24 deprecation
  dates (Jun 2, 2026 / Sep 16, 2026) apply. The
  scope of THIS BBF is the gitleaks-action only;
  smoke.yml's Node-20 pins are tracked as a
  future BBF. If stale pins are found in other
  workflow files later, they get their own BBFs.

**Honest disclosures:**

- The Node-20 deprecation is the same defect class
  as the v0.7.128 (σ) meta-footgun: a config
  surface that "loads successfully" but doesn't
  actually apply. The gitleaks-action @v2 loads
  on Node 20 today, but the upstream runtime
  will force Node 24 anyway; if `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION`
  is not set, the v2 action will fail.
- The bump does NOT change the gitleaks behavior
  on the `tests/unit/test_log_redaction.py`
  fixtures (the `[allowlist]` config from PR #136
  amend #2 is still honored by the bundled gitleaks
  CLI in v3, which uses the same gitleaks 8.x line
  per the action's bundled-binary policy).
- After the bump, the `gitleaks (secret scan)` job
  will run on Node 24. The action's
  `DBG using existing gitleaks config` log line
  (the diagnostic I used in the FU-18 amend chain)
  is preserved in v3 — no diagnostic regression.
- The v3 bump may surface a NEW CI failure if the
  bundled gitleaks CLI in v3 has a different default
  version than v2's. Per the v3 migration section of
  the upstream README, v3 still uses the gitleaks
  8.x line (no major version bump). Pre-merge CI
  will catch any behavioral diff in 1 cycle; the
  v7.114 amend-fold discipline applies.

**Hermes verification (re-derive, post-merge):**

- `git show main:.github/workflows/security-audit.yml
  | grep "gitleaks-action@"` returns `@v3`.
- `git show main:.github/workflows/security-audit.yml
  | grep "actions/checkout@v"` returns `@v6` (in
  the gitleaks job) and `@v5` (in the other jobs,
  unchanged).
- `pytest tests/unit/test_log_redaction.py` still
  passes 5/5 (the v3 action does not affect the
  test fixtures).
- Pre-merge CI on the amended SHA: 12/12 green
  (specifically the `gitleaks (secret scan)` job
  must remain green after the bump — this is the
  critical verification).

**Final report format:** the squash-merge commit
body documents this BBF's 2-line YAML diff + the
new FU-39 ledger entry + the +1 file (the new
brief). The commit body uses inline-backtick-wrapped
`path:N` references where appropriate and
paraphrases where not, per the v0.7.128 (σ)
discipline.
