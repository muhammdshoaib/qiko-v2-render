#!/bin/bash
# Runs ON the preprod EC2 box via SSM Run Command (invoked by .github/workflows/deploy-preprod.yml).
# Code is delivered via S3 (org policy disables deploy keys, so the box no longer git-pulls):
# CI uploads a `git archive` tarball to S3, this script downloads + atomically swaps it in.
set -uxo pipefail
umask 077

exec 9>"/var/lock/qiko-preprod-deploy.lock"
if ! flock -n 9; then
  echo "FATAL: another qiko-preprod deployment is already running" >&2
  exit 1
fi
: "${RELEASE_SHA:?set RELEASE_SHA}"
: "${RELEASE_SHA256:?set RELEASE_SHA256}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "FATAL: invalid RELEASE_SHA" >&2; exit 1; }
[[ "$RELEASE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "FATAL: invalid RELEASE_SHA256" >&2; exit 1; }

BUCKET="qiko-v2-preprod-deploy-064247010239"
REGION="eu-central-1"
KEY="preprod/deploy-$RELEASE_SHA.tar.gz"
BASE="/opt/docker/qiko"
PRESERVED_ENV=""
cleanup() {
  [ -n "$PRESERVED_ENV" ] && rm -f "$PRESERVED_ENV"
  rm -f /tmp/qiko-v2-deploy.tar.gz
}
trap cleanup EXIT

# 1. Fetch the code artifact CI just uploaded.
aws s3 cp "s3://$BUCKET/$KEY" /tmp/qiko-v2-deploy.tar.gz --region "$REGION" \
  || { echo "FATAL: could not download s3://$BUCKET/$KEY" >&2; exit 1; }
printf '%s  %s\n' "$RELEASE_SHA256" /tmp/qiko-v2-deploy.tar.gz | sha256sum -c - \
  || { echo "FATAL: artifact checksum mismatch" >&2; exit 1; }

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
if [ -f "$BASE/platform/.env" ]; then
  PRESERVED_ENV=$(mktemp)
  cp "$BASE/platform/.env" "$PRESERVED_ENV" \
    || { echo "FATAL: could not preserve the preprod environment" >&2; exit 1; }
fi

rm -rf "$BASE/platform.prev" \
  || { echo "FATAL: could not remove the previous release directory" >&2; exit 1; }
if [ -d "$BASE/platform" ]; then
  mv "$BASE/platform" "$BASE/platform.prev" \
    || { echo "FATAL: could not preserve the current release" >&2; exit 1; }
fi
mv "$BASE/platform.staging" "$BASE/platform" \
  || { echo "FATAL: could not activate the staged release" >&2; exit 1; }

cd "$BASE/platform" || exit 1
export COMPOSE_PROJECT_NAME=qiko-preprod

# 3. Restore the preserved .env; only bootstrap from SSM if the host has none yet.
if [ -n "$PRESERVED_ENV" ]; then
  cp "$PRESERVED_ENV" .env \
    || { echo "FATAL: could not restore the preprod environment" >&2; exit 1; }
  rm -f "$PRESERVED_ENV" \
    || { echo "FATAL: could not remove the temporary environment copy" >&2; exit 1; }
  PRESERVED_ENV=""
else
  if ! aws ssm get-parameter --region "$REGION" --name /qiko/preprod/ENV --with-decryption \
    --query Parameter.Value --output text > .env; then
    echo "FATAL: could not bootstrap the preprod environment" >&2
    exit 1
  fi
fi
if [ ! -f .env ] || [ -L .env ]; then
  echo "FATAL: .env must be a regular file, not a symbolic link" >&2
  exit 1
fi
if ! chmod 600 .env; then
  echo "FATAL: could not restrict .env permissions" >&2
  exit 1
fi
ENV_OWNER_UID=$(stat -c '%u' .env) \
  || { echo "FATAL: could not read .env owner" >&2; exit 1; }
CURRENT_UID=$(id -u) \
  || { echo "FATAL: could not determine the deployment user" >&2; exit 1; }
if [ "$ENV_OWNER_UID" != "$CURRENT_UID" ]; then
  echo "FATAL: .env must be owned by the deployment user (uid $CURRENT_UID), found uid $ENV_OWNER_UID" >&2
  exit 1
fi
ENV_MODE=$(stat -c '%a' .env) \
  || { echo "FATAL: could not read .env permissions" >&2; exit 1; }
if [ $((8#$ENV_MODE & 077)) -ne 0 ]; then
  echo "FATAL: .env must not grant permissions to group or other (mode $ENV_MODE)" >&2
  exit 1
fi
if ! grep -q '^POSTGRES_PASSWORD=' .env; then
  echo "FATAL: .env is missing POSTGRES_PASSWORD -- refusing to deploy with a broken env" >&2
  exit 1
fi

C="docker compose -f docker-compose.yml -f docker-compose.preprod.yml"
wait_for_healthy() {
  service="$1"
  ready=0
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    SERVICE_ID="$($C ps -q "$service" --status running 2>/dev/null || true)"
    if [ -n "$SERVICE_ID" ]; then
      HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE_ID" 2>/dev/null || true)"
      [ "$HEALTH" = "healthy" ] && ready=1 && break
    fi
    sleep 5
  done
  if [ "$ready" -ne 1 ]; then
    echo "FATAL: required service $service did not become healthy" >&2
    exit 1
  fi
}

# Validate and build without disturbing the currently running public services. A failed build or
# startup preflight must never be silently swallowed.
if ! $C config --quiet; then
  echo "FATAL: docker compose configuration is invalid" >&2
  exit 1
fi
# Pre-build sweep: free space so a build can't hit ENOSPC on a disk left cluttered by prior runs.
# Only dangling images + build cache here (safe: never removes a tagged/in-use image or a volume).
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true
if ! $C build; then
  echo "FATAL: docker compose build failed" >&2
  exit 1
fi
if ! $C run --rm --no-deps qiko-core python -c 'from app.core.config import Settings; from app.modules.email.sender import SmtpEmailSender; Settings().assert_secrets_set(); SmtpEmailSender().check_connection()'; then
  echo "FATAL: resolved non-dev environment failed startup preflight" >&2
  exit 1
fi

# Start only the stateful dependencies and require both health checks before touching the schema.
if ! $C up -d db redis; then
  echo "FATAL: could not start the database and Redis" >&2
  exit 1
fi
wait_for_healthy db
wait_for_healthy redis

# 4. Run migrations from the newly built image in an isolated one-off qiko-core container. A failed
#    migration must never be silently swallowed; the final retry failure is fatal.
migrated=0
for i in 1 2 3 4 5 6 7 8; do
  if $C run --rm --no-deps qiko-core alembic upgrade head; then
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

# Only expose the newly built application after migrations succeed.
if ! $C up -d --force-recreate qiko-core worker creator admin caddy; then
  echo "FATAL: docker compose could not recreate the preprod application stack" >&2
  exit 1
fi

# Every required service must be running. Services with health checks must also become healthy.
for service in qiko-core worker creator admin caddy db redis; do
  SERVICE_ID="$($C ps -q "$service" --status running 2>/dev/null || true)"
  if [ -z "$SERVICE_ID" ]; then
    echo "FATAL: required service $service is not running" >&2
    exit 1
  fi
done
wait_for_healthy qiko-core
wait_for_healthy db
wait_for_healthy redis

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
