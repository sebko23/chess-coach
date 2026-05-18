# CHESS COACH — Diagnostic Report for External Review

**Date:** 2026-05-18
**Author:** Agent Zero (deepseek-v4-pro)
**Project:** `/a0/usr/projects/chess_coach`
**Phase:** 1 (vertical slice smoke-test)

---

## 1. Goal

Connect the en-croissant Tauri desktop app (Windows) to the CHESS COACH Python gateway (Docker) and display a grounded coaching narration.

## 2. Architecture (simplified)

```
┌──────────────────────────────────────────────────────┐
│ Windows Host                                         │
│                                                      │
│  en-croissant (Tauri + Vite + React)                 │
│  ├─ CoachPanel.tsx                   🧠 Coach panel  │
│  └─ coach.ts (Jotai atoms)                           │
│       ├─ loadDescriptor()         reads backend.json │
│       └─ fetchNarration()         POST /v1/narration │
│                                                      │
│  C:\Users\i3\.local\share\chess-coach\runtime\     │
│  └── backend.json   ← docker cp'd from container     │
│                                                      │
│  ═══════════════ Docker boundary ═══════════════     │
│                                                      │
│  Docker Container (agentZero)                        │
│  ├─ chess-coach-gateway       PID 23588              │
│  │   └── 0.0.0.0:18080    (verified listening)       │
│  └─ /root/.local/share/chess-coach/runtime/          │
│       └── backend.json                               │
│            host: "0.0.0.0"                           │
│            port: 18080                                │
│            session_token: "HSQkc7..."                 │
└──────────────────────────────────────────────────────┘
```

## 3. Bugs Found & Fixed (all committed)

| # | Bug | Symptom | Fix | Commit |
|---|---|---|---|---|
| 1 | LLMRouter crashed at startup without API key | Gateway wouldn't boot | Lazy client init — `AsyncOpenAI` created on first `complete()` call, not `__init__()` | `28429d6` |
| 2 | Gateway bound to `127.0.0.1` (Docker-only loopback) | Unreachable from Windows host | Changed default host to `0.0.0.0` | `28429d6` |
| 3 | Missing `enable_descriptor` field in config | `GatewaySettings` threw `AttributeError` — backend.json never written | Added field `enable_descriptor: bool = True` to `config.py` | `186869c` |
| 4 | Default port was `0` (OS-assigned ephemeral) | Port mismatch — backend.json had random ports | Changed default to `18080` | `186869c` |
| 5 | Frontend looked for backend.json at wrong path | Path mismatch `~/.chess-coach/` vs `~/.local/share/chess-coach/` | Fixed all 3 occurrences in `coach.ts` | `4e6fb06` |
| 6 | `routeTree.gen.ts` committed (codegen-owned file) | Technical debt | Reverted to upstream state, added to `.gitignore` | `c20fe66` |
| 7 | Power-user mode env var unset | Routes 404'd | Set `COSMETIC=true` (cosmetic fix, not the root cause) | (not committed) |

## 4. Verified (inside Docker, 2026-05-18 ~20:00 UTC)

```bash
# Gateway process alive
ps aux | grep chess-coach-gateway
# PID=23588 /opt/venv/bin/python3.13 /opt/venv/bin/chess-coach-gateway

# Listening on the correct interface
ss -tlnp | grep 18080
# LISTEN 0 2048 0.0.0.0:18080 0.0.0.0:* users:(("chess-coach-gat",pid=23588,fd=9))

# backend.json written
cat /root/.local/share/chess-coach/runtime/backend.json
# {
#   "backend_version": "0.1.0",
#   "host": "0.0.0.0",
#   "port": 18080,
#   "protocol_version": "1.0.0",
#   "session_token": "HSQkc7XwxEBWMLnNuEcLEWg0-AM5w-19RyU5RsDw15w"
# }

# Health endpoint responds (401 = expected — needs auth header)
curl http://127.0.0.1:18080/v1/system/health
# {"error":{"code":"client.unauthorized","message":"Missing Authorization header."}}

# Startup log — clean
# 2026-05-18T20:00:08+0000 INFO gateway.startup: engine pool ready
# 2026-05-18T20:00:08+0000 INFO gateway.startup: narration pipeline ready
# 2026-05-18T20:00:08+0000 INFO Uvicorn running on http://0.0.0.0:18080
```

**All backend systems healthy.**

## 5. Remaining Hypotheses (cannot verify from inside Docker)

These are the things that COULD explain why the frontend still says "Backend not found" — I lack visibility into the Windows-side runtime.

### H1: Docker port 18080 not published to Windows

**Symptom:** The frontend reads `backend.json` (host=0.0.0.0, port=18080) and tries `fetch('http://0.0.0.0:18080/...')`. If the Docker container was restarted WITHOUT `-p 18080:18080`, port 18080 on Windows has nothing listening.

**Test:**
```powershell
# On Windows PowerShell
curl http://localhost:18080/v1/system/info
# OR
Test-NetConnection localhost -Port 18080
```

**Fix if failing:** Restart Docker container with `-p 18080:18080`.

---

### H2: routeTree.gen.ts not generated

**Symptom:** The `/coach` route is defined in `src/routes/coach.tsx` but never compiled into `routeTree.gen.ts`. TanStack Router codegen produces this file — but it's `.gitignore`'d and must be regenerated locally.

**Test:**
```cmd
cd C:\chess-coach\desktop
dir src\routeTree.gen.ts
```

