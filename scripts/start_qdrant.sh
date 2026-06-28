#!/bin/bash
# Chess Coach Qdrant Startup — stabilized variant.
#
# Behaviour contract (post-patch):
#   * Idempotent: a second invocation while Qdrant is healthy is a no-op.
#   * Non-destructive: NEVER sends SIGKILL. If a stale process holds 6333, the
#     script sends SIGTERM and waits up to 15s. If the port is still busy after
#     that, the script REFUSES to start.
#   * Concurrent-invocation safe: flock on /tmp/chess_coach_qdrant.lock.
#   * PID-ownership verified before any kill is even considered.
#
# Original kill: `kill $EXISTING_PID` (SIGTERM) — kept but now gated by PID
# ownership check. No escalation to SIGKILL was ever present here, but the
# unconditional-kill shape was the same family of bug.
set -e

echo "=== Chess Coach Qdrant Startup ==="
cd /a0/usr/projects/chess_coach

# --- Lockfile: prevent concurrent runs from racing each other ---
LOCKFILE=/tmp/chess_coach_qdrant.lock
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "Another qdrant start is already in progress (lock held). Exiting."
    exit 0
fi

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
    echo "   Loaded .env"
fi

QDRANT_BIN="${QDRANT_BIN:-/usr/local/bin/qdrant}"
QDRANT_DATA_DIR="${QDRANT_DATA_DIR:-/a0/usr/projects/chess_coach/data/qdrant}"
QDRANT_PORT=6333

echo "1. Checking for existing Qdrant on port $QDRANT_PORT..."
if ss -tln 2>/dev/null | grep -q ":${QDRANT_PORT} "; then
    EXISTING_PID=$(ss -tlnp 2>/dev/null | grep ":${QDRANT_PORT} " | grep -oP 'pid=\K[0-9]+' | head -1 || true)
    if [ -n "${EXISTING_PID:-}" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        # Verify it is OUR binary before deciding
        CMDLINE=$(tr '\0' ' ' < /proc/"$EXISTING_PID"/cmdline 2>/dev/null || true)
        if echo "$CMDLINE" | grep -q 'qdrant'; then
            echo "   Healthy qdrant already running (PID $EXISTING_PID). Doing nothing."
            exit 0
        fi
        echo "   Port $QDRANT_PORT held by a foreign process (PID $EXISTING_PID, cmd=$CMDLINE)."
        echo "   Refusing to start. Resolve manually before retrying."
        exit 1
    fi
    # Stale binding — graceful SIGTERM only, then wait. Never SIGKILL.
    echo "   Stale binding on $QDRANT_PORT — sending SIGTERM and waiting up to 15s..."
    if [ -n "${EXISTING_PID:-}" ]; then
        kill -TERM "$EXISTING_PID" 2>/dev/null || true
    fi
    WAITED=0
    while [ "$WAITED" -lt 15 ]; do
        if ! ss -tln 2>/dev/null | grep -q ":${QDRANT_PORT} "; then
            break
        fi
        sleep 1
        WAITED=$((WAITED + 1))
    done
    if ss -tln 2>/dev/null | grep -q ":${QDRANT_PORT} "; then
        echo "   Port $QDRANT_PORT still busy after 15s graceful wait. Refusing to start."
        echo "   Inspect with: ss -tlnp | grep $QDRANT_PORT"
        exit 1
    fi
fi

echo "2. Ensuring data directory exists..."
mkdir -p "$QDRANT_DATA_DIR"
echo "   Data dir: $QDRANT_DATA_DIR"

echo "3. Starting Qdrant..."
nohup "$QDRANT_BIN" \
    --config-path "$QDRANT_DATA_DIR/config.yaml" \
    --disable-telemetry \
    >> /tmp/qdrant.log 2>&1 &
QDRANT_PID=$!
echo "   PID: $QDRANT_PID"

echo "4. Waiting for Qdrant to be ready..."
for i in $(seq 1 15); do
    if curl -sf "http://localhost:${QDRANT_PORT}/healthz" > /dev/null 2>&1; then
        echo "   Qdrant ready on port $QDRANT_PORT (${i}s)"
        echo "=== Qdrant ready ==="
        exit 0
    fi
    sleep 1
done

echo "ERROR: Qdrant did not become ready within 15s — check /tmp/qdrant.log"
exit 1
