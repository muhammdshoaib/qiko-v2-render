# Qiko V2 Platform

AI-first, agentic, dockerised platform. Two deployables, two languages.

| Deployable | Stack | Role |
|---|---|---|
| `qiko-core/` | Python 3.11 · FastAPI · SQLAlchemy 2 (async) · Postgres/pgvector · Redis · arq | Modular monolith: identity, agentcore, AI gateway, knowledge/RAG, chat, voice, channels, billing, admin, agents, teams, leads, excel, signal, tasks, email, storage |
| `frontend/` | Next.js 15 (App Router) · React 19 · Tailwind 4 · TanStack Query · pnpm/Turborepo | `apps/creator` (Creator/Studio) · `apps/admin` (Admin console) · shared `packages/ui` + `packages/api-client` |

Everything runs in Docker, behind Caddy, with secrets in AWS SSM per environment. The
architecture and the decisions behind it live in `../02-target-architecture.md` and
`../05-decisions-adr.md`.

---

## Principles (do not break these)

- **Agentic-first.** Every generative feature (chat, RFP evaluation, voice, signal) goes through
  `agentcore` (grounded generator → independent critic → accept/escalate gate → feedback flywheel)
  and the provider-agnostic **AI gateway** (Bedrock/Claude default, configured fallback). No feature
  makes a direct LLM call that bypasses the gate.
- **Multi-tenant by construction.** The tenant is derived from the verified auth token (never a
  client header). Data access is filtered centrally; a tenant can never read another tenant's data.
- **Config, not code.** Model, region, embeddings, provider, integrations and secrets are all
  configuration (env / SSM). Switching a provider needs no code change.
- **Secure by default.** httpOnly cookie auth + CSRF, RBAC on every endpoint, rate limiting,
  security headers, signature-verified webhooks, encrypted-at-rest secrets.

---

## Repository layout

```
platform/
├── qiko-core/                # FastAPI backend
│   ├── app/
│   │   ├── core/             # config, db, logging, tenancy, middleware, ratelimit,
│   │   │                     # observability, crypto, deps (auth/RBAC), dev_gateways
│   │   ├── db/               # SQLAlchemy models, async stores, migration helpers
│   │   ├── modules/          # one folder per domain (service + router + tests)
│   │   └── main.py           # app factory: middleware + routers + service singletons
│   ├── alembic/              # migrations
│   └── tests/                # pytest (functional), 80% coverage gate
├── frontend/                 # Next.js monorepo (pnpm + turbo)
│   ├── apps/creator          # Creator/Studio SPA
│   ├── apps/admin            # Admin console
│   └── packages/{ui,api-client}
├── docker-compose.yml        # base services (qiko-core, db=pgvector:pg18, redis)
├── docker-compose.dev.yml    # dev overlay (ports, hot reload)
├── docker-compose.preprod.yml
├── docker-compose.live.yml
├── loadtest/                 # k6 load test + SLO/OWASP checklist
└── docs/playbooks/           # per-environment runbooks (dev / preprod / live)
```

---

## Environments

| Env | Purpose | Compose files |
|---|---|---|
| **dev** | Local development, identical stack for every engineer | `docker-compose.yml` + `docker-compose.dev.yml` |
| **preprod** | Client-facing staging for validation | `docker-compose.yml` + `docker-compose.preprod.yml` |
| **live** | Production | `docker-compose.yml` + `docker-compose.live.yml` |

Each environment has its own database, secrets and region profile. See the playbook for each:
- [`docs/playbooks/dev.md`](docs/playbooks/dev.md)
- [`docs/playbooks/preprod.md`](docs/playbooks/preprod.md)
- [`docs/playbooks/live.md`](docs/playbooks/live.md)

---

## Quick start (dev)

```bash
cd platform
cp .env.example .env                       # dev defaults; never commit .env
COMPOSE_PROJECT_NAME=qiko-dev \
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# apply migrations
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head

# verify
curl -s localhost:8000/health            # {"status":"ok",...}
```

Frontend:

```bash
cd platform/frontend
pnpm install
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter creator dev   # http://localhost:3000
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter admin  dev   # http://localhost:3001
```

---

## Testing & quality

```bash
cd platform/qiko-core
python -m pytest            # functional tests, fails under 80% coverage
ruff check .                # lint

cd platform/frontend
pnpm --filter creator build && pnpm --filter admin build   # typecheck + build
```

CI (`.github/workflows/ci.yml`) runs ruff + pytest (coverage gate) on the backend.

---

## API surface

All endpoints are under `/api/v1`, authenticated by the `qiko_access` httpOnly cookie and
RBAC-gated. Highlights: `/auth/*`, `/knowledge/*`, `/agents/*`, `/chat/*`, `/voice/speak`,
`/excel/*`, `/signal/*`, `/teams/*`, `/leads`, `/admin/*`, and public signature-verified webhooks
(`/billing/webhook/stripe`, `/channels/whatsapp/webhook`). Interactive docs at `/docs` in dev.

---

## Deploy & ops

Deploys are Docker-Compose per environment behind Caddy (see the playbooks). Backend migrations
run with `alembic upgrade head` inside the `qiko-core` container. Rollback = redeploy the previous
image tag; data is safe because volumes are external and Postgres has PITR in preprod/live.
Secrets are loaded from AWS SSM per environment — never baked into images or committed.
