# Qiko V2 Platform

AI-first, agentic, dockerised platform. Two deployables, two languages.

| Deployable | Stack | Role |
|---|---|---|
| `qiko-core/` | Python 3.11 · FastAPI · SQLAlchemy 2 (async) · Postgres/pgvector · Redis · arq | Modular monolith: identity/auth, agents (workers), agentcore, AI gateway, knowledge/RAG, chat/embed, RFP/tenders, sales intelligence, finance, CRM, teams, billing, channels, voice, admin, leads, signal, notifications |
| `frontend/` | Next.js 15 (App Router) · React 19 · Tailwind · TanStack Query · pnpm/Turborepo | `apps/creator` (Creator/Studio) · `apps/admin` (Admin console) · shared `packages/ui` + `packages/api-client` |

The container stack runs behind Caddy. Local host mode keeps the backend services in Docker and
runs the two Next.js apps on the host for hot reload.

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
- **Fail closed.** A non-dev deploy refuses to boot on insecure or non-persistent configuration
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
├── docker-compose.dev.yml    # local persistence, arq worker, loopback ports, and Caddy
├── docker-compose.dev.parity.yml # containerized Creator/Admin parity overlay
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
| **dev** | Host frontend development or full container parity | `docker-compose.yml` + `docker-compose.dev.yml` (+ `docker-compose.dev.parity.yml` for parity) |
| **preprod** | Client-facing staging for validation | `docker-compose.yml` + `docker-compose.preprod.yml` |
| **live** | Production | `docker-compose.yml` + `docker-compose.live.yml` |

Each environment has its own database, secrets and region profile. See the playbook for each:
- [`docs/playbooks/dev.md`](docs/playbooks/dev.md)
- [`docs/playbooks/preprod.md`](docs/playbooks/preprod.md)
- [`docs/playbooks/live.md`](docs/playbooks/live.md)

## Quick start (dev)

The complete setup, host frontend, parity, authentication, testing, reset, and troubleshooting
instructions are in the [canonical local development guide](docs/playbooks/dev.md).

```bash
./scripts/dev.sh setup
./scripts/dev.sh up
# In a second terminal:
./scripts/dev.sh frontend
```

Open Creator at `http://qiko.localhost:8080` and Admin at
`http://admin.qiko.localhost:8080`. Local development uses Postgres, Redis, and the arq worker. Run
`./scripts/dev.sh parity` to build and check the full container stack.

## Testing and quality

Use the exact local commands in the
[local development testing section](docs/playbooks/dev.md#tests-and-quality-checks). CI
(`.github/workflows/ci.yml`) runs change detection, backend lint and pytest with the coverage
gate, OpenAPI drift checks, frontend lint and tests, API client generation, and frontend builds.

## Configuration and secrets

Settings are env-driven and read in one place (`app/core/config.py`). Locally they come from `.env`;
in the cloud they come from AWS SSM per environment. Key flags:

| Env var | Purpose | Default |
|---|---|---|
| `ENVIRONMENT` | `dev` \| `preprod` \| `live`. Only `dev` exposes `/docs`. | `dev` |
| `SESSION_SECRET` | Signs session/access tokens. Required in non-dev; a non-dev deploy refuses to boot on the insecure local default. | `change-me-locally` (dev only) |
| `ENCRYPTION_KEY` | Dedicated key for secrets at rest (channel tokens, Vapi/Salesforce secrets). It must be strong and distinct from `SESSION_SECRET` in non-dev. Deriving it from `SESSION_SECRET` is a legacy/dev-only compatibility fallback and is rejected in non-dev. | derived from `SESSION_SECRET` in legacy/dev only |
| `USE_DB_STORES` | `true` uses the Postgres-backed stores so local data survives restarts. The supported local workflow requires `true`. | `true` in `.env.example` |
| `TASK_BACKEND` | `arq` runs jobs on the worker tier. The supported local workflow requires `arq` and starts the worker. | `arq` in `.env.example` |

**Startup guard (fail closed).** Before serving traffic, every non-dev environment validates strong
and distinct session and encryption secrets, the complete consent pseudonym keyring, persistent
Postgres stores, the arq worker backend, explicit trusted proxy networks, and deliverable SMTP
configuration with a non-placeholder sender. `Settings.assert_secrets_set` in
`qiko-core/app/core/config.py` is the authoritative requirement list and is called from the app
lifespan. Dev is exempt from this non-dev guard.

## API surface

Protected application endpoints are under `/api/v1`, authenticated by the `qiko_access` httpOnly
cookie, and RBAC-gated (the tenant is derived from the verified token, never a client header).
Public exceptions include health, pre-auth identity and onboarding flows, explicitly enabled public
chat/embed routes, and signature-verified webhooks. The routers mounted in `app/main.py` include:

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
generated OpenAPI schema at `/openapi.json`.

**Intentionally locked for the current client release:** Pricing/Billing and CRM are built but not
exposed in the Creator navigation for now (the CRM tab on a worker is present but disabled, and the
billing pages are nav-locked). The backend endpoints exist and are tested; the surfaces are simply
gated in the UI until the client release enables them.

## Deploy and ops

Deployments use Docker Compose behind Caddy, with environment configuration injected separately
from application artifacts. The automated preprod pipeline follows this release history:

1. A merge into `preprod` (promoted from `main`) runs `.github/workflows/deploy-preprod.yml` for
   that exact commit SHA. Pushing to `main` deploys nothing.
2. CI creates a tracked-files-only `git archive`, computes its SHA-256 checksum, and publishes both
   under immutable, commit-SHA-addressed artifact names.
3. The deployment receives the release SHA and checksum, fetches that exact artifact, verifies its
   checksum, and atomically activates the extracted release while preserving environment config.
4. It validates Compose, builds the images, and runs the non-dev configuration and email preflight
   before changing the running application tier.
5. It requires Postgres and Redis to be healthy, then runs `alembic upgrade head` from the newly
   built qiko-core image before replacing the stateless API, worker, and frontend services.
6. CI health-checks the release and records the verified preprod SHA only after success.

A failed deployment does not trigger an automatic rollback. Rollback requires an explicit review of
the selected immutable SHA-addressed artifact, the terminal deployment result, current schema, and
migration compatibility. The reviewer must decide whether a forward fix, a reviewed downgrade, or
a data recovery step is required before executing a rollback and re-verifying health. Named volumes
preserve database files across container recreation, but they do not make application or schema
rollback automatically safe. See the environment playbooks for reviewed release procedures.

## Creating a worker

See [`docs/creating-a-worker.md`](docs/creating-a-worker.md) for both the product flow (a tenant
user creating and training a worker in the Creator app) and the developer guide (building a brand
new custom worker vertical end to end).
