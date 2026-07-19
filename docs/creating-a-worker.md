# Creating a worker

This guide has two parts.

- **Part A** is the product flow: how a tenant user creates, trains and uses a worker in the
  Creator app, with the equivalent API calls.
- **Part B** is the developer guide: how to build a brand new custom worker type (a vertical) end
  to end, using the existing `pre_sales_writer` and `sales_intelligence` verticals as the worked
  reference.

Throughout, "worker" and "agent" are the same thing. In the product a worker is an `Agent` row; in
the code it is a `WorkerConfig` over the shared AgentCore engine plus the tenant knowledge base. A
worker is configuration, not a fork of the codebase.

Some quick vocabulary you will see below:

- **`atype`** (agent type): the worker's vertical. The server allowlist is
  `{"worker", "pre_sales_writer", "sales_intelligence", "finance"}` (see
  `app/modules/agents/router.py:AGENT_TYPES`). `worker` is the generic chat/research worker; the
  others unlock a bespoke Studio cockpit.
- **`config`**: a free-form JSON dict on the worker, merge-patched via
  `PUT /agents/{id}/config`. It holds the system prompt, tone, guardrails/rules, gate threshold,
  retrieval depth, and per-vertical settings (for example `opportunity_criteria`,
  `si_service_keywords`, Vapi/Calendly/Salesforce settings, `archived`).
- **AgentCore**: the shared generate, then critic (grounding), then accept/escalate gate engine
  (`app/modules/agentcore/`). The knowledge base grounds the answers.

---

## Part A: creating a worker (product flow)

All requests are under `/api/v1`, authenticated by the `qiko_access` httpOnly cookie (set at
login), and CSRF-protected. Log in first. The tenant is taken from the verified token, never from a
request field. The examples below use the API paths that the Creator app calls through its
`apps/creator/lib/api.ts` wrapper.

### A1. Create the worker

In the Creator app: open **Workers**, type a name into "New worker name..." and click
**Create Worker**. This calls `createAgent(name)` and creates a generic worker (`atype: "worker"`).

Under the hood:

```
POST /api/v1/agents
Content-Type: application/json

{ "name": "Bid Writer", "atype": "worker" }
```

To create a vertical worker instead, set `atype` to one of the allowed values:

```
POST /api/v1/agents
{ "name": "Pre-Sales Writer", "atype": "pre_sales_writer" }
```

Notes:

- The response is the created `Agent` (`id`, `tenant`, `name`, `atype`, `status: "training"`,
  `config: {}`, `created_at`).
- Creation is gated by the tenant subscription's worker limit. The plan is looked up server side
  from the real subscription, never trusted from the client. Over the limit returns `403`.
- An invalid `atype` returns `422`.
- The new worker starts in `status: "training"`.

### A2. Pick the vertical

The vertical is the `atype` chosen at creation (step A1). It decides which Studio cockpit the worker
opens in later (see A6). The generic `worker` type gives grounded Chat plus batch Research plus
Knowledge; the vertical types add a dedicated cockpit on top of the same engine.

### A3. Train it (Background, Tone, Behavior)

On the worker detail page (**Workers > your worker**), the **Train** tab has four steps:
**Background**, **Tone**, **Behavior**, **Knowledge**. The first three write into the worker's
`config` via a merge patch. Each save calls `updateAgentConfig(id, patch)`:

```
PUT /api/v1/agents/{id}/config
Content-Type: application/json

{
  "patch": {
    "system_prompt": "You are a UK public-sector bid writer. Answer only from the knowledge base.",
    "tone": "professional, concise, British English",
    "rules": ["Never invent figures", "Cite the source document for every claim"],
    "guardrails": ["Decline anything outside tendering"]
  }
}
```

Important details:

- The body is wrapped in `patch`. The patch is **merged** into the existing config, so you only
  send the keys you are changing; other keys are preserved.
