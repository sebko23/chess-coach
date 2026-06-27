#!/bin/bash
set -e
echo "=== Chess Coach Qdrant Startup ==="
cd /a0/usr/projects/chess_coach

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
EXISTING_PID=$(ss -tlnp 2>/dev/null | grep ":${QDRANT_PORT}" | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$EXISTING_PID" ]; then
    echo "   Found existing process (PID $EXISTING_PID), stopping..."
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 2
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
