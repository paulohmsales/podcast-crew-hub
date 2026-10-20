#!/bin/bash
# Ship the working tree to the VPS, build the image there and roll the stack.
# Run from the repo root on your machine:  deploy/deploy.sh
set -euo pipefail
HOST=${DEPLOY_HOST:-jobz-vps}
DIR=/opt/entaoganhei/src
REV=$(git rev-parse --short HEAD)$(git diff --quiet HEAD || echo "-dirty")

echo "→ syncing $REV to $HOST:$DIR"
ssh "$HOST" "mkdir -p $DIR /opt/entaoganhei/backups"
rsync -az --delete --exclude .git --exclude .venv --exclude '*.db*' --exclude __pycache__ ./ "$HOST:$DIR/"

ssh "$HOST" bash -s -- "$REV" <<'REMOTE'
set -euo pipefail
REV=$1
cd /opt/entaoganhei/src
echo "→ building $REV"
docker build -q -f deploy/Dockerfile -t entaoganhei:latest -t "entaoganhei:$REV" . >/dev/null
docker stack deploy -q --resolve-image never -c deploy/stack.yml entaoganhei
docker service update -q --image "entaoganhei:$REV" entaoganhei_web >/dev/null
docker image prune -f --filter "until=168h" --filter "reference=entaoganhei" >/dev/null || true
REMOTE
echo "✓ deployed $REV → https://podcast.example.com"
