# Qiko V2 Platform

AI-first, agentic, dockerised platform. Two deployables, two languages.

| Deployable | Stack | Role |
|---|---|---|
| `qiko-core/` | Python 3.11 · FastAPI · SQLAlchemy 2 (async) · Postgres/pgvector · Redis · arq | Modular monolith: identity/auth, agents (workers), agentcore, AI gateway, knowledge/RAG, chat/embed, RFP/tenders, sales intelligence, finance, CRM, teams, billing, channels, voice, admin, leads, signal, notifications |
| `frontend/` | Next.js 15 (App Router) · React 19 · Tailwind · TanStack Query · pnpm/Turborepo | `apps/creator` (Creator/Studio) · `apps/admin` (Admin console) · shared `packages/ui` + `packages/api-client` |

Everything runs in Docker, behind Caddy, with secrets in AWS SSM per environment.

## Architecture in one minute

- **Modular monolith.** One FastAPI app (`qiko-core`). Each domain lives under
  `app/modules/<name>` as a service plus a router, mounted in `app/main.py`. A separate `worker`
  container runs the arq task tier from the same image.
- **AgentCore is the shared engine.** Every generative feature runs on `app/modules/agentcore`:
  a grounded generator, then an independent grounding critic, then an accept/escalate gate, with a
  verified-answers flywheel that lets human-approved answers override the AI draft for the same
  topic thereafter. See `app/modules/agentcore/runtime.py`.
- **A worker is configuration, not a fork.** An `Agent` row (a customer-facing worker) is a
  `WorkerConfig` over AgentCore plus the shared knowledge service. See
  `app/modules/workers/config.py` and `app/core/deps.py:assemble_worker`.
- **Provider-agnostic AI gateway.** AgentCore depends only on the `LLMProvider` protocol
  (`app/modules/ai/gateway.py`). The default provider is AWS Bedrock/Claude in `eu-central-1`,
  wrapped in a fallback provider; a deterministic `StubProvider` is used for dev and tests when no
  AWS credentials are present.
- **Data.** Postgres with pgvector for the knowledge base (tenant-scoped RAG). Redis backs the arq
  queue. Persistent state lives in named Docker volumes.

## Principles (do not break these)

- **Agentic-first.** Every generative feature (chat, RFP drafting, evaluation, voice, signal) goes
  through AgentCore (grounded generator, independent critic, accept/escalate gate, feedback
  flywheel) and the provider-agnostic AI gateway. No feature makes a direct LLM call that bypasses
  the gate.
- **Multi-tenant by construction.** The tenant is derived from the verified auth token, never a
  client header (see `app/core/deps.py:authed_tenant`). Data access is filtered centrally; a tenant
  can never read another tenant's data.
- **Config, not code.** Model, region, embeddings, provider, integrations, secrets and per-worker
  behaviour are all configuration (env / SSM / `Agent.config`). Switching a provider needs no code
  change.
- **Secure by default.** httpOnly cookie auth plus CSRF, RBAC on every endpoint, rate limiting,
  security headers, signature-verified webhooks, encrypted-at-rest secrets.
- **Fail closed.** A non-dev deploy refuses to boot on an insecure or in-memory configuration
  (see the startup guard below).

## Repository layout

```
platform/
├── qiko-core/                # FastAPI backend
│   ├── app/
│   │   ├── core/             # config, db, logging, tenancy, middleware, ratelimit,
│   │   │                     # observability, crypto, deps (auth/RBAC), dev_gateways
│   │   ├── db/               # SQLAlchemy models, async stores, migration helpers
│   │   ├── modules/          # one folder per domain (service + router + tests)
│   │   ├── tasks/            # arq task tier (jobs.py, queue.py, worker.py)
│   │   └── main.py           # app factory: middleware + routers + service singletons
│   ├── alembic/              # migrations
│   └── tests/                # pytest (functional), 80% coverage gate
├── frontend/                 # Next.js monorepo (pnpm + turbo)
│   ├── apps/creator          # Creator/Studio SPA
│   ├── apps/admin            # Admin console
│   └── packages/{ui,api-client}
├── docker-compose.yml        # base services (qiko-core, worker, creator, admin, db, redis)
├── docker-compose.dev.yml    # dev overlay (ports, in-memory stores, eager tasks)
├── docker-compose.preprod.yml
├── docker-compose.live.yml
├── loadtest/                 # k6 load test + SLO/OWASP checklist
└── docs/
    ├── creating-a-worker.md  # how to create a worker and how to build a new vertical
    └── playbooks/            # per-environment runbooks (dev / preprod / live)
```

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

## Quick start (dev)

```bash
cd platform
cp .env.example .env                       # dev defaults; never commit .env
COMPOSE_PROJECT_NAME=qiko-dev \
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# apply migrations
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head

# verify
curl -s localhost:8000/health            # {"status":"ok","environment":"dev",...}
```

The dev overlay sets `USE_DB_STORES=false` and `TASK_BACKEND=eager`, so tasks run inline and no
separate worker container is needed for local iteration.

Frontend:

```bash
cd platform/frontend
pnpm install
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter creator dev   # http://localhost:3000
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1 pnpm --filter admin  dev   # http://localhost:3001
```

## Testing and quality

```bash
cd platform/qiko-core
python -m pytest            # functional tests, fails under 80% coverage
ruff check .                # lint

cd platform/frontend
pnpm -r lint                                                # eslint across the workspace
pnpm --filter creator build && pnpm --filter admin build   # typecheck + Next production build
```

