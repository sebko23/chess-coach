#!/bin/bash
set -e
echo "=== Chess Coach Gateway Startup ==="
cd /a0/usr/projects/chess_coach

echo "1. Reinstalling package from source..."
/opt/venv/bin/pip install --force-reinstall --no-deps -e . --quiet
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
