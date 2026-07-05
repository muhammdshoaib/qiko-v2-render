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
sleep 15
$C exec -T qiko-core alembic upgrade head || true
$C ps --format "{{.Service}} {{.State}} {{.Status}}"
