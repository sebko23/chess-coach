# Session Handover — Maia Engine Fix

**Date:** 2026-06-15
**Status:** WIP commit `e8c76ca` — engine registers, analysis fails
**Next session task:** 20-min targeted edit, NOT a full session

---

## Current state

| Item | State |
|------|-------|
| `EngineSpec` extra_args support | ✅ committed (`extra_args: list[str] = field(default_factory=list)`) |
| Maia spec registered in pool | ✅ committed (`lc0` + `--weights=...` + `--backend=blas`) |
| lc0 binary | ✅ present at `/a0/usr/projects/chess_coach/data/engines/lc0` |
| maia-1500.pb | ✅ present at `/a0/usr/projects/chess_coach/data/engines/maia-1500.pb` |
| `GET /v1/engines` | ✅ returns Maia-1500 entry |
| `POST /v1/analysis` with Maia | ❌ HANGS — see bugs below |

---

## Known bugs (root cause confirmed)

### Bug 1: lc0 rejects `Hash` and `Threads` setoption

**Symptom:**
```
error Unknown option
```
**Cause:** lc0 has no UCI `Hash` or `Threads` options — it manages its own backend threads and uses the `BackendOptions` system instead. `setoption Hash 64` / `setoption Threads 2` fail.

**Location:** `services/chess_coach/engine_orch/pool.py` — `analyze()` method unconditionally calls:
```python
options.setdefault("Threads", self._default_threads)
options.setdefault("Hash", self._default_hash_mb)
```

### Bug 2: UCI handshake breaks waiting for `readyok`

**Symptom:** After failed setoption, lc0 stops responding to `isready` → `readyok` never arrives → `wait_for_ready` times out.

**Cause:** Cascading from Bug 1. Once setoption fails, the engine's UCI state machine desyncs.

### Bug 3: `go depth 1` is wrong for Maia

**Symptom:** If handshake did succeed, depth-based search would be meaningless.

**Cause:** Maia is a **fixed policy network** — there is no search tree, only a one-shot policy distribution over legal moves. lc0 with `--weights=maia-*.pb` is configured via `go nodes 1`, not `go depth N`.

---

## Targeted fix (20 min)

### Edit 1: `services/chess_coach/engine_orch/pool.py`

In `analyze()`, replace:
```python
options.setdefault("Threads", self._default_threads)
options.setdefault("Hash", self._default_hash_mb)
```
with:
```python
skip = getattr(spec, "skip_options", frozenset())
if "Threads" not in skip:
    options.setdefault("Threads", self._default_threads)
if "Hash" not in skip:
    options.setdefault("Hash", self._default_hash_mb)
```

### Edit 2: `services/chess_coach/engine_orch/pool.py`

In `EngineSpec` dataclass, add field:
```python
skip_options: frozenset[str] = frozenset()
```

### Edit 3: Maia registration

Wherever Maia is registered (likely in `pool.py` engine specs list), use:
```python
EngineSpec(
    name="maia-1500",
    cmd=...,
    extra_args=[...],
    skip_options=frozenset({"Hash", "Threads"}),
)
```

### Edit 4: `go nodes 1` for lc0 engines

In `analyze()`, after building the `go` command, detect lc0/Maia and use nodes instead of depth:
```python
if "lc0" in spec.cmd or any("lc0" in a for a in spec.extra_args):
    go_cmd = "go nodes 1"
else:
    go_cmd = f"go depth {depth}"
```

---

## Verification steps after fix

1. `curl -X POST /v1/analysis -d '{"engine":"maia-1500","fen":"<startpos>","depth":1}'`
2. Expect: 200 with `best_move` (e.g. `e2e4` for 1500-rated policy) and `score` (policy prob)
3. Compare against reference: `echo -e 'uci\nucinewgame\nisready\nposition startpos\ngo nodes 1\nquit' | lc0 --weights=maia-1500.pb`

---

## Files to touch (only these)

- `services/chess_coach/engine_orch/pool.py` — all 4 edits above

No other modules need changes. Frontend, gateway routes, schemas are unaffected.

---

## Commit message template

```
fix(maia): skip Hash/Threads for lc0 + go nodes 1 for policy nets

- Add EngineSpec.skip_options frozenset
- Filter skip_options before set_options in pool.analyze()
- Use 'go nodes 1' for lc0/Maia engines (fixed policy network)
- Resolves lc0 'error Unknown option' and readyok hang
```
RESOLVED — HTTP 200, commit 5c05764
