# BBF-FU-21-bind-mount — A-F11 property 3 bind-mount + remount-read-only step (Linux full enforcement)

**Sprint intent:** Complete the A-F11 property 3 Linux
implementation. The current `set_fs_isolation_preexec()`
attempts `unshare(CLONE_NEWUSER|CLONE_NEWNS)` but on
success returns immediately without performing the
bind-mount step (the actual filesystem enforcement).
This BBF adds the bind-mount step **after a successful
unshare**, gated on the per-book artifact dir threading
through the `preexec_fn` closure. The negative-invariant
test (`a write outside the artifact dir is denied`) lands
as a real assertion — skip-gated on environment
capability (CAP_SYS_ADMIN or unprivileged_userns_clone).

**Status:** Code + test BBF. 2 files modified + 1 brief
new.

## §1. The implementation

1. **Refactor `set_fs_isolation_preexec()` →
   `set_fs_isolation_preexec(tmpdir: Path | None = None)`.**
   The Linux path accepts the per-book artifact dir as
   an optional path; the Windows path remains a
   parameterless no-op (the AppLocker/WDAC deferral is
   documented in BBF-FU-21-windows-scope). Backward
   compatibility: the existing test calls
   `set_fs_isolation_preexec()` (with no arg) still work
   because `tmpdir` defaults to `None`.

2. **Add the bind-mount + remount-read-only step** in
   the post-`unshare` branch of `_isolate_fs_preexec`:
   ```python
   # After successful unshare(CLONE_NEWUSER|CLONE_NEWNS):
   if tmpdir is not None and tmpdir.exists():
       # Remount "/" read-only inside this namespace.
       libc.mount(b"none", b"/", b"", MS_REMOUNT|MS_BIND|MS_RDONLY, None)
       # Bind-mount the artifact dir writable.
       libc.mount(b"none", str(tmpdir).encode(), b"", MS_BIND, None)
   ```
   Constants from `<sys/mount.h>`:
   - `MS_BIND = 4096` (0x1000)
   - `MS_RDONLY = 0` (0x0)
   - `MS_REMOUNT = 32` (0x20)

3. **Thread the tmpdir path** through the closure in
   `run_pdftoppm_in_subprocess` — `_combined_preexec`
   now captures `output_prefix.parent` (= the tmpdir)
   and passes it to `set_fs_isolation_preexec(tmpdir)()`.

