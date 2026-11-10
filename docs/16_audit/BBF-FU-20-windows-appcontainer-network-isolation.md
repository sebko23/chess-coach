# BBF — FU-20 Windows AppContainer network isolation

**Date:** 2026-11-09
**Status:** Implementation landed behind an opt-in flag. **FU-20 is NOT marked resolved** — production enablement is a separate product decision.
**Scope:** A-F11 property 2 (no network access in the PDF-parsing subprocess) on Windows.

---

## 1. The defect this BBF closes

A-F11 requires the PDF parser to run with **no network access**. The
Linux half was closed on 2026-10-29 by `BBF-FU-20-linux-phase1-network-isolation`,
which established a combined `CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWNS`
namespace and made Windows PDF parsing an **explicit refusal**: a typed
`NetworkIsolationUnsupportedError` (HTTP 501, `internal.not_implemented`)
raised before any parser process or Job Object target was created.

That refusal was correct, but it left Windows without a no-network
boundary. This BBF implements one.

### 1.1 Why the AppContainer mechanism

The alternatives were considered and rejected on measured grounds:

| Option | Verdict |
|---|---|
| Windows Firewall rule | Host-global, requires administrator rights, and is not process-scoped. Explicitly excluded by the authorization. |
| Proxy-environment stripping | Defense in depth, never isolation. A raw socket ignores it. Already retired on Linux. |
| Job Object network-rate control | Throttling, never isolation. Already rejected on Linux. |
| Windows Sandbox / Hyper-V container | A deployment-level boundary, not a process-scoped one. Out of scope. |
| **AppContainer with zero capabilities** | **Chosen.** Process-scoped, kernel-enforced, no administrator rights required. |

### 1.2 The threat-model fact that shapes the whole design

**An AppContainer token does not revoke an inherited network handle.**

This was measured, not assumed. A connected TCP socket that is
*inherited* by an AppContainer process remains fully usable inside it:
the child reported the socket as `PRESENT ... inheritable=True` and
`send()` on it succeeded, with the server observing the bytes.

AppContainer blocks **new** outbound access (the token holds no
`internetClient` capability), but it does not un-connect a socket that
crossed the boundary. The mitigation is therefore **not** the container
alone; it is the **inherited-handle policy**.

---

## 2. The security contract

### 2.1 Identity: a product-owned AppContainer package

The parser runs in an AppContainer whose package SID is a fixed,
documented, **product-owned** constant:

```
S-1-15-2-1307264423-3961844790-1637159078-741858669-3028905837-1642583832-2140039969
```

**Derivation.** `SHA-256("ChessCoach.PdfParser")`, taken as its first 28
bytes (seven big-endian 32-bit groups), each rendered in **decimal**,
under the `S-1-15-2` application-package authority. The decimal form is
mandatory: a hex-formatted variant is rejected by
`ConvertStringSidToSidW` with `ERROR_INVALID_SID` (1337), because
AppContainer package subauthorities are decimal.

**Ownership.** The constant belongs to Chess Coach alone. It is **not**
borrowed from a Store package, and it is **not** claimed to be the output
of `DeriveAppContainerSidFromAppContainerName` — that API was measured to
be a host-specific no-op on the validation host (`S_OK` with a zero count
and a null SID, exactly like `CreateAppContainerProfile`).

**Registration.** Windows launches AppContainer processes **by SID**, and
an unregistered SID cannot back a launched token: the measured launch
failed with `CreateProcessW` error 2 (`ERROR_FILE_NOT_FOUND`). The
production path therefore registers the product SID in the **per-user**
mapping key

```
HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppContainer\Mappings\<SID>
```

with a `Moniker` / `DisplayName` pair and `Capabilities` / `Children`
subkeys — the same shape Windows itself uses — and creates the moniker
package folder under `%LOCALAPPDATA%\Packages` with the required `AC\Temp`
child. Both steps are per-user, idempotent, and need **no administrator
privilege**. There is no host-global registry change, no service, no
firewall rule, and no privileged helper.

### 2.2 Capabilities: zero

The `SECURITY_CAPABILITIES` structure carries the product SID and an
**empty** capability array. The launched token therefore holds **no**
`S-1-15-3-*` capability at all, and in particular no `internetClient`, so
it cannot open a new outbound connection.

`CapabilitySet` refuses to be constructed with `internetClient`, and
`build_launch_plan()` refuses a network-capable set outright. There is no
code path that grants a network capability to the parser.