CI (`.github/workflows/ci.yml`) runs change-detection, then ruff plus pytest (coverage gate) on the
backend and `pnpm -r lint` plus `pnpm -r build` on the frontend.

## Configuration and secrets

Settings are env-driven and read in one place (`app/core/config.py`). Locally they come from `.env`;
in the cloud they come from AWS SSM per environment. Key flags:

| Env var | Purpose | Default |
|---|---|---|
| `ENVIRONMENT` | `dev` \| `preprod` \| `live`. Only `dev` exposes `/docs` and debug errors. | `dev` |
| `SESSION_SECRET` | Signs session/access tokens. Required in non-dev; a non-dev deploy refuses to boot on the insecure local default. | `change-me-locally` (dev only) |
| `ENCRYPTION_KEY` | Dedicated key for secrets at rest (channel tokens, Vapi/Salesforce secrets). Kept separate from `SESSION_SECRET` so the two rotate independently. If unset, the key is derived from `SESSION_SECRET` (legacy fallback, still decryptable after you set a dedicated key). | derived from `SESSION_SECRET` |
| `USE_DB_STORES` | `true` uses the Postgres-backed stores (data survives a restart); `false` uses in-memory dev stores. Must be `true` in non-dev. | `false` (dev) |
| `TASK_BACKEND` | `arq` runs jobs on the worker tier; `eager` runs them inline in-process. Must be `arq` in non-dev. | `eager` (dev) |

**Startup guard (fail closed).** On boot, a non-dev environment refuses to start unless
`SESSION_SECRET` is set to a real value AND `USE_DB_STORES=true` AND `TASK_BACKEND=arq`. This stops
a misconfigured production deploy from silently dropping all data on restart or running a 30-minute
generation inline. See `Settings.assert_secrets_set` in `app/core/config.py`, called from the app
lifespan in `app/main.py`. dev is unaffected.

## API surface

All endpoints are under `/api/v1`, authenticated by the `qiko_access` httpOnly cookie and
RBAC-gated (the tenant is derived from the verified token, never a client header). The routers
mounted in `app/main.py` include:

- Identity and auth: `/auth/*` (login, signup, refresh, forgot/reset password), `/users/*`,
  `/auth/2fa/*` (TOTP), onboarding, plus the platform-admin org endpoints.
- Workers: `/agents/*` (create/list/config/ready, plus Vapi/Calendly/Salesforce connections) and
  the batch answering endpoints under `/agents/*`.
- Knowledge: `/knowledge/*` (ingest, ingest-file, search, documents, evaluate) and knowledge
  `/sources/*`.
- Chat and embed: `/chat/*` plus the public embeddable chat router.
- RFP / tenders: `/rfp/packs/*` (upload, background generation, status, requirements, brief,
  compliance, assignments, exports) and `/assignments/*`.
- Sales intelligence: `/sales-intelligence/*` (opportunities, sources/connectors, Salesforce),
  and `/notifications/*`.
- Finance: `/finance/*`. CRM: `/crm/*`. Teams: `/teams/*`. Leads: `/leads`. Signal: `/signal/*`.
- Billing: `/billing/*` (plans, subscriptions). Channels: `/channels/*`. Voice: `/voice/*`.
  Excel: `/excel/*`. Admin console: `/admin/*`.
- Public, signature-verified webhooks: `/billing/webhook/stripe`, `/channels/whatsapp/webhook`.

Interactive docs are served at `/docs` in dev only. The full, always-current contract is the
generated OpenAPI schema at `/api/v1/openapi.json`.

**Intentionally locked for the current client release:** Pricing/Billing and CRM are built but not
exposed in the Creator navigation for now (the CRM tab on a worker is present but disabled, and the
billing pages are nav-locked). The backend endpoints exist and are tested; the surfaces are simply
gated in the UI until the client release enables them.

## Deploy and ops

Deploys are Docker Compose per environment, behind Caddy, with secrets from AWS SSM. The automated
pipeline is currently wired for **preprod**:

1. A push to `main` runs `.github/workflows/deploy-preprod.yml`.
2. CI builds a clean `git archive` tarball (tracked files only, no `.git`/`node_modules`) and
   uploads it to S3, keeping the prior artifact as `deploy-previous.tar.gz` for rollback.
3. CI triggers the on-box script `.github/deploy/redeploy-preprod.sh` via **AWS SSM Run Command**
   (the SSM-managed boxes do not git-pull; port 22 is closed).
4. The script downloads and atomically swaps the code, preserves the live `.env`, runs
   `docker compose build`, `up -d --force-recreate`, then `alembic upgrade head` (with retries).
5. It then **auto-reclaims disk**: it prunes unused images and the build cache so a cluttered disk
   can no longer hit ENOSPC. It never touches named volumes, so Postgres data is safe.
6. CI health-checks `https://preprod.qiko.ai/api/v1/health` and, on failure, restores
   `deploy-previous.tar.gz` and redeploys.

Migrations run with `alembic upgrade head` inside the `qiko-core` container. Rollback is a redeploy
of the previous artifact; data is safe because it lives in named volumes. Secrets are loaded from
AWS SSM per environment, never baked into images or committed. See the playbooks for the exact
per-environment procedures.

## Creating a worker

See [`docs/creating-a-worker.md`](docs/creating-a-worker.md) for both the product flow (a tenant
user creating and training a worker in the Creator app) and the developer guide (building a brand
new custom worker vertical end to end).