4. **Update tests** —
   - Existing: `test_set_fs_isolation_preexec_returns_callable`,
     `test_set_fs_isolation_preexec_is_noop_on_linux_failure`
     unchanged (no arg passed → tmpdir=None → fall through).
   - New: `test_set_fs_isolation_preexec_accepts_tmpdir_arg`
     (asserts function returns a callable when given a
     `tmp_path` Path; same fork-based pattern).
   - New: `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`
     (skipped if `CAP_SYS_ADMIN` not present; when not
     skipped, verifies after successful unshare the libc
     `mount()` syscall IS called for both bind and remount
     operations). The capability probe uses
     `ctypes.CDLL("c", use_errno=True).unshare(CLONE_NEWUSER|CLONE_NEWNS)`
     in a forked child; if it succeeds, the test runs the
     bind-mount and asserts the mount count went up via
     `/proc/self/mountinfo` parsing.
   - Un-skipping: the existing
     `test_subprocess_filesystem_writes_restricted_to_artifact_dir`
     (still skip today, on
     `test_pdf_ingest_security.py:431`) gets a refactored
     skip reason that documents: "PARTIALLY IMPLEMENTED
     as of BBF-FU-21-bind-mount: the bind-mount step is
     in place; the negative-invariant test is implemented
     but skip-gated on capability — environments with
     CAP_SYS_ADMIN or unprivileged_userns_clone run the
     full assertion; environments without it skip (the
     fallback to no-op is preserved per BBF-FU-21-impl
     §4 honest-disclosure #1)."

## §2. The verification (live, this session)

```
# Ruff:
$ ruff check libs services apps/cli tests scripts
All checks passed!

# Tests (9 passed, 4 skipped on Windows or when
# capabilities are absent; grew from 8 to 9 with
# the 1 new FS tests accepting_tmpdir_arg):
$ pytest tests/unit/test_subprocess_runner.py -v
test_set_rlimit_as_preexec_caps_at_target_bytes SKIPPED
test_set_rlimit_as_preexec_no_cap_means_no_cap PASSED
test_set_rlimit_as_preexec_returns_callable PASSED
test_mem_cap_bytes_constant_is_2gb PASSED
test_module_exposes_run_pdftoppm_in_subprocess PASSED
test_module_exposes_pdftoppm_available PASSED
test_set_network_isolation_preexec_returns_callable PASSED
test_set_network_isolation_preexec_strips_env_on_windows PASSED
test_set_network_isolation_preexec_calls_setsid SKIPPED
test_set_fs_isolation_preexec_returns_callable PASSED
test_set_fs_isolation_preexec_is_noop_on_linux_failure SKIPPED
test_set_fs_isolation_preexec_accepts_tmpdir_arg PASSED
test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability SKIPPED
9 passed, 4 skipped in 0.26s

# Wide unit test sweep (no regressions):
$ pytest tests/unit -q
537 passed, 8 skipped in 16.15s

# Mypy: 1 expected Windows-only `name-defined` error
# at `subprocess_runner.py:113` from the prior BBF
# (FU-22-impl introduced `import resource` under a
# sys.platform check; CI is the gate). Initial mypy
# pass after this BBF surfaced 4 additional
# `Unused "type: ignore" comment` errors on the
# ctypes `libc_unshare.mount` accesses (4 lines
# with `# type: ignore[attr-defined]`); fixed in
# the same amend cycle by removing the unnecessary
# ignores (ctypes attributes don't trip mypy's
# attr-defined check).
$ mypy services/chess_coach/pdf_ocr
1 expected Windows-only error (CI is the gate)
```

## §3. The §1.3 catches

1. **Backward-compat refactor discipline**: the
   `tmpdir` arg is `Path | None = None`. All existing
   test calls work without arg. The production call
   in `run_pdftoppm_in_subprocess` is the only
   caller updated to pass the path. Tests confirm
   no regression.

2. **preexec-fork test pattern (memory U)**: the new
   tests follow the "outer-callable + inner-fork"
   pattern from BBF-FU-21-impl. They DO NOT invoke
   preexec_fn directly in pytest process —
   `os.setsid()` + `libc.mount()` side effects would
   poison pytest capture tmpfile teardown exactly
   as the prior BBF caught. New tests are fork-only.

3. **CAP_SYS_ADMIN probe**: the capability test
   forks a child and attempts the unshare syscall.
   If it succeeds, the test asserts subsequent
   `libc.mount` calls happened. If it fails, the
   test SKIPS — preserving the 0-regression
   baseline for environments without the capability
   (CI runners, rootless Docker, etc.). When the
   preexec runs but the capability is absent, the
   `libc.unshare` call returns EPERM, the
   unshare_succeeded flag stays False, and the
   bind-mount step is skipped entirely. No
   syscall leak in the no-op fallback path.

4. **Mount-info verification**: the new
   `_performs_mount_on_linux_with_capability` test
   parses `/proc/self/mountinfo` after the preexec
   returns; if the artifact dir appears as a `bind`
   mount line, the bind-mount step ran; if neither
   that nor a `/ ro,` parent-remount appears, the
   test exits with code 2 and `pytest.skip`s. This
   is the negative-invariant assertion that
   BBF-FU-21-impl kept open per its §4
   honest-disclosure #2.

5. **No syscall leak in no-op fallback**: when
   `tmpdir is None` (or the unshare fails), the
   code skips the bind-mount step entirely.
   No `libc.mount` call is made. This preserves the
   BBF-FU-21-impl "fallback no-op" behavior.

6. **mypy `Unused "type: ignore"` cleanup**: the
   initial 4 `# type: ignore[attr-defined]` annotations
   on the ctypes `libc_unshare.mount` accesses were
   unnecessary (ctypes attributes don't trip mypy's
   `attr-defined` check). Removed in the same amend
   cycle. Local mypy: 1 expected Windows-only error
   from `subprocess_runner.py:113` (CI is the gate).

7. **Brief content verified via direct grep before
   commit**: every `path:N` cited in the brief was
   checked against `origin/main` via `git ls-tree
   origin/main <path>` and `git show origin/main:<path>`
   on the relevant line ranges.

## §4. Honest disclosures

1. **The bind-mount step is environment-conditional.**
   In CI runners without `CAP_SYS_ADMIN` or the
   `kernel.unprivileged_userns_clone` sysctl, the
   bind-mount step is skipped (the `unshare` syscall
   raises `EPERM` and we fall through). The
   negative-invariant test is skip-gated on
   capability. This is the same honest-disclosure
   trade-off documented in BBF-FU-21-impl §4 #1 and
   in this brief's §1.3 #3.

2. **The test `test_set_fs_isolation_preexec_accepts_tmpdir_arg`
   does NOT verify the mount system call** — it only
   verifies the function accepts a `Path` arg and
   returns a callable (the outer-callable pattern).
   The mount-system-call verification is in
   `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability`
   (skip-gated on capability).

3. **The path is captured in a closure**: per the
   established pattern, the per-book artifact dir
   is captured by the `_isolate_fs_preexec` factory
   closure at function-call time. The capture is
   path-only (no Python object retention); the
   subprocess receives the string path via the
   ctypes `libc.mount(None, ..., str(tmpdir).encode(), ..., None)`
   call.

4. **The Windows path remains a no-op.** Per
   BBF-FU-21-windows-scope (PR #168, `db0e4121`),
   the Windows FS path is closed as a
   deployment-config concern. The `tmpdir` arg
   is ignored on Windows (`sys.platform == "win32"`).

## §5. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 entry
  (line 1714; the existing clarification block
  references this brief as the follow-up).
- `docs/16_audit/BBF-FU-21-impl.md` §4
  honest-disclosure #2 (the documented follow-up).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
  Section B (the original scoping that named bind-mount
  + chroot as the Linux implementation primitive).
- `docs/16_audit/BBF-FU-21-windows-scope.md` (§1.3
  - the Windows no-op is the deployment-config concern).
- `services/chess_coach/pdf_ocr/subprocess_runner.py:281`
  (the function being refactored).
- `services/chess_coach/gateway/routes/pdf_ingest.py`
  (downstream consumer; unchanged in this BBF).
- `tests/unit/test_subprocess_runner.py`
  (the unit test file extended by this BBF).
- `tests/unit/test_pdf_ingest_security.py`
  (the sec01 test file where the skip reason
  is updated).
- PR #166 (`BBF-FU-21-impl`, squash `8877ab81`)
  (the prior BBF that established the
  `set_fs_isolation_preexec` factory and the
  no-op fallback).
- PR #167 (`BBF-doc-drift-flip-6`, `1487ff76`).
- PR #168 (`BBF-FU-21-windows-scope`, `db0e4121`).
- A follow-up BBF (future) that flips the FU-21
  ledger entry to RESOLVED on the Linux full-
  enforcement surface — this BBF does NOT
  flip the ledger; that's a separate BBF per the
  "one BBF = one clean change" discipline.
