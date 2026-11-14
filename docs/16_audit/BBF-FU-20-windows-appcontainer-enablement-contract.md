# FU-20 Windows AppContainer — enablement contract

**Date:** 2026-11-14
**Repository:** `sebko23/chess-coach`
**Base:** `main @ 0243d3151dd009cd641d6eefa3d3fb408dd68c19`
**Subject:** the Windows PDF-parsing network-isolation path
**Status:** contract only — **no code change, no default flip**

## 0. What this document is, and is not

This document defines **what it takes to enable** the Windows AppContainer
network-isolation path, and **what acceptance means** if a deployment turns
it on. It is the artifact the implementation directive required before
FU-20 could be closed.

It deliberately does **not**:

- change any code, default, CI job, workflow, dependency, or test;
- flip the shipped default away from the 501 `internal.not_implemented`
  refusal;
- mark FU-20 resolved;
- enable the path in any deployment.

The Windows path is currently **opt-in** via
`CHESS_COACH_WINDOWS_APPCONTAINER=1`, and the shipped default remains the
501 refusal. This document makes the opt-in an explicit, reviewable
decision surface instead of an undocumented environment variable.

## 1. Current state (measured on the base tree)

| Property | Measured |
|---|---|
| opt-in switch | `CHESS_COACH_WINDOWS_APPCONTAINER=1` (`services/chess_coach/pdf_ocr/subprocess_runner.py`) |
| switch evaluation | **call time**, not import time — a deployment or a test can change it within one process |
| truthy values | `1`, `true`, `yes`, `on` (case-insensitive, whitespace-trimmed) |
| staging root | `CHESS_COACH_APPCONTAINER_STAGING_ROOT`, defaulting to `%PROGRAMDATA%\ChessCoach` |
| shipped default | **off** — the 501 `internal.not_implemented` refusal |
| Linux | unaffected: network isolation is enforced fail closed by the namespace launcher |
| other platforms | unaffected: no isolation boundary, PDF parsing refused |

The flag selects a **containment mechanism**, not a deployment setting,
which is why it is an environment variable rather than a
`GatewaySettings` field: the PDF-OCR module is imported by the shared
runner independently of the gateway. This mirrors the existing
`CHESS_COACH_OCR_BACKEND` pattern.

## 2. The two decisions this contract governs

Enabling the path requires **two separate decisions**, and this document
states what each one commits you to.

### Decision A — per-deployment enablement

*"This Windows deployment will run PDF parsing under the AppContainer
boundary."*

Consequences:

- the deployment must set `CHESS_COACH_WINDOWS_APPCONTAINER=1` for the
  gateway process;
- the parser and its runtime must be staged **outside the user profile**
  (see §4), because an AppContainer token cannot traverse the user
  profile;
- the host must be able to create the product package profile
  (`ChessCoach.PdfParser`, moniker `ChessCoach.PdfParser_8wekyb3d8bbwe`);
- the deployment accepts the residual limitations in §5.

### Decision B — the shipped default

*"Windows PDF parsing is isolated by default, and the 501 refusal is
retired."*

**This document does not request Decision B.** It records what Decision B
would require, so that the choice can be made explicitly rather than by
accident of a default.

Decision B would require, at minimum:

1. flipping the shipped default so the flag is no longer needed;
2. updating the CI assertion that pins the opt-in default, which
   currently asserts `windows_appcontainer_is_enabled() is False` and
   raises `AssertionError('the default Windows refusal was weakened')`
   if the 501 refusal does not fire;
3. changing the Windows error taxonomy so that an unsupported platform is
   no longer a normal, expected response;
4. re-proving the Windows path on CI with the **default** configuration
   (the existing proof runs the opt-in case explicitly);
5. accepting that a Windows deployment which cannot create the AppContainer
   package would fail PDF parsing with a **500** setup error rather than a
   **501** refusal — a different operational signal for the same
   environmental condition;
6. updating `docs/08_security/security-strategy.md` §A-F11 and the FU-20
   ledger entry; and
7. a fresh product-owner acceptance, because the residual limitations in
   §5 stop being "opt-in trade-offs" and become "shipped behaviour".

**Recommendation:** keep Decision B unmade. The implementation is proven
and the opt-in is available; a default flip is a product risk decision
that should be taken on its own evidence, not as a side effect of
documenting the contract.

## 3. Acceptance criteria for a deployment that enables the path

A deployment may set the flag only when **all** of these hold.

