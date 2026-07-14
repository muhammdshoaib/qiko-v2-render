#!/bin/bash
# Runs ON the preprod EC2 box via SSM Run Command (invoked by .github/workflows/deploy-preprod.yml).
# Code is delivered via S3 (org policy disables deploy keys, so the box no longer git-pulls):
# CI uploads a `git archive` tarball to S3, this script downloads + atomically swaps it in.
set -uxo pipefail

BUCKET="qiko-v2-preprod-deploy-064247010239"
REGION="eu-central-1"
KEY="preprod/deploy-latest.tar.gz"
BASE="/opt/docker/qiko"

# 1. Fetch the code artifact CI just uploaded.
aws s3 cp "s3://$BUCKET/$KEY" /tmp/qiko-v2-deploy.tar.gz --region "$REGION" \
  || { echo "FATAL: could not download s3://$BUCKET/$KEY" >&2; exit 1; }

# 2. Extract to a staging dir, then atomically swap. All persistent state lives in named docker
#    volumes (postgres_data, caddy_data, caddy_config) that are independent of this directory, so
#    a full swap is safe and also drops files deleted upstream (unlike an in-place overlay).
rm -rf "$BASE/platform.staging"
mkdir -p "$BASE/platform.staging"
tar xzf /tmp/qiko-v2-deploy.tar.gz -C "$BASE/platform.staging" \
  || { echo "FATAL: extract failed" >&2; exit 1; }
if [ ! -f "$BASE/platform.staging/docker-compose.yml" ]; then
  echo "FATAL: artifact missing docker-compose.yml -- refusing to swap" >&2; exit 1
fi

rm -rf "$BASE/platform.prev"
[ -d "$BASE/platform" ] && mv "$BASE/platform" "$BASE/platform.prev"
mv "$BASE/platform.staging" "$BASE/platform"

cd "$BASE/platform" || exit 1
export COMPOSE_PROJECT_NAME=qiko-preprod

# 3. Env comes from SSM Parameter Store, never baked into the artifact.
aws ssm get-parameter --region "$REGION" --name /qiko/preprod/ENV --with-decryption \
  --query Parameter.Value --output text > .env

C="docker compose -f docker-compose.yml -f docker-compose.preprod.yml"
$C up -d --build
sleep 25

# 4. Migrations with retry: qiko-core can still be restarting right after `up -d --build`, and a
#    failed migration must never be silently swallowed -- the final failure is fatal.
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