### 2.3 Handles: a populated stdout/stderr-only allowlist

**This is the measured production mitigation**, and it supersedes the
earlier `bInheritHandles=FALSE` wording (see §7).

* `bInheritHandles=**TRUE**` — required, because
  `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` is honoured only when it is `TRUE`.
  Measured: with a handle list and `bInheritHandles=FALSE`,
  `CreateProcessW` fails with `ERROR_INVALID_PARAMETER` (87).
* The allowlist contains **only** the parser's stdout and stderr
  handles, created inheritable, with `STARTF_USESTDHANDLES` and the
  corresponding `STARTUPINFOEX` fields set.
* No other handle crosses into the child — in particular **no connected
  socket**.

Measured on a native Windows host, in the same run:

| Arm | Handle reported in the child | `send()` on the socket | Server observed the bytes |
|---|---|---|---|
| Production allowlist | `PRESENT ... inheritable=False` | `SEND-FAILED` (`WSAENOTSOCK`, 10038) | **no** |
| Bypass (no allowlist) | `PRESENT ... inheritable=True` | `SENT-OK(14)` | **yes** |

The second arm is the **mandatory positive control**: it proves the
socket was genuinely usable, so the first arm's exclusion cannot be
dismissed as a dead endpoint.

The **empty** explicit handle list is **prohibited**: it was measured not
to provide an empty allowlist, because the child's own standard handles
occupy the same handle values.

### 2.4 Ordering: everything before the first instruction

The launch sequence is fixed and fails closed at every stage:

1. prepare the package identity and the zero-capability set;
2. create the target **suspended** (`CREATE_SUSPENDED`) with the
   attribute list;
3. create and configure the Job with the per-process 2 GiB memory limit
   and kill-on-close behaviour;
4. assign the still-suspended target to the Job;
5. **verify the target's AppContainer identity and capabilities while it
   is still suspended** — launcher-side `TokenIsAppContainer` must be
   `True`, `TokenAppContainerSid` must exactly equal the product SID, and
   the token must hold no `S-1-15-3-*` capability;
6. resume only after every stage above has succeeded.

Any failure in steps 1–5 aborts the launch **without resuming the
target**, so no unconstrained parser code ever runs. The pre-resume
verification is what makes this a *verified* boundary rather than an
*assumed* one: a token that is not the product AppContainer is terminated
before it executes a single instruction.

### 2.5 Staging: outside the user profile

An AppContainer token cannot traverse the user profile, so a
profile-resident executable is unlaunchable inside the container (measured:
`STATUS_DLL_NOT_FOUND`). The parser and its runtime are therefore staged
under `ProgramData\ChessCoach\poppler` by default (override with
`CHESS_COACH_APPCONTAINER_STAGING_ROOT`), and the **product SID** is
granted the minimum access: read+execute on the staged executable and its
runtime, modify on the artifact directory that holds the input PDF and
the output PNGs. No source tree, no parent-process directory, and no
arbitrary user-profile path is granted.

**The grant must cover the staged files, and the staged directory as
well.** Two measured facts fix the shape:

* `icacls /grant *SID:(OI)(CI)(RX)` applied to a **file** returns exit 0
  and adds **no ACE** — the inheritance flags are meaningless on a file.
  A file therefore gets the plain right. **This was the real cause of the
  first production failure:** the staged files had no product-SID ACE at
  all, so the parser died with `STATUS_DLL_NOT_FOUND`.
* The same form applied to the **directory** adds the inheritable ACE, so
  the right reaches the files it contains.

The production caller now grants `staged.directory` together with the
staged files. The directory grant is a deliberate **superset**: measured
on this host, granting the files alone was already sufficient for the
parser to resolve its runtime. It is kept because it states the intent
(the container may reach into the staged runtime) and removes the
dependence on the inherited-user ACEs of the staging tree.

The production path was measured end-to-end through the shipped entry
point: the real Poppler runs inside the AppContainer and returns the
rendered page.

The PDF is passed to `pdftoppm` **by file path**, not stdin, because the
production launch shape does not inherit a stdin handle.

---

## 3. The failure taxonomy

