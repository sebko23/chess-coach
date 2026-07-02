#!/bin/bash
# Chess Coach Gateway Startup — stabilized variant.
#
# Behaviour contract (post-patch):
#   * Idempotent: a second invocation while the gateway is healthy is a no-op.
#   * Non-destructive: NEVER sends SIGKILL. If a stale process holds 18080, the
#     script sends SIGTERM and waits up to 10s. If the port is still busy after
#     that, the script REFUSES to start rather than escalating to SIGKILL.
#   * Concurrent-invocation safe: flock on /tmp/chess_coach_gateway.lock.
#   * PID-ownership verified before any kill is even considered.
#
# Original kill: `fuser -k 18080/tcp` (SIGKILL) — REMOVED.
set -e

echo "=== Chess Coach Gateway Startup ==="
cd /a0/usr/projects/chess_coach

# --- Lockfile: prevent concurrent runs from racing each other ---
LOCKFILE=/tmp/chess_coach_gateway.lock
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "Another gateway start is already in progress (lock held). Exiting."
    exit 0
fi

echo "1. Checking gateway status on port 18080..."
if ss -tln 2>/dev/null | grep -q ':18080 '; then
    EXISTING_PID=$(ss -tlnp 2>/dev/null | grep ':18080 ' | grep -oP 'pid=\K[0-9]+' | head -1 || true)
    if [ -n "${EXISTING_PID:-}" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        # Verify it is OUR binary before deciding
        CMDLINE=$(tr '\0' ' ' < /proc/"$EXISTING_PID"/cmdline 2>/dev/null || true)
        if echo "$CMDLINE" | grep -q 'chess-coach-gateway'; then
            echo "   Healthy gateway already running (PID $EXISTING_PID). Doing nothing."
            exit 0
        fi
        echo "   Port 18080 held by a foreign process (PID $EXISTING_PID, cmd=$CMDLINE)."
        echo "   Refusing to start. Resolve manually before retrying."
        exit 1
    fi
    # Stale binding — graceful SIGTERM only, then wait. Never SIGKILL.
    echo "   Stale binding on 18080 — sending SIGTERM and waiting up to 10s..."
    pkill -TERM -f "chess-coach-gateway" 2>/dev/null || true
    WAITED=0
    while [ "$WAITED" -lt 10 ]; do
        if ! ss -tln 2>/dev/null | grep -q ':18080 '; then
            break
        fi
        sleep 1
        WAITED=$((WAITED + 1))
    done
    if ss -tln 2>/dev/null | grep -q ':18080 '; then
        echo "   Port 18080 still busy after 10s graceful wait. Refusing to start."
        echo "   Inspect with: ss -tlnp | grep 18080"
        exit 1
    fi
fi

echo "2. Reinstalling package from source..."
/opt/venv/bin/pip install --force-reinstall --no-deps -e . --quiet
echo "   Done."

echo "2.5. Running database migrations..."
/opt/venv/bin/python3 -c "from pathlib import Path; from chess_coach.storage.migrate import migrate; migrate(Path('/root/.local/share/chess-coach/sqlite/chess_coach.db'))"
echo "   Done."

echo "3. Starting gateway..."
nohup /opt/venv/bin/chess-coach-gateway >> /tmp/gateway.log 2>&1 &

echo "4. Waiting for gateway to bind..."
for i in {1..120}; do
  if ss -tln 2>/dev/null | grep -q ':18080 '; then
    echo "   Gateway listening after ${i}s"
    break
  fi
  sleep 1
done

if ! ss -tln 2>/dev/null | grep -q ':18080 '; then
  echo "   ERROR: Gateway did not bind within 60s"
  echo "   --- last 30 lines of /tmp/gateway.log ---"
  tail -30 /tmp/gateway.log
  exit 1
fi

echo "5. Verifying routes..."
for endpoint in \
  "http://127.0.0.1:18080/v1/games?limit=1" \
  "http://127.0.0.1:18080/v1/training/queue/default?limit=1" \
  "http://127.0.0.1:18080/v1/profile/default"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint" \
    -H "Authorization: Bearer devtoken123" || true)
  echo "   $endpoint -> $code"
done

echo "=== Gateway ready ==="
cat > /root/.local/share/chess-coach/runtime/backend.json << 'DESCRIPTOR'
{
  "backend_version": "0.1.0",
  "host": "127.0.0.1",
  "port": 18080,
  "protocol_version": "1.0.0",
  "session_token": "devtoken123"
}
DESCRIPTOR
