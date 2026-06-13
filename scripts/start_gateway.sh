#!/bin/bash
set -e
echo "=== Chess Coach Gateway Startup ==="
cd /a0/usr/projects/chess_coach

echo "1. Reinstalling package from source..."
/opt/venv/bin/pip install --force-reinstall --no-deps -e . --quiet
echo "   Done."

echo "1.5. Running database migrations..."
cd /a0/usr/projects/chess_coach && /opt/venv/bin/python3 -c "from pathlib import Path; from chess_coach.storage.migrate import migrate; migrate(Path('/root/.local/share/chess-coach/sqlite/chess_coach.db'))"
echo "   Done."


echo "2. Starting gateway..."
fuser -k 18080/tcp 2>/dev/null || true
sleep 1
nohup /opt/venv/bin/chess-coach-gateway >> /tmp/gateway.log 2>&1 &
sleep 4

echo "3. Verifying routes..."
for endpoint in \
  "http://127.0.0.1:18080/v1/games?limit=1" \
  "http://127.0.0.1:18080/v1/training/queue/default?limit=1" \
  "http://127.0.0.1:18080/v1/profile/default"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint" \
    -H "Authorization: Bearer devtoken123")
  echo "   $endpoint → $code"
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