| Failure | Exception | HTTP | Parser executed? |
|---|---|---|---|
| The Windows boundary is off, or the backend is unavailable | `NetworkIsolationUnsupportedError` | **501** `internal.not_implemented` | no |
| A containment stage failed (package, capabilities, Job, assignment, verification, resume, staging, ACL) | `NetworkIsolationSetupError` | **500** `internal.network_isolation_setup_failed` | **no** |
| The Job's per-process limit was hit | `WindowsJobLimitExceededError` | 422 | n/a |
| The target exceeded its budget | `WindowsJobTimeoutError` | 504 | n/a |
| The parser itself failed | `RuntimeError` | 422 | yes |

A setup failure is **never** downgraded into "run it anyway". There is no
unrestricted fallback, no firewall substitute, and no proxy-only
behaviour.

---

## 4. The opt-in boundary

**The Windows AppContainer path is opt-in through
`CHESS_COACH_WINDOWS_APPCONTAINER=1`, and the default 501 refusal remains
shipped.**

The flag is evaluated at **call time**, so a deployment or a test can
switch it within one process. With the flag off, `ensure_network_isolation_supported()`
raises the 501 refusal exactly as before, and no parser process, Job
target, or AppContainer is created.

The opt-in exists because production enablement is a **separate product
decision**: the implementation is measured and proven, but shipping it as
the default Windows behaviour requires an explicit, reviewed acceptance
of the residual limitations in §6.

---

## 5. The proof

### 5.1 Identity gate (measured before any production edit)

The native-Windows validation required by the implementation directive
passed in full:

| Assertion | Result |
|---|---|
| `ConvertStringSidToSidW` parses the constant | pass |
| A suspended helper launches under the SID with zero capabilities | pass |
| Launcher-side pre-resume `TokenIsAppContainer` | `True` |
| Launcher-side `TokenAppContainerSid` | exactly the product SID |
| `S-1-15-3-*` capabilities in the token | **none** (no `internetClient`) |
| Minimum-ACL access with the product-SID grant | pass |
| The same run **without** the grant | fails closed (`CreateProcessW` 5) |
| Restricted helper opens a new outbound TCP connection | denied (`TIMEOUT`) |
| Unrestricted control in the same run | **connects** (`CONNECTED`) |
| Real Poppler under the product SID | exit 0, `page-1.png` |
| Populated allowlist vs a live inherited socket | excluded; server saw no bytes |
| Unrestricted inherited-socket control | sent; server saw the bytes |

The SID was independently reproduced by the controller from
`SHA-256("ChessCoach.PdfParser")` and matched exactly.

### 5.2 Test suites

| Suite | Result |
|---|---|
| `tests/windows/test_windows_appcontainer_enforcement.py` (15 real-Win32 tests) | **15 passed** |
| `tests/windows/test_windows_job_enforcement.py` (pre-existing) | 18 passed, 1 skipped (a non-Windows assertion) |
| `tests/unit/test_windows_appcontainer.py` | **40 passed** |
| `tests/unit/test_windows_appcontainer_cleanup.py` | 12 passed, 1 skipped (no pre-existing mapping in that environment) |
| `tests/unit/test_pdf_ingest_security.py` + `test_pdf_ingest_route.py` | 67 passed, 2 skipped (Linux namespace gating) |

The real-Windows suite proves: the token identity and zero capabilities;
new-outbound denial against an unrestricted control **in the same run**;
parent/child/grandchild denial (with an unrestricted three-generation
control in which every generation connects); the inherited-socket bypass
and the populated-allowlist mitigation; pre-resume Job assignment; the
real Poppler workload and its expected artifact; the no-ACL fail-closed
behaviour; the error taxonomy; and deterministic cleanup.

### 5.3 Independent leaf review

An independent, adversarial leaf review of the implementation head
returned **UNSAFE** and raised six blocking findings, all confirmed
empirically with real Win32 calls:

| # | Finding | Resolution |
|---|---|---|
| B1 | The explicit allowlist was silently dropped when stdout/stderr were absent, leaving `bInheritHandles=TRUE` with no attribute — the bypass shape | The launch now **fails closed** at stage `handle_policy`; measured: no bytes reach the server |
| B2 | The per-file ACL grant added no ACE, so the staged parser could not load its own runtime | The grant now covers the staged directory as well; measured: the real Poppler runs and produces its artifact |
| B3 | The CI job staged Poppler but never put it on `PATH`, so the two real-Poppler tests **skipped** and the job went green without the workload | The staged Poppler is on `PATH`, and a missing Poppler is a **failure**, not a skip |
| B4 | `AppContainerUnsupportedError` mapped to 422 instead of the documented 501 | The unsupported condition now maps to the 501 refusal |
| B5 | The Job and completion-port handles were unowned, and the token handle from `OpenProcessToken` was never closed | Every handle is owned and closed on every path; measured: handle delta over 10 launches is **0** |
| B6 | The `ConvertStringSidToSidW` allocation was never freed | It is released |

