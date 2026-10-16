# BBF-FU-20-21-22-A-F11-spikes — three investigation-first spike briefs for A-F11 properties 2/3/4

**Sprint intent:** Three investigation-first spike briefs
in one BBF, one per A-F11 property: FU-20 (network
isolation), FU-21 (read-only filesystem), FU-22 (2 GB
memory cap). Each spike is a 1-section brief that
audits the current state of the relevant sandbox
primitive, designs a follow-up implementation BBF, and
surfaces what the implementation would actually look
like (code change, test, CI hookup). No actual
implementation lands in this BBF — that's the
follow-up BBF's scope.

**Identified:** 2026-10-16, during the `go FU-20-and-FU-21-and-FU-22`
directive. FU-19 (PR #143) added 4 sandbox-isolation
tests to `tests/unit/test_pdf_ingest_security.py`
yesterday: 1 real test (property 1, subprocess isolation,
PASS) + 3 skip tests (properties 2/3/4, pointing at
FU-22/FU-21/FU-20 as the future implementation BBFs).
This BBF is the investigation-first step that turns
those skip tests into actionable implementation
plans.

**The 3 A-F11 properties + their current state:**

| # | Property | Enforced today? | Implementation primitive | Est. lift |
|---|---|---|---|---|
| 1 | Subprocess isolation (Popen) | Partial (pdf2image) | (already in place) | (done) |
| 2 | No network access (FU-20) | **No** | Linux: `preexec_fn=os.setsid` + `unshare -n` / Windows: Job Object | Heavy |
| 3 | Read-only filesystem (FU-21) | **No** | Linux: `chroot` / `bind mount` / `unshare -m` / Windows: AppLocker / WDAC | Heavy |
| 4 | 2 GB memory cap (FU-22) | **No** | Linux: `setrlimit(RLIMIT_AS, 2GB)` via `preexec_fn` / Windows: Job Object memory cap | **Light** |

The 3 follow-up implementation BBFs all need the same
architectural change: **bypass pdf2image's
`convert_from_bytes` and call `pdftoppm` directly via
`subprocess.Popen`** with the right sandbox primitives.
The current pdf2image API (per its `convert_from_bytes`
signature) does not expose `preexec_fn`, `cwd`, `env=`,
or any sandbox primitive — it constructs the Popen
internally with `env=os.environ.copy()`. So all three
follow-up BBFs share a common first step: introduce a
new `services/chess_coach/pdf_ocr/subprocess_runner.py`
module that wraps `subprocess.Popen` with the
sandbox-primitive `preexec_fn` callable, then refactor
`services/chess_coach/gateway/routes/pdf_ingest.py`
to use that wrapper instead of `convert_from_bytes`.

**The 3 spike sections (one per FU):**

The brief has 3 sections (A, B, C), one per A-F11
property. Each section audits the current state,
designs the follow-up implementation, and surfaces
what the implementation BBF would look like. Each
follow-up implementation BBF is its own PR; this BBF
just produces the design briefs.

### Section A: FU-20 (network isolation) — heavy lift

**Current state:** pdf2image's `Popen` inherits
`env=os.environ.copy()` from the parent FastAPI
process. The subprocess has full outbound network
access; a malicious PDF that achieves code execution
via a poppler CVE (e.g. CVE-2017-18267) can exfiltrate
data over the network.

**Follow-up BBF design (FU-20-impl):**

Linux path:
1. Add a `preexec_fn=` callable to the new
   `subprocess_runner.py` module that calls
   `os.setsid()` then `subprocess.run(['unshare', '-n', ...])`
   to enter a fresh network namespace.
2. Refactor `pdf_ingest.py` to call pdftoppm via the
   new wrapper instead of `convert_from_bytes`.
3. Add a test that attempts to bind a TCP listener
   inside the subprocess (e.g. via a synthetic PDF
   that triggers a CVE-like behavior) and asserts the
   bind is denied.

Windows path:
1. Use the `win32job` module to create a Job Object
   with `JOB_OBJECT_NET_RATE_CONTROL` flag.
2. The Job Object is inherited by the subprocess via
   the `win32job.AssignProcessToJobObject` call.
3. Add a test that asserts the subprocess cannot make
   outbound TCP connections.

**Cross-platform note:** the implementation must
detect the platform at runtime and apply the
appropriate primitive. The pre-existing platform
detection in `pdf_ocr/protection.py` (env-var based)
can be the model.

**Cost estimate:** ~2-3 hours. Heavy because both
Linux and Windows paths need new code, new tests, and
new CI gates.

### Section B: FU-21 (read-only filesystem) — heavy lift

**Current state:** pdf2image writes its own temp file
via `tempfile.mkstemp()` (typically `%TEMP%\\tmp<random>`
on Windows, `/tmp/tmp<random>` on Linux). The
subprocess has full read-write filesystem access; a
malicious PDF can read or modify anything the FastAPI
process can.

Per A-F11 the per-book artifact dir at
`data/debug/books/<book_id>/` is the ONLY allowed
write target for the parser. This is not enforced.

**Follow-up BBF design (FU-21-impl):**

Linux path:
1. Add a `preexec_fn=` callable that calls
   `os.chroot(per_book_artifact_dir)` after first
   `bind mount`-ing `/dev/null`, `/proc/self/fd/0`,
   `pdftoppm`'s read-only dependencies, and the
   `pdftoppm` binary itself inside the chroot.
2. Or use `unshare -m` for mount-namespace isolation
   without chroot (lighter-weight, but doesn't
   prevent the subprocess from seeing the host FS
   via `/proc`).
3. Refactor `pdf_ingest.py` to use the new wrapper.
4. Add a test that attempts to write to `/etc/passwd`
   from the subprocess (e.g. via a synthetic PDF that
   triggers a CVE-like write) and asserts the write
   is denied.

Windows path:
1. Use AppLocker or Windows Defender Application
   Control (WDAC) to restrict the subprocess to
   read-only access outside the per-book artifact dir.
2. AppLocker is the older, simpler API; WDAC is the
   newer, more flexible API.
3. The implementation must be activated per-process via
   a separate setup step; it's not as clean as Linux's
   `preexec_fn`.

**Cost estimate:** ~2-3 hours. Heavy because of the
chroot/bind-mount setup complexity on Linux and the
AppLocker/WDAC platform dep on Windows.

### Section C: FU-22 (2 GB memory cap) — light lift

**Current state:** No `RLIMIT_AS` (Linux) or Job Object
memory cap (Windows) is applied to the `Popen`
invocation of `pdftoppm`. A malicious PDF can balloon
`pdftoppm` RSS without bound.

The existing 5-minute wall-clock timeout
(`PARSER_TIMEOUT_SECONDS=300`) + outer
`asyncio.wait_for(330)` bounds RUNTIME but not MEMORY.
A PDF that fattens up RSS in the first few seconds will
not be caught by either timeout.

**Follow-up BBF design (FU-22-impl):**

Linux path (1-2 hours, lightest of the three):
1. Add a `preexec_fn=` callable that calls
   `resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))`.
   This is a single function call; the implementation
   is trivial.
2. Refactor `pdf_ingest.py` to use the new wrapper.
3. Add a test that uses a synthetic large-PDF scenario
   (force pdftoppm to allocate > 2 GB) and asserts the
   subprocess is killed with `MemoryError` or
   `OSError` (the perror codes that RLIMIT_AS produces
   when exceeded).

Windows path:
1. Use `win32job` to set
   `JOB_OBJECT_LIMIT_PROCESS_MEMORY` to 2 GB.
2. The Job Object is inherited by the subprocess.
3. Add a test that asserts the subprocess is killed
   when RSS exceeds 2 GB.

**Cost estimate:** ~1-2 hours. Lightest of the three
because `setrlimit` is a single function call on Linux
and the test surface is straightforward (force a
synthetic large-PDF scenario, assert subprocess
killed at 2 GB RSS).

**Why this section is the most actionable:** the
ledger entry for FU-22 explicitly says "Possibly the
most actionable of the three for first implementation:
`RLIMIT_AS` is a single `setrlimit()` call (no
namespace setup, no Job Object API to interact with),
and the test surface is straightforward." This spike
section is the most likely first-implementation target.

### Cross-spike architectural concern: the shared subprocess-wrapper module

All 3 follow-up implementation BBFs need a new
`services/chess_coach/pdf_ocr/subprocess_runner.py`
module that wraps `subprocess.Popen` with the sandbox
primitives. The simplest design: one module with three
`preexec_fn=` callables (one per property), composed
together when both/all are needed.

**Recommended implementation order:**

1. **FU-22-impl first** (lightest, single `setrlimit`
   call). This establishes the
   `subprocess_runner.py` module + the refactor
   pattern. ~1-2 hours.
2. **FU-20-impl second** (Linux `unshare -n` +
   Windows Job Object). Builds on the same module.
   ~2-3 hours.
3. **FU-21-impl last** (chroot + bind-mount or AppLocker
   — the most complex). Builds on the same module.
   ~2-3 hours.

This order is light → medium → heavy, so each
implementation BBF can verify the architectural pattern
before the next one scales it up.

**Work product:**

This BBF produces 2 file changes:

1. `docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md` (NEW,
   this brief).
2. `docs/16_audit/OPEN-FOLLOWUPS.md` (modified, +1
   cross-reference in the FU-20/21/22 entries pointing
   at this brief).

**Out of scope (NOT in this BBF):**

- The actual implementation of properties 2, 3, 4
  (network isolation, read-only fs, 2 GB cap). These
  are the follow-up BBFs (FU-20-impl, FU-21-impl,
  FU-22-impl). This BBF is investigation-first only.
- The conversion of the 3 `pytest.skip` tests in
  `tests/unit/test_pdf_ingest_security.py` (added by
  PR #143) into real tests. That happens in the
  follow-up implementation BBFs.
- The actual `subprocess_runner.py` module. That's
  the first follow-up BBF's scope.
- Refactoring pdf2image or forking pdf2image. Out of
  scope; we work around pdf2image by calling pdftoppm
  directly.

**Honest disclosures:**

- **The investigation-first scope of this BBF is
  intentional.** Per the ledger entries for FU-20/21/22,
  each property is "Real contract gap, but heavy-lift
  caveat applies." Trying to do all 3 implementations
  in one BBF would take 5-8 hours and risks shipping
  incomplete code. Investigation-first is the
  §1.3-honest scope.
- **The 3 follow-up implementation BBFs are NOT in
  scope for this BBF.** The user's directive
  `go FU-20-and-FU-21-and-FU-22` names 3 ledger
  entries, not 3 implementation PRs. The
  investigation-first pattern matches the literal
  ledger entry text.
- **The architectural concern (shared
  `subprocess_runner.py` module) is real.** The 3
  follow-up BBFs all need the same module; an
  implementation-order decision is recommended
  (FU-22 first, then FU-20, then FU-21) so the
  pattern is established with the lightest lift
  first.
- **The `pytest.skip` tests in
  `tests/unit/test_pdf_ingest_security.py` (added by
  PR #143) reference the future implementation BBFs
  by name (FU-22, FU-21, FU-20).** When each
  implementation BBF lands, the corresponding skip
  marker is removed and a real assertion is added
  (per the existing skip reason strings).

**Hermes verification (re-derive, post-merge):**

- `git show main:docs/16_audit/BBF-FU-20-21-22-A-F11-spikes.md`
  shows the 3-section brief with the design notes
  for each property.
- `git show main:docs/16_audit/OPEN-FOLLOWUPS.md |
  grep "BBF-FU-20-21-22-A-F11-spikes.md"` shows the
  cross-reference in the FU-20/21/22 entries.
- `git show main:tests/unit/test_pdf_ingest_security.py |
  grep "pytest.mark.skip"` shows the 3 skip tests
  unchanged from PR #143 (the follow-up implementation
  BBFs turn them into real tests).

**Final report format:** the squash-merge commit body
documents the 3-section brief scope + the 2-file
change + the recommended implementation order
(FU-22 first, then FU-20, then FU-21).
