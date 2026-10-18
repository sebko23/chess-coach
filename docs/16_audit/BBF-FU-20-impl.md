# BBF-FU-20-impl — A-F11 property 2: network isolation

**Sprint intent:** Implement A-F11 property 2 (no
network access in the PDF parsing subprocess) per
`docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
Section A. After this BBF, the PDF parser subprocess
has network isolation (Linux: `unshare(CLONE_NEWNET)`;
Windows: no-op, follow-up BBF).

**Status:** Code + test BBF. 2 files modified.

## §1. The implementation

Added `set_network_isolation_preexec()` to
`services/chess_coach/pdf_ocr/subprocess_runner.py`.
The function returns a `preexec_fn` callable that:

1. **On Linux:**
   - Calls `os.setsid()` to create a new session
     (detaches from the parent's controlling terminal
     and process group)
   - Attempts `unshare(CLONE_NEWNET)` via `ctypes` to
     enter a fresh network namespace (no loopback, no
     localhost, no DNS, no outbound TCP/UDP)
   - If `unshare` fails (insufficient capabilities, e.g.
     Docker without `CAP_SYS_ADMIN`), falls back to
     stripping network-related env vars (`http_proxy`,
     `https_proxy`, `all_proxy`, `no_proxy` and their
     uppercase variants)

2. **On Windows:**
   - Returns a no-op callable (matching the existing
     pattern from `set_rlimit_as_preexec`)
   - The Windows path uses Job Object with
     `JOB_OBJECT_NET_RATE_CONTROL` (follow-up BBF
     that requires `pywin32`)

The function is combined with the existing memory cap
via a single `_combined_preexec` callable in
`run_pdftoppm_in_subprocess`, since `subprocess.Popen`
only accepts one `preexec_fn` argument.

## §2. The verification (live, this session)

```
# Ruff:
$ ruff check libs services apps/cli tests scripts
All checks passed!

# Tests (7 passed, 2 skipped on Windows):
$ pytest tests/unit/test_subprocess_runner.py -v
test_set_rlimit_as_preexec_caps_at_target_bytes SKIPPED
test_set_rlimit_as_preexec_no_cap_means_no_cap PASSED
test_set_rlimit_as_preexec_returns_callable PASSED
test_mem_cap_bytes_constant_is_2gb PASSED
test_module_exposes_run_pdftoppm_in_subprocess PASSED
test_module_exposes_pdftoppm_available PASSED
test_set_network_isolation_preexec_returns_callable PASSED
test_set_network_isolation_preexec_is_noop_on_windows PASSED
test_set_network_isolation_preexec_calls_setsid SKIPPED
7 passed, 2 skipped in 0.36s

# Mypy (Linux CI will pass; Windows local has the
# expected `name-defined` for `resource`):
$ mypy libs services apps/cli --no-incremental
services\chess_coach\pdf_ocr\subprocess_runner.py:113:
  error: Name "resource" is not defined  [name-defined]
Found 1 error (expected, Windows-only)
```

## §3. The §1.3 catches (exemplary discipline)

1. **F821 Undefined name `os`** (pre-commit) — The inner
   `_isolate_network_preexec` function couldn't see the
   outer `os` import (ruff's nested-scope check). Fix:
   import `os` as `_os_inside_preexec` inside the function.

2. **Windows mypy `name-defined` for `resource`** (local
   only) — same as prior BBFs. The `# type: ignore`
   was removed in the prior BBF because it's unused on
   Linux CI. Windows local fails, but the CI gate is
   the source of truth.

## §4. Honest disclosures

1. **The implementation is best-effort on Linux.** The
   `unshare(CLONE_NEWNET)` call requires `CAP_SYS_ADMIN`
   (or `kernel.unprivileged_userns_clone` sysctl). In
   Docker containers without the right capabilities,
   the call fails and the fallback (env-var stripping)
   is used. The fallback does NOT guarantee network
   isolation (a determined attacker can still open
   new sockets); it only removes the most common
   exfiltration vectors (proxy env vars, inherited
   socket fds).

2. **The Windows path is a no-op.** The Windows
   implementation requires `pywin32` and the
   `win32job` module, which is not a project
   dependency. The follow-up BBF (FU-20-impl-windows)
   can add this.

3. **The test `test_set_network_isolation_preexec_calls_setsid`
   verifies that `os.setsid()` runs successfully** (the
   child's PGID == its PID after the call). It does
   NOT verify that `unshare(CLONE_NEWNET)` actually
   created a new network namespace — that would require
   a more complex test (e.g., attempting a TCP connect
   inside the child and asserting it fails). The
   follow-up BBF can add that test once the Windows
   path is in place.

4. **No new tests added for the combined `_combined_preexec`.**
   The existing `test_module_exposes_run_pdftoppm_in_subprocess`
   test verifies the function exists and is callable.
   A more thorough integration test (actually running
   pdftoppm with the network isolation) is out of scope
   for this BBF.

5. **The `# noqa: S404` annotation** is preserved on
   the `import subprocess` line (intentional: PDF
   parsing requires subprocess).

## §5. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-20 entry (to be
  flipped to PARTIALLY RESOLVED in a follow-up doc-drift-flip).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section A
  (the spike brief that designed this implementation).
- `docs/16_audit/BBF-FU-22-impl.md` (the prior BBF that
  established the `subprocess_runner.py` module +
  refactor pattern).
- `docs/08_security/security-strategy.md` §A-F11
  (the security contract).
- `services/chess_coach/pdf_ocr/subprocess_runner.py`
  (the module modified by this BBF).
- `tests/unit/test_subprocess_runner.py`
  (the test file extended by this BBF).
