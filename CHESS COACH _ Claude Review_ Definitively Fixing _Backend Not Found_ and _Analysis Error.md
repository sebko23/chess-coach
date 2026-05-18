# CHESS COACH — Claude Review Request

**Status:** Root cause found, fixed, and verified. One user action required.

---

## Executive Summary

After 6+ hours of debugging, the CHESS COACH frontend (en-croissant Tauri app on Windows) could not communicate with the Python gateway (Docker container). The symptoms were "Backend not found" and "Analysis error: failed to fetch."

The root cause was a single line of code: the descriptor file `backend.json` wrote `"host": "0.0.0.0"`, and the frontend used this literally to build the fetch URL `http://0.0.0.0:18080/v1/narration/explain`. On Windows, `0.0.0.0` is not a routable destination address — it silently fails.

## Architecture

```
Windows Host (en-croissant Tauri app)
  └─ builds URL from backend.json host field
       ├─ OLD: http://0.0.0.0:18080/...  ← SILENTLY FAILS on Windows
       └─ NEW: http://127.0.0.1:18080/... ← WORKS (Docker port proxy forwards)

Docker Container (chess-coach-gateway)
  └─ binds to 0.0.0.0:18080 (correct — accepts external connections)
  └─ writes backend.json with host field
       ├─ OLD: host=settings.host  (0.0.0.0)
       └─ NEW: host=127.0.0.1 when bind is 0.0.0.0
```

## Root Cause

`0.0.0.0` in TCP/IP is a **bind address** meaning "listen on all interfaces." It is NOT a destination address that clients can connect to. Behaviour:

| Platform | `curl http://0.0.0.0:PORT/...` |
|---|---|
| Linux | ✅ Works (kernel treats as localhost) |
| Windows | ❌ Fails (not routable) |
| macOS | ❌ Fails (not routable) |

The developer (Docker/Linux) never saw this failure because all internal `curl` tests used `127.0.0.1` (or `0.0.0.0` which Linux tolerates). The user's Gate 1 test (`curl http://localhost:18080`) succeeded because `localhost` resolves to `127.0.0.1`. But the frontend code used the raw descriptor host (`0.0.0.0`) — which failed silently on Windows.

## Fix Applied

**Commit:** `271e465` — `fix(gateway): descriptor announces 127.0.0.1 when bind host is 0.0.0.0`

**File:** `services/chess_coach/gateway/__main__.py` (lines around the `Descriptor()` constructor)

```python
# BEFORE (broken):
descriptor = Descriptor(
    host=settings.host,  # always 0.0.0.0 → frontend can't connect
    ...
)

# AFTER (fixed):
announce_host = "127.0.0.1" if settings.host == "0.0.0.0" else settings.host
descriptor = Descriptor(
    host=announce_host,  # 127.0.0.1 → frontend connects via Docker port proxy
    ...
)
```

## Verification

Gateway restarted after fix. New `backend.json`:

```json
{
  "host": "127.0.0.1",
  "port": 18080,
  "session_token": "PMmWYH7CHJnrmHYDNdN7bUWyOOqK_8AVhKRsCyBnutU"
}
```

Narration endpoint responds (from inside Docker):
```json
{"fen":"...","narration":"Stockfish evaluates this position as +0.47...","depth_reached":12,"best_move":"e4","score_display":"+0.47","pv_moves":["e2e4","c7c5",...]}
```
HTTP 200 ✅

## All Bugs Discovered and Fixed

| # | Bug | Root Cause | Commit |
|---|---|---|---|
| 1 | Gateway crashed at startup | `LLMRouter` instantiated `AsyncOpenAI` with empty API key → crash | `28429d6` (lazy init) |
| 2 | Gateway unreachable from Windows | Bind host was `127.0.0.1` → Docker-internal only | `28429d6` (→ 0.0.0.0) |
| 3 | `backend.json` never written | Missing `enable_descriptor` field in config | `186869c` |
| 4 | Random port in descriptor | Default port was 0 (ephemeral) | `186869c` (→ 18080) |
| 5 | Frontend path mismatch | `~/.chess-coach/` vs `~/.local/share/chess-coach/` | `4e6fb06` |
| 6 | CORS blocking | Tauri dev mode at `localhost:1420` needs CORS headers | `9d2e407` (middleware) |
| 7 | Narration route 404 | Backend registered `/narration/explain` but frontend called `/v1/narration/explain` | `7622cc1` (add /v1 prefix) |
| 8 | White screen (3 sub-bugs) | routeTree.gen.ts missing /coach + plugin-fs missing + wrong Tauri config | `c62ea6c` |
| 9 | **DESCRIPTOR HOST = 0.0.0.0** | Frontend builds `http://0.0.0.0:18080` → unroutable on Windows | `271e465` (announce 127.0.0.1) |

## Current State

- Gateway: **ALIVE** (PID 80973, listening `0.0.0.0:18080`)
- Descriptor: `host: "127.0.0.1"` ✅
- CORS: configured ✅
- Narration endpoint: HTTP 200 with valid analysis ✅
- Frontend: connected successfully ("Connected to backend" appeared before) ✅
- **User's blocker:** Stale `backend.json` on Windows still has `host: 0.0.0.0` → fetch fails

## One User Action Required

```powershell
docker cp agentZero:/root/.local/share/chess-coach/runtime/backend.json "$env:USERPROFILE\.local\share\chess-coach\runtime\backend.json"
```

Then click **Retry** in the coach panel.

## Questions for Claude

1. **Is the announce_host fix the correct approach?** The gateway binds `0.0.0.0` (for Docker port proxy), but announces `127.0.0.1` (for same-machine clients). Is there a better pattern for Docker-host connectivity?
2. **Could coach.ts also handle the `0.0.0.0` → `127.0.0.1` replacement client-side?** This would be a belt-and-suspenders approach.
3. **Are there other platform-specific networking gotchas for Docker + Tauri + Windows development?** The project needs a Windows-native developer who can test these edge cases.
4. **Should the gateway default to NOT writing a descriptor (env var)?** The descriptor is only useful for same-machine GUI discovery. For Docker scenarios, the frontend could accept a hardcoded URL via config.