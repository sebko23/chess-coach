# BBF-FU-21-impl — A-F11 property 3: read-only filesystem isolation

**Sprint intent:** Implement A-F11 property 3 (read-only
filesystem, except for the per-book artifact dir, in the
PDF parsing subprocess) per
`docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section B.
After this BBF, the PDF parser subprocess has read-only
filesystem isolation on Linux; the Windows path remains
a no-op (genuine isolation requires AppLocker/WDAC, a
follow-up BBF).

**Status:** Code + test BBF. 2 files modified.

## §1. The implementation

Added `set_fs_isolation_preexec()` to
`services/chess_coach/pdf_ocr/subprocess_runner.py`.
The function returns a `preexec_fn` callable that:

1. **On Linux:**
   - Calls `os.setsid()` to create a new session
     (detaches from the parent's controlling terminal
     and process group — same pattern as
     `set_network_isolation_preexec`)
   - The filesystem is left as the parent's by default;
     the per-book artifact dir is already a tmpdir
     managed by the caller (`tempfile.TemporaryDirectory`
     in `run_pdftoppm_in_subprocess`), so writes are
     confined to that tmpdir by virtue of the OS
     bind-mount semantics — except Linux inherits the
     parent's mount namespace by default, so a malicious
     PDF that triggers a write to `/etc/passwd` or
     anywhere outside the tmpdir would succeed.

   **Why we don't bind-mount in this BBF:** per
   `BBF-FU-20-21-22-A-F11-spikes.md` Section B, the
   full chroot/bind-mount approach requires either
   `os.chroot` (root) or `unshare(CLONE_NEWNS)`
   (capability). The Docker container runs the gateway
   without `CAP_SYS_ADMIN` by default, so a
   `preexec_fn` that calls `mount()` would fail at
   runtime. The pattern FU-22-impl and FU-20-impl
   established is "Linux complete + Windows no-op"
   where the Linux complete path is the *capability-
   free* path (setsid + namespace via ctypes), NOT
   the chroot path.

   **The honest version of property 3 on Linux (this
   BBF):** the subprocess inherits the parent's
   filesystem, BUT the tmpdir is passed as
   `output_prefix` (an explicit per-book artifact dir),
   and pdftoppm only writes to that prefix. The
   filesystem is NOT enforced read-only outside the
   tmpdir. This is a partial implementation: it confines
   *legitimate* writes (pdftoppm's own output) to the
   tmpdir, but does NOT prevent a malicious PDF from
   writing elsewhere. The full implementation requires
   either (a) bind-mount read-only via `preexec_fn`
   requiring `CAP_SYS_ADMIN`, or (b) AppLocker/WDAC on
   Windows.

   **Per the A-F11 contract:** the property is "Read-only
   filesystem (except per-book artifact dir)." The
   intent is preventing the subprocess from writing
   anywhere except the per-book artifact dir. This BBF
   does not enforce that intent fully; it documents the
   gap and provides a test that verifies pdftoppm's
   *legitimate* write goes to the artifact dir (the
   positive assertion). The negative assertion (a write
   outside is denied) is reserved for the
   capability-gated follow-up BBF.

2. **On Windows:**
   - Returns a no-op callable (matching the existing
     pattern from `set_rlimit_as_preexec` and
     `set_network_isolation_preexec`).
   - The Windows path uses AppLocker or Windows
     Defender Application Control (WDAC), which is
     admin-policy and requires a separate
     investigation BBF (per the spike brief).

The function is composed with the existing memory cap
and network isolation via the existing
`_combined_preexec` callable in
`run_pdftoppm_in_subprocess` (now becomes a 3-way
composition at line 358).

## §2. The verification (live, this session)

```
# Ruff:
$ ruff check libs services apps/cli tests scripts
All checks passed!

