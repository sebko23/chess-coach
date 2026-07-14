# ADR-0006: Engine pool failure modes and concurrent request handling

- **Status**: accepted
- **Date**: 2026-07-14
- **Deciders**: project owner
- **Consulted**: External developer review (2026-07-14)

## Context

The external developer review (2026-07-14) raised concerns about
several potential failure modes in `engine_orch/pool.py` and
`gateway/routes/eval_graph.py`. This ADR documents the audit
findings, the decision to defer code fixes to separate sprints,
and the reasoning behind that deferral.

The audit was performed by reading the actual code in the chess-coach
repo (not by guessing from the rendered view), with the goal of
distinguishing real bugs from speculative concerns.

## Decision

BBF-34 ships documentation only (the audit summary below + the
README/docs updates). The three real bugs identified by the audit
are tracked as separate sprints (BBF-35, BBF-36, BBF-37) to be
scoped and verified independently.

## Audit findings

### Finding 1: Engine pool has no timeouts on Stockfish calls

**Severity**: real (silent failure mode)

**Code location**: `services/chess_coach/engine_orch/pool.py`,
lines 130-145 (`analyze()` method, the `async for ev in engine.go(...)`
loop).

**What the code does**: the `async for` loop has no outer
`asyncio.wait_for(..., timeout=...)`. If Stockfish hangs (malformed
FEN, segfault while still holding stdout, UCI protocol mismatch),
the gather in `eval_graph.py` waits forever.

**What the reviewer's concern was**: same finding, framed as
"hanging reads from Stockfish". The reviewer suggested wrapping
engine I/O in `asyncio.wait_for` with a clear timeout.

**Decision**: **defer to BBF-35**. The fix is small (~10 lines)
but needs:
1. A defined timeout value (default candidates: 30 s for `go()`,
   5 s for `quit()`)
2. A recovery path when the timeout fires (mark the slot's
   engine as None so the next request gets a fresh subprocess)
3. A regression test that exercises the timeout path

Without all three, the fix could turn one failure mode into
another.

**Current behavior** (for the BBF-34 audit record, since this
gates users today):
- A hung Stockfish call blocks one pool slot AND its semaphore
  permit
- Subsequent requests for the same game wait on the semaphore
- Requests for other games continue normally if there are free
  slots
- The only recovery is a backend restart (kills all subprocesses)

### Finding 2: Engine pool reuses dead subprocesses

**Severity**: real (silent failure mode)

**Code location**: `services/chess_coach/engine_orch/pool.py`,
`_acquire()` method (around line 240). The check is
`if slot.engine is None or slot.engine._proc is None` but
`slot.engine` is only set to None if the **initial** start fails.
A subprocess that dies *after* a successful start (segfault,
OOM kill, parent process group kill) leaves `slot.engine._proc`
non-None but with a dead pid.

**What the code does**: `slot.engine._proc` is checked once at
construction. There's no `.poll()` check inside the loop. If
the subprocess dies after the first analysis, the next request
acquires the slot, calls `engine.position()`, and waits forever
for the dead process.

**What the reviewer's concern was**: framed as "zombie slots
that always fail". The reviewer suggested `proc.poll()` checking
+ log + restart.

**Decision**: **defer to BBF-35**, ideally in the same commit as
Finding 1. The fix is a 5-line addition to `_acquire()`: check
`slot.engine._proc.poll() is not None` and reset
`slot.engine = None` if so.

### Finding 3: Eval graph concurrent-request race

**Severity**: real but benign

**Code location**: `services/chess_coach/gateway/routes/eval_graph.py`,
the route handler at lines ~200-260.

**What the code does**:
1. Phase 1: SELECT positions + LEFT JOIN analyses. Identifies
   the `missing` list.
2. Phase 2: `asyncio.gather(*tasks, return_exceptions=True)` runs
   Stockfish analyses for missing positions and INSERTs each
   one.
3. Phase 3: re-read the freshly-inserted rows.

**Race**: two concurrent requests for the same game's eval-graph:
- Both see the same `missing` positions
- Both INSERT into `analyses`
- The `analyses` table has a primary key on
  `(position_id, engine_id, depth, settings_hash)` which causes
  one INSERT to win and the other to raise `IntegrityError`
- `return_exceptions=True` swallows it silently
- Wasted Stockfish work but no corruption

**What the reviewer's concern was**: framed as "race conditions
on first access" with a suggestion for `defaultdict(asyncio.Lock)`
per-key dedup.

**Decision**: **defer to BBF-36**. The dedup is ~15 lines and is
a clean optimization (avoids duplicated Stockfish calls under
concurrent traffic for the same game). Verifying requires either:
- A load test that hammers the eval-graph endpoint with N
  concurrent requests for the same game
- A unit test with mocked Stockfish that asserts dedup

Both require their own setup; doesn't fit in BBF-34's docs scope.

**Current behavior** (for the audit record):
- The `analyses` table's primary key prevents corruption
- `return_exceptions=True` on the gather prevents 500s
- Wasted Stockfish work: N concurrent requests compute N analyses
  per cache-miss position, only the first INSERT wins
