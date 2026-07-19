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

# Preserve the live .env across the swap. It's the source of truth once set (contains
# POSTGRES_PASSWORD, SESSION_SECRET, Bedrock/Stripe/SMTP config, PUBLIC_API_BASE baked into the
# frontend build). The git-archive artifact never contains it (gitignored), and the SSM param is
# only a bootstrap fallback for a fresh host -- so keep the existing one rather than clobber it.
PRESERVED_ENV=""
if [ -f "$BASE/platform/.env" ]; then
  PRESERVED_ENV=$(mktemp)
  cp "$BASE/platform/.env" "$PRESERVED_ENV"
fi

rm -rf "$BASE/platform.prev"
[ -d "$BASE/platform" ] && mv "$BASE/platform" "$BASE/platform.prev"
mv "$BASE/platform.staging" "$BASE/platform"

cd "$BASE/platform" || exit 1
export COMPOSE_PROJECT_NAME=qiko-preprod

# 3. Restore the preserved .env; only bootstrap from SSM if the host has none yet.
if [ -n "$PRESERVED_ENV" ]; then
  cp "$PRESERVED_ENV" .env
else
  aws ssm get-parameter --region "$REGION" --name /qiko/preprod/ENV --with-decryption \
    --query Parameter.Value --output text > .env
fi
if ! grep -q '^POSTGRES_PASSWORD=' .env; then
  echo "FATAL: .env is missing POSTGRES_PASSWORD -- refusing to deploy with a broken env" >&2
  exit 1
fi

C="docker compose -f docker-compose.yml -f docker-compose.preprod.yml"
# Pre-build sweep: free space so a build can't hit ENOSPC on a disk left cluttered by prior runs.
# Only dangling images + build cache here (safe: never removes a tagged/in-use image or a volume).
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true
# Build must succeed -- a failed build must never be silently swallowed (set -e is not on, so
# check explicitly) or the deploy would "succeed" while serving the previous stale images.
if ! $C build; then
  echo "FATAL: docker compose build failed" >&2
  exit 1
fi
$C up -d --force-recreate
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

# 5. Reclaim disk (garbage collection). Every deploy builds fresh images; the previous build's
#    images become unused and, left unchecked, filled the 40G disk until ENOSPC killed a deploy.
#    Now that the new stack is up + migrated, prune images not referenced by a running container
#    plus the build cache, and drop the previous release dir. `image prune -af` cannot remove the
#    images the 7 running containers use, and NOTHING here touches named volumes (Postgres data is
#    safe). Non-fatal: a cleanup hiccup must not fail an otherwise-successful deploy.
echo "reclaiming disk (docker prune)..."
docker image prune -af >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true
rm -rf "$BASE/platform.prev" >/dev/null 2>&1 || true
df -h / | tail -1

$C ps --format "{{.Service}} {{.State}} {{.Status}}"
