# BBF-FU-18-keyring-test — close the A-F10 keyring integration gap

**Sprint intent:** close the A-F10 contract gap. The security
strategy (`docs/08_security/security-strategy.md:50-55`) requires
API keys to be stored in the OS-native keychain (Windows Credential
Manager via the `keyring` Python lib). The actual production code
(`services/chess_coach/llm_router/config.py:9-10`) reads
`OPENROUTER_API_KEY` from `os.environ`, with no keyring integration
anywhere in the codebase. This BBF designs the keyring integration
shape (decision brief) and a follow-up implementation BBF will ship
the code + tests.

**Root cause / context:**

- `docs/16_audit/OPEN-FOLLOWUPS.md:1404-1452` (FU-18, 2026-08-11):
  "No test exists in the repo verifying that secrets are read from
  the OS-native store." The ledger entry framed this as a missing
  test, but the investigation-first pass below discovered a wider
  gap: the **entire keyring integration is missing**, not just
  unenforced-by-test.
- `docs/08_security/security-strategy.md:50-55` (Secrets
  management): "API keys (OpenRouter, OpenAI, Anthropic, Lichess,
  Chess.com) stored in OS-native keychain: Windows: Credential
  Manager (via `keyring` Python lib). Plaintext fallback
  (`secrets.env`) **only** in dev mode and only when an explicit
  `--dev-secrets` flag is passed."
- `docs/08_security/security-strategy.md:112-116` (A-F10): the
  contract is the OS-native store on Windows; the security model
  acknowledges that same-user malware can read the credentials but
  the recommendation is to provision separate keys per app.

**Investigation-first pass (live, this session):**

The pre-implementation investigation ran the following probes
against `main@9791dafc` (post-BBF-cla-bot-wire):

1. `grep -n "OPENROUTER_API_KEY" services/chess_coach/llm_router/config.py`
   = `:9-10` (the `get_api_key()` function reads from `os.environ`).
2. `grep -rnE "import keyring|from keyring|get_password|set_password"`
   in `services/` and `apps/` = **0 matches** (the keyring
   integration does not exist anywhere in the codebase).
3. `grep -nE "^name = \"keyring\"|^name = \"secretstorage\"|^name = \"pywin32\""`
   in `uv.lock` = only `pywin32` matches (a transitive dep, not
   the keyring backend). `keyring` is NOT a declared runtime dep.
4. `grep -E "^\\\"(name = \\\"keyring\\\"|name = \\\"secretstorage\\\")\\\"$"`
   in `uv.lock` = 0 matches.
5. `services/chess_coach/gateway/__main__.py:18-22` shows
   `load_dotenv()` runs at startup, populating `os.environ` from
   `.env` if present. The `.env` file path is in `.gitignore` but
   the API key is read from `os.environ` in the production code
   path (no keyring call).

**Conclusion of investigation-first pass:**

