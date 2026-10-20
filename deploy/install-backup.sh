#!/bin/bash
# One-time, on the VPS: install the nightly backup timer (the VPS has no cron).
set -euo pipefail
cat > /etc/systemd/system/entaoganhei-backup.service <<'EOF'
[Unit]
Description=Então Ganhei SQLite backup
[Service]
Type=oneshot
ExecStart=/opt/entaoganhei/src/deploy/backup.sh
EOF
cat > /etc/systemd/system/entaoganhei-backup.timer <<'EOF'
[Unit]
Description=Nightly Então Ganhei backup
[Timer]
OnCalendar=*-*-* 05:30:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now entaoganhei-backup.timer
