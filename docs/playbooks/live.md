# Playbook — live (production)

Production. Change-controlled. Prefer promoting a preprod-validated build; never experiment here.

## Stack
`docker-compose.yml` + `docker-compose.live.yml` on the production EC2 host, behind Caddy, secrets
from AWS SSM under the live prefix. Postgres: automated encrypted backups + PITR; volumes external.

## Pre-flight (must all be true)
- The exact build was validated in preprod (CI green, k6 SLOs met, OWASP checklist clean).
- Migrations reviewed and reversible (or a backup taken immediately before).
- A rollback target (previous image/commit) is known.
- Announce the window if downtime is possible.

## Deploy
```bash
# on the live host
cd /opt/docker/qiko/platform
git fetch && git checkout <validated-sha>
export COMPOSE_PROJECT_NAME=qiko-live

# 1) backup first (safety net)
docker exec qiko-live-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > ~/qiko-live-$(date +%F-%H%M).sql.gz

# 2) migrate then deploy
docker compose -f docker-compose.yml -f docker-compose.live.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.live.yml exec -T qiko-core alembic upgrade head
```

## Verify
```bash
curl -sf https://qiko.ai/api/v1/health
docker compose -f docker-compose.yml -f docker-compose.live.yml ps    # all healthy
```
Watch logs + error tracking (Sentry) for 10 min; confirm a real login + a chat answer + a webhook.

## Rollback (fast)
```bash
git checkout <previous-good-sha>
docker compose -f docker-compose.yml -f docker-compose.live.yml up -d --build
```
External volumes keep the data. If a migration corrupted data, restore the pre-deploy dump:
```bash
gunzip -c ~/qiko-live-<ts>.sql.gz | docker exec -i qiko-live-db-1 sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

## Danger zone (stop & get explicit human approval)
`docker compose down -v`, dropping/truncating tables, secret rotation, Stripe live refunds, real
outbound sends (email/WhatsApp) at scale, force-push/history rewrite. State the action, wait.

## Incident quick-reference
- **Site down** — `docker compose ps`; restart the unhealthy container; check Caddy + DB health.
- **DB unhealthy** — check disk (`df -h`), Postgres logs; never `down -v` in prod.
- **Bad deploy** — roll back to the previous SHA (above); data is safe on external volumes.
- **Suspected breach** — rotate `SESSION_SECRET` + affected integration secrets in SSM, redeploy
  (invalidates sessions), review access logs.
