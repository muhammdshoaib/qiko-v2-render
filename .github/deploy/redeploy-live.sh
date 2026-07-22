#!/bin/bash
# Runs ON the live (production) EC2 box via SSM Run Command (invoked by
# .github/workflows/deploy-live.yml). Modelled on redeploy-preprod.sh; differs only by the live
# S3 bucket/prefix, the qiko-live compose project + overlay, and the /qiko/live/ENV SSM parameter,
# plus a production-only pre-migration DB backup (step 3b). Code is delivered via S3 (org policy
# disables deploy keys, so the box no longer git-pulls): CI uploads a `git archive` tarball to S3,
# this script downloads + atomically swaps it in.
set -uxo pipefail

# Live deploy bucket. Mirrors the preprod naming convention (qiko-v2-<env>-deploy-<accountid>);
# must exist with host-role read access (see docs/playbooks/live.md).
BUCKET="qiko-v2-live-deploy-064247010239"
REGION="eu-central-1"
KEY="live/deploy-latest.tar.gz"
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
# POSTGRES_PASSWORD, SESSION_SECRET, ENCRYPTION_KEY, Bedrock/Stripe/SMTP config, PUBLIC_API_BASE
# baked into the frontend build). The git-archive artifact never contains it (gitignored), and the
# SSM param is only a bootstrap fallback for a fresh host -- so keep the existing one rather than
# clobber it.
PRESERVED_ENV=""
if [ -f "$BASE/platform/.env" ]; then
  PRESERVED_ENV=$(mktemp)
  cp "$BASE/platform/.env" "$PRESERVED_ENV"
fi

rm -rf "$BASE/platform.prev"
[ -d "$BASE/platform" ] && mv "$BASE/platform" "$BASE/platform.prev"
mv "$BASE/platform.staging" "$BASE/platform"

cd "$BASE/platform" || exit 1
export COMPOSE_PROJECT_NAME=qiko-live

# 3. Restore the preserved .env; only bootstrap from SSM if the host has none yet.
if [ -n "$PRESERVED_ENV" ]; then
  cp "$PRESERVED_ENV" .env
else
  aws ssm get-parameter --region "$REGION" --name /qiko/live/ENV --with-decryption \
    --query Parameter.Value --output text > .env
fi
if ! grep -q '^POSTGRES_PASSWORD=' .env; then
  echo "FATAL: .env is missing POSTGRES_PASSWORD -- refusing to deploy with a broken env" >&2
  exit 1
fi

C="docker compose -f docker-compose.yml -f docker-compose.live.yml"

# 3b. PRODUCTION-ONLY safety net: take a compressed pg_dump before we build/migrate, so a bad
#     migration can be restored even though an artifact rollback alone cannot undo schema changes.
#     Non-fatal: if the DB is not up yet (very first deploy) this is skipped, never blocking the
#     deploy. Never touches named volumes. Keeps the 7 most recent dumps.
if $C ps db --status running >/dev/null 2>&1; then
  mkdir -p "$BASE/backups"
  STAMP=$(date +%F-%H%M%S)
  if $C exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$BASE/backups/qiko-live-$STAMP.sql.gz"; then
    echo "pre-deploy backup written to $BASE/backups/qiko-live-$STAMP.sql.gz"
    ls -1t "$BASE"/backups/qiko-live-*.sql.gz | tail -n +8 | xargs -r rm -f
  else
    echo "WARN: pre-deploy backup failed (continuing); check DB health" >&2
  fi
fi

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
#    images become unused and, left unchecked, fill the disk until ENOSPC kills a deploy. Now that
#    the new stack is up + migrated, prune images not referenced by a running container plus the
#    build cache, and drop the previous release dir. `image prune -af` cannot remove the images the
#    running containers use, and NOTHING here touches named volumes (Postgres data is safe).
#    Non-fatal: a cleanup hiccup must not fail an otherwise-successful deploy.
echo "reclaiming disk (docker prune)..."
docker image prune -af >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true
rm -rf "$BASE/platform.prev" >/dev/null 2>&1 || true
df -h / | tail -1

$C ps --format "{{.Service}} {{.State}} {{.Status}}"
