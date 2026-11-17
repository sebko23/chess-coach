# BBF-doc-drift-flip-17 — close the FU-20 stale out-of-scope list and record the enablement contract

**Status:** Doc + config BBF. 3 files modified (`.env.example` modified, `docs/16_audit/OPEN-FOLLOWUPS.md` modified, `docs/16_audit/BBF-doc-drift-flip-17.md` NEW per-flip brief).
**Base:** `025ddb3e983fc936aa97abd719ec1f53cda6bf5b`

## §1. Why this flip exists

FU-20's ledger entry carries a stale `**Out of scope (follow-up BBFs):**` list
whose three enumerated items have all shipped. Each item is a dead deferral:
the ledger asserts open work that no longer exists, inside an entry whose own
lead reads RESOLVED for its named scope.

The three items, as written in the ledger:

1. "Full Windows network isolation via custom C extension or AppContainer
   (requires significant new code)."
2. "Verification that `unshare(CLONE_NEWNET)` actually creates a new network
   namespace (the existing test only verifies `os.setsid()` runs)."
3. "The `JOB_OBJECT_LIMIT_PROCESS_MEMORY` (memory cap on Windows, separate
   from network isolation) — was deferred by FU-22-impl."

The list is a single ledger line; the three items are quoted here with the
line-wrapping they carry in the source.