The re-review of the corrected head confirmed B1, B3, B4, B5 and B6
closed and raised F1: the production ACL grant covered only the staged
files, so the containing directory never received the product-SID ACE.
F1 is fixed and measured as described in §2.5.

Later reviews raised five further findings, each fixed and each
verified on the native Windows host:

| # | Finding | Resolution |
|---|---|---|
| HIGH-1 | No committed test or CI step exercised the **production** entry point -- every test drove the low-level launcher | The enforcement suite now calls the shipped `run_pdftoppm_in_subprocess` with the opt-in on and asserts a rendered page, and the CI job runs the same production call |
| MEDIUM-2 | The capability list was read with the `TOKEN_GROUPS` inline layout instead of the `TOKEN_CAPABILITIES` pointer layout, and the `internetClient` flag was computed against the group list, where capability SIDs never appear | The capability list is read through its pointer at offset 8, and the flag is computed against the capability SIDs |
| F1 | The reader read the pointer field at offset 8 of the **8-byte** `TOKEN_CAPABILITIES` buffer the production token actually has -- an out-of-bounds heap read | The count and the buffer length are checked first, and the pointer is read only when the buffer can hold it |
| F2 | A failed `GetTokenInformation` became an empty capability list, so a token could pass verification with no proof that it held no network capability | A failed read is reported as a failed read, and the verification fails closed on it |
| -- | The cleanup certificate's "foreign preservation" assertion was vacuous: the foreign tree was a sibling the cleanup never inspects | The foreign state now sits at the path the cleanup inspects, so the ownership predicate is what preserves it |

The CI failures those findings exposed were also fixed: the certificate's
inline program was corrupted by PowerShell backtick escaping, the
certificate ran before the production step and deleted the tree `PATH`
pointed into, the AppContainer unit tests assumed Windows import-time
constant values, and the new Windows-only module needed a
platform-independent test suite to keep the cross-platform coverage floor.

### 5.4 CI

The new `windows-appcontainer-isolation` job in
`.github/workflows/smoke.yml` stages the **pinned** Poppler 26.09.0
(`Release-26.09.0-0.zip`, tag `v26.09.0-0`) under
`C:\ProgramData\ChessCoachCI` and runs, in this order:

1. the real AppContainer enforcement suite;
2. the AppContainer unit and cleanup suites;
3. the taxonomy and default-refusal check;
4. the **production entry point** with the opt-in on -- the shipped
   `run_pdftoppm_in_subprocess`, which is the only step that proves the
   production chain end to end;
5. the cleanup certificate.

The certificate is **last** on purpose.  It removes the application-owned
staging tree, and the staging step puts that tree on `PATH`, so running
the certificate earlier would delete the directory `PATH` points into
and make the production step fail with "pdftoppm was not found".  As the
last step, the cleanup property is proved on the state the job actually
created and nothing after it depends on that state.

The certificate is a program in a file,
`scripts/dev/verify_appcontainer_cleanup.py`, not an inline command.  An
inline `python -c "..."` inside a PowerShell double-quoted string is
subject to backtick escaping, and a backtick-n in the program becomes a
NEWLINE -- which silently corrupted the certificate once and made the
step fail with a `SyntaxError` instead of a certificate result.  A file
removes the whole class of hazard.

The certificate proves three things, and it is proven non-vacuous: the
cleanup removes the application-owned state it created, it **preserves**
a foreign tree that carries no ownership marker, and a second cleanup is
a successful no-op.  The foreign state sits at exactly the path the
cleanup inspects, so the **ownership predicate** is what preserves it --
a cleanup that ignored the marker would remove that tree and the
certificate would fail.  Each of the five mutations below is caught:

| Mutation | Caught with |
|---|---|
| the ownership-marker check broken, so an unmarked tree is removed | "the cleanup removed the UNMARKED tree" |
| the cleanup removes the unmarked tree it owns | "the cleanup removed the UNMARKED tree" |
| the cleanup removes nothing | "the owned staging tree was not removed" / "the owned staging tree still exists" |
| the cleanup reports a removal on every call | "the cleanup is not idempotent" |
| the cleanup nukes the whole staging root | "the owned staging tree was not removed" / "the owned staging tree still exists" |
| the cleanup removes the owned staging ROOT instead of the tree inside it | "the cleanup removed the whole staging ROOT, not just the staging tree inside it" |

