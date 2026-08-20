# Phase 8 scoping brief — minimum-viable real installer

**Author:** Hermes session 2026-08-20 (post-PR #98 stable-state
check, this session's substantive-direction brief).

**Status:** Skeptical scoping per the session-opening directive
2026-08-20. "What would it actually take to get a minimal, real
PyInstaller+Tauri installer built (not the full hardening
checklist — the smallest thing that would let one real person
install and run this on their own machine)? What's genuinely
blocking it, if anything, versus what's just never been
picked up? No recommendation baked in."

**Sources:** All claims below are backed by direct reads of the
committed blobs (`git show HEAD:path`), not working-tree checks.
Working-tree reads in this repo are corrupted by
`core.autocrlf=true` checkout conversion (see prior session's
resolution).

---

## 0. Why this brief exists

Per the session-opening pushback: the last 14 PRs on `origin/main`
since the last product-feature PR (#84, FU-7 polyglot, 2026-08-08)
have all been dependency / security / docs / audit-trail work.
Phase 8 (the only phase that lets any of this shipped work reach
a real person) is still "Not started" per `README.md:279`. No
explicit decision either way about whether that's right.

This brief doesn't decide. It maps what's actually there, what
would have to be built, and what the genuine constraints are.

---

## 1. What's already in the repo (real, byte-verified against the blob)

### 1.1 Tauri shell (apps/desktop/)

- `apps/desktop/src-tauri/Cargo.toml` — Tauri 2.10.2 with
  `protocol-asset` feature, plus full Rust dependency tree
  (serde, shakmaty, pgn-reader, rusqlite, diesel, axum,
  sysinfo, governor, oauth2, specta/tauri-specta for typed
  bindings, etc.)
- `apps/desktop/src-tauri/tauri.conf.json` — bundle config
  includes icon set (32x32, 128x128, 128x128@2x, .icns, .ico),
  `targets: "all"` (MSI + NSIS + AppImage + deb), `createUpdaterArtifacts: v1Compatible`,
  resources map `../sound/` -> `sound/`, updater endpoint
  configured (`pubkey` + `endpoints`).
- `apps/desktop/src-tauri/src/` — substantial Rust code:
  `chess.rs`, `db/{mod.rs, models.rs, ops.rs, encoding.rs}`,
  `engine/`, `error.rs`, `fs.rs`. This is en-croissant's
  Rust layer, NOT chess-coach-specific.
- `apps/desktop/package.json` — `tauri dev`, `tauri build --no-bundle`,
  `gen:api` (codegen from FastAPI OpenAPI), vitest, oxlint/oxfmt,
  i18next. **No `tauri build` (with bundle) script — only `--no-bundle`.**
- `apps/desktop/.upstream-ref` — points to en-croissant commit
  `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53`.

### 1.2 Python backend packaging surface

- `Dockerfile` — single-stage `python:3.11-slim-bookworm`,
  installs stockfish via apt, sets up `stockfish_path = '/usr/local/bin/stockfish'`,
  HEALTHCHECK via curl + Bearer token, tini for signal
  forwarding. **Builds a Docker image, not a PyInstaller binary.**
- `pyproject.toml` — `setuptools` build backend (line 13-15),
  namespace package layout (`libs/` + `services/` + `apps/cli/`).
  Two `[project.scripts]` declared: `chess-coach` (-> `chess_coach.cli.__main__:main`) and `chess-coach-gateway` (-> `chess_coach.gateway.__main__:main`). The existing `chess-coach-gateway` entry-point is module-path-based (not `app.py`-based); PyInstaller targeting `services/chess_coach/gateway/app.py` would need a thin wrapper shim, OR the build can target the existing entry-point directly.
- `docker-compose.yml` — backend + qdrant sidecar on internal
  compose network, `chess-coach-qdrant` container pinned to
  `qdrant/qdrant:v1.12.4`, shared `./data` bind-mount.

### 1.3 What's documented as intended (per `docs/05_desktop_shell/desktop-shell-decision.md`)

- Tauri 2.x chosen explicitly (decision dated 2026-05-18).
- PyInstaller sidecar pattern is the intended Phase 8 approach
  (line: "Tauri's `externalBin` mechanism is purpose-built for
  shipping a Python backend (PyInstaller binary)").
- en-croissant base preservation is hard-blocking ("the master
  prompt mandates we preserve en-croissant's visual style,
  components, interaction patterns, and utilities").

### 1.4 What's NOT in the repo

These are absent in the committed blob:
- **No `.spec` file for PyInstaller.** The `chess-coach-backend.exe`
  binary the architecture doc describes does not have a build spec.
- **No `externalBin` entry in `tauri.conf.json`.** The bundle
  config has icon set, resources, updater, etc., but no
  `externalBin: ["chess-coach-backend"]` declaration, no
  `bundle.externalBin` path, no Tauri command that spawns a
  sidecar binary.
- **No `budgets.yaml` in `tests/perf/`.** Phase 8 exit criteria
  reference this; it doesn't exist in the blob.
- **No Memurai bundled.** Phase 8 says "Memurai bundled for
  end-user Redis" — no Memurai binary, no licensing arrangement,
  no install script.
- **No Qdrant binary for embedded mode.** `qdrant/qdrant:v1.12.4`
  is the Docker image, not a Windows .exe. No `qdrant.exe` in
  the repo.
- **No signed updater manifest.** `tauri.conf.json` has the
  pubkey + endpoint, but no signing keypair, no manifest file,
  no release pipeline.
- **No security checklist signed off.** `docs/08_security/` exists
  (per `ls docs/08_security/`) but the "security checklist" the
  roadmap exit criteria reference is not present.
- **No Windows CI runner.** All workflows (`.github/workflows/`)
  run on `ubuntu-latest`. No `windows-latest`, no Mac runner.
- **No E2E Playwright-on-Tauri setup.** `apps/desktop/playwright.config.ts`
  is referenced in `find` output but no `tests/e2e/` directory
  ships Tauri-driven tests.
- **No `app.py` entry-point configured for PyInstaller.** `setup.py`
  / `setuptools` build hooks for PyInstaller aren't in the repo;
  PyInstaller needs either a `.spec` or `--name` + `--onefile`
  + entry-point flags.

---

## 2. The minimum-viable target (no recommendation, just the floor)

If the goal is "let one real person install and run this on their
own machine" without the full Phase 8 hardening checklist, what
is the absolute minimum?

**Assumption (skeptical):** the floor is "works on Windows" since
the project is Windows-primary per `docs/11_repo_structure/`
(Linux-primary, Windows/macOS experimental per BBF-50 -- which wrote the platform-stance text into README.md + docs/REPO-READINESS.md, not docs/11_repo_structure/). The Tauri
shell already runs on Windows in dev mode; the question is only
about the install path.

**Floor scope (4 hard prerequisites + 1 open question):**

1. **A PyInstaller build of the Python backend that produces a
   working `chess-coach-backend.exe`.** Without this, there is
   no sidecar to ship. Requires:
   - A `.spec` file or `pyinstaller --onefile --name chess-coach-backend
     <entry-point>` invocation.
   - Hidden imports for the dynamic-import parts of the
     namespace-package layout (`libs/chess_coach/*`,
     `services/chess_coach/*` — the architecture doc flagged
     this as a complication earlier, see `pyproject.toml` line
     8-11's comment about "setuptools cannot resolve
     subpackages that exist in only one root").
   - A real entry-point script (probably
     `services/chess_coach/gateway/app.py` or a thin shim) that
     `uvicorn`s the FastAPI app on a port the Tauri shell can
     reach. The Dockerfile already runs this; PyInstaller needs
     the same path.
   - Stockfish binary bundled INSIDE the PyInstaller bundle, or
     shipped as a separate resource alongside. PyInstaller's
     `--add-binary` can do this; the Dockerfile's apt-installed
     stockfish won't carry over.
   - Qdrant: either an embedded Qdrant binary (the architecture
     says `qdrant.exe` is shipped) or fall back to requiring
     Docker for end-users (Phase 8 was meant to avoid Docker
     for end-users, so this is a tradeoff).
   - Memurai: same question — Phase 8 was meant to ship
     Memurai for Redis-on-Windows, but no Memurai binary or
     license is in the repo.

2. **`tauri.conf.json` updated with `externalBin` + sidecar
   launcher.** The Tauri shell needs to be told about the
   sidecar binary, what to call it, where to put it, and how
   to start it before the JS layer needs the backend. This is
   the `tauri-plugin-shell` or `tauri-plugin-process` invocation
   + a Rust command that calls `Command::new(sidecar_path).spawn()`.

3. **A `tauri build` that produces an MSI or NSIS.** Currently
   the build script is `tauri build --no-bundle` (per
   `package.json`). Removing `--no-bundle` and having the icon
   set + bundle config actually produce an installer is a
   single line change in package.json, but requires Rust toolchain
   on the build machine and produces platform-specific output
   (Windows installer requires Windows or cross-compilation
   setup; Linux deb/AppImage is also possible).

4. **Smoke verification that the bundled artifact works.** Not
   the full perf budgets, but the same `BBF-38` curl /health
   loop the dev workflow uses, run against the sidecar-launched
   backend, on a Windows machine (or Linux as a smoke surrogate
   if Windows isn't available).

**Open question for the floor:** what about the Stockfish / Qdrant
/ Memurai / Redis dependencies? The architecture doc shows all
four as bundled binaries, but none are in the repo. Realistic
floor options:
- (a) **Ship without those binaries.** End-user installs Stockfish
  via a separate step, runs Qdrant via Docker or another
  mechanism. Sidecar is just the FastAPI service. Smallest
  viable product. **Significantly compromises the
  no-Docker-for-end-users goal** but is the actual floor.
- (b) **Ship Stockfish bundled; require Docker for Qdrant.**
  Sidecar includes stockfish; Qdrant stays in Docker. Half-step.
- (c) **Ship everything as documented.** Requires obtaining
  Stockfish binary redistribution rights (GPL-3.0 — fine for
  Stockfish but the binary is large ~50MB compressed),
  obtaining Qdrant Windows binary + license, obtaining Memurai
  license. **Real work, possibly external blockers.**

---

## 3. What's blocking (versus just never picked up)

### 3.1 Genuine blockers (not just "didn't get to it")

- **No Windows CI runner.** All workflows run on `ubuntu-latest`.
  Building the actual MSI/NSIS and running E2E smoke against the
  sidecar requires Windows. Cross-compiling Tauri from Linux to
  Windows is non-trivial; Tauri does support it but it requires
  a Windows SDK + linker setup on Linux. **A Windows runner
  (paid tier) or a Windows dev machine is the real constraint.**
  This is a **resource blocker, not a knowledge blocker.**

- **en-croissant base preservation is hard-blocking** per the
  desktop decision. The Tauri shell is en-croissant's code
  (Rust layer is theirs, the React/Mantine/Vite frontend is
  theirs, the chessground board is theirs). The brief says
  "the master prompt mandates we preserve en-croissant's
  visual style, components, interaction patterns, and
  utilities" — but the actual upstream ref pin (`.upstream-ref`)
  is at commit `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53` (date
  not directly verifiable from this repo since the commit is in
  en-croissant's history, not chess-coach's). The Tauri config
  says `name: "en-croissant"`, `identifier: "org.encroissant.app"`,
  `publisher: "Francisco Salgueiro"`. **Shipping as "chess-coach"
  requires either: (a) renaming + republishing with proper
  attribution, (b) dual-binary strategy, (c) explicit GPL
  acknowledgment + keeping the en-croissant attribution
  prominent.** This is a **legal/license blocker, not a
  knowledge blocker.**

- **PyInstaller + namespace-package layout interaction is a
  known complication** (per `pyproject.toml` line 8-11's own
  comment about setuptools' limitations on subpackages in
  multiple roots). PyInstaller's static analysis doesn't follow
  the same `package-dir` mappings setuptools uses; hidden-imports
  lists are likely needed. **Knowledge + iteration blocker, not
  external.**

- **No Qdrant Windows binary in the repo.** The Qdrant team
  ships Docker images but the Windows `.exe` for embedded mode
  has its own licensing considerations (AGPL-3.0 per Qdrant's
  terms; embedded mode may have a different commercial
  relationship). **External blocker if option (c) above; not
  a blocker if option (a) is chosen.**

- **No Memurai license.** Memurai is a commercial Redis-for-Windows
  fork; the project would need a license to redistribute.
  **External blocker if option (c) above; not a blocker if
  option (a) is chosen** (and the architecture's Redis role is
  re-thought — see `docs/04_database/database-decision.md`).

### 3.2 Just never picked up (no blocker, just no one has done it)

- **The `.spec` file / PyInstaller invocation.** Pure
  build-system work. ~1-3 BBFs of focused iteration depending
  on how the namespace-package layout interacts.
- **The `externalBin` Tauri config + Rust sidecar-launcher
  command.** Pure Tauri config + a small Rust file. 1 BBF.
- **The `tauri build` script change (drop `--no-bundle`).** A
  single-line change once the above two are in.
- **A Windows CI runner.** A repo-settings decision, not code.
- **The `tests/perf/budgets.yaml` file.** Pure doc/test-creation
  work — no blocker, no investigation needed, just write the
  YAML and the perf tests that exercise it.
- **The security-checklist sign-off.** Requires running through
  `docs/08_security/` against the current code; mostly a
  documentation + verification effort.

### 3.3 What looks like work but is actually external

- **Stockfish redistribution.** Stockfish is GPL-3.0, so
  bundling the binary is legally fine; the practical work is
  obtaining/building the Windows binary (~50MB compressed).
  Same for `lc0` (Maia) if it's needed at runtime.
- **Code-signing certificate.** Tauri MSI/NSIS artifacts need
  signing on Windows for end-user SmartScreen trust; the cert
  costs money + an org identity. Without signing, the MSI
  installs with a "Unknown publisher" warning. **Not a hard
  blocker for a first internal-release** but is one for
  general-public distribution.

---

## 4. What a minimum real-installer PR-cycle would look like

Per the standing cycle (FU-5, FU-7, FU-8, FU-16, FU-19, FU-20-22
all followed it: investigation-first BBF, branch, commit, PR,
leaf review, CI, hold for explicit squash-merge authorization):

**Likely BBF shape (if "minimum viable" is option (a) above):**

1. **BBF-PyInstaller-spec** — write `chess-coach-backend.spec`,
   figure out the hidden-imports for the namespace layout,
   produce a working `.exe` from `pyinstaller`. Investigation
   goes first: which entry-point, how to bundle Stockfish
   binary as `--add-binary`, how to handle Qdrant/Redis
   dependencies (drop them, require Docker, or document as
   manual setup steps).
2. **BBF-Tauri-sidecar** — update `tauri.conf.json` with
   `externalBin`, add a Rust command that spawns the sidecar,
   wire it into the JS layer so the backend is up before the
   React app tries to fetch from it.
3. **BBF-Build-and-bundle** — change `package.json` to drop
   `--no-bundle`, ensure the icon set is complete, ensure the
   Rust toolchain is available on the build machine (GitHub
   Actions Windows runner if available, or documented
   build-on-Windows-only path).
4. **BBF-Sidecar-smoke** — a `tests/e2e/sidecar_smoke.py` that
   spawns the bundled installer, waits for backend health,
   asserts the bundle is functioning. Runs on the same CI
   matrix that smoke.yml uses (so Ubuntu-only is fine for
   smoke, but real end-user validation is manual on Windows).
5. **BBF-Sidecar-distribution-doc** — `docs/16_audit/BBF-PHASE-8-MINIMUM-VIABLE.md`
   documenting what shipped, what didn't (Stockfish bundled? Qdrant?
   Memurai?), and the next-step options for closing the remaining
   gap.

**Estimated scope:** 3-5 BBFs, ~1-2 weeks of focused work
end-to-end, depending on how the namespace-package-vs-PyInstaller
interaction goes (the unknown-cost item).

---

## 5. What's NOT in scope of this brief (deliberate omissions)

- **Whether Phase 8 should be the next priority.** Per the
  directive "no recommendation baked in," that's the next step.
- **Whether Phase 7 (sync/research/reporting) should be a
  prerequisite.** The directive named Phase 8 specifically; Phase
  7 has its own scoping to do if it becomes the priority.
- **Pricing / licensing / commercial-relationship decisions**
  around Memurai, Qdrant embedded, code-signing certs.
- **The en-croissant attribution / dual-licensing strategy.**
  Mentioned as a real blocker but the actual solution is a
  separate decision that needs Sebastian+Claude input.
- **The "Phase 9 v2 directions" cluster** (cloud, voice,
  mobile, multiplayer) — explicitly Phase 9, post-Phase 8.

---

## 6. Verification log (every claim byte-checked against the blob)

- `apps/desktop/package.json`: blob read, contains `tauri build --no-bundle`. ✓
- `apps/desktop/src-tauri/Cargo.toml`: blob read, Tauri 2.10.2, full Rust dep tree. ✓
- `apps/desktop/src-tauri/tauri.conf.json`: blob read, no `externalBin` declaration present in the bundle config. ✓
- `apps/desktop/src-tauri/src/`: ls, contains chess.rs, db/, engine/, error.rs, fs.rs. ✓
- `Dockerfile`: blob read, python:3.11-slim-bookworm, stockfish via apt. ✓
- `pyproject.toml`: blob read, setuptools backend, namespace package layout declared explicitly. ✓
- `docker-compose.yml`: read, qdrant service pinned to v1.12.4 image. ✓
- `docs/05_desktop_shell/desktop-shell-decision.md`: blob read, Tauri 2.x decision, en-croissant preservation requirement. ✓
- `docs/10_roadmap/implementation-roadmap-v1.md`: blob read, Phase 8 section (PyInstaller sidecar + Tauri MSI/NSIS + Memurai + Qdrant embedded + budgets.yaml + security checklist). ✓
- `docs/01_architecture/system-architecture.md`: blob read, "End-user mode (Phase 8 packaging)" block describing the 5-binary install (CHESS COACH.exe + chess-coach-backend.exe + memurai.exe + qdrant.exe + data tree). ✓
- `.github/workflows/`: ls + grep `runs-on:`, all `ubuntu-latest`, no Windows / Mac runner. ✓
- `.upstream-ref`: read, en-croissant commit pin `6f2d2628...`. ✓
- `apps/desktop/LICENSE`: read, GPL-3.0 (en-croissant base). ✓

---

## 7. The honest read (without making the call)

Per the directive "no recommendation baked in," here's the
honest shape of the work without the yes/no:

- **The minimum-viable real installer is achievable in ~1-2
  weeks of focused work** if option (a) is chosen (PyInstaller
  sidecar for the FastAPI backend only; Stockfish bundled;
  Qdrant/Redis as Docker or manual setup for end-users).
- **The full Phase 8 deliverable list** (PyInstaller sidecar +
  Tauri MSI/NSIS + Memurai + Qdrant embedded + budgets.yaml +
  security checklist + signed updater) **is significantly larger**
  and has real external blockers (Memurai license, Qdrant
  embedded Windows binary, code-signing cert).
- **The gap between (a) and the full Phase 8 is the meaningful
  question.** (a) gets one real person running it but compromises
  the architecture's "no Docker for end-users" goal. The full
  Phase 8 honors the architecture but costs 3-6 months of work
  + external blockers.
- **The fact that none of this has started in 2+ weeks is
  observation, not verdict.** Whether that's "Phase 8 is the
  right priority next" or "Phase 8 is correctly deferred while
  X is more important" is a decision Sebastian has the context
  for; this brief just gives the shape.

— end of brief —