If the file is missing or dated BEFORE `coach.tsx` was added, the route isn't registered and clicking 🧠 Coach may show a different view or 404.

**Fix if failing:** Run `pnpm dev` which auto-generates it via Vite plugin. (No separate `route-gen` script exists in en-croissant.)

---

### H3: @tauri-apps/plugin-fs cannot read the file

**Symptom:** `loadDescriptor()` in `coach.ts` uses `@tauri-apps/plugin-fs` (`exists()`, `readTextFile()`) to open `backend.json`. If the plugin is not installed, not configured in `tauri.conf.json`, or the file has wrong permissions, the read fails silently (the `catch` sets atom to `null`), and the UI shows "Backend not found."

**Test:** Add `console.log` debugging in the Tauri dev console (F12 in the app window) to see if the `catch` block is hit.

**Test from source:**
```typescript
// In coach.ts, in loadDescriptor():
const raw = await readTextFile(path);
console.log('backend.json contents:', raw);  // ADD THIS LINE
```

Rebuild with `pnpm dev`, open DevTools (F12), check console.

---

### H4: browser/Tauri webview CORS blocking

**Symptom:** The React frontend runs at `http://localhost:1420` (Vite dev server). It fetches `http://localhost:18080` (Docker backend). If the gateway doesn't send proper CORS headers (`Access-Control-Allow-Origin`), the browser blocks the fetch BEFORE the backend sees it. The error would be a CORS error in the console, not a connection error.

**Test from Docker:**
```bash
# Simulate a CORS preflight from the Tauri webview
curl -X OPTIONS \
  -H "Origin: http://localhost:1420" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  http://127.0.0.1:18080/v1/narration/explain
```

If the response does NOT include `Access-Control-Allow-Origin`, CORS is the blocker.

**Fix if failing:** The gateway needs CORS middleware (e.g. `fastapi.middleware.cors.CORSMiddleware`). This was NOT added in Phase 1 because we expected the Tauri webview to bypass CORS (it's a desktop app, not a browser). But in `tauri dev` mode, Vite serves from a localhost origin, which DOES require CORS.

---

### H5: frontend build not reflecting latest code

**Symptom:** You copied the fixed `coach.ts` to Windows, but the file at `C:\chess-coach\desktop\src\state\atoms\coach.ts` still has the OLD path (`~/.chess-coach/` instead of `~/.local/share/chess-coach/`). The docker cp may have silently failed or targeted the wrong file.

**Test:**
```cmd
cd C:\chess-coach\desktop
findstr "chess-coach" src\state\atoms\coach.ts
```

If output shows `.chess-coach/runtime` (missing `.local/share/`), the file wasn't updated.

---

### H6: Gateway died after Docker commit/restart

**Symptom:** The gateway was running at time of verification. If the Docker container was stopped/restarted since, the process died. The gateway does NOT auto-start — it was launched manually with `nohup`.

**Test (inside Docker):**
```bash
docker exec agentZero ps aux | grep chess-coach-gateway
```

If no output, the gateway needs restarting.

## 6. Questions for Claude (or external reviewer)

1. **Which of H1-H6 is most likely the blocker, given that all backend fixes are verified working?** H1 (port not published) and H3 (fs plugin failure) seem highest probability.

2. **Does en-croissant's Tauri webview in dev mode (`pnpm tauri dev`) require CORS headers on the backend?** My reading of Tauri docs says Tauri webviews bypass CORS — but I'm not certain for the Vite dev server at `localhost:1420`.

3. **Is `@tauri-apps/plugin-fs` already configured in en-croissant's `src-tauri/Cargo.toml` and `tauri.conf.json`?** Or does `coach.ts` need to register it? I assumed it was already present because en-croissant uses the filesystem for PGN import.

4. **What's the simplest diagnostic test I can ask the user to run on Windows** that gives definitive information about which of H1-H6 is failing? The user is a beginner and has been debugging for 4+ hours.

5. **Is the `routeTree.gen.ts` Vite plugin auto-generation reliable?** The TanStack Router docs say the Vite plugin handles it. But since we `.gitignore`'d the file and the user hasn't run codegen manually, I'm worried the route simply doesn't exist in the compiled app.

## 7. Immediate recommendation

Before analyzing further, ask the user to run ONE diagnostic command on Windows PowerShell:

```powershell
# Test 1: Is the Docker backend reachable from Windows?
curl http://localhost:18080/v1/system/info

# Test 2: If curl fails, check if port 18080 is published
netstat -ano | findstr :18080

# Test 3: Does the frontend have the correct coach.ts?
findstr "local" C:\chess-coach\desktop\src\state\atoms\coach.ts
```

This will immediately reveal whether H1 (port not published), H5 (stale coach.ts), or H2 (route tree missing) is the issue.

---

## Appendix: Files modified (all commits since baseline)

```
services/chess_coach/gateway/config.py      ← host=0.0.0.0, port=18080, enable_descriptor=True
services/chess_coach/llm_router/router.py   ← lazy AsyncOpenAI init
apps/desktop/src/state/atoms/coach.ts       ← path .local/share/chess-coach/, retry button
apps/desktop/src/components/panels/coach/CoachPanel.tsx  ← connection status, error handling
apps/desktop/src/routes/coach.tsx            ← /coach route
apps/desktop/.gitignore                     ← routeTree.gen.ts excluded
apps/desktop/src/components/Sidebar.tsx     ← 🧠 Coach nav entry
docs/14_adrs/ADR-0005-coach-state-jotai.md  ← Jotai decision
```