#!/bin/bash
# Runs ON the preprod EC2 box via SSM Run Command (invoked by .github/workflows/deploy-preprod.yml).
set -uxo pipefail
cd /opt/docker/qiko/platform || exit 1
export COMPOSE_PROJECT_NAME=qiko-preprod
export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no"
git fetch origin preprod -q && git reset --hard origin/preprod -q
aws ssm get-parameter --region me-central-1 --name /qiko/preprod/ENV --with-decryption --query Parameter.Value --output text > .env
C="docker compose -f docker-compose.yml -f docker-compose.preprod.yml"
$C up -d --build
sleep 25
# Retry migrations for a while: qiko-core can still be restarting (old container terminating,
# new one not yet accepting exec) right after `up -d --build`, and a failed migration must never
# be silently swallowed (see git history) -- so this loop is verbose and the final failure is fatal.
migrated=0
for i in 1 2 3 4 5 6 7 8; do
  if $C exec -T qiko-core alembic upgrade head; then
    migrated=1
    break
  fi
  echo "alembic upgrade head failed (attempt $i/8), retrying in 15s..."
  sleep 15
done
if [ "$migrated" -ne 1 ]; then
  echo "FATAL: alembic upgrade head did not succeed after 8 attempts" >&2
  exit 1
fi
$C ps --format "{{.Service}} {{.State}} {{.Status}}"
