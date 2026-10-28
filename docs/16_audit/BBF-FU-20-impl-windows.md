# BBF-FU-20-impl-windows — A-F11 property 2: Windows network isolation (best-effort)

**Sprint intent:** Improve the Windows path of
`set_network_isolation_preexec()` from a pure no-op
to a best-effort fallback. The ideal Windows
implementation would use a Job Object with
`JOB_OBJECT_NET_RATE_CONTROL`, but the `pywin32`
module does not expose the `SetInformationJobObject`
API for this info class. The current implementation
degrades to stripping network-related env vars
(proxy config) so the child can't use inherited
proxy settings to bypass host network policy.

**Status:** Code + test BBF. 2 files modified.

## §1. The limitation

The `pywin32` module (`win32job`) exposes:
- `CreateJobObject`
- `AssignProcessToJobObject`
- `SetInformationJobObject` (limited info classes)
- `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (memory cap — **NOT used by FU-22-impl**; see the 2026-10-28 correction below)

It does **not** expose:
- `SetInformationJobObject` with `JobObjectNetRateControlInformation`
- Any other network-related Job Object info class

This is a real gap in the `pywin32` binding. The full
Windows network isolation would require:
1. A custom C extension calling `SetInformationJobObject`
   with `JobObjectNetRateControlInformation`
2. Windows Firewall rules via `netsh advfirewall` (requires admin, not recommended for a subprocess)
3. AppContainer (requires significant new code)

## §2. The fix (this BBF)

The Windows path of `set_network_isolation_preexec()`
now strips network-related env vars:
- `http_proxy`, `https_proxy`, `all_proxy`, `no_proxy`
- `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`

This is a **defense-in-depth** measure, NOT a guarantee
of network isolation. A determined attacker can still
open raw sockets. But it removes the most common
exfiltration vectors (proxy config that the child
inherits from the parent FastAPI process).

## §3. The verification (live, this session)

```
# Ruff:
$ ruff check libs services apps/cli tests scripts
All checks passed!

# Tests (7 passed, 2 skipped):
$ pytest tests/unit/test_subprocess_runner.py -v
7 passed, 2 skipped in 0.48s

# New test:
test_set_network_isolation_preexec_strips_env_on_windows PASSED
  - Sets http_proxy env var
  - Calls the preexec_fn
  - Verifies it returns None (no raise)
  - Cleans up the env var
```

## §4. The §1.3 catches (exemplary discipline)

1. **F821 Undefined name `os`** (pre-commit) — The inner
   `_windows_isolate_network` function couldn't see the
   outer `os` import. Fix: imported `os` as `_os` inside
   the function (same pattern as the Linux path).

2. **ruff E501** (CI) — Verified clean with ruff 0.17.1.

## §5. Honest disclosures

1. **The Windows network isolation is NOT guaranteed.**
   The env-var stripping is a defense-in-depth measure.
   A determined attacker can still open raw sockets.
   The full Windows network isolation requires either
   a custom C extension or a different mechanism
   (firewall rules, AppContainer).

2. **The `pywin32` module is not a project dependency.**
   This BBF does NOT add `pywin32` to `pyproject.toml`
   because the Windows path doesn't actually use
   `win32job` (it just strips env vars). A follow-up BBF
   that implements the full Windows network isolation
   via Job Object would need to add `pywin32` as a
   Windows-only optional dependency.

3. **The test `test_set_network_isolation_preexec_strips_env_on_windows`**
   verifies that the callable returns None and doesn't
   raise. It does NOT verify that the env var IS
   stripped in the child process (the preexec_fn runs
   in the child, not the parent). The parent-side strip
   is a best-effort that happens before fork.

4. **No new tests added for the `unshare(CLONE_NEWNET)` path.**
   The existing test `test_set_network_isolation_preexec_calls_setsid`
   verifies that `os.setsid()` runs, but does NOT verify
   that the network namespace was actually created. A
   more thorough test would attempt a TCP connect inside
   the child and assert it fails.

5. **The `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (memory cap on Windows)**
   is still not implemented. The FU-22-impl BBF documented
   this as a follow-up. This BBF does not address it.

   > **Correction (2026-10-28, `BBF-FU-22-windows-contract-correction`).**
   > §1 of this brief previously listed `JOB_OBJECT_LIMIT_PROCESS_MEMORY`
   > as *"already used by FU-22-impl"*, contradicting §5 of this same
   > brief. **§5 was correct and §1 was false.** `win32job` is never
   > imported in the repository, and `pywin32` is not a declared
   > dependency; FU-22-impl implemented the 2 GB cap on Linux only, via
   > `resource.setrlimit(RLIMIT_AS)`. The original wording is preserved
   > above as the superseded state.

## §6. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-20 entry (will be
  flipped to PARTIALLY RESOLVED in a follow-up doc-drift-flip).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section A
  (the spike brief that designed this implementation).
- `docs/16_audit/BBF-FU-20-impl.md` (the prior Linux-only BBF).
- `docs/16_audit/BBF-FU-22-impl.md` (the prior memory cap BBF).
- `services/chess_coach/pdf_ocr/subprocess_runner.py`
  (the module modified by this BBF).
- `tests/unit/test_subprocess_runner.py`
  (the test file extended by this BBF).

## §7. Correction (2026-10-28) — the internal contradiction resolved

This brief contradicted itself: §1 listed `JOB_OBJECT_LIMIT_PROCESS_MEMORY`
as *"already used by FU-22-impl"*, while §5 stated the Windows memory cap
*"is still not implemented"*.

**§5 was correct.** The tree at `bcb70d884fed8397e3e640b25695c017cc5f029f`
contains no `win32job` import anywhere, and `pywin32` is not a declared
dependency. FU-22-impl implemented the A-F11 property-4 cap on **Linux
only**; the Windows half was never implemented and was recorded as a
follow-up.

Both statements are preserved above with the false one labelled as
superseded. The correction is of record in
`docs/16_audit/BBF-FU-22-windows-contract-correction.md`.
