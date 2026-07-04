# Playbook — dev (local)

Local development. Every engineer runs the identical Docker stack. No AWS, no real secrets.

## Stack
`docker-compose.yml` + `docker-compose.dev.yml` → `qiko-core` (:8000), `db` (pgvector:pg18, :5432),
`redis` (:6379). Project name: `qiko-dev`. Integrations use dev **stub gateways**; embeddings/LLM
fall back to local/stub when no AWS creds are present.

## First run
```bash
cd platform
cp .env.example .env                        # dev defaults (POSTGRES_PASSWORD=change-me-locally, etc.)
export COMPOSE_PROJECT_NAME=qiko-dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head
curl -s localhost:8000/health               # expect {"status":"ok","environment":"dev"}
```

Frontend (separate terminals):
```bash
cd platform/frontend && pnpm install
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter creator dev   # :3000
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter admin  dev   # :3001
```

## Everyday commands
```bash
# logs / status
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f qiko-core
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

# tests + lint (backend)
cd qiko-core && python -m pytest && ruff check .

# new migration after model changes
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core \
  alembic revision --autogenerate -m "describe change"
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head
```

## Reset (safe — dev data only)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v   # drops the dev volume
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Troubleshooting
- **db unhealthy / "PostgreSQL data … unused mount"** — pg18 stores data in a version subdir; the
  volume must mount at `/var/lib/postgresql` (already fixed in `docker-compose.yml`). If you hit a
  stale volume: `down -v` then `up`.
- **`alembic.ini not found` in container** — the image must COPY `alembic/` + `alembic.ini`
  (already in the Dockerfile). Rebuild `qiko-core`.
- **401 on `/api/v1/*`** — endpoints require the `qiko_access` cookie; log in first (`/auth/login`).
- **LLM answers look like the stub** — no AWS creds locally, so the gateway falls back to the stub
  provider. Set `AI_PROVIDER`/creds to use Bedrock.