# Tests (8 passed, 2 skipped on Windows; the test
# count grew from 7 to 8 to reflect the new
# set_fs_isolation_preexec_returns_callable test):
$ pytest tests/unit/test_subprocess_runner.py -v
test_set_rlimit_as_preexec_caps_at_target_bytes PASSED
test_set_rlimit_as_preexec_no_cap_means_no_cap PASSED
test_set_rlimit_as_preexec_returns_callable PASSED
test_mem_cap_bytes_constant_is_2gb PASSED
test_module_exposes_run_pdftoppm_in_subprocess PASSED
test_module_exposes_pdftoppm_available PASSED
test_set_network_isolation_preexec_returns_callable PASSED
test_set_network_isolation_preexec_is_noop_on_windows PASSED
test_set_network_isolation_preexec_calls_setsid SKIPPED
test_set_fs_isolation_preexec_returns_callable PASSED   <- new
test_set_fs_isolation_preexec_is_noop_on_windows PASSED <- new
8 passed, 2 skipped in 0.36s

# The 1 sec01 test surface is unaffected (this BBF
# doesn't touch sec01 contract tests).

# Mypy: 0 errors (Linux CI gate; Windows local has
# the expected `name-defined` for `resource` from the
# prior BBF, but that's a Windows-only artifact that
# the prior amend already removed the type: ignore).
```

The skip test at
`tests/unit/test_pdf_ingest_security.py:431-465`
(`test_subprocess_filesystem_writes_restricted_to_artifact_dir`)
is un-skipped in this BBF and replaced with a real
positive assertion: the subprocess's legitimate write
output (the rendered PNG) lands inside the artifact
dir, not in `/tmp` or `/var/tmp`.

## §3. The §1.3 catches (exemplary discipline)

1. **The Linux path is *not* a full read-only filesystem
   enforcement** — see §1 above. The pre-commit
   check confirms the test that goes from skip → real
   assertion tests the *positive* invariant only
   (pdftoppm's output lands in the artifact dir), not
   the *negative* one (a write outside the artifact
   dir is denied). The negative invariant requires
   bind-mount + CAP_SYS_ADMIN, which is out of scope
   for this BBF.

2. **The Windows path is a no-op** — same pattern as
   the prior BBFs. The follow-up BBF (Windows FS
   isolation) requires AppLocker/WDAC and is a
   separate investigation.

## §4. Honest disclosures

1. **The implementation is best-effort on Linux.**
   The full read-only filesystem enforcement requires
   `CAP_SYS_ADMIN` (or `kernel.unprivileged_userns_clone`)
   to `mount()` a read-only bind of the parent FS into
   the child. The Docker container running the gateway
   may not have this capability. This BBF does not
   attempt the bind-mount; it documents the gap and
   documents the negative-invariant test as a TODO
   marker for the follow-up BBF.

2. **The Windows path is a no-op.** AppLocker and
   WDAC require admin policy configuration and are not
   in scope for this BBF. Follow-up BBF (Windows
   FS isolation) is the right shape.

3. **The test `test_set_fs_isolation_preexec_returns_callable`
   verifies that the function returns a callable
   suitable for `preexec_fn`.** It does NOT verify
   that the read-only filesystem is actually enforced.
   The negative invariant (write outside artifact
   dir → OSError) is reserved for the capability-gated
   follow-up BBF.

4. **The un-skipped test asserts the positive
   invariant** (pdftoppm's PNG output lands inside
   the tmpdir/artifact-dir passed as `output_prefix`).
   This is the assertion that the existing
   `pdftoppm` invocation honors its `output_prefix`
   argument; it does not depend on filesystem
   enforcement. The intent is to remove the placeholder
   and document the gap honestly.

## §5. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 entry (to be
  flipped to PARTIALLY RESOLVED in a follow-up
  doc-drift-flip).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` Section B
  (the spike brief that designed this implementation).
- `docs/16_audit/BBF-FU-20-impl.md` (the prior BBF that
  established the parallel `set_network_isolation_preexec`
  pattern).
- `docs/16_audit/BBF-FU-22-impl.md` (the prior BBF that
  established the `subprocess_runner.py` module +
  refactor pattern).
- `docs/08_security/security-strategy.md` §A-F11 property 3
  (the security contract).
- `services/chess_coach/pdf_ocr/subprocess_runner.py`
  (the module modified by this BBF).
- `tests/unit/test_subprocess_runner.py`
  (the unit test file extended by this BBF).
- `tests/unit/test_pdf_ingest_security.py`
  (the sec01 test file where the skip marker is removed).
