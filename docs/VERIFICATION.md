# Verification Guide

This document is for the **next developer** with a working
Docker host who wants to close the verification gaps left by
the BBF-27..31 repo-readiness push. It documents exactly which
gaps remain, how to verify each one, and what to do if a
verification fails.

The BBF-27..31 push shipped the code (Dockerfile, docker-compose,
smoke test, CI workflow, .env.example) but could not verify it
end-to-end in the agentZero container's environment (host Docker
runtime broken with `procReady not received` errors). The
verification steps below are what a fresh dev should run to
confirm the code actually works on a healthy Docker host.

## What was verified vs what wasn't

| Sprint | Code shipped | Verified |
|---|---|---|
| BBF-27 docs | README/CONTRIBUTING/BUILDING/REPO-READINESS/CHANGELOG | yes by inspection (linter + structure check) |
| BBF-28 Dockerfile | Dockerfile + docker-compose.yml + .dockerignore | NO **NOT verified end-to-end** (host Docker broken) |
| BBF-29 smoke test | tests/integration/smoke_test.py | yes verified against the live agentZero gateway (4.6s end-to-end) |
| BBF-30 CI | .github/workflows/smoke.yml | NO **NOT run end-to-end** (no GitHub Actions runner in this env) |
| BBF-31 .env.example | .env.example + .dockerignore fix | yes by inspection (no env needed) |

## Verifying BBF-28 (Docker build)

**Prerequisites**: a working Docker host. The agentZero dev
machine is one such host when its Docker runtime is healthy.
On Windows 11 + WSL2 + Docker Desktop, this usually Just Works.
On the dev machine used for BBF-18..BBF-31, Docker was broken
(see commit messages for the symptom: `procReady not received`).

**Steps**:

```bash
cd <repo>
docker compose build
# Should complete in < 60s on a fast connection. Output should
# show the apt-get install of stockfish, the uv pip install
# of the package, and the tini install.

docker compose up -d
# Should bring the gateway up. `docker compose ps` should show
# the backend as `(healthy)` within 30s.

curl -sS http://127.0.0.1:18080/v1/system/health \
  -H "Authorization: Bearer devtoken123"
# Should echo {"data":{"status":"ok",...}}
```

**If the build fails**:

1. Check the build log for the failing layer. The most common
   culprits are:
   - `apt-get install stockfish` fails -> check your apt sources
     or use a different stockfish binary path
   - `uv pip install -e .` fails -> check pyproject.toml; run
     `uv pip install -e .` locally first to debug
   - tini install fails -> check the package name; tini is
     standard on Debian-slim but may need a different name on
     Alpine-based images

2. If the failure is `procReady not received` (Windows 11 + WSL2
   + Docker Desktop), this is a host issue, not a Dockerfile
   issue. See https://github.com/microsoft/WSL/issues/ for
   workarounds (usually restarting the WSL2 VM fixes it).

**If the smoke test fails against the docker-compose backend**:

1. Check `docker compose logs backend` for the gateway's stdout/stderr.
2. The most common failures are:
   - Gateway can't bind to port 18080 -> another process is using
     it. Check `lsof -i :18080` (or `netstat -an` on Windows).
   - Gateway crashes on startup -> look for Python tracebacks in
     the logs; usually a missing system dep.
   - Smoke test can't connect -> check the port publishing
     (`docker compose ps` should show `0.0.0.0:18080->18080/tcp`).

## Verifying BBF-30 (GitHub Actions CI)

**Prerequisites**: a working GitHub repo with Actions enabled.
The repo `github.com/sebko23/chess-coach` is already set up for
this.

**Steps**:

1. Push a branch with a small change (e.g. a typo fix in a doc).
2. Open a PR from that branch to main.
3. The CI should run automatically. The Actions tab should show
   the `smoke` job.
4. The job should:
   - Build the Docker image (~30s on a fast connection)
   - Wait for the healthcheck (~5-30s)
   - Run the smoke test (~15s with MAX_WORKERS=1, faster with
     more workers)
   - Pass.

**If the CI fails**:

1. Check the Actions log. The smoke test step should show the
   `[1/4] [2/4] [3/4] [4/4]` output if it ran at all.
2. If the build fails, see the BBF-28 verification above.
3. If the smoke test fails:
   - Check the `docker logs` step at the bottom (only runs on
     failure).
   - The most common CI failure is the smoke test timing out:
     the first eval-graph call takes ~12s with MAX_WORKERS=1, and
     the request has a 60s timeout. The default `MAX_WORKERS=1`
     is set in the workflow's services block; bump to 2-4 if you
     need faster smoke tests.

## Manual smoke test from cold start

This is the **first thing a new dev should do** after cloning.
Tests the full BBF-28..31 chain end-to-end without GitHub Actions.

```bash
cd <repo>

# 1. Build the image
docker compose build

# 2. Start the gateway
docker compose up -d
# Wait for healthy
docker compose ps  # should show (healthy) within 30s

# 3. Run the smoke test
python tests/integration/smoke_test.py
# Expected: "OK smoke_test passed: 7 positions, all with score_cp"

# 4. Stop
docker compose down
```

Total time-to-verified: ~2-3 minutes on a healthy Docker host.

## Re-verifying after a code change

If you change the gateway code, the imports, the Dockerfile, or
the smoke test, re-run:

```bash
docker compose build
docker compose up -d
python tests/integration/smoke_test.py
```

If you change the eval-graph endpoint (BBF-22 contract), the smoke
test's assertions need to be updated. The script is intentionally
minimal so this is a 5-line edit.

If you change the CI workflow (`.github/workflows/smoke.yml`),
push to a branch and verify the Actions tab shows the expected
output. The workflow uses `services:` with explicit healthchecks
so the runner waits for the gateway before running the smoke
test.

## What this guide does NOT cover

- **Performance verification.** The smoke test doesn't measure
  wall-clock perf beyond "first eval-graph completes in < 60s".
  If you need perf verification, see `docs/17_lazy_eval_graph/
  RESULTS.md` for the 6000-game stress test (BBF-25) and run
  that with `CHESS_COACH_MAX_WORKERS=4` to see the 4x parallelism
  in action.

- **Frontend verification.** The smoke test doesn't cover
  `apps/desktop/`. The desktop is a Tauri app that needs a host
  display to build, which CI runners don't have. A frontend CI
  would need Playwright or similar and is a separate sprint.

- **Linting CI.** No lint job exists yet. Adding one is a
  one-sprint follow-on: `.github/workflows/lint.yml` that runs
  `tsc` on the desktop and `ruff` on the backend.

## Reporting back

If you successfully verify the BBF-28 build and the BBF-30 CI,
please open a follow-up PR that:
1. Updates the CHANGELOG to mark the verification as complete
2. Removes the "honest verification gap" notes from the BBF-28
   and BBF-30 commit messages (or adds a follow-up commit
   noting the verification)

This makes the gap closure visible in the commit history.