- End-user impact: identical results to a single request; just
  slower

### Finding 4: Desktop hardcodes the wrong data dir on Windows

**Severity**: real (UX bug, not data-corruption)

**Code location**: `apps/desktop/src/state/atoms/coach.ts`,
around line 65 (`backendDescriptorPathAtom`).

**What the code does**: the desktop resolves the backend
descriptor at `$HOME/.local/share/chess-coach/runtime/backend.json`
on all platforms. It does **not** read `CHESS_COACH_DATA_DIR`.

**What the backend writes** (`services/chess_coach/gateway/config.py`):
- Linux: `~/.local/share/chess-coach/runtime/backend.json` ✓
- macOS: `~/Library/Application Support/chess-coach/runtime/backend.json` ✗
- Windows: `%LOCALAPPDATA%\chess-coach\runtime\backend.json` ✗

On macOS and Windows, the desktop's hardcoded path **does not
match** the backend's actual path. A user who sets
`CHESS_COACH_DATA_DIR` consistently on both works around the bug,
but the defaults don't match.

**What the reviewer's concern was**: framed as "path mismatches"
in section 6.1.

**Decision**: **defer to BBF-37**. The fix needs:
1. Read `CHESS_COACH_DATA_DIR` from Tauri env (different API than
   browser env — uses `@tauri-apps/api/window` or `process.env` via
   the `@tauri-apps/plugin-os` plugin depending on Tauri version)
2. Match the backend's three platform defaults
3. Test on all three platforms (linux: docker compose, macOS: not
   possible from this dev environment, Windows: agentZero is
   Linux-only)

The Tauri env API is unfamiliar enough that this needs a careful
read of `apps/desktop/src-tauri/` first. Doesn't fit in BBF-34.

**Current behavior** (for the audit record):
- Linux users: works out of the box
- macOS users: desktop shows "backend not found" by default; can
  work around by exporting `CHESS_COACH_DATA_DIR`
  consistently in both shells
- Windows users: same; the workaround path needs both shells to
  set `CHESS_COACH_DATA_DIR=$HOME/AppData/Local/chess-coach` (or
  the dev sets a shared location)
- Linux users who set `CHESS_COACH_DATA_DIR` to a non-default
  location: must set it in **both** the backend launch and the
  desktop launch

### Finding 5: PGN parser breaks on first malformed game

**Severity**: minor (existing behavior, not new)

**Code location**: `services/chess_coach/gateway/routes/pgn_import.py`,
around line 164.

**What the code does**: when `chess.pgn.read_game()` raises,
the loop `break`s, ending the import. Subsequent (potentially
valid) games in the same PGN are dropped.

**Decision**: **defer indefinitely**. This is documented behavior;
the loop break is conservative (the parser may have consumed
input in an unrecoverable state, so continuing could be worse).
A more sophisticated fix would catch the exception, store the
position consumed so far, and continue from there. That's a
real but non-trivial fix; defer to a separate sprint if the
reviewer or a user reports it.

## Alternatives considered

| Option | Pros | Cons | Rejected because |
|---|---|---|---|
| Land all fixes in BBF-34 | Single sprint chain | Mixes docs and code; harder to verify; no proper regression tests for engine pool changes | Yes, defer fixes |
| Land docs only in BBF-34 | Matches the user's explicit "Just do BBF-34 as proposed"; preserves BBF-N brief workflow | Three real bugs remain in code | Yes, this is the chosen path |
| Skip the audit entirely | Smaller commit | Reviewer's concerns would rot undocumented; next dev has to redo the audit | Yes, do the audit |

## Consequences

### Positive

- The three real bugs (engine pool timeouts, eval-graph race,
  desktop discovery) are now **documented with code-level
  evidence** rather than speculative concerns
- Each gets its own sprint with its own verification
- The docs (license matrix, README, docs/README.md, tests/README.md)
  ship in a single self-contained sprint
- Reviewer gets honest answers (yes/no/maybe) rather than a
  blanket "good catch, will fix"
- Future contributors can read this ADR to learn what's already
  been audited

### Negative / accepted tradeoffs

- The repo is shipped with three known bugs (BBF-35/36/37 fixes
  pending)
- Users who hit the engine pool timeout bug today have no
  recourse except a backend restart
- The Windows desktop discovery bug ships, fixed only by an
  env-var workaround
- The "race" findings carry semantic weight — "real but benign"
  reads like hand-waving. Mitigation: each finding has explicit
  "Current behavior" sentences documenting the user-visible impact
  for users today

## Follow-ons (separate sprints)

- BBF-35: engine pool timeout + dead-subprocess recovery (~15 LOC,
  ~1 day)
- BBF-36: eval-graph concurrent-request dedup (~15 LOC, ~0.5 day)
- BBF-37: desktop discovery env-var support on macOS/Windows
  (~20 LOC + Tauri plugin read, ~1 day; needs macOS/Windows
  validation)

Refs: External developer review (2026-07-14); ADR-0001 (async/sync
boundary, which the engine pool code follows); ADR-0005 (coach state
jotai, the desktop file involved)
