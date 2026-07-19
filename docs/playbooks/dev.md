# Playbook: dev (local)

Local development. Every engineer runs the identical Docker stack. No AWS, no real secrets.

## Stack
`docker-compose.yml` + `docker-compose.dev.yml` bring up `qiko-core` (:8000), `db` (pgvector:pg18,
:5432) and `redis` (:6379), plus `creator` (:3000) and `admin` (:3001). Project name: `qiko-dev`.
The dev overlay sets `USE_DB_STORES=false` and `TASK_BACKEND=eager`, so data is in-memory and tasks
run inline (no separate worker container is needed). Integrations use dev stub gateways;
embeddings and the LLM fall back to local/stub when no AWS credentials are present.

## First run
```bash
cd platform
cp .env.example .env                        # dev defaults (POSTGRES_PASSWORD=change-me-locally, etc.)
export COMPOSE_PROJECT_NAME=qiko-dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head
curl -s localhost:8000/health               # expect {"status":"ok","environment":"dev",...}
```

Frontend (separate terminals). You can run the apps inside Docker (ports 3000/3001 above) or on the
host for hot reload:
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

# lint + build (frontend)
cd frontend && pnpm -r lint && pnpm --filter creator build && pnpm --filter admin build

# new migration after model changes
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core \
  alembic revision --autogenerate -m "describe change"
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head
```

## Reset (safe: dev data only)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v   # drops the dev volume
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Troubleshooting
- **db unhealthy / "PostgreSQL data ... unused mount":** pg18 stores data in a version subdir; the
  volume must mount at `/var/lib/postgresql` (already set in `docker-compose.yml`). If you hit a
  stale volume, run `down -v` then `up`.
- **`alembic.ini not found` in the container:** the image must COPY `alembic/` and `alembic.ini`
  (already in the Dockerfile). Rebuild `qiko-core`.
- **401 on `/api/v1/*`:** endpoints require the `qiko_access` cookie; log in first (`/auth/login`).
- **LLM answers look like the stub:** no AWS credentials locally, so the gateway falls back to the
  stub provider. Set `AI_PROVIDER` plus AWS credentials to use Bedrock.
- **Long jobs (tender generation, ingest) run in the request:** expected in dev, because
  `TASK_BACKEND=eager` runs them inline. In non-dev they run on the arq worker tier.
