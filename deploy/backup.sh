#!/bin/bash
# Nightly SQLite backup on the VPS (installed as entaoganhei-backup.timer by
# deploy/install-backup.sh). Keeps 30 days.
set -euo pipefail
OUT=/opt/entaoganhei/backups
CID=$(docker ps -q -f name=entaoganhei_web | head -1)
[ -n "$CID" ] || { echo "app container not running" >&2; exit 1; }
STAMP=$(date -u +%Y%m%d-%H%M)
docker exec "$CID" python -c "import sqlite3; s=sqlite3.connect('/data/entao-ganhei.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker cp "$CID:/data/backup.db" "$OUT/entao-ganhei-$STAMP.db"
docker exec "$CID" rm -f /data/backup.db
gzip -f "$OUT/entao-ganhei-$STAMP.db"
find "$OUT" -name 'entao-ganhei-*.db.gz' -mtime +30 -delete
