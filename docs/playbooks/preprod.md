# Playbook: preprod (staging)

Client-facing staging for validation before production. Real AWS, real integrations (test keys),
its own database and secrets. Mirrors live as closely as possible.

## Stack
`docker-compose.yml` + `docker-compose.preprod.yml` on the preprod EC2 host, behind Caddy (the
preprod overlay adds the `caddy` service on ports 80/443). Secrets come from AWS SSM. The full
stack runs `qiko-core`, the arq `worker`, `creator`, `admin`, `db` (pgvector) and `redis`. Preprod
sets `ENVIRONMENT=preprod`, and the base compose sets `USE_DB_STORES=true` and `TASK_BACKEND=arq`,
so the startup guard is satisfied and data persists to named volumes.

## Deploy (automated)
Every push to `main` triggers `.github/workflows/deploy-preprod.yml`. Because the org disables
deploy keys and port 22 is closed on the SSM-managed boxes, code is shipped to the host via **S3**,
not a host-side git pull:

1. CI packages a clean `git archive` tarball (tracked files only, no `.git`/`node_modules`).
2. CI keeps the currently-live artifact as `deploy-previous.tar.gz` (rollback target), then uploads
   the new tarball to `s3://qiko-v2-preprod-deploy-064247010239/preprod/` as both
   `deploy-<sha>.tar.gz` and `deploy-latest.tar.gz`.
3. CI dispatches `.github/deploy/redeploy-preprod.sh` to the host via **AWS SSM Run Command**.
4. On the host, the script downloads `deploy-latest.tar.gz`, extracts to a staging dir, verifies it
   contains `docker-compose.yml`, and atomically swaps it into `/opt/docker/qiko/platform`
   (persistent state lives in named Docker volumes, independent of the directory).
5. It preserves the live `.env` across the swap (only bootstrapping from the SSM parameter
   `/qiko/preprod/ENV` if the host has none yet), and refuses to deploy if `.env` is missing
   `POSTGRES_PASSWORD`.
6. It prunes dangling images and build cache (pre-build sweep), runs `docker compose build`, then
   `up -d --force-recreate`.
7. It runs `alembic upgrade head` inside `qiko-core` with up to 8 retries (the container may still
   be starting); the final failure is fatal.
8. It **auto-reclaims disk**: `docker image prune -af` plus `docker builder prune -f` and drops the
   previous release dir. This never touches named volumes, so Postgres data is safe.
9. CI health-checks `https://preprod.qiko.ai/api/v1/health` (expects 200). On any failure it
   restores `deploy-previous.tar.gz` to `deploy-latest.tar.gz` and redeploys.

IAM: the CI user `qiko-ci-deploy` has S3 read/write on the deploy prefix; the host role
`qiko-preprod-ec2` has S3 read on it.

### Deploy manually
Re-run the workflow (for a transient failure) or run the on-box script directly (it always pulls
the latest artifact from S3):
```bash
# re-run from your machine
gh workflow run deploy-preprod.yml

# or, on the preprod host, run the same script the pipeline uses
bash /opt/docker/qiko/platform/.github/deploy/redeploy-preprod.sh
```

## Secrets (AWS SSM)
The whole `.env` is stored as one SecureString parameter, `/qiko/preprod/ENV`, and used only to
bootstrap a fresh host (the live `.env` on the box is the source of truth once set). To change a
secret, update the `.env` on the host (or update the SSM parameter and re-bootstrap), then redeploy.
```bash
# read the bootstrap env (careful: prints secrets)
aws ssm get-parameter --region eu-central-1 --name /qiko/preprod/ENV --with-decryption \
  --query Parameter.Value --output text

# overwrite it
aws ssm put-parameter --region eu-central-1 --name /qiko/preprod/ENV --type SecureString \
  --value "$(cat updated.env)" --overwrite
```
Required keys in `.env`: `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`, `SESSION_SECRET`,
`ENCRYPTION_KEY`, `USE_DB_STORES=true`, `TASK_BACKEND=arq`, `AWS_REGION` and Bedrock config,
`PUBLIC_API_BASE` (baked into the frontend build), plus any integration keys in use
(`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`, `WHATSAPP_*`, `GA4_*`, SMTP, `SIGNAL_ENGINE_*`,
Salesforce/Vapi/Calendly). Never commit these.

## Verify (post-deploy)
```bash
curl -sf https://preprod.qiko.ai/api/v1/health        # 200
# containers healthy (the arq worker shows "unhealthy" by design: it has no HTTP server on :8000)
docker compose -f docker-compose.yml -f docker-compose.preprod.yml ps
# smoke + SLO check
BASE_URL=https://preprod.qiko.ai k6 run loadtest/smoke.js
```

## Rollback
The pipeline rolls back automatically if the health check fails (it restores
`deploy-previous.tar.gz` and redeploys). To roll back manually, restore the previous artifact and
re-run the on-box script:
```bash
aws s3 cp s3://qiko-v2-preprod-deploy-064247010239/preprod/deploy-previous.tar.gz \
          s3://qiko-v2-preprod-deploy-064247010239/preprod/deploy-latest.tar.gz
bash /opt/docker/qiko/platform/.github/deploy/redeploy-preprod.sh   # on the host
```
Named volumes keep the data. If a migration is bad, `alembic downgrade -1` (only if the
down-revision is safe), else restore from the latest backup (see the live playbook).

## Gate before promoting to live
- Do not send a preprod test email until the live `https://qiko.ai/qiko-logo-email.png` asset has
  been deployed and verified as HTTP 200 with `Content-Type: image/png` using the live playbook.
- All CI green (ruff + pytest coverage, frontend lint + build), k6 SLOs met (error rate < 1%,
  p95 < 800 ms).
- OWASP checklist reviewed (`loadtest/SLOs-and-hardening-checklist.md`).
- Webhooks signature-verified with the preprod secrets; auth + RBAC exercised.