- `system_prompt`, `gate_threshold` and `retrieval_k` are read when the worker is assembled (see
  `app/core/deps.py:assemble_worker`), so they change how the worker actually answers. Other keys
  (tone, rules, guardrails) are stored and used by the relevant vertical or surfaced in the UI.
- Secret connection values (Vapi, Salesforce) are written through their own dedicated endpoints and
  are never returned in plaintext by the generic config endpoints. For example
  `POST /agents/{id}/vapi-credentials` encrypts the key at rest and returns only a masked preview.

### A4. Add knowledge (the shared KB)

The **Knowledge** step of the Train tab uploads documents into the tenant knowledge base. This is
the pgvector-backed RAG store that grounds every answer. There are two ways in:

Upload a file (PDF, DOCX, XLSX, TXT), multipart form:

```
POST /api/v1/knowledge/ingest-file
Content-Type: multipart/form-data

doc_id=policies-2024
file=@company-policies.pdf
```

Or ingest raw text:

```
POST /api/v1/knowledge/ingest
Content-Type: application/json

{ "doc_id": "about-us", "text": "We are a security services provider ..." }
```

Both chunk plus embed plus store the document and return the number of chunks. Uploads are capped at
10 MB; raw text ingest is capped at 2 MB. The knowledge base is tenant-scoped and shared by every
worker in the tenant, so a document ingested once grounds all of the tenant's workers.

### A5. Move from Training to Ready

When training is complete, mark the worker ready:

```
POST /api/v1/agents/{id}/ready
```

This flips `status` from `training` to `ready`. The Creator UI shows a "Ready" badge instead of
"Training".

### A6. Use it in the Studio cockpit

Open **Studio** and select the worker. The Studio route `/studio/[id]` reads the worker's `atype`
and routes to the right cockpit (see `apps/creator/app/studio/[id]/page.tsx:VERTICAL_ROUTES`):

- `worker`: the generic cockpit (Overview, grounded **Chat**, batch **Research**, Knowledge).
- `pre_sales_writer`: the pre-sales cockpit at `/studio/[id]/pre-sales` (tender packs, drafting,
  review, export).
- `sales_intelligence`: the sales-intelligence cockpit at `/studio/[id]/sales-intelligence`
  (opportunity pipeline, TED/UNGM ingestion, Salesforce push, notifications).
- `finance`: the finance cockpit at `/studio/[id]/finance` (workbook upload, analytics, analyst
  chat).

