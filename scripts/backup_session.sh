#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/.local/share/chess-coach/backups/code"
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/services_$TIMESTAMP.tar.gz" /a0/usr/projects/chess_coach/services/ 2>/dev/null
git -C /a0/usr/projects/chess_coach diff > "$BACKUP_DIR/uncommitted_$TIMESTAMP.patch" 2>/dev/null
git -C /a0/usr/projects/chess_coach log --oneline -20 > "$BACKUP_DIR/gitlog_$TIMESTAMP.txt"
git -C /a0/usr/projects/chess_coach status > "$BACKUP_DIR/gitstatus_$TIMESTAMP.txt"
echo "=== BACKUP COMPLETE ==="
ls -lh "$BACKUP_DIR" | tail -6