The A-F10 contract is **entirely unenforced** on `main@9791dafc`.
The production code reads `OPENROUTER_API_KEY` from `os.environ`,
which is plaintext by definition (env vars are visible to any
process in the same user session via `/proc/<pid>/environ` on
Linux or Process Explorer / WMI on Windows). The recommended UI
flow (security-strategy.md:116, "during onboarding, recommend
that users provision separate API keys for CHESS COACH") can be
shipped, but the underlying contract is not honored without the
keyring integration.

The FU-18 ledger entry's "no test" framing was a partial diagnosis.
The substantive fix requires: (1) adding the `keyring` runtime
dep, (2) creating a `secrets` module that wraps keyring with
env-var fallback for dev mode, (3) refactoring
`llm_router/config.py` to use the new module, (4) adding tests
that assert the keyring path is the production path, (5) adding
a secret-redaction test for the logger.

**Scope (this BBF — decision brief):**

- `docs/16_audit/BBF-FU-18-keyring-test.md` — this brief
  (tracked at `docs/16_audit/BBF-*.md` per the v0.7.92 lost-briefs
  convention).

**Scope (next BBF — implementation, NOT this BBF):**

- `pyproject.toml` — add `keyring>=24.0` to `[project.dependencies]`
  (the `keyring` library's backends handle Windows Credential
  Manager via `keyring.backends.Windows` on Windows, Keychain on
  macOS, Secret Service on Linux).
- `services/chess_coach/secrets.py` (NEW) — a thin wrapper that
  exports:
  - `get_secret(name: str, *, dev_fallback: bool = True) -> str | None`
    — call `keyring.get_password(SERVICE_NAME, name)` first; if
    `None` and `dev_fallback=True`, fall back to
    `os.environ.get(name)`. If `dev_fallback=False`, return `None`
    on keyring miss (production-mode strict).
  - `set_secret(name: str, value: str) -> None` — call
    `keyring.set_password(SERVICE_NAME, name, value)`. (Not used
    in production code; only for the test fixture + an optional
    CLI tool.)
  - `delete_secret(name: str) -> None` — call
    `keyring.delete_password(SERVICE_NAME, name)`. (Same as
    `set_secret` — only for test fixture + optional CLI.)
  - `SERVICE_NAME` constant = `"chess-coach"` (the keyring
    service identifier; one namespace per application).
- `services/chess_coach/llm_router/config.py` — refactor
  `get_api_key()` to:
  ```python
  def get_api_key(*, dev_fallback: bool = True) -> str:
      from chess_coach.secrets import get_secret
      return get_secret("OPENROUTER_API_KEY", dev_fallback=dev_fallback) or ""
  ```
  The existing `OPENROUTER_API_KEY = ""` deprecated module-level
  constant stays (it is unused; removing it is a separate cleanup
  BBF).
- `services/chess_coach/gateway/__main__.py` — add a `--dev-secrets`
  flag to the CLI (per security-strategy.md:54: "only when an
  explicit `--dev-secrets` flag is passed"). When the flag is set,
  the secrets module enables the plaintext env-var fallback; when
  unset, the secrets module returns `None` on keyring miss. The
  gateway logs a WARNING at startup if `--dev-secrets` is set
  and a key was loaded from the env-var fallback.
- `tests/unit/test_secrets.py` (NEW) — unit tests for the
  secrets module:
  - `test_get_secret_returns_keyring_value_when_present` —
    set a keyring value via `set_secret()`, then assert
    `get_secret()` returns it.
  - `test_get_secret_falls_back_to_env_var_when_dev_fallback_true`
    — clear the keyring value, set the env var, assert
    `get_secret(dev_fallback=True)` returns the env var.
  - `test_get_secret_returns_none_when_dev_fallback_false_and_keyring_empty`
    — clear keyring, set env var, assert
    `get_secret(dev_fallback=False)` returns `None`.
  - `test_get_secret_never_logs_value` — set a keyring value,
    call `get_secret()`, capture logger output, assert the
    value string is not in the output.
- `tests/unit/test_llm_router_config.py` (NEW) — unit tests for
  the refactored `llm_router/config.py:get_api_key()`:
  - `test_get_api_key_delegates_to_secrets_module` — patch
    `chess_coach.secrets.get_secret`, assert `get_api_key()`
    calls it with the right name + dev_fallback.
  - `test_get_api_key_returns_empty_string_on_none` — patch
    `get_secret` to return `None`, assert `get_api_key()` returns
    `""` (the existing contract).
- `tests/unit/test_log_redaction.py` (NEW or extended) — secret
  redaction test: set a logger to capture, log a message
  containing `OPENROUTER_API_KEY=sk-abc123`, assert the captured
  output does NOT contain `sk-abc123` (the redaction filter
  replaces matched key patterns with `***` per
  security-strategy.md:55). If a redaction filter does not
  exist yet, this BBF also adds a minimal filter at
  `services/chess_coach/log_redaction.py`.

**Scope (out of scope, NOT this or the next BBF):**

- The Lichess / Chess.com token storage. Those are per-user
  OAuth tokens, not per-process API keys; the storage model is
  different (the gateway brokers a per-user OAuth flow, then
  stores the token under a per-user keyring entry, not under
  `chess-coach` service name). Tracked as a separate FU.
- A `chess-coach secrets` CLI tool that lets the user
  set/delete keyring entries from the terminal. Useful but
  orthogonal; the user can use the system-native `cmdkey`
  (Windows) / `secret-tool` (Linux) / `security` (macOS)
  commands in the meantime.
- An encryption-at-rest layer above keyring. The OS-native
  keychain is the contract per A-F10; layering encryption
  above is out of scope.
- Keyring backend selection on Linux/macOS. The `keyring`
  library's auto-detection picks the right backend; no code
  change needed.
- The `.env` file removal. `.env` is still useful for
  non-secret config (e.g., `CHESS_COACH_DATA_DIR`); only the
  secret-bearing lines should be migrated to keyring. A
  separate BBF can audit `.env` usage and document the
  secret-vs-non-secret split.
- The `OPENROUTER_API_KEY = ""` deprecated module-level
  constant in `llm_router/config.py:12`. Removing it is a
  cleanup BBF; this BBF only refactors `get_api_key()`.
- A migration script that moves an existing `.env` value into
  keyring. Users can do this manually with the OS-native
  commands; a one-time script is nice-to-have but not
  required by the contract.

**Precise edits (next BBF, NOT this one):**

1. `pyproject.toml` — add `"keyring>=24.0"` to
   `[project.dependencies]` after `"python-dotenv"`.
2. `services/chess_coach/secrets.py` (NEW, ~50 LOC) — module
   per the scope above.
3. `services/chess_coach/llm_router/config.py` — refactor
   `get_api_key()` per the scope above.
4. `services/chess_coach/gateway/__main__.py` — add the
   `--dev-secrets` CLI flag + startup WARNING log per the
   scope above.
5. `services/chess_coach/log_redaction.py` (NEW, ~30 LOC) —
   minimal redaction filter if one does not exist. If one
   already exists, this BBF just adds the test.
6. `tests/unit/test_secrets.py` (NEW) — 4 tests per the scope
   above.
7. `tests/unit/test_llm_router_config.py` (NEW) — 2 tests
   per the scope above.
8. `tests/unit/test_log_redaction.py` (NEW or extended) —
   1 test per the scope above.

**Verification protocol (next BBF):**

- V1: `pip install -e '.[dev]'` succeeds and `keyring` is in
  the installed deps.
- V2: `python -c "import keyring; print(keyring.get_keyring())"`
  returns the platform-native backend
  (`keyring.backends.Windows.WinVaultKeyring` on Windows,
  `keyring.backends.macOS.Keyring` on macOS, `keyring.backends.SecretService.Keyring`
  on Linux with `gnome-keyring` / `kwallet` running).
- V3: `pytest tests/unit/test_secrets.py -v` = 4/4 green.
- V4: `pytest tests/unit/test_llm_router_config.py -v` = 2/2
  green.
- V5: `pytest tests/unit/test_log_redaction.py -v` = 1/1 green
  (or the existing log_redaction test count +1).
- V6: `pytest tests/unit tests/integration
       --ignore=tests/integration/test_engine_orch.py
       --ignore=tests/integration/test_ocr_backend.py
       --ignore=tests/integration/test_pdf_import.py
       --ignore=tests/integration/test_probe_with_gold_set.py
       --ignore=tests/integration/test_pyinstaller_binary.py`
  = green, no regressions.
- V7: `ruff check services/chess_coach/secrets.py
       services/chess_coach/llm_router/config.py
       services/chess_coach/gateway/__main__.py
       tests/unit/test_secrets.py
       tests/unit/test_llm_router_config.py` = All checks
  passed.
- V8: `git diff --numstat` shows the expected file list
  (8 files, ~200-300 LOC, all under the secrets/config/
  log_redaction + tests scopes).
- V9: byte-integrity: 0 literal `\u2019` in the diff.
- V10: 0 bare `path:N` references in the commit body (per
  the (σ) meta-footgun discipline).

**Cross-references:**

- `docs/16_audit/OPEN-FOLLOWUPS.md:1404-1452` (FU-18) — the
  ledger entry this BBF ships the decision for.
- `docs/08_security/security-strategy.md:50-55` (Secrets
  management) — the A-F10 contract.
- `docs/08_security/security-strategy.md:112-116` (A-F10
  detailed) — the same-user-malware acknowledgment + the
  separate-keys onboarding recommendation.
- `services/chess_coach/llm_router/config.py:9-10` (the
  current plaintext env-var read).
- `services/chess_coach/gateway/__main__.py:18-22` (the
  `load_dotenv()` startup behavior).
- `pyproject.toml:30-49` (the runtime deps list, where
  `keyring>=24.0` will be added).
- v0.7.92 lost-briefs incident (the convention that
  BBF briefs live at `docs/16_audit/BBF-*.md`).
- v0.7.103 strategic-decision-bbf-pattern (the discipline
  that ships a decision brief before the implementation BBF
  it would govern).
- v0.7.107 brief-vs-code-divergence (the pre-implementation
  check that surfaced the wider gap than the ledger entry's
  "no test" framing).

**Honest disclosures:**

- The FU-18 ledger entry's "no test" framing was a partial
  diagnosis. The investigation-first pass discovered that the
  **entire keyring integration is missing**, not just
  unenforced-by-test. The next BBF is a multi-file
  implementation, not a "test addition" as the original
  ledger entry suggested.
- The plaintext env-var fallback is a deliberate
  security-vs-developer-experience trade-off. The contract
  (`security-strategy.md:54`) requires the fallback to be
  gated on an explicit `--dev-secrets` flag, which the
  implementation BBF will honor. The fallback is NOT used
  in production; it exists for dev-mode convenience.
- The "separate-keys onboarding recommendation" from
  `security-strategy.md:116` is a UI-layer recommendation
  (out of scope for this BBF). The architectural
  enforcement (keyring storage) is the load-bearing piece;
  the UI recommendation is a defense-in-depth measure.
- The implementation BBF will ship tests for the keyring
  integration. Whether the tests run on CI is a separate
  question (CI runners may not have a `gnome-keyring` /
  `kwallet` service available, which would make the
  secrets tests fail). The implementation BBF's
  "Verification protocol" V3 assumes a backend is
  available; if the CI runner does not have one, the
  implementation BBF must use a `keyring` test backend
  (e.g., `keyring.backends.fail.Keyring` for the
  fail-closed case) and skip the integration tests
  on CI. The exact CI wiring is part of the implementation
  BBF's scope, not this decision brief.
- The v0.7.128 (σ) meta-footgun applies to this BBF's
  commit body too. The verifications V1-V10 above wrap all
  `path:N` references in backticks where appropriate, but
  the commit body's verification section must NOT include
  unbackticked `file:N` references (per the (σ) discipline
  recorded in the BBF-cla-bot-wire post-mortem).

**Final report format:** the squash-merge commit body
documents this BBF's 1-file diff (the brief itself) + the
deferred implementation BBF's scope (the 8-file list above).
The commit body uses inline-backtick-wrapped `path:N` references
where appropriate, paraphrases where not, and avoids unbackticked
bare refs per the (σ) discipline.

**Hermes verification (re-derive, post-merge):**

- `git show main:docs/16_audit/BBF-FU-18-keyring-test.md | head -5`
  returns the brief's "Sprint intent" paragraph.
- `git show main:docs/16_audit/BBF-FU-18-keyring-test.md | grep -c "keyring"`
  > 0 (the brief mentions the library by name).
- `git show main:docs/16_audit/OPEN-FOLLOWUPS.md | grep -A 2 "## FU-18"`
  is updated to point at this BBF as the decision brief.
  The ledger entry's status flip (OPEN → RESOLVED) is the
  follow-up that shipped via PR #137 (see the 4-amend chain
  in the FU-18 entry itself for the SHA trail; the new
  brief at `docs/16_audit/BBF-FU-18-doc-drift.md` records
  the doc-only BBF). The pre-flip line range was
  `OPEN-FOLLOWUPS.md:1404-1452`; the post-PR-#137 range is
  ~62 lines longer (the entry grew to document the 4-amend
  chain + the open follow-ups).
- The 5-7th lines from the bottom of the brief's
  "Investigation-first pass" section cite the
  `OPEN-FOLLOWUPS.md:1404-1452` line range (pre-PR-#137; the
  pre-flip range is the historically-accurate one for this
  brief, which was written before the doc-drift follow-up).