# BBF-FU20-network-skip-correction — correct the A-F11 property-2 skip and its FU references

**Sprint intent:** `tests/unit/test_pdf_ingest_security.py::test_subprocess_cannot_initiate_outbound_network`
carried a `pytest.mark.skip` whose reason was false on three separate counts, and the
corresponding FU-42 ledger rows pointed at the wrong follow-ups. This BBF corrects the
claims and closes the one genuinely untested part of A-F11 property 2: the **wiring** of
the isolation helper into the `preexec_fn` handed to `subprocess.Popen`.

This is the test-code follow-up recorded in `BBF-doc-drift-flip-9c.md` §5
("Recorded follow-up (deliberately outside this BBF)"), which shipped via PR #174
(squash `e08a4346`).

**Status:** Test-code + ledger BBF. 4 files (2 test files, 1 ledger, 1 new brief).

---

## §1. What was false

`test_subprocess_cannot_initiate_outbound_network`'s skip reason (pre-patch L392–403) made
three claims that the live implementation contradicts:

| Claim in the skip reason | Live reality |
|---|---|
| "is NOT enforced today" | Implemented 2026-10-18 by BBF-FU-20-impl (PRs #163/#164). `set_network_isolation_preexec()` exists at `services/chess_coach/pdf_ocr/subprocess_runner.py` L128. |
| "The pdf2image/Popen subprocess inherits the parent FastAPI process's full outbound network access" | False on Linux. The helper calls `os.setsid()` then `unshare(CLONE_NEWNET)` via ctypes (L206–242). The route no longer uses pdf2image at all — it calls `run_pdftoppm_in_subprocess`, which is exactly why `preexec_fn` is available. |
| "Tracked as FU-22 (A-F11 property 2 — network isolation)" | **Wrong FU.** Property 2 / network isolation is **FU-20** (entry: `PARTIALLY RESOLVED 2026-10-18`, PRs #163/#164). **FU-22** is property 4, the 2 GB memory cap (`RESOLVED 2026-10-16`, PR #145, squash `ae543ea8`). |

The FU mapping, verified against the live ledger:

- **FU-20** = A-F11 property 2 = network isolation
- **FU-21** = A-F11 property 3 = read-only filesystem
- **FU-22** = A-F11 property 4 = 2 GB memory cap

The skip body also said "This test is skip pending FU-22" and the placeholder comment said
"real assertion added when FU-22 lands" — the same error, twice more.

## §2. The real gap: wiring, not the helper

Before this BBF, `tests/unit/test_subprocess_runner.py` already covered the helper
itself:

| Existing test | Asserts | Platform |
|---|---|---|
| `test_set_network_isolation_preexec_returns_callable` | callable contract; does not raise | all |
| `test_set_network_isolation_preexec_strips_env_on_windows` | best-effort proxy strip | Windows-only |
| `test_set_network_isolation_preexec_calls_setsid` | forked child has PGID == PID | Linux (`skipif` win32) |
| `test_set_fs_isolation_preexec_performs_mount_on_linux_with_capability` | real fs isolation | Linux + capability |

`run_pdftoppm_in_subprocess` composes three pre-exec hooks into a single callable because
`subprocess.Popen` accepts only one `preexec_fn`:

```python
def _combined_preexec() -> None:
    set_rlimit_as_preexec(mem_cap_bytes)()
    set_network_isolation_preexec()()      # <-- line 602
    set_fs_isolation_preexec(tmpdir)()
```

**Nothing tested that composition.** `grep` for `_combined_preexec` found it only in the
implementation. A regression that deleted line 602 would disable A-F11 property 2 in
production while every existing test stayed green. That is the hole this BBF closes.

## §3. What this BBF changes

### `tests/unit/test_pdf_ingest_security.py`

1. **Corrected skip reason.** States accurately that property 2 is enforced on Linux
   (FU-20, PRs #163/#164) but not on Windows (best-effort proxy-env stripping, explicitly
   *not* a guarantee — the implementation's own comment at L182–183 says a determined
   attacker can still open raw sockets). Corrects FU-22 → FU-20 and names FU-22 as the
   memory cap resolved by PR #145.
2. **Corrected docstring.** Removes "This test is skip pending FU-22" and instead points at
   the three tests that *do* cover the property deterministically.
3. **Corrected the section-E header comment**, which repeated the same inverted FU mapping.
4. **New test `test_network_isolation_is_wired_into_the_popen_preexec`.** Replaces the
   `assert True` placeholder with a real, deterministic, cross-platform assertion:
   substitutes the three hook factories with recorders, substitutes `subprocess.Popen` with
   a fake that invokes `preexec_fn` inline (the real one runs it between fork and exec),
   calls `run_pdftoppm_in_subprocess`, and asserts the composition ran
   `["rlimit", "network", "fs"]` in order and that `Popen` received a callable
   `preexec_fn`.

### `tests/unit/test_subprocess_runner.py`

5. **New test `test_set_network_isolation_preexec_requests_unshare`** (Linux-gated). Mocks
   `ctypes.CDLL` / `ctypes.util.find_library` so the real syscall never runs, and asserts
   `unshare(0x40000000)` is **requested** exactly once. Deliberately does **not** assert the
   syscall succeeded: that needs CAP_SYS_ADMIN, which CI containers generally lack, and the
   implementation intentionally falls back to proxy-env stripping there.

### `docs/16_audit/OPEN-FOLLOWUPS.md`

6. **FU-42 test table, row 2**: `SKIP — pending FU-22` → `SKIP — capability-gated; FU-20
   implemented (PRs #163/#164), Windows is best-effort only`.
7. **FU-42 test table, row 4**: `SKIP — pending FU-20` → `PASS — FU-22-impl, PR #145`. This
   row was wrong twice over: the test passes today (verified), and FU-20 is network
   isolation, not the memory cap.
8. **The prose under the table**, which said "Tests 2-4 use `pytest.skip`" — now accurate:
   tests 2 and 3 skip, test 4 runs.

---

## §4. What this BBF does NOT do

- **Does not unskip `test_subprocess_cannot_initiate_outbound_network`.** The only
  end-to-end formulation ("open a socket in the child, observe denial") is
  capability-dependent on Linux and impossible on Windows. Unskipping would make CI flaky.
- **Does not assert `unshare` succeeded**, nor that egress is actually denied. That is
  FU-20's own out-of-scope note (2): "Verification that `unshare(CLONE_NEWNET)` actually
  creates a new network namespace (the existing test only verifies `os.setsid()` runs)."
- **Does not touch the filesystem skip** (L449), which is correctly capability-gated.
- **Does not modify the memory test body**, which works as-is.
- **Does not claim Windows network isolation.** The Windows path remains proxy-env
  stripping, a defense-in-depth measure.
- **Does not modify `subprocess_runner.py`** — this is a test-only correction of claims
  about it.

---

## §5. Verification (live, this session)

- Focused suite before: `uv run pytest tests/unit/test_pdf_ingest_security.py tests/unit/test_subprocess_runner.py -q` → **19 passed, 7 skipped**.
- Focused suite after: same command → **20 passed, 8 skipped**. Net +1 passing (the new wiring test) and +1 skip (the new Linux-only `unshare` test, correctly gated off on Windows).
- **Mutation test (the wiring test is load-bearing):** temporarily replaced
  `set_network_isolation_preexec()()` at `subprocess_runner.py` L602 with `pass`, re-ran
  the wiring test → **FAILED** with `observed: ['rlimit', 'fs']`. Source restored and verified
  byte-identical.
- **Mock-mechanism probe** for the `unshare` test: `ctypes.CDLL` interception records
  `0x40000000` and satisfies the `calls == [CLONE_NEWNET]` assertion. The full test cannot
  execute on this Windows host (`os.fork` absent, `resource` module absent), which is
  exactly why it is `skipif`-gated to Linux; CI on Linux exercises it.
- **Defect found and fixed during implementation:** the first version of the mock used a bare
  `lambda` for `libc.unshare`. The implementation assigns `.argtypes` and `.restype` before
  calling, which a lambda cannot accept (`AttributeError`). Replaced with a `_FakeUnshare`
  class exposing settable `argtypes` / `restype`.
- **Defect found and fixed during implementation:** the first version of the wiring test did
  not invoke `preexec_fn` inside the fake `Popen`, so `calls` stayed empty. The real
  `Popen` runs the hook between fork and exec; the fake now does the same inline.

---

## §6. Platform matrix

| Test | Linux CI | Windows | macOS |
|---|---|---|---|
| `test_network_isolation_is_wired_into_the_popen_preexec` | passes | passes | passes |
| `test_set_network_isolation_preexec_requests_unshare` | passes | skipped (`skipif`) | passes |
| `test_subprocess_cannot_initiate_outbound_network` | skipped (capability) | skipped (capability) | skipped (capability) |

No test added here depends on `CAP_SYS_ADMIN`, on network reachability, on a `pdftoppm`
binary, or on timing.

---

## §7. Cross-references

- `services/chess_coach/pdf_ocr/subprocess_runner.py` L128 (`set_network_isolation_preexec`), L182–183 (the implementation's own "NOT a guarantee" caveat), L206–242 (Linux `setsid` + `unshare`), L600–604 (`_combined_preexec`), L615 (`preexec_fn=` passed to `Popen`).
- `tests/unit/test_pdf_ingest_security.py` — section E header comment, the network skip, and the new wiring test.
- `tests/unit/test_subprocess_runner.py` — the three pre-existing network tests and the new `unshare`-request test.
- `docs/16_audit/OPEN-FOLLOWUPS.md` — FU-20 (network isolation), FU-21 (filesystem), FU-22 (memory cap), FU-42 (this table).
- `docs/16_audit/BBF-doc-drift-flip-9c.md` §5 — the follow-up this BBF discharges.
- PR #174, squash `e08a4346` — where the follow-up was recorded.

---

## §8. Pre-leaf-review checklist

1. **Numstat:** `git diff --numstat origin/main..HEAD` — read it live; do not assume.
2. **No implementation change:** `services/` must not appear in the diff.
3. **FU accuracy:** every FU reference in the changed regions must be network = FU-20,
   filesystem = FU-21, memory = FU-22.
4. **No false Windows claim:** the corrected skip must state that Windows is best-effort
   proxy-env stripping, not isolation.
5. **No capability dependency:** no new assertion may require CAP_SYS_ADMIN, network, or
   `pdftoppm`.
6. **Wiring test is load-bearing:** confirm the mutation experiment in §5 (dropping the
   network hook must fail the test).
7. **Filesystem skip untouched** and still capability-gated.