This is the **flip-12 shape** (flip-16's §3): the entry has no existing
`**Status (clarified ...)**` block, so the stale block is replaced in place,
and the historical prose it introduced is preserved rather than deleted.

Flip-16 explicitly **excluded** FU-20, and its reasoning was correct *at the
time*: the entry's then-live `**Status:** OPEN` line sat inside a preserved
`**Identified:**` / `**The gap:**` historical body, under a lead that already
scoped Windows as a separately-approved follow-up, and the entry carried an
explicit `**Historical state (superseded 2026-10-29 by ...)**` block. It was
historical content, not a contradiction.

What changed since: **PR #195 landed the AppContainer backend on 2026-11-11**
and **PR #200 landed the enablement contract on 2026-11-14**. The out-of-scope
list is not historical content — it is the entry's *own* enumeration of what
remains to be done, and every enumerated item is now discharged. The
`**Status:** OPEN` line flip-16 excluded is a different line and is left
untouched here for the same reason flip-16 gave.

## §2. The scope-discharge test

`docs/16_audit/BBF-FLIP-PROCESS-RULES.md` §6 requires walking the entry's OWN
enumerated scope list step by step, not asking whether the artifact exists.
Each item was measured against the base tree, not read from the ledger.

**(1) Full Windows network isolation — DISCHARGED.** The AppContainer backend
shipped in squash `f57bfcc1` (PR #195), an ancestor of the base.

| Claim | Measured |
|---|---|
| the AppContainer backend exists | `services/chess_coach/pdf_ocr/windows_appcontainer.py` is **present** |
| it is a real boundary, not a stub | the real-Windows suite is present at `tests/windows/test_windows_appcontainer_enforcement.py` and the unit suite at `tests/unit/test_windows_appcontainer.py` |
| the CI job exercises it | `.github/workflows/smoke.yml` contains the `windows-appcontainer-isolation` job |
| it is reachable | `services/chess_coach/pdf_ocr/subprocess_runner.py` reads `CHESS_COACH_WINDOWS_APPCONTAINER` and evaluates it at call time |

**(2) Namespace verification — DISCHARGED.** The Linux Phase 1 implementation
and the release-scope closure landed in squash `df3ed9bf`, which is the commit
that added both `services/chess_coach/pdf_ocr/linux_sandbox.py` and the
production-container proof script; the correction push it carried also
corrected the residue the earlier closure attempt left.

| Claim | Measured |
|---|---|
| a production-container proof exists | `scripts/dev/verify_linux_network_isolation.py` is **present** |
| it verifies the namespace identity | the script reads `/proc/self/ns/net` |
| it verifies escape resistance | the script requires `escape_refused=1` from the launcher's status channel and parses `escape_errno=` (the launcher reports the `EPERM` refusal) |
| the ledger already records the measurement | the entry's own lead states the re-entry attempt is "**refused with `EPERM`** (`escaped = False`)" — the `escaped = False` phrasing is the ledger's rendering of the launcher's `escape_refused=1` / `escape_errno=EPERM` status, not a literal in the verify script |

Note that item (2)'s wording — "the existing test only verifies `os.setsid()`
runs" — is the *pre-2026-10-29* description. It describes the 2026-10-18
implementation, which the entry's own `**Historical state (superseded
2026-10-29 ...)**` block already marks as not proven. The out-of-scope list
was never updated to match.

**(3) Windows memory cap — DISCHARGED.** The Job Object backend shipped in
squash `ed803d6d` (PR #190, `BBF-FU-22-B2-windows-job-object`), an ancestor of
the base.

| Claim | Measured |
|---|---|
| the limit is implemented | `services/chess_coach/pdf_ocr/windows_job.py` sets `JOB_OBJECT_LIMIT_PROCESS_MEMORY` |
| it is enforced before the parser runs | the target is created `CREATE_SUSPENDED`, assigned to the Job, and only then resumed |
| the ledger already records it | FU-22's own entry reads "**RESOLVED** 2026-10-29 via PR #190 ... Windows enforced via a Job Object per-process limit" |

## §3. The replacement shape

The stale block is **one line** (ledger line 1682). It is replaced by **one
line**, so the edit is line-count neutral by construction.

The replacement states what is actually true now: all three enumerated items
are discharged, with the commits that discharged them, and the one item that
genuinely remains — the **product-enablement decision** — is named as such,
with a pointer to the contract that governs it.

The historical prose around it is preserved **byte-for-byte**: the lead's
2026-10-18 history paragraph, the `**Historical state (superseded
2026-10-29 ...)**` block, the `**Identified:**` / `**The gap:**` body, and
the `**Status:** OPEN` line at 1764 that flip-16 deliberately left alone.

No clarification block is introduced, so the unique-clarification rule holds.

## §4. The enablement contract is recorded, not enacted

The contract (`docs/16_audit/BBF-FU-20-windows-appcontainer-enablement-contract.md`)
landed through PR #200 as a **documentation-only** change. It records two
separate decisions:

- **Decision A** — per-deployment enablement;
- **Decision B** — flipping the shipped default.

**Decision B is not requested**, and this flip does not request it either.
Nothing here changes a default, a code path, a CI job, or an environment
variable's behaviour. The Windows path stays **opt-in** through
`CHESS_COACH_WINDOWS_APPCONTAINER=1`; the shipped default stays the **501
`internal.not_implemented`** refusal; no parser process, Job target, or
AppContainer is created while the opt-in is off.

**FU-20 remains open** after this flip, because the product-enablement
decision has not been taken. The flip records the decision's surface; it does
not make the decision.

## §5. Why line-count neutrality is load-bearing here

PR #194 landed ten `**Original entry:** lines N-M` pointers in this same
ledger whose **values are line numbers**. Measured on the base tree, FU-20's
entry spans lines 1663–1801, and **nine** of the ten pointer targets lie
below it. A net line-count change anywhere inside the entry would shift those
pointer start lines and silently re-point them at the wrong FU entries — the
exact defect class PR #194 was merged to fix, and one no CI gate in this
repository can catch.

The edit is therefore line-count neutral **by construction**: one line replaced
by one line. The ledger stays at **3,884 lines** and exactly **one** line
differs from the base.

The `.env.example` addition is a **separate file**, so it cannot affect any
ledger line number.

## §6. The `.env.example` addition

Decision A requires an operator to set `CHESS_COACH_WINDOWS_APPCONTAINER=1`.
Until this flip, the **only** places that variable was named were the security
strategy, the three audit briefs, the ledger, the CI workflow, and the code
itself. `.env.example` — the **template** an operator copies to `.env` — did
**not** mention it, so an operator following the template had no way to
discover the opt-in. (The gateway auto-loads `.env`, not the template:
`load_dotenv()` in `services/chess_coach/gateway/app.py` and
`services/chess_coach/gateway/__main__.py`, and pydantic's
`env_file=".env"` in `services/chess_coach/gateway/config.py`.)

The addition is a **commented-out** entry, matching the file's existing
convention for optional variables (`CHESS_COACH_HOST` and
`CHESS_COACH_OCR_BACKEND` are commented out). It is a template, not a
default: leaving it commented preserves the shipped 501 refusal exactly.

The **template** is not read by any test or workflow (measured: no
`.py`/`.yml`/`.yaml`/`.sh`/`.toml` file in the base tree references it), so the
addition carries no CI surface. Measured on the base tree, three files mention
the template — `.dockerignore`, `docs/CHANGELOG.md`, and `docs/VERIFICATION.md` —
and none cites it as a `path:NNN` reference, so the addition cannot invalidate a preexisting citation.

The **file it templates** *is* read at runtime: the gateway loads `.env` at
startup (`env_file=".env"` in `services/chess_coach/gateway/config.py`, and an
explicit `load_dotenv()` in `services/chess_coach/gateway/__main__.py`). That
is precisely why the template matters — the opt-in is invisible to an
operator who follows it. `.dockerignore` keeps `**/.env` out of the build
context while explicitly re-including `**/.env.example`, so the template stays
committed and the real `.env` stays out of both git and the image.

## §7. Verification

- The ledger stays at **3,884 lines**, with its trailing newline preserved.
- Exactly **one** ledger line differs from the base; every other line is
  byte-identical.
- All ten PR #194 pointer values resolve to their entries' headings in the
  would-land tree.
- FU-20's `**Identified:**` body, `**The gap:**` body, `**Status:** OPEN` line,
  its `**Historical state (superseded 2026-10-29 ...)**` block, and the lead's
  2026-10-18 history paragraph are byte-identical to the base.
- The `.env.example` blob stays LF-clean; its committed line count grows only
  by the added lines.
- `git diff --check` is clean; no file-mode regressions.
- The flip-rules and commit-reference gates pass against the commit body and
  the PR body, and are proven **non-vacuous** on this change.
- The gate specs are listed here so the count is reproducible. `--anchor` and
  `--preserve` are argparse `nargs="*"` and therefore **last-wins**, so each
  of these was run in its own invocation:

  | Spec | Asserts |
  |---|---|
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1665=RESOLVED for the named release scope` | the lead is untouched |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1678=BBF-FU-20-windows-appcontainer-network-isolation.md` | the brief pointer is untouched |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1682=Out of scope (follow-up BBFs):` | the replaced line starts as claimed |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1682=all three enumerated items are now` | the replacement states the discharge |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1682=landed 2026-11-11` | the corrected date |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1682=FU-20 remains open` | the remaining item is named |
  | `--anchor docs/16_audit/OPEN-FOLLOWUPS.md:1764=Status:** OPEN` | the historical OPEN line is untouched |
  | `--anchor .env.example:81=Windows AppContainer network isolation (opt-in)` | the new block's heading |
  | `--anchor .env.example:92=CHESS_COACH_WINDOWS_APPCONTAINER=1` | the opt-in line is commented in place |
  | `--anchor .env.example:96=CHESS_COACH_APPCONTAINER_STAGING_ROOT` | the staging line is commented in place |
  | `--anchor docs/16_audit/BBF-doc-drift-flip-17.md:1=BBF-doc-drift-flip-17` | the brief's title |
  | `--anchor docs/16_audit/BBF-doc-drift-flip-17.md:4=025ddb3e983fc936aa97abd719ec1f53cda6bf5b` | the brief's pinned base |
  | `--anchor docs/16_audit/BBF-doc-drift-flip-17.md:6=Why this flip exists` | the brief's first section |
  | `--preserve docs/16_audit/OPEN-FOLLOWUPS.md:1663-1681` | everything above the edited line is byte-identical |
  | `--preserve docs/16_audit/OPEN-FOLLOWUPS.md:1683-1801` | everything below the edited line is byte-identical |

  `--expect-files`, `--numstat`, and `--require-ancestor` accumulate their
  values and were passed in a single invocation.

## §8. Explicit exclusions

- **FU-20's `**Status:** OPEN` line (1764).** It sits inside the entry's
  preserved `**Identified:**` / `**The gap:**` historical body, under a lead
  that reads `RESOLVED for the named release scope (2026-10-30)`. This is the
  same reasoning flip-16 recorded, and it still holds.
- **FU-20's lead status line (1665).** It is accurate: the named release scope
  is closed, and the same line already states that the Windows AppContainer
  work "remains **opt-in**, so the 501 refusal is still what ships by
  default". It also already points at the Windows AppContainer implementation
  by the date label the ledger's own paragraph carries. It is not
  contradictory, so it is not touched.

  A note on that label: the ledger's paragraph header reads
  `**2026-11-09 Windows AppContainer implementation ...**`, but the squash
  that landed the backend is dated **2026-11-11** (`f57bfcc1`). The label is
  pre-existing ledger text and is **not** touched here — correcting it would
  be a second, separate correction with its own line-count consideration.
  The date this flip asserts is the **commit's** date, which is the one the
  brief's own measurement can support.
- **The ledger's "This file is untracked" header.** The file **is** tracked
  and is **not** ignored, so that header line is stale. Correcting it is a
  one-line change with no pointer impact, but it is a **separate** defect
  class from the enumerated-scope discharge this flip performs, and mixing the
  two would make the flip's measured scope ambiguous. It is left for its own
  flip.
- **FU-7, FU-9, FU-23, FU-27.** Each truthfully open; unchanged.
- **Decision B (the shipped-default flip).** Not requested here. See §4.
- No source, test, or workflow file is touched; the only configuration-related change is the commented-out `.env.example` template block.

## §9. Honest limitations

- **No runtime test was executed for this flip.** The change is one ledger
  line and one commented block in a template file, with no behavioural surface.
  The scope-discharge measurements in §2 are static reads of the base tree.
  FU-20's and FU-22's own behaviours were verified by their own BBFs; this
  flip does not re-verify them.
- **This flip does not re-run the Windows AppContainer proof.** It reads the
  shipped tree's structure and the landed CI job's presence; it does not
  reproduce the native-Windows measurement.
- **The `.env.example` addition is a discoverability improvement, not an
  enablement mechanism.** Setting the variable still requires the operator to
  stage the parser outside the user profile and to accept the residual
  limitations; the template's comment says so.
- **This flip does not claim the ledger is free of further stale
  declarations.** It closes the one enumerated-scope deferral it measured. A
  later state change could make another entry stale, exactly as it made this
  one.
- **The container-side copy of the status record and the stale ledger mirror
  are outside this repository.** The authoritative copies are the committed
  blobs; the mirrored files under the container's project directory and the
  host's `Downloads/` directory are not.

## §10. Maintenance-cost estimate

One line in the ledger, one commented block in `.env.example`, and this brief.
The next flip that edits above ledger line 1801 must re-verify the pointer
values against the would-land tree, as PR #194's rebase did.