The cleanup removes `root / "poppler"`, **not** the root: the certificate
proves the root itself survives, with only the `poppler` subtree
removed.

The pre-existing Windows Job Object job is untouched and continues to
protect the memory-cap half of A-F11.

CI uses **no** Linux emulation, Docker, WSL, documentation-only
assertion, or skipped test as a substitute for real Win32/AppContainer
proof.

---

## 6. Residual limitations

These are real and are **not** closed by this BBF.

1. **Windows filesystem isolation is still not enforced at the process
   level.** A-F11 property 3 (read-only filesystem except the per-book
   artifact dir) remains a deployment-config concern on Windows
   (AppLocker/WDAC). This BBF addresses property 2 only.
2. **The opt-in must be set for the Windows path to run at all.** Until
   the enablement decision, Windows PDF parsing is still refused.
3. **The AppContainer grants the parser its own package identity**, which
   the OS may grant additional rights to through other policy. This BBF
   controls the capability set and the filesystem ACLs it applies; it does
   not control host policy applied elsewhere.
4. **The staging directory is not cryptographically protected.** It lives
   under `ProgramData` with an ownership marker, and the cleanup removes
   only what it owns, but a local administrator can always modify it.
5. **Windows Defender or antivirus software that injects into the
   process** is out of scope for any userland containment boundary.

---

## 7. Superseded wording

The implementation directive's §3.1 originally read *"Launch the parser
with `bInheritHandles=FALSE`"*. **Sections 11–13 of that directive
supersede it**, and the implementation follows the settled shape:

* `bInheritHandles=TRUE` with a populated stdout/stderr-only
  `PROC_THREAD_ATTRIBUTE_HANDLE_LIST`;
* `bInheritHandles=FALSE` is documented only as a **fail-closed
  alternative**, because it excludes the socket but also removes the
  stdout/stderr capture the parser's diagnostics depend on.

`HandlePolicy(use_explicit_allowlist=False)` — the shape that applies **no**
handle list and therefore lets every inheritable handle cross — appears
**only** in the bypass-demonstration positive control, never in the
production launch path. A unit test asserts the production policy's
allowlist is never empty.

---

## 8. Cleanup of application-owned state

The application creates three pieces of state. The cleanup removes
exactly those and **nothing else**:

| State | Removal rule |
|---|---|
| The AppContainer mapping under the product SID | Removed only when it is keyed by the product SID **and** its `Moniker` value is the product moniker. A mapping with a different moniker belongs to another installation and is preserved. |
| The `ProgramData\ChessCoach*\poppler` staging tree | Removed only when it carries the `.chesscoach-staging` ownership marker. An unmarked tree is preserved. |
| The `%LOCALAPPDATA%\Packages\<moniker>` package folder | Removed only when it is named for the product moniker. A sibling package folder is preserved. |

The cleanup never enumerates the mappings key, so another identity's
mapping is unreachable by construction. It is **idempotent**: a second
pass removes nothing and reports no error. Both halves are tested —
owned-state removal and pre-existing-state preservation.

---

## 9. Repository-integrity disclosure

During the FU-20 **feasibility** phase, `phaseB2` was briefly written into
the audited repository working tree and moved out immediately. The
verified final feasibility state was **341 baseline untracked entries,
zero tracked changes, and no `tmp_fu20*` artifact**, and no persistent
repository mutation resulted. This is preserved here verbatim as a
matter of record; it is not concealed, and it is not expanded into a
separate audit task.

---

## 10. Related records

- `docs/16_audit/BBF-FU-20-linux-phase1-network-isolation.md` — the
  Linux half of A-F11 property 2 and the explicit Windows refusal this
  BBF replaces on the opt-in path.
- `docs/16_audit/BBF-FU-22-B2-windows-job-object.md` — the Job Object
  backend this BBF extends with the AppContainer layer.
- `docs/16_audit/BBF-FU-20-impl-windows.md` — the earlier
  best-effort proxy-stripping Windows attempt, preserved as history.
- `docs/16_audit/OPEN-FOLLOWUPS.md` — the FU-20 ledger entry.
- `docs/08_security/security-strategy.md` — the A-F11 property record.