| # | Criterion | How it is evidenced |
|---|---|---|
| 1 | The host is Windows and the gateway runs on it | platform check at call time |
| 2 | The product package profile can be created and mapped | the path creates and verifies the exact product SID; a failure is a 500 setup error, never a silent skip |
| 3 | The parser and runtime are staged outside the user profile | `CHESS_COACH_APPCONTAINER_STAGING_ROOT` points at a non-profile location, e.g. `%PROGRAMDATA%\ChessCoach` |
| 4 | The staging directory is writable by the account that owns it | the path applies the ACLs it needs; a local administrator can always modify it (§5.4) |
| 5 | The deployment accepts the §5 residual limitations | explicit product-owner acceptance |
| 6 | The 501 refusal is still understood as the off-state | the flag is off by default; operators can disable it per deployment |

The **proof** that the path works is the repository's own Windows CI job
(`windows-appcontainer-isolation` in the smoke workflow), which runs the
real enforcement suite, the unit suites, the cleanup certificate, and the
production entry point against a **real** Poppler build staged under
`C:\ProgramData\ChessCoachCI`. That job is the evidence base for this
contract; a deployment does not re-derive it.

## 4. Staging requirement

An AppContainer token cannot traverse the user profile, so the parser and
its runtime must live outside it.

| Setting | Value |
|---|---|
| default staging root | `%PROGRAMDATA%\ChessCoach` |
| override | `CHESS_COACH_APPCONTAINER_STAGING_ROOT` |
| CI staging root | `C:\ProgramData\ChessCoachCI` |

The staging directory holds an ownership marker. Cleanup removes **only**
application-owned state — the exact product-SID mapping and the marked
`ProgramData\ChessCoach*\poppler` trees — and leaves foreign state intact.
Cleanup is idempotent and is certified by the CI cleanup-certificate step.

## 5. Residual limitations (accepted by enabling, not closed by it)

These are real, are **not** closed by the implementation, and are the
substance of Decision A.

1. **Windows filesystem isolation is still not enforced at the process
   level.** A-F11 property 3 (read-only filesystem except the per-book
   artifact dir) remains a deployment-config concern on Windows
   (AppLocker/WDAC). This path addresses **property 2 only**.
2. **The opt-in must be set for the Windows path to run at all.** While it
   is off, Windows PDF parsing is refused.
3. **The AppContainer grants the parser its own package identity**, which
   the OS may grant additional rights to through other policy. This path
   controls the capability set and the filesystem ACLs it applies; it does
   not control host policy applied elsewhere.
4. **The staging directory is not cryptographically protected.** It lives
   under `ProgramData` with an ownership marker and cleanup removes only
   what it owns, but a local administrator can always modify it.
5. **Windows Defender or antivirus software that injects into the
   process** is out of scope for any userland containment boundary.
6. **Inherited handles.** An AppContainer token does **not** revoke an
   inherited network handle. The mitigation is a populated stdout/stderr-only
   handle allowlist (`bInheritHandles=TRUE` with an explicit list); an
   omitted list removes the explicit attribute while leaving inheritance
   enabled, which is fail-open and is therefore rejected at validation.

## 6. Failure taxonomy (unchanged by enablement)

| Failure | Exception | HTTP | Parser executed? |
|---|---|---|---|
| The Windows boundary is off, or the backend is unavailable | `NetworkIsolationUnsupportedError` | **501** `internal.not_implemented` | no |
| A containment stage failed (package, capabilities, Job, assignment, verification, resume, staging, ACL) | `NetworkIsolationSetupError` | **500** `internal.network_isolation_setup_failed` | no |
| The Job's per-process limit was hit | `WindowsJobLimitExceededError` | 422 | n/a |
| The target exceeded its budget | `WindowsJobTimeoutError` | 504 | n/a |
| The parser itself failed | `RuntimeError` | 422 | yes |

A setup failure is **never** downgraded into "run it anyway". There is no
unrestricted fallback, no firewall substitute, and no proxy-only
behaviour. Operators can therefore tell an unsupported platform (501) from
a blocked or misconfigured deployment (500).

## 7. What stays true on `main` after this document

- the Windows AppContainer path is **opt-in** through
  `CHESS_COACH_WINDOWS_APPCONTAINER=1`;
- the shipped default is the **501 `internal.not_implemented`** refusal;
- no parser process, Job target, or AppContainer is created while the
  opt-in is off;
- FU-20 remains **open**, pending the product-enablement decision;
- Linux network isolation remains enforced fail closed.

## 8. Related records

- Implementation brief:
  `docs/16_audit/BBF-FU-20-windows-appcontainer-network-isolation.md`
- Earlier Windows implementation brief (superseded):
  `docs/16_audit/BBF-FU-20-impl-windows.md`
- Linux Phase 1 brief:
  `docs/16_audit/BBF-FU-20-linux-phase1-network-isolation.md`
- Security strategy §A-F11:
  `docs/08_security/security-strategy.md`
- FU-20 ledger entry:
  `docs/16_audit/OPEN-FOLLOWUPS.md`
