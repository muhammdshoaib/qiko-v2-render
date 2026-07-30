# Playbook: live (production)

Production is **qiko.ai** (creator app + API on one origin) and **admin.qiko.ai** (admin app).
Change-controlled: always promote a preprod-validated build; never experiment here.

## Stack
`docker-compose.yml` + `docker-compose.live.yml` on the production EC2 host, behind Caddy, with
secrets from AWS SSM under the live prefix. The live overlay sets `ENVIRONMENT=live`,
`LOG_LEVEL=WARNING`, `USE_DB_STORES=true`, `TASK_BACKEND=arq` and per-service resource limits, and
adds the `caddy` service (ports 80/443) using `Caddyfile.live`. `db` and `redis` stay on the
private `app-net` only and are never exposed. Compose project name: `qiko-live`. Persistent state
lives in named Docker volumes (`postgres_data`, `caddy_data`, `caddy_config`); take encrypted
backups. The overlay differs from preprod only by environment, log level, domain and limits.

## Deploy model
Live uses the same delivery model as preprod: a clean `git archive` tarball shipped to the box via
S3, then swapped in on the host via AWS SSM Run Command (the org disables deploy keys and port 22
is closed, so there is no host-side git pull). The pipeline is `.github/workflows/deploy-live.yml`
+ `.github/deploy/redeploy-live.sh`, pointed at the live S3 bucket, the `qiko-live` project and the
live compose overlay.

**Production never auto-deploys.** `deploy-live.yml` has NO `push` trigger. It runs only on a
manual `workflow_dispatch`, requires typing `deploy-live` in the confirm input, and is gated by
the `live` GitHub Environment (configure required reviewers on it). Preprod, by contrast, deploys
on every push to `main`.

## One-time setup (before the first live deploy)
1. **Production box:** provision the EC2 host (SSM-managed, Docker + compose installed, an IAM role
   with S3 read on the live deploy prefix and Bedrock access). It is NOT hardcoded anywhere.
2. **GitHub secrets/variables** (repo settings; scope the `live` ones to the `live` Environment):
   - `LIVE_SSM_INSTANCE_ID` - the production box's SSM instance id (e.g. `i-0abc...`). REQUIRED.
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` - CI deploy credentials (shared
     with preprod; the CI user needs S3 read/write on the live deploy prefix and `ssm:SendCommand`
     / `ssm:GetCommandInvocation` on the live box).
   - Optionally `LIVE_HOST` if you script external health checks against a raw host rather than the
     domain.
3. **S3 deploy bucket:** create `qiko-v2-live-deploy-<accountid>` (the workflow + redeploy script
   default to `qiko-v2-live-deploy-064247010239`, mirroring the preprod convention). Grant the CI
   user read/write and the host role read on the `live/` prefix. If you use a different name,
   update `DEPLOY_BUCKET` in `deploy-live.yml` and `BUCKET` in `redeploy-live.sh`.
4. **Live env / secrets in SSM:** store the full `.env` as one SecureString parameter
   `/qiko/live/ENV` (used only to bootstrap a fresh host; the on-box `.env` is the source of truth
   once set). Build it from `.env.live.example`. See the checklist below.
5. **`live` GitHub Environment:** create it and add required reviewers (and optionally a wait
   timer) so every production run needs human approval.

## Required production env vars + secrets (from `.env.live.example`)
Store as `/qiko/live/ENV` and/or place as `.env` on the box. Real values via SSM, never committed.

**Must be set (deploy refuses to start / breaks without these):**
- `ENVIRONMENT=live`, `LOG_LEVEL=WARNING`
- `USE_DB_STORES=true`, `TASK_BACKEND=arq` (startup guard enforces both in non-dev)
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and a matching `DATABASE_URL` assembled from those values for the private `db` service
- `REDIS_URL=redis://redis:6379/0`
- `SESSION_SECRET` - strong random; the startup guard refuses the insecure default in non-dev.
- `ENCRYPTION_KEY` - strong random, SEPARATE from `SESSION_SECRET` (encryption-at-rest for channel
  tokens / Vapi / Salesforce secrets; rotating `SESSION_SECRET` must not brick these).
- `CONSENT_PSEUDONYM_KEYS` - JSON keyring with an active key of at least 32 random characters. Retain
  every prior version required to read legal consent history.
- `CONSENT_PSEUDONYM_ACTIVE_VERSION=v1` and `FORWARDED_ALLOW_IPS=172.28.20.2`.
- `PUBLIC_API_BASE=https://qiko.ai/api/v1` - baked into the frontend build (creator + admin).
- `PUBLIC_BASE_URL=https://qiko.ai`
- `PUBLIC_CHAT_ENABLED=false` (enterprise launch; `/embed/*`, `/widget.js` and the public chat API are disabled)
- `COOKIE_DOMAIN=.qiko.ai` - so qiko.ai and admin.qiko.ai share the auth/CSRF cookies.
- `CORS_ALLOW_ORIGINS=["https://qiko.ai","https://admin.qiko.ai"]` - MUST be a JSON array (a bare
  or comma-separated string fails to parse and the app will not start).
