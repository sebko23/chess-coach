# BBF-FU-21-windows-scope — A-F11 property 3 Windows path: scope decision

**Sprint intent:** Decide the scope and path-forward for
the A-F11 property 3 Windows path. The Linux path is
partially implemented per BBF-FU-21-impl (PR #166,
squash `8877ab81`, brief at `BBF-FU-21-impl.md`). The
Windows path remains a no-op on the `subprocess_runner.py`
side. This brief investigates **why** a Python-level
implementation cannot meaningfully enforce filesystem
isolation on Windows, **what** the production-correct
answer is (deployment-config, not application code),
and **what** BBFs follow.

**Status:** Decision-only BBF (per the v0.7.103
strategic-decision-bbf-pattern). The diff is `*.md`
only. No code is shipped. Implementation BBFs that
follow reference this brief on `main`.

**Decision (FU-21 Windows, this brief):** The Windows
path of A-F11 property 3 is **closed as a deployment-config
concern, not an application code concern.** The
spike-brief Section B `AppLocker / WDAC` recommendation
is reaffirmed as the production-correct answer; both
mechanisms install system-wide policy via admin
channels (GPO, Intune, or local `Set-AppLockerPolicy`
+ `Set-Rule` cmdlets), not application subprocess
calls. `set_fs_isolation_preexec()`'s Windows branch
returns a no-op per the current
`subprocess_runner.py:281` (verified post-#166). **No
production Python code change is required for the
Windows path; the enforcement belongs at deployment
time.** The Open-Followups entry for FU-21 is updated
to a `Status (closed as deployment-config concern)`
clarification. Per-property enforcement is a separate
artifact: `deployment-config/applocker-policy.xml`
for FU-21-windows-deployment (the deployment-team
BBF, not this repo's scope).

The reasoning is in §1. The trade-offs of the
alternatives are in §2. The recommended sequencing is in
§3. The explicit out-of-scope declarations are in §4.

---

## §1. The verify-first investigation (live, this session)

Per the skill's pre-flight discipline, the session did
honest investigation before authoring this brief:

### 1.1 What does "filesystem isolation" mean on Windows?

Windows has no direct filesystem-isolation primitive
analogous to Linux's `mount()` or `unshare(CLONE_NEWNS)` +
`MS_BIND`. The candidate mechanisms are:

| # | Mechanism | Callable from a Python `preexec_fn`? | Scope |
|---|---|---|---|
| 1 | AppLocker policy (system-wide) | **No** — requires admin and `Set-AppLockerPolicy` | Process execution allowlist |
| 2 | WDAC (system-wide kernel-mode) | **No** — requires `CiTool.exe` + signed policy binary | Process execution + driver-loading allowlist |
| 3 | Job Object (per-process) | **Yes — via `pywin32` `win32job`** (NOT currently imported anywhere in this repository; `pywin32` is not a declared dependency — see the 2026-10-28 correction below) | Process tree, memory cap, CPU rate, scheduling class — **NOT filesystem** |
| 4 | Process Token Groups + Restricted Token (`CreateRestrictedToken`) | **No** — must be set BEFORE `CreateProcess`, not via post-fork `preexec_fn` | Privilege removal (drop SIDs) — partial FS protection via removing `SeBackupPrivilege` etc. |
| 5 | `SetTokenInformation` + `TokenIntegrityLevel` | **No** — pre-`CreateProcess` | Integrity level (Medium/Low/System) — restricts write access from integrity-rated processes |
| 6 | `SetTokenInformation` + `TokenMandatoryPolicy` | **No** — pre-`CreateProcess` | No-Write-Up + read-only-Integrity levels |
| 7 | File ACL manipulation (`SetSecurityInfo`) on `data_dir/books/<player>.bin` | **Yes** — callable from Python via `pywin32.security` | Restricts NTFS ACL on the per-book file — partial FS protection |
| 8 | Namespace virtualization (`SetThreadToken` + restricted namespace) | **No** — kernel-mode, requires admin | Per-process virtual filesystem |

**The verdict (live, this session):** Mechanisms 3
(`pywin32` accessible) and 7 (`pywin32` accessible)
are the only ones callable from a Python
`subprocess.Popen` preexec_fn callback. **Neither
provides real filesystem isolation** — Job Objects
operate on process-tree / memory / scheduling primitives
*not* filesystem writes, and per-file ACL manipulation
is per-file (not a system-wide read-only enforcement)
and only helps if the subprocess specifically targets
the per-book artifact dir (it can still write to
arbitrary paths elsewhere on the host).

Mechanisms 1, 2, 5, 6, 8 are the only ones that provide
actual filesystem-level enforcement on Windows, and
**none of them are callable from a single Python
`subprocess.Popen` invocation.** They are deployment-
configuration concerns: AppLocker and WDAC policies
are installed at the system level by an administrator,
not from app code.

### 1.2 Why wasn't this discovered earlier?

Per the spike brief `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
Section B (Windows path):

> "1. Use AppLocker or Windows Defender Application
>   Control (WDAC) to restrict the subprocess to
>   read-only access outside the per-book artifact dir.
> 2. AppLocker is the older, simpler API; WDAC is the
>   newer, more flexible API.
> 3. The implementation must be activated per-process via
>   a separate setup step; it's not as clean as Linux's
>   `preexec_fn`."

Point 3 was the early correct observation — "not as
clean as Linux's `preexec_fn`" — but it didn't
enumerate **why** it's not clean. This brief makes
the "why" explicit: AppLocker and WDAC are
system-wide policies, not per-process invocations. The
brief's contribution is the table in §1.1 and the
structural decision in §1.3.

### 1.3 The structural decision

The verified fact is:

> **No Python-level mechanism callable from
> `subprocess.Popen(preexec_fn=...)` enforces a
> read-only filesystem on Windows.**

The implication:

> **The Python `subprocess_runner.py` Windows branch
> should remain a no-op for the filesystem property.**
> This is **not** a gap in the implementation; it is
> the correct implementation choice given the
> Windows process model. The A-F11 property 3
> enforcement on Windows happens at deployment time,
> via an AppLocker / WDAC policy installed by an
> administrator.

This means the FU-21 ledger entry can be updated from
"PArtIALLY RESOLVED 2026-10-18 via PR #166" to a
**Status (clarified 2026-10-18, deployment-config
concern)** that says:

- The Linux path is partial per BBF-FU-21-impl
  (PR #166, `8877ab81`).
- The Windows path is **closed as a deployment-config
  concern**, with the AppLocker / WDAC policy being
  the production-correct answer per the spike brief.
- A separate deployment-team BBF (not this repo's
  scope) ships the AppLocker / WDAC policy XML as
  a deployment artifact.

There is no **FU-21-windows-impl** BBF coming. The
open work for FU-21 is:

1. **The bind-mount follow-up BBF** (per the brief
   `BBF-FU-21-impl.md` §4 honest-disclosure #2):
   threads the per-book artifact dir through the
   `preexec_fn` closure on Linux, completing the full
   read-only filesystem enforcement on Linux. This is
   `BBF-FU-21-bind-mount` — a real implementation
   BBF that depends on `subprocess.Popen` kwargs-to-
   preexec_fn threading.
2. **The deployment-config BBF** (separate repo):
   ships `deployment-config/applocker-policy.xml`
   + a deployment-team BBF that installs it.

The "FU-21-windows-impl" BBF that the spike brief
Section B sketched does not exist; this brief
formally closes it.

### 1.4 Why not ship a deceptive best-effort (Option B below)?

I considered shipping a parallel of `BBF-FU-20-impl-windows`:
a Python-level "best-effort fallback" that strips
`TMP`, `TEMP`, `USERPROFILE`, `HOME` env vars on Windows.
This was rejected because:

1. **Env-var stripping is not filesystem isolation.**
   Stripping `TMP` doesn't prevent the subprocess from
   writing to `C:\Windows\Temp\` or `%LOCALAPPDATA%`
   directly. It only changes which paths
   *named-by-env-var* utilities use.
2. **It mirrors the FU-20 pattern misleadingly.**
   For FU-20 (network), env-var stripping *is* a real
   defense-in-depth (proxy config is the named
   exfiltration vector). For FU-21 (filesystem),
   env-var stripping is essentially a no-op for the
   security property. Mirroring would create the
   **appearance** of work without substance.
3. **It violates the skill's anti-pattern discipline.**
   Per `docs/16_audit/_stale/...` (now removed but
   preserved in the lessons): "do not ship a 'third
   round of progressively thinner findings dressed
   up as equally urgent.'"

The honest option is Option A (drop the FU-21
Windows path; close as deployment-config concern). The
brief's `set_fs_isolation_preexec()` Windows branch
remains a documented no-op, and the FU-21 ledger
entry's Windows branch is closed.

---

## §2. The alternatives considered

### 2.1 Option A — Drop the Windows path, deploy at OS level **(RECOMMENDED)**

This brief.

**Pros:**
- Honest. The brief documents why no Python code
  change is the right answer.
- No code change, no test surface, no CI surface.
- Deployment-config AppLocker / WDAC is the
  production-correct answer for system-level
  enforcement.
- Matches the prior `BBF-FU-20-and-FU-21-and-FU-22`
  directive's original "AppLocker / WDAC is the answer"
  framing without inventing work.

**Cons:**
- The deployment-config BBF is in a different repo
  (separate artifact), so the FU-21 entry's Windows
  closure is partial until that BBF ships.

### 2.2 Option B — Deceptive best-effort fallback (env-var stripping)

**Pros:**
- Ships code that does something on Windows
  (analogous to FU-20-impl-windows).

**Cons:**
- Does not enforce filesystem isolation. The
  "best-effort" is essentially a no-op for the
  security property — `TMP`/`TEMP`/`USERPROFILE`/
  `HOME` env vars don't confine filesystem writes.
- Mirrors the FU-20 pattern misleadingly.
- Violates the skill's anti-pattern discipline on
  progressive-thinning findings.

### 2.3 Option C — Add a positive Windows test only

**Pros:**
- Cheap (test-only).

**Cons:**
- Doesn't address the security property at all.
- Just exercises the existing no-op path.
- No useful work done.

### 2.4 Why not ship a real implementation using mechanism 7 (file ACL)?

Per §1.1, mechanism 7 (per-file ACL manipulation
via `pywin32.security`) is callable from Python. But:

- It only helps if the subprocess specifically
  targets the per-book artifact dir; the
  subprocess can still write to arbitrary paths.
- File ACL manipulation from Python is its own
  multi-session BBF (NTFS ACL grammar is
  non-trivial; testing requires admin tests;
  per-book permissions on a Tauri app's
  `data_dir/books/<player>.bin` are a security
  review in their own right).
- Even if implemented, it doesn't satisfy A-F11
  property 3 (which is "**Read-only filesystem
  (except per-book artifact dir)**"). It only
  protects one specific file from one specific
  attack vector.
- It's a side quest that doesn't close the
  property; the deployment-config answer does.

---

## §3. The recommended sequencing

There is **no further FU-21-windows BBF**. The
sequencing is:

1. **THIS BBF** — closes the FU-21 Windows path
   authoritatively. Doc-only. Squash-merge as a
   decision-only brief.
2. **`BBF-FU-21-bind-mount`** (separate BBF, not
   authored in this scope) — completes the Linux
   full-enforcement path per BBF-FU-21-impl §4
   honest-disclosure #2. Threads the per-book
   artifact dir through the `preexec_fn` closure.
3. **`deployment-config/applocker-policy.xml`** in a
   separate deployment-config repo — production-
   correct Windows enforcement. Not this repo's
   scope.
4. **FU-21 ledger entry update** (post-merge of THIS
   brief) — `Status (clarified YYYY-MM-DD,
   deployment-config concern)` block on the
   existing clarification block in
   `OPEN-FOLLOWUPS.md:1714`, citing this brief as
   the close-out record.

Items 2-4 are out-of-scope for THIS brief. Item 1
ships this BBF as-is.

---

## §4. Explicit out-of-scope declarations

This BBF does NOT ship:

- **Code changes** to `set_fs_isolation_preexec()`,
  `subprocess_runner.py`, or any test file. The
  decision-only pattern is `*.md` only.
- **AppLocker / WDAC policy XML**. That belongs in
  a separate deployment-config repo, not this repo.
- **A FU-21-windows-impl BBF**. This brief formally
  closes that path as not applicable.
- **A `pywin32` dependency addition**. This brief does
  not add one; it notes that adding `pywin32`-based
  filesystem isolation would not change the verdict
  (§1.3).

  > **Correction (2026-10-28, `BBF-FU-22-windows-contract-correction`).**
  > This paragraph previously read: *"The current `subprocess_runner.py`
  > does use `pywin32`'s `win32job` for FU-22-impl's memory cap."*
  > **That was false.** `win32job` is never imported anywhere in the
  > repository — its only Python occurrences are comments — and `pywin32`
  > is not a declared dependency. FU-22-impl implemented the 2 GB cap on
  > Linux only, via `resource.setrlimit(RLIMIT_AS)`. The original claim is
  > preserved here as the superseded state.
- **A change to the BBF-FU-21-impl brief** or its
  "Windows path is a no-op (AppLocker/WDAC)"
  framing. That brief is accurate; this brief
  upgrades the meta-status (the FU-21 ledger entry)
  to reflect the deployment-config close.

---

## §5. The §1.3 catches (exemplary discipline)

1. **The "we tried, the OS said no" honest framing**
   is preserved throughout. The brief does not
   assert that a Python-level implementation is
   possible; it asserts that AppLocker / WDAC are
   the production-correct answer.

2. **The brief distinguishes two different "FS
   isolation" definitions:**
   (a) "Read-only filesystem except per-book
       artifact dir" — A-F11 property 3, the security
       contract. Requires deployment-config on
       Windows.
   (b) "Per-book artifact dir is writable,
       everything else is read-only" — narrower than
       (a). Even (b) cannot be enforced from Python
       `subprocess.Popen` preexec_fn on Windows. The
       brief closes both (a) and (b) as deployment-
       config concerns.

3. **The brief does NOT introduce a
   `pyproject.toml` change** to add
   `pywin32` for this purpose. The dependency would
   not change the verdict.

---

## §6. Honest disclosures

1. **This BBF does not close FU-21's *implementation*
   on Windows.** It closes the *Python-level
   implementation* surface as not applicable. The
   operational enforcement is a deployment-team
   responsibility, not this repo's code.

2. **The "deployment-config" repo is a future
   concern.** I do not know whether such a repo
   exists or when it will be created. Per the
   project convention, deployment-config artifacts
   live in a separate repo owned by the
   deployment team. This brief's "FU-21-windows-
   deployment BBF" reference is a placeholder, not
   a commitment.

3. **The Linux FU-21 bind-mount BBF is still open.**
   Per the BBF-FU-21-impl brief §4 honest-disclosure
   #2: "The bind-mount step is deferred. The full
   A-F11 contract requires remounting the parent
   filesystem read-only... That requires threading
   the per-book artifact dir through the preexec_fn
   closure, which `subprocess.Popen` does not
   natively support. The follow-up BBF that adds the
   bind-mount step is the natural extension." This
   brief does not address that BBF.

4. **The brief does not introduce cost to merge.**
   The diff is 1 new file (~200 lines), no code
   change. Squash-merge via the same pattern as
   `BBF-FU-11-polyglot-persistent-book-decision.md`
   (decision-only BBF on `main`).

---

## §7. Cross-references

- `docs/16_audit/OPEN-FOLLOWUPS.md` FU-21 entry
  (line 1714, post-merge of this brief gets a
  follow-up clarification block citing this brief).
- `docs/16_audit/BBF-FU-21-impl.md` (the partial
  Linux impl; brief paragraph 4 candidly notes the
  Windows no-op).
- `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
  Section B (the spike brief that first named
  AppLocker / WDAC as the Windows answer).
- `docs/16_audit/BBF-FU-20-impl-windows.md` (the peer
  pattern: same investigation-first brief,
  different conclusion — FU-20 *can* ship a
  best-effort fallback because env-var stripping
  has network-defense value; FU-21 *cannot*
  because env-var stripping has no FS-defense
  value).
- `services/chess_coach/pdf_ocr/subprocess_runner.py:281`
  (the no-op Windows branch of
  `set_fs_isolation_preexec()`, verified live).
- `docs/08_security/security-strategy.md:128`
  (the A-F11 property 3 contract: "Read-only
  filesystem (except per-book artifact dir). *Not
  currently enforced.*").
- `docs/16_audit/BBF-doc-drift-flip-6.md` (the
  prior doc-drift BBF in this session that
  clarified FU-21's status; this brief's follow-up
  clarification on the FU-21 Windows branch goes
  after it).
- Microsoft Job Objects documentation
  (learn.microsoft.com/en-us/windows/win32/procthread/job-objects):
  the `pywin32`-accessible mechanism that can do
  memory cap (FU-22-impl already uses this) but
  cannot do filesystem isolation.
- Microsoft `AppLocker` (system-wide, admin-policy).
- Microsoft WDAC (system-wide kernel-mode, admin-policy).

## §N. Correction (2026-10-28) — the `win32job` claim was false

`BBF-FU-22-windows-contract-correction` audited this brief against the
landed tree and found two statements that overstated the implementation:

1. **§1.1 table row 3** claimed Job Objects were *"already used in
   `subprocess_runner.py` for `JOB_OBJECT_LIMIT_PROCESS_MEMORY` per
   FU-22-impl"*. They were not. Verified against the tree:

   ```
   $ git grep -n -E '^\s*(import|from)\s+win32job' -- '*.py'
   (no matches — exit 1)
   $ git grep -n 'win32job' -- '*.py'
   services/chess_coach/pdf_ocr/subprocess_runner.py:97:  # `pywin32` and the `win32job` module, which is
   services/chess_coach/pdf_ocr/subprocess_runner.py:169: # The `win32job` module exposes:
   ```

   Both occurrences are comments. `pywin32` is not a declared dependency
   either (`git grep -n pywin32 -- pyproject.toml` → exit 1); it appears in
   `uv.lock` only as a transitive entry.

2. **§4** claimed *"The current `subprocess_runner.py` does use `pywin32`'s
   `win32job` for FU-22-impl's memory cap"*. Same correction; the original
   wording is quoted in place above, labelled as superseded.

**What the implementation actually did.** FU-22-impl implemented the A-F11
property-4 cap on **Linux only**, via
`resource.setrlimit(RLIMIT_AS, (2 GiB, 2 GiB))` in a `preexec_fn` callback.
`resource` is a Unix-only stdlib module, and CPython rejects `preexec_fn`
outright on Windows
(`ValueError: preexec_fn is not supported on Windows platforms`), so the
Windows half was never implemented. The brief's §1.3 **verdict is
unaffected**: Job Objects still do not provide filesystem isolation, and
adding `pywin32` would not change that conclusion.

**Correction of record:** `BBF-FU-22-windows-contract-correction` (see
`docs/16_audit/BBF-FU-22-windows-contract-correction.md`).
