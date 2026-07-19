# Playbook: live (production)

Production. Change-controlled. Always promote a preprod-validated build; never experiment here.

## Stack
`docker-compose.yml` + `docker-compose.live.yml` on the production EC2 host, behind Caddy, secrets
from AWS SSM under the live prefix. The live overlay sets `ENVIRONMENT=live`, `LOG_LEVEL=WARNING`
and resource limits; the base compose sets `USE_DB_STORES=true` and `TASK_BACKEND=arq`, so the
startup guard is satisfied. Persistent state lives in named Docker volumes; take encrypted backups.

## Deploy model
Live uses the same delivery model as preprod: an S3 code artifact swapped in on the box via AWS SSM
Run Command (the org disables deploy keys and port 22 is closed, so there is no host-side git pull).
The automated GitHub workflow is currently wired for preprod only
(`.github/workflows/deploy-preprod.yml` + `.github/deploy/redeploy-preprod.sh`). The live pipeline
mirrors it: a `deploy-live.yml` plus a `redeploy-live.sh` variant pointed at the live S3 bucket and
the live instance id. Until that live workflow is added, promote to live with the on-box procedure
below, which uses the identical compose files and migration/backup steps.

## Pre-flight (must all be true)
- The exact build (commit SHA) was validated in preprod: CI green, k6 SLOs met, OWASP checklist clean.
- Migrations reviewed and reversible (or a backup taken immediately before).
- A rollback target (the previous artifact / SHA) is known.
- Announce the window if downtime is possible.

## Deploy (on-box, manual promotion)
Run these on the live host. They ship the validated build's artifact and never touch named volumes.
```bash
export COMPOSE_PROJECT_NAME=qiko-live
cd /opt/docker/qiko/platform
C="docker compose -f docker-compose.yml -f docker-compose.live.yml"

# 1) backup first (safety net)
$C exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > ~/qiko-live-$(date +%F-%H%M).sql.gz

# 2) put the validated artifact in place (from the live deploy bucket), preserving the live .env,
#    then rebuild + recreate. Persistent state is in named volumes, so a full swap is safe.
#    (Fetch/extract the validated deploy-<sha>.tar.gz over this dir, keeping .env; the redeploy
#    script automates exactly this on preprod.)

# 3) rebuild, recreate, migrate
$C build
$C up -d --force-recreate
$C exec -T qiko-core alembic upgrade head
```

## Verify
```bash
curl -sf https://qiko.ai/api/v1/health
docker compose -f docker-compose.yml -f docker-compose.live.yml ps    # all healthy
```
The arq `worker` container reports "unhealthy" by design (it has no HTTP server on :8000); that is
expected, not a fault. Watch logs and error tracking (Sentry) for 10 minutes; confirm a real login,
a chat answer and a webhook.

## Rollback (fast)
Redeploy the previous validated artifact/SHA with the same on-box steps above (backup, swap in the
previous artifact, `up -d --force-recreate`, `alembic upgrade head` if needed). Named volumes keep
the data. If a migration corrupted data, restore the pre-deploy dump:
```bash
gunzip -c ~/qiko-live-<ts>.sql.gz | docker compose -f docker-compose.yml -f docker-compose.live.yml \
  exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

## Danger zone (stop and get explicit human approval)
`docker compose down -v`, dropping/truncating tables, secret rotation, Stripe live refunds, real
outbound sends (email/WhatsApp) at scale, force-push/history rewrite. State the action, then wait.

## Incident quick-reference
- **Site down:** `docker compose ... ps`; restart the unhealthy container; check Caddy and DB health.
- **Disk full (ENOSPC):** `df -h`; `docker image prune -af` and `docker builder prune -f` (never
  touches named volumes). The redeploy script does this automatically each deploy.
- **DB unhealthy:** check disk, then Postgres logs; never `down -v` in production.
- **Bad deploy:** roll back to the previous artifact/SHA (above); data is safe on named volumes.
- **Suspected breach:** rotate `SESSION_SECRET` and affected integration secrets in SSM, redeploy
  (invalidates sessions), review access logs. Note that rotating `SESSION_SECRET` does not brick
  encrypted secrets because `ENCRYPTION_KEY` is a separate key.