- `AWS_REGION=eu-central-1` and Bedrock config (`AI_PROVIDER=bedrock`, `BEDROCK_MODEL`,
  `BEDROCK_INFERENCE_PROFILE`, `EMBEDDINGS_PROVIDER=titan`, `EMBEDDINGS_DIM`, `VOICE_MODEL`).
- Email: `EMAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`.

**Optional (set only those in use):** `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`, `WHATSAPP_*`,
`SLACK_*`, `CLICKUP_API_TOKEN`, `CALENDLY_TOKEN`, `SIGNAL_ENGINE_URL`/`SIGNAL_ENGINE_API_KEY`,
`GA4_*`, `SALESFORCE_*`, `SENTRY_DSN`, `OTEL_ENABLED`/`OTEL_EXPORTER_ENDPOINT`.

```bash
# write the bootstrap env to SSM (careful: contains secrets)
aws ssm put-parameter --region eu-central-1 --name /qiko/live/ENV --type SecureString \
  --value "$(cat .env.live)" --overwrite
# read it back
aws ssm get-parameter --region eu-central-1 --name /qiko/live/ENV --with-decryption \
  --query Parameter.Value --output text
```

## Pre-flight (must all be true before cutover)
- The exact build (commit SHA) was validated in preprod: CI green, k6 SLOs met, OWASP checklist clean.
- All required live env vars + secrets are in `/qiko/live/ENV` (checklist above).
- Migrations reviewed and reversible (or a backup taken immediately before; the deploy script also
  takes a pre-migration `pg_dump`).
- A rollback target (the previous artifact / SHA) is known.
- DNS is ready to point but NOT yet pointed (Cloudflare change is the deliberate last step).
- Announce the window if downtime is possible.

## Cutover (the exact sequence a human runs)
Do steps 1-4 with Cloudflare still NOT pointing at the box, so you validate before going live.

1. **Ship + bring up the live stack** via the manual pipeline (recommended):
   ```bash
   gh workflow run deploy-live.yml -f confirm=deploy-live
   # then approve the `live` environment gate in the GitHub UI when prompted
   ```
   The on-box script serializes deploys with a lock and runs with `umask 077`. After restoring or
   bootstrapping `.env`, it sets mode `600`, verifies ownership by the deployment user, and rejects
   group/other permissions. It starts and health-checks only `db` and `redis`, validates Compose,
   builds, and runs the non-dev startup preflight. For an existing database it then stops the public
   and write-capable services and creates and validates a pre-migration dump. Migration runs from the
   new image in a one-off `qiko-core` container. Only after success does the script recreate
   `qiko-core`, `worker`, `creator`, `admin` and `caddy`, probe the local applications/routes, and
   require every service to be running plus `qiko-core`, `db` and `redis` to be healthy.

   The script does not query public `qiko.ai`, which still points at the old origin before step 3.
   To run the same checked path directly on the box after the reviewed artifact is in S3:
   ```bash
   bash /opt/docker/qiko/platform/.github/deploy/redeploy-live.sh
   ```

2. **Validate on the box before DNS** (bypass Cloudflare by resolving the domains to the box IP):
   ```bash
   curl -sf --resolve qiko.ai:443:<BOX_IP> https://qiko.ai/api/v1/health          # expect 200
   curl -sf --resolve admin.qiko.ai:443:<BOX_IP> https://admin.qiko.ai/ -o /dev/null
   docker compose -f docker-compose.yml -f docker-compose.live.yml ps             # all healthy
   ```
   Caddy will obtain Let's Encrypt certs for qiko.ai + admin.qiko.ai automatically once the DNS
   records resolve to the box (HTTP-01/TLS-ALPN). If Cloudflare proxying (orange cloud) is on, use
   Full (strict) SSL, or grey-cloud during issuance so Caddy can complete the ACME challenge.

3. **Point Cloudflare at the box (deliberate last step, done by a human):**
   - `qiko.ai` -> production box (A/AAAA or CNAME).
   - `admin.qiko.ai` -> production box.
   - SSL/TLS mode: Full (strict). Leave grey-cloud until certs issue, then enable proxying if desired.

