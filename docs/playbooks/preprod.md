# Playbook — preprod (staging)

Client-facing staging for validation before production. Real AWS, real integrations (test keys),
its own database and secrets. Mirrors live as closely as possible.

## Stack
`docker-compose.yml` + `docker-compose.preprod.yml` on the preprod EC2 host, behind Caddy, secrets
from AWS SSM under the preprod prefix. Postgres has automated backups + PITR.

## Deploy
Every push to `main` triggers `.github/workflows/deploy-preprod.yml`: GitHub Actions fast-forwards
the `preprod` branch, then dispatches `.github/deploy/redeploy-preprod.sh` to the preprod host via
**AWS SSM Run Command** (not a host-side systemd watcher). The workflow health-checks the result
and rolls back automatically on failure.

To deploy manually (e.g. re-running after a transient failure), run the same script directly on
the host:
```bash
# on the preprod host
cd /opt/docker/qiko/platform
bash .github/deploy/redeploy-preprod.sh
```

## Secrets (AWS SSM)
Loaded at container start from SSM (never in the image or `.env`). Set/rotate with:
```bash
aws ssm put-parameter --name /qiko-preprod/STRIPE_SECRET --type SecureString --value '…' --overwrite
```
Required per env: `POSTGRES_*`, `SESSION_SECRET`, `AWS_REGION`, Bedrock config, `STRIPE_SECRET`/
`STRIPE_WEBHOOK_SECRET`, `WHATSAPP_*`, `GA4_*`, SMTP creds, `SIGNAL_ENGINE_*`.

## Verify (post-deploy)
```bash
curl -sf https://preprod.qiko.ai/api/v1/health        # 200
# containers healthy
docker compose -f docker-compose.yml -f docker-compose.preprod.yml ps
# smoke + SLO check
BASE_URL=https://preprod.qiko.ai k6 run loadtest/smoke.js
```

## Rollback
```bash
# redeploy the previous image/commit; external volumes keep the data
git checkout <previous-good-sha> && docker compose -f docker-compose.yml -f docker-compose.preprod.yml up -d --build
```
If a migration is bad: `alembic downgrade -1` (only if the down-revision is safe), else restore from
the latest backup (see live playbook — same procedure).

## Gate before promoting to live
- All CI green (ruff + pytest coverage), k6 SLOs met (error rate <1%, p95 <800ms).
- OWASP checklist reviewed (`loadtest/SLOs-and-hardening-checklist.md`).
- Webhooks signature-verified with the preprod secrets; auth + RBAC exercised.
