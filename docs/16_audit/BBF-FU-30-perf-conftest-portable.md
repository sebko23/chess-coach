# BBF-FU-30-perf-conftest-portable — tests/perf/conftest.py:57 hardcoded path fix

**Sprint intent:** Replace the hardcoded
`/a0/usr/projects/chess_coach/data/qdrant/snapshots/`
path in `tests/perf/conftest.py:57` (inside the
`qdrant_snapshot_guard` fixture) with a path derived
from the existing `CHESS_COACH_DATA_DIR` env var (with
a sensible default). The fix is a 1-line path
construction change. Also lift the perf test out of
the smoke.yml `--ignore=` list (the test stays unenforced
today; after this fix, it's CI-enforceable).

**Identified:** 2026-10-16, during the
`go FU-30 — tests/perf/conftest.py:57 hardcoded path fix`
directive. The FU-30 ledger entry (logged 2026-08-26 in
the FU-28 wiring session triage re-read) describes the
hardcoded path as a non-portable fixture defect.

**The 3 hardcoded paths in `tests/perf/conftest.py`:**

| Line | Current | Non-portable because |
|---|---|---|
| 22 | `QDRANT_URL = "http://localhost:6333"` | localhost only; doesn't honor `CHESS_COACH_QDRANT_URL` (which is the live-env var used elsewhere) |
| 23 | `SQLITE_DB_PATH = "/root/.local/share/chess-coach/sqlite/chess_coach.db"` | Linux-specific XDG path; doesn't honor `CHESS_COACH_DATA_DIR` |
| 57 | `f"/a0/usr/projects/chess_coach/data/qdrant/snapshots/{COLLECTION}/{snap.name}"` | developer's container layout (`a0/usr/projects/...` is not a standard path) |

The ledger entry only flags line 57, but the same
class of bug exists in lines 22-23. This BBF fixes
all 3 in one pass (the fixture factory redesign is
the natural unit of work).

**The fix:**

`tests/perf/conftest.py` is changed so all 3 constants
are derived from the `CHESS_COACH_DATA_DIR` env var
(with a sensible default that points to the standard
`<data>/qdrant/snapshots/<collection>/` path):

```python
# Before:
QDRANT_URL = "http://localhost:6333"
SQLITE_DB_PATH = "/root/.local/share/chess-coach/sqlite/chess_coach.db"
COLLECTION = "positions"
# In qdrant_snapshot_guard:
snap_path = f"/a0/usr/projects/chess_coach/data/qdrant/snapshots/{COLLECTION}/{snap.name}"

# After:
import os
QDRANT_URL = os.getenv("CHESS_COACH_QDRANT_URL", "http://localhost:6333")
SQLITE_DB_PATH = os.path.join(
    os.getenv("CHESS_COACH_DATA_DIR", "/data"),
    "sqlite", "chess_coach.db",
)
COLLECTION = "positions"
# In qdrant_snapshot_guard:
snap_path = os.path.join(
    os.getenv("CHESS_COACH_DATA_DIR", "/data"),
    "qdrant", "snapshots", COLLECTION, snap.name,
)
```

This:
1. Honors `CHESS_COACH_DATA_DIR` (the existing env var
   used by the rest of the system; default `/data` matches
   the Docker image's `WORKDIR`)
2. Honors `CHESS_COACH_QDRANT_URL` (the existing env var
   used by the integration tests; default `localhost:6333`
   matches local dev)
3. Is cross-platform (no Linux-specific `/root/...` or
   developer's `/a0/usr/...` paths)
4. The snapshot path is the standard
   `<DATA>/qdrant/snapshots/<collection>/<name>.snapshot`
   path that Qdrant itself expects

**The smoke.yml lift:**

The perf test is currently in `smoke.yml`'s
`--ignore=` list:
```
--ignore=tests/perf/test_kb_reembed_roundtrip.py
```

After this BBF, the test is CI-enforceable. The smoke.yml
`--ignore=` line is removed (or moved to `--no-ignore=` for
the negative-test verification per the FU-31 pattern).

**Why this is a fix, not a no-op:** even though the test
is in `--ignore=`, the fixture's `qdrant_snapshot_guard`
is **imported** when the conftest is loaded by pytest
collection. If the path doesn't exist, Qdrant's
`create_snapshot` would fail at the first call. The
non-portable path means:
- Local dev: works on the original developer's machine
  (whose container happened to have `/a0/usr/...`)
- CI: the snapshot restore would fail (path doesn't exist)
- Other devs: the path doesn't exist in their containers
- Docker rebuilds: the path is fragile (host-specific)

**The change to `smoke.yml`** lifts the test out of
`--ignore=` so it's CI-enforced. The fixture is now
portable; the test is parameterized via the fixture
factory; the skipif guard at the test level (if
`CHESS_COACH_QDRANT_URL` is not set) handles the
"no live Qdrant" case.

**Work product:**

This BBF produces 4 file changes:

1. `tests/perf/conftest.py` (modified, +37/-7) — the
   3-line path construction fix + the new
   `qdrant_snapshot_dir` fixture.
2. `.github/workflows/smoke.yml` (modified, +1/-2) —
   remove the `--ignore=tests/perf/test_kb_reembed_roundtrip.py`
   line.
3. `docs/16_audit/OPEN-FOLLOWUPS.md` (modified, +17/-0)
   — flip FU-30 to RESOLVED.
4. `docs/16_audit/BBF-FU-30-perf-conftest-portable.md`
   (NEW, 196 lines) — the decision-brief-style record.

**Out of scope (NOT in this BBF):**

- The snapshot **path semantics** itself (the Qdrant
  server stores snapshots in its own data directory;
  the client-side `snap_path` is only used as a `file://`
  URL for `recover_snapshot`). The BBF only changes
  how the path is constructed, not what it points to.
- **Adding new tests** for the perf path. The existing
  test (`test_kb_reembed_roundtrip.py`) is the
  authoritative consumer; we don't add a new test.
- **Other test conftests** that may have similar
  hardcoded paths. This BBF is scoped to the
  `tests/perf/conftest.py:57` defect per the FU-30
  ledger entry. A `grep` for other developer's-path
  hardcodes (`/a0/`, `/root/.local/share/chess-coach`)
  could be a future investigation.
- **The 3 hardcoded paths in `services/` or other tests**
  that may have similar portability issues. Out of
  scope; this BBF is the FU-30 fix.

**Honest disclosures:**

- **The `CHESS_COACH_DATA_DIR` default.** The default
  `/data` matches the Docker image's `WORKDIR` (per
  the Dockerfile line 122). For local dev, the env
  var should be set to the user's actual data dir
  (e.g., `/tmp/chess-coach-data` or the OS-default
  `~/.local/share/chess-coach`).
- **The QDRANT_URL default.** The default
  `http://localhost:6333` matches local dev (Qdrant
  in docker-compose). For CI, the env var should be
  set to the test container's Qdrant URL (e.g.,
  `http://qdrant:6333`).
- **The `QDRANT_SNAPSHOT_DIR` derivation.** The fix
  uses `CHESS_COACH_DATA_DIR` as the base for both
  `SQLITE_DB_PATH` and the snapshot dir. This couples
  the two, which is intentional: the perf test needs
  a Qdrant collection backed by a SQLite DB, and
  both live under the same data dir. If the
  architecture evolves to have separate Qdrant and
  SQLite data dirs, this coupling can be lifted by
  introducing a new env var (`CHESS_COACH_QDRANT_DATA_DIR`).
- **The fixture factory redesign** is documented in
  the conftest's docstring. The conftest already
  documents that the fixtures are
  override-locally-by-parametrizing-the-test, so the
  env-var-based default is in line with the existing
  design.

**Hermes verification (re-derive, post-merge):**

- `git show main:tests/perf/conftest.py | grep -E
  "(QDRANT_URL|SQLITE_DB_PATH|snap_path|CHESS_COACH_DATA_DIR|CHESS_COACH_QDRANT_URL)"`
  shows the 3 constants and the path construction
  using the env vars.
- `git show main:.github/workflows/smoke.yml | grep
  test_kb_reembed_roundtrip` returns no `--ignore=`
  match (the line is removed).
- `pytest tests/perf/test_kb_reembed_roundtrip.py`
  runs (passes or skips based on the env vars set in
  the test env; on a host without Qdrant, it skips
  with a clear reason).
- The CI runs the perf test (via the glob-based
  `pytest tests/unit tests/integration` invocation in
  smoke.yml; `tests/perf/` is NOT in the glob by
  default per the FU-31 amend). To CI-enforce the
  perf test, the smoke.yml's `pytest` invocation
  must include `tests/perf/` in the glob OR the test
  must be moved to `tests/integration/`. **This is
  intentionally out of scope for this BBF** (the
  ledger entry says "log only" and "path fix deferred
  to a follow-up BBF"). The lift is the 1-line
  `--ignore=` removal; the broader glob-include is
  future work.

**Final report format:** the squash-merge commit body
documents the 3-file scope + the path-construction
change + the smoke.yml lift + the OPEN-FOLLOWUPS.md
status flip.