4. **Post-cutover health-check:**
   ```bash
   curl -sf https://qiko.ai/api/v1/health           # 200
   curl -sfI https://admin.qiko.ai/                  # 200/redirect to login
   curl -sSf -o /dev/null -w '%{http_code} %{content_type}\n' \
     https://qiko.ai/qiko-logo-email.png             # exactly: 200 image/png
   BASE_URL=https://qiko.ai k6 run loadtest/smoke.js # smoke + SLOs
   ```
   The email wordmark uses the stable live URL above. Deploy and verify the live PNG asset before
   sending any preprod test email, because preprod email deliberately loads that live asset. The arq
   `worker` has no HTTP server on :8000, so its inherited image health check is disabled. It must be
   running, but has no health status. Watch logs and Sentry for 10 minutes; confirm a real login, a
   chat answer and a webhook.

## Provision a tenant

Tenant provisioning uses an operator-owned JSON manifest and the configured `DATABASE_URL`. The CLI
is a dry-run unless `--apply` is supplied, validates the full plan before writing, and does not send
email. It creates or aligns the tenant, users, roles and agents in one database transaction.

The real manifest contains customer email addresses, so keep it in an access-controlled path outside
the repository. Never commit the real manifest, customer details, passwords or secrets. The
checked-in `qiko-core/scripts/provision_tenant.example.json` uses fake `example.com` data only.
New users receive unique unrecoverable bootstrap credentials and establish their own password through
the reset flow; no shared initial password exists.

```bash
cp qiko-core/scripts/provision_tenant.example.json /secure/operator/path/tenant.json
chmod 600 /secure/operator/path/tenant.json

# Review first. No writes.
cd qiko-core
uv run python scripts/provision_tenant.py \
  --manifest /secure/operator/path/tenant.json

# Apply the reviewed manifest. Live requires the exact tenant slug as confirmation.
uv run python scripts/provision_tenant.py \
  --manifest /secure/operator/path/tenant.json \
  --apply \
  --confirm-tenant example-tenant

# Repeat the dry-run. It should report zero planned changes.
uv run python scripts/provision_tenant.py \
  --manifest /secure/operator/path/tenant.json
```

Existing passwords are unchanged by default. `--reset-existing-passwords` replaces them with unique,
unrecoverable values and forces each user through password reset; it is a separate reviewed
operation. Agent config is merged, so omitted keys are preserved; set `"archived": true` to keep a
worker hidden. Never pass a database URL, password, email address or secret on the command line.

## Rollback plan
- **Controlled, manual only:** the workflow never starts a second deploy automatically after failure.
  First wait for the original SSM command to become terminal, inspect logs and `alembic current`, and
  confirm the previous artifact understands the current schema.
- **Reviewed artifact rollback:**
  ```bash
  aws s3 cp s3://qiko-v2-live-deploy-064247010239/live/deploy-previous.tar.gz \
            s3://qiko-v2-live-deploy-064247010239/live/deploy-latest.tar.gz
  bash /opt/docker/qiko/platform/.github/deploy/redeploy-live.sh   # on the box
  ```
  Named volumes keep the data, so an artifact rollback is safe.
- **Bad migration (data corrupted):** an artifact rollback does not undo a schema change. Restore
  the pre-deploy dump (the redeploy script writes one to `/opt/docker/qiko/backups/`, or you took
  one manually):
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.live.yml \
    exec -T db sh -c 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < /opt/docker/qiko/backups/qiko-live-<ts>.dump
  ```
  If the down-revision is known safe, `alembic downgrade -1` is an alternative.
- **DNS rollback:** if the box is unhealthy and cannot be fixed quickly, revert the Cloudflare
  records (repoint away / back to the previous origin) - the fastest way to stop serving a broken
  production.

## Danger zone (stop and get explicit human approval)
`docker compose down -v`, dropping/truncating tables, secret rotation, Stripe live refunds, real
outbound sends (email/WhatsApp) at scale, force-push/history rewrite. State the action, then wait.

## Incident quick-reference
- **Site down:** `docker compose ... ps`; restart the unhealthy container; check Caddy and DB health.
- **TLS errors after cutover:** check Cloudflare SSL mode is Full (strict) and that Caddy issued
  certs (`docker compose ... logs caddy`); grey-cloud briefly if ACME cannot complete behind proxy.
- **Disk full (ENOSPC):** `df -h`; `docker image prune -af` and `docker builder prune -f` (never
  touches named volumes). The redeploy script does this automatically each deploy.
- **DB unhealthy:** check disk, then Postgres logs; never `down -v` in production.
- **Bad deploy:** roll back to the previous artifact/SHA (above); data is safe on named volumes.
- **Suspected breach:** rotate `SESSION_SECRET` and affected integration secrets in SSM, redeploy
  (invalidates sessions), review access logs. Rotating `SESSION_SECRET` does not brick encrypted
  secrets because `ENCRYPTION_KEY` is a separate key.
