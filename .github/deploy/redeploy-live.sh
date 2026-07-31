#!/bin/bash
# Runs ON the live (production) EC2 box via SSM Run Command (invoked by
# .github/workflows/deploy-live.yml). Modelled on redeploy-preprod.sh; differs only by the live
# S3 bucket/prefix, the qiko-live compose project + overlay, and the /qiko/live/ENV SSM parameter,
# plus a production-only pre-migration DB backup (step 3b). Code is delivered via S3 (org policy
# disables deploy keys, so the box no longer git-pulls): CI uploads a `git archive` tarball to S3,
# this script downloads + atomically swaps it in.
set -uxo pipefail
umask 077

# Serialise all on-host deploy entry points, including manual SSM commands outside GitHub Actions.
exec 9>"/var/lock/qiko-live-deploy.lock"
if ! flock -n 9; then
  echo "FATAL: another qiko-live deployment is already running" >&2
  exit 1
fi
: "${RELEASE_SHA:?set RELEASE_SHA}"
: "${RELEASE_SHA256:?set RELEASE_SHA256}"
[[ "$RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "FATAL: invalid RELEASE_SHA" >&2; exit 1; }
[[ "$RELEASE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "FATAL: invalid RELEASE_SHA256" >&2; exit 1; }

# Live deploy bucket. Mirrors the preprod naming convention (qiko-v2-<env>-deploy-<accountid>);
# must exist with host-role read access (see docs/playbooks/live.md).
BUCKET="qiko-v2-live-deploy-064247010239"
REGION="eu-central-1"
KEY="live/deploy-$RELEASE_SHA.tar.gz"
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
# POSTGRES_PASSWORD, SESSION_SECRET, ENCRYPTION_KEY, Bedrock/Stripe/SMTP config, PUBLIC_API_BASE
# baked into the frontend build). The git-archive artifact never contains it (gitignored), and the
# SSM param is only a bootstrap fallback for a fresh host -- so keep the existing one rather than
# clobber it.
if [ -f "$BASE/platform/.env" ]; then
  PRESERVED_ENV=$(mktemp)
  cp "$BASE/platform/.env" "$PRESERVED_ENV" \
    || { echo "FATAL: could not preserve the live environment" >&2; exit 1; }
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
export COMPOSE_PROJECT_NAME=qiko-live

# 3. Restore the preserved .env; only bootstrap from SSM if the host has none yet.
if [ -n "$PRESERVED_ENV" ]; then
  cp "$PRESERVED_ENV" .env \
    || { echo "FATAL: could not restore the live environment" >&2; exit 1; }
  rm -f "$PRESERVED_ENV" \
    || { echo "FATAL: could not remove the temporary environment copy" >&2; exit 1; }
  PRESERVED_ENV=""
else
  if ! aws ssm get-parameter --region "$REGION" --name /qiko/live/ENV --with-decryption \
    --query Parameter.Value --output text > .env; then
    echo "FATAL: could not bootstrap the live environment" >&2
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

C="docker compose -f docker-compose.yml -f docker-compose.live.yml"

# 3b. Record whether this is a genuine first deploy BEFORE Compose creates the named volume. Then
# start only DB + Redis. Existing stopped containers or an orphaned volume are brought up and backed
# up; only a truly absent volume skips the pre-migration dump.
DB_VOLUME="${COMPOSE_PROJECT_NAME}_postgres_data"
EXISTING_DB=0
docker volume inspect "$DB_VOLUME" >/dev/null 2>&1 && EXISTING_DB=1
if ! $C up -d db redis; then
  echo "FATAL: could not start the database and Redis" >&2
  exit 1
fi
for service in db redis; do
  ready=0
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    SERVICE_ID="$($C ps -q "$service" --status running 2>/dev/null || true)"
    if [ -n "$SERVICE_ID" ]; then
      HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE_ID")"
      [ "$HEALTH" = "healthy" ] && ready=1 && break
    fi
    sleep 5
  done
  if [ "$ready" -ne 1 ]; then
    echo "FATAL: $service did not become healthy" >&2
    exit 1
  fi
done

# Pre-build sweep: free space so a build cannot hit ENOSPC. Never touches named volumes.
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f >/dev/null 2>&1 || true
if ! $C config --quiet; then
  echo "FATAL: docker compose configuration is invalid" >&2
  exit 1
fi
if ! $C build; then
  echo "FATAL: docker compose build failed" >&2
  exit 1
fi
if ! $C run --rm --no-deps qiko-core python -c 'from app.core.config import Settings; from app.modules.email.sender import SmtpEmailSender; Settings().assert_secrets_set(); SmtpEmailSender().check_connection()'; then
  echo "FATAL: resolved non-dev environment failed startup preflight" >&2
  exit 1
fi

# For an existing live database, quiesce every write-capable/public service after the new images are
# built, then take the validated backup. This creates a short deliberate maintenance window but
# prevents writes between the recovery point and the migration.
if [ "$EXISTING_DB" -eq 1 ]; then
  if ! $C stop caddy worker qiko-core creator admin; then
    echo "FATAL: could not quiesce the existing application stack" >&2
    exit 1
  fi
  mkdir -p "$BASE/backups"
  STAMP=$(date +%F-%H%M%S)
  BACKUP="$BASE/backups/qiko-live-$STAMP.dump"
  if ! $C exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP"; then
    echo "FATAL: pre-deploy database backup failed" >&2
    rm -f "$BACKUP"
    exit 1
  fi
  if [ ! -s "$BACKUP" ] || ! $C exec -T db pg_restore -l < "$BACKUP" >/dev/null; then
    echo "FATAL: pre-deploy database backup is empty or invalid" >&2
    rm -f "$BACKUP"
    exit 1
  fi
  echo "pre-deploy backup written to $BACKUP"
  ls -1t "$BASE"/backups/qiko-live-*.dump | tail -n +8 | xargs -r rm -f
fi

# Run migrations from the newly built image BEFORE exposing the new API or starting the worker.
# DB + Redis are already healthy; `run` creates an isolated one-off qiko-core container.
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

# Only after migrations succeed do we recreate the public API, worker and web applications.
if ! $C rm -sf caddy worker qiko-core creator admin; then
  echo "FATAL: docker compose could not remove the previous stateless containers" >&2
  exit 1
fi
if ! $C up -d --force-recreate qiko-core worker creator admin caddy; then
  echo "FATAL: docker compose could not recreate the live application stack" >&2
  exit 1
fi
sleep 25

# Validate the NEW stack directly on the box before DNS is touched. This cannot accidentally check
# the old public qiko.ai origin during the first cutover.
healthy=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if $C exec -T qiko-core python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read()'; then
    healthy=1
    break
  fi
  echo "local qiko-core health check failed (attempt $i/12), retrying in 10s..."
  sleep 10
done
if [ "$healthy" -ne 1 ]; then
  echo "FATAL: the new qiko-core container did not become healthy" >&2
  exit 1
fi
for url in http://creator:3000/login http://admin:3001/login; do
  if ! $C exec -T qiko-core python -c \
    "import urllib.request; urllib.request.urlopen('$url', timeout=10).read(1)"; then
    echo "FATAL: web application probe failed for $url" >&2
    exit 1
  fi
done
for host in qiko.ai admin.qiko.ai; do
  if ! $C exec -T qiko-core python -c \
    "import socket; s=socket.create_connection(('caddy', 80), timeout=5); s.sendall(b'GET /login HTTP/1.1\\r\\nHost: $host\\r\\nConnection: close\\r\\n\\r\\n'); response=s.recv(64); s.close(); assert response.startswith((b'HTTP/1.1 200', b'HTTP/1.1 308'))"; then
    echo "FATAL: Caddy route probe failed for $host" >&2
    exit 1
  fi
done

# Every required service must be running. The worker has no HTTP health endpoint, so running state is
# the appropriate check; qiko-core was validated above and DB/Redis have compose health checks.
for service in qiko-core worker creator admin caddy db redis; do
  SERVICE_ID="$($C ps -q "$service" --status running 2>/dev/null || true)"
  if [ -z "$SERVICE_ID" ]; then
    echo "FATAL: required service $service is not running" >&2
    exit 1
  fi
done
for service in qiko-core db redis; do
  ready=0
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    SERVICE_ID="$($C ps -q "$service" --status running 2>/dev/null || true)"
    if [ -n "$SERVICE_ID" ]; then
      HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$SERVICE_ID")"
      [ "$HEALTH" = "healthy" ] && ready=1 && break
    fi
    sleep 5
  done
  if [ "$ready" -ne 1 ]; then
    echo "FATAL: required service $service did not become healthy" >&2
    exit 1
  fi
done

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