Grounded question answering (used by the generic cockpit's Chat and Research) goes through the
batch endpoints, each answer grounded, confidence-scored and gated:

```
POST /api/v1/agents/batch-answer
{ "agent_id": "<id>", "questions": ["What is our incident response SLA?"] }
```

When a reviewer approves or edits an answer, record it so it becomes verified ground truth for that
topic (the flywheel):

```
POST /api/v1/agents/feedback
{ "agent_id": "<id>", "requirement_id": "q1", "approved_text": "Our SLA is ...", "topic": "sla" }
```

### A7. Archive (soft hide)

There is no hard delete. To hide a worker, set `archived` in its config; the row and its data stay,
so setting it back restores the worker exactly as it was:

```
PUT /api/v1/agents/{id}/config
{ "patch": { "archived": true } }
```

`GET /agents` hides archived workers.

---

## Part B: building a new custom worker type (developer guide)

This is the end to end path to add a brand new vertical. Use the existing verticals as references:
`app/modules/rfp/` (backing the `pre_sales_writer` cockpit) and `app/modules/sales_intelligence/`.
The steps below are ordered; do them in order.

### B0. How a worker is assembled (understand this first)

A worker is assembled in `app/core/deps.py:assemble_worker`:

1. It builds a `WorkerConfig` (`app/modules/workers/config.py`) from the worker's `Agent.config`:
   `system_prompt`, `gate_threshold` and `retrieval_k` are read from config if present.
2. It constructs an `AgentCore` (`app/modules/agentcore/runtime.py`) with a `Generator` (the
   grounded writer), the gate threshold, and the verified-answers store (the flywheel). AgentCore
   runs generate, then an independent grounding critic, then the accept/escalate gate.
3. The `Generator` talks to the AI gateway (`app/modules/ai/gateway.py`), which returns the
   configured provider (Bedrock/Claude by default) wrapped in a fallback provider, with a
   deterministic `StubProvider` for dev/tests.
4. The `Worker` also holds the shared knowledge service, so retrieval grounds every answer.

The rule to keep answers grounded and gated: your vertical must produce answers **through this
engine** (call `assemble_worker` / `build_tenant_worker` and use `worker.answer(...)`), not by
calling `get_provider().generate(...)` directly for anything that should be grounded. Direct gateway
calls are only appropriate for whole-document, non-grounded tasks (for example the RFP tender-brief
and compliance extraction, which read the uploaded document itself, not the KB).

Fail-closed detail worth copying: when a generated answer comes from the `StubProvider` fallback
(a real provider outage), the RFP pipeline raises `StubProviderUnavailable` and never persists the
stub as if it were a real draft (see `app/modules/rfp/generation.py`). Do the same in your vertical.

### B1. Define the `atype`

1. Add your vertical to the server allowlist in `app/modules/agents/router.py`:

   ```python
   AGENT_TYPES = {"worker", "pre_sales_writer", "sales_intelligence", "finance", "my_vertical"}
   ```

   This is the single source of truth. Without it, `POST /agents` rejects the new type with `422`.
2. If the frontend `createAgent` helper enumerates the types, add it there too
   (`apps/creator/lib/api.ts`), and add a humanised label in `apps/creator/lib/stringUtils.ts`
   (`workerTypeLabel`) and an icon/tint in the workers list and Studio.

### B2. Add the backend module

Create `app/modules/my_vertical/` following the shape of `app/modules/finance/` (a compact
reference) or `app/modules/rfp/` (a larger one). Typical files:

```
app/modules/my_vertical/
├── __init__.py
├── models.py      # dataclasses / typed shapes for the domain
├── service.py     # the domain logic; a Protocol store + InMemory<X>Store default
├── router.py      # the tenant-scoped HTTP API (APIRouter with a prefix + tags)
└── (parser.py / analytics.py / etc. as needed)
```

Guidelines that match the existing modules:

- **Router.** `router = APIRouter(prefix="/my-vertical", tags=["my-vertical"])`. Every endpoint
  depends on `authed_tenant` for the tenant, and mutating endpoints add
  `require_role(Role.editor)`. Never read the tenant from the body or a header.
- **Service.** Define a `Protocol` store plus an `InMemory...Store` default (like
  `AgentService`/`InMemoryAgentStore` in `app/modules/agents/service.py`) so the module works with
  no database in dev/tests. Keep the service request-free (no FastAPI objects) so a background job
  can reuse it (see B5).
- **Grounded answers.** Where the vertical answers questions, assemble the worker and use it:

  ```python
  from app.core.deps import build_tenant_worker

  worker = await build_tenant_worker(request, tenant, agent_id=body.agent_id)
  result = await worker.answer(req_id, question)   # grounded + critic + gate
  ```

Then mount the router in `app/main.py`:

1. Import it near the other router imports:
   `from app.modules.my_vertical.router import router as my_vertical_router`.
2. Add it to the `for r in (...)` include loop that mounts everything under `/api/v1`.
3. If the service needs a singleton, create it in `create_app()` on `app.state` (in-memory
   default), and add the DB-backed version in the `lifespan` `use_db_stores` block.
4. Add a `get_my_vertical(request)` accessor in `app/core/deps.py` (the one-liner
   `return request.app.state.my_vertical`) and use it via `Depends` in the router.

Wire the stores and dependencies:

- If the vertical needs persistence, add a `Sql...Store` in `app/db/stores.py` implementing the
  same Protocol as the in-memory store, and construct it in the `lifespan` block in `app/main.py`
  exactly like the RFP/SI stores are constructed there.
- If it needs new tables, add SQLAlchemy models under `app/db/`, then generate and apply a
  migration:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core \
    alembic revision --autogenerate -m "add my_vertical tables"
  docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T qiko-core alembic upgrade head
  ```

### B3. Drive behaviour from `Agent.config`, not hardcoding

Per-worker behaviour must come from the worker's `config` dict, not constants. Follow the
sales-intelligence pattern (`app/modules/sales_intelligence/qualification.py`), which reads keys
such as `si_service_keywords`, `si_target_countries` and `si_technology_keywords` from
`Agent.config`, each with a sensible default when the key is missing:

1. Choose config keys for your vertical (for example `mv_threshold`, `mv_categories`).
2. Read them from the worker's config with defaults, so a worker that configures nothing still
   behaves sensibly:

   ```python
   agent = await agents.get(tenant, agent_id)
   cfg = agent.config if agent else {}
   categories = cfg.get("mv_categories") or DEFAULT_CATEGORIES
   threshold = float(cfg.get("mv_threshold", 0.6))
   ```

3. Users set these through the existing generic endpoint, no new endpoint needed:
   `PUT /agents/{id}/config` with `{ "patch": { "mv_categories": [...] } }`.
4. If a value is a secret (an API key or token), do not store it in plain config. Write it through
   a dedicated endpoint that encrypts it (see the Vapi/Salesforce handlers in
   `app/modules/agents/router.py`, which call `app.core.crypto.encrypt` and return only a masked
   preview), and add the key name to `_REDACTED_CONFIG_KEYS` so the generic config views never leak
   it.

### B4. Add the frontend cockpit and route to it

1. Add the Studio cockpit page at
   `frontend/apps/creator/app/studio/[id]/my-vertical/page.tsx`, following an existing cockpit
   (`.../pre-sales/page.tsx` or `.../finance/page.tsx`) for structure, `@qiko/ui` components and
   TanStack Query usage.
2. Register the route in `frontend/apps/creator/app/studio/[id]/page.tsx` by adding an entry to
   `VERTICAL_ROUTES`:

   ```ts
   const VERTICAL_ROUTES: Record<string, string> = {
     pre_sales_writer: "pre-sales",
     sales_intelligence: "sales-intelligence",
     finance: "finance",
     my_vertical: "my-vertical",
   };
   ```

   The generic Studio page redirects to `/studio/{id}/my-vertical` when the worker's `atype`
   matches.
3. Add the client calls in the app's API layer (`frontend/apps/creator/lib/api.ts`), following the
   existing exported helpers (for example the `listSalesOpportunities` / `getSalesOpportunity`
   functions). Use the shared `request(...)` wrapper so the auth cookie is sent
   (`credentials: "include"`).
4. If and when the generated `packages/api-client` is adopted app-wide, regenerate its types after
   your OpenAPI schema changes (`pnpm --filter @qiko/api-client generate`). Today both apps use
   their own `lib/api.ts`, so adding your calls there is what is required.

### B5. Background work (only if you need long-running generation)

If the vertical does heavy generation (like the RFP pipeline, which can take tens of minutes), never
block the request. Register an arq job and return immediately with a pollable status, exactly like
`generate_tender_artifacts`:

1. Register the job in `app/tasks/jobs.py`:

   ```python
   @registry.register("run_my_vertical")
   async def run_my_vertical(*, tenant: str, entity_id: str, sessionmaker=None, **deps) -> dict:
       # Build DB-backed services from `sessionmaker` on the arq worker tier (no Request there),
       # or use injected in-memory services on the eager dev path. Mirror _build_rfp_deps.
       ...
   ```

2. In the endpoint that starts the work, write an initial "pending" status, enqueue the job, and
   return `202 Accepted`. Mirror `app/modules/rfp/router.py:_start_generation`: on the eager
   backend (dev/tests) the job runs inline against the same in-memory stores; on the arq backend
   (prod) only serialisable ids go on the wire and the worker rebuilds its own stores from the DB.
3. Expose a `GET /my-vertical/{id}/status` endpoint that returns the stored status dict. Design the
   status like the RFP `gen_status` (see the contract at the top of
   `app/modules/rfp/generation.py`): per-stage state plus counters, updated after each stage so a
   poller sees progress. Make each stage independent (one failing does not sink the others) and
   make long loops resumable/idempotent so an arq retry after a restart resumes rather than
   restarting.
4. Run the heavy generation off the event loop where it does blocking work (use
   `asyncio.to_thread(...)` around provider calls, as AgentCore and the RFP module do).

The arq worker tier is the `worker` container in `docker-compose.yml`
(`command: ["arq", "app.tasks.worker.WorkerSettings"]`). It runs from the same image, so any job
you register is available to it. In dev, `TASK_BACKEND=eager` runs jobs inline, so you do not need
the worker container locally.

### B6. Testing and the quality gates

1. Backend tests: add `app/modules/my_vertical/` tests under `qiko-core/tests/` (functional, using
   the in-memory stores). Run:

   ```bash
   cd qiko-core && python -m pytest && ruff check .
   ```

   `pytest` enforces `--cov-fail-under=80` (from `pyproject.toml`), so cover your service and
   router. `ruff check` must pass.
2. Frontend: typecheck and build both apps, plus lint:

   ```bash
   cd frontend && pnpm -r lint && pnpm --filter creator build && pnpm --filter admin build
   ```

3. CI (`.github/workflows/ci.yml`) runs the same gates: ruff plus pytest (coverage) when
   `qiko-core/**` changes, and `pnpm -r lint` plus `pnpm -r build` when `frontend/**` changes.

### B7. Deploy

Nothing special. Once merged to `main`, the new vertical ships with the normal pipeline: CI packages
the code, uploads it to S3, and triggers the on-box redeploy via SSM, which rebuilds, runs
`alembic upgrade head` (so your migration is applied) and recreates the containers. See
`docs/playbooks/preprod.md`. Make sure any new integration secrets are added to the environment's
`.env` (bootstrapped from AWS SSM) before the code that reads them goes live.

---

## Checklist for a new vertical

Backend:

- [ ] Add the `atype` to `AGENT_TYPES` in `app/modules/agents/router.py`.
- [ ] Create `app/modules/my_vertical/` with `service.py` (Protocol store + in-memory default) and
      `router.py` (tenant-scoped, `require_role` on mutations).
- [ ] Answer questions through `build_tenant_worker(...).answer(...)` so answers stay grounded and
      gated; fail closed on a stub provider for anything you persist.
- [ ] Read per-worker behaviour from `Agent.config` with sensible defaults; encrypt any secrets and
      add their keys to `_REDACTED_CONFIG_KEYS`.
- [ ] Mount the router in `app/main.py`, add the `app.state` singleton (in-memory + Sql in the
      `use_db_stores` lifespan block) and a `get_my_vertical` accessor in `app/core/deps.py`.
- [ ] Add a `Sql...Store` in `app/db/stores.py` and any models plus an Alembic migration if new
      tables are needed.

Background (only if long-running):

- [ ] Register an arq job in `app/tasks/jobs.py`, return `202` with an initial status, and expose a
      pollable `GET .../status`. Keep stages independent and the work resumable/idempotent.

Frontend:

- [ ] Add the cockpit page under `app/studio/[id]/my-vertical/page.tsx`.
- [ ] Add the `atype` to `VERTICAL_ROUTES` in `app/studio/[id]/page.tsx`.
- [ ] Add the API helpers in `apps/creator/lib/api.ts` and a label in `lib/stringUtils.ts`.

Quality and ship:

- [ ] `pytest` (>= 80% coverage) and `ruff check` pass.
- [ ] `pnpm -r lint` and `pnpm -r build` pass.
- [ ] Merge to `main`; the S3 + SSM pipeline builds, migrates and redeploys automatically.
