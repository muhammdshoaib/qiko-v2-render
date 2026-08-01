# Local development

This is the single canonical guide for running Qiko locally. Local development uses persistent
Postgres stores, Redis, and the separate arq worker for every supported workflow.

## Prerequisites

Run commands from the repository root unless a section says otherwise.

| Tool | Supported version |
|---|---|
| Git | A current version that can clone this repository |
| Bash | Required by `./scripts/dev.sh` |
| Docker | Docker Engine with Docker Compose 2 or newer. On macOS, use Docker Desktop. |
| Docker Compose | Version 2 or newer, including current Compose 5 releases |
| Python | `setup` requires a `python3` executable. The backend and CI toolchain use Python 3.11. |
| Node.js | Major version 20 or newer. Docker and CI use Node.js 20. |
| pnpm | Exactly `9.12.0` |
| uv | Exactly `0.11.23`, only for backend tests and OpenAPI synchronization on the host |

If pnpm is not already at the supported version, a Node.js installation with Corepack can activate
it before setup:

```bash
corepack enable
corepack prepare pnpm@9.12.0 --activate
pnpm --version
```

Start Docker Desktop before running a lifecycle command. `dev.sh` normally finds `docker` on
`PATH`. On macOS it also falls back automatically to Docker Desktop's bundled CLI. Export the
resolved CLI once so both `dev.sh` and the direct migration commands later in this guide use the
same executable:

```bash
# When docker is on PATH:
export DOCKER_BIN="$(command -v docker)"

# Or, on macOS when Docker Desktop's CLI is not on PATH:
export DOCKER_BIN=/Applications/Docker.app/Contents/Resources/bin/docker
```

Then run `./scripts/dev.sh setup`. The selected CLI must provide Docker Compose 2 or newer and must
be able to contact a running Docker daemon.

## Local architecture and permitted differences

Both supported modes use the `qiko-dev` Compose project, Caddy, qiko-core, the arq worker,
Postgres with pgvector, and Redis.

- **Host frontend mode** uses Caddy plus the Creator and Admin Next.js development servers on the
  host. It is the normal edit loop and provides Next.js hot reload. `./scripts/dev.sh up` starts
  `qiko-core`, `worker`, `db`, `redis`, and `caddy`; `./scripts/dev.sh frontend` starts both host
  Next.js servers.
- **Parity mode** uses the same Dockerfiles and stack as the container deployment shape. It builds
  and starts `qiko-core`, `worker`, `creator`, `admin`, `db`, `redis`, and `caddy`, then migrates and
  checks the HTTP contract.

The permitted difference is where Next.js runs: host development servers in host mode, built
frontend containers in parity mode. Browser origins, Caddy routing, Postgres persistence, Redis,
arq behavior, migrations, and API paths remain the same. Local-only configuration uses the stub AI
provider, console email, HTTP on loopback, and local placeholder values. Do not add external
credentials to make the basic local stack work.

## Hostnames and ports

| URL or port | Purpose |
|---|---|
| `http://qiko.localhost:8080` | Canonical Creator origin through Caddy |
| `http://admin.qiko.localhost:8080` | Canonical Admin origin through Caddy |
| `http://qiko.localhost:8080/api/v1` | Browser API base through Caddy |
| `http://qiko.localhost:8080/health` | Health endpoint through Caddy |
| `http://qiko.localhost:8080/docs` | FastAPI interactive docs in local development |
| `http://qiko.localhost:8080/openapi.json` | Runtime OpenAPI document |
| `127.0.0.1:8000` | Direct qiko-core diagnostic port |
| `3000` | Host Creator Next.js server, proxied by Caddy in host mode |
| `3001` | Host Admin Next.js server, proxied by Caddy in host mode |

The defaults come from `QIKO_DEV_HTTP_PORT=8080`, `QIKO_DEV_API_PORT=8000`,
`QIKO_DEV_CREATOR_PORT=3000`, and `QIKO_DEV_ADMIN_PORT=3001` in `.env.example`. Every configured
port must be numeric and between 1 and 65535. Postgres port 5432 and Redis port 6379 are internal to
the Compose network and are not published to the host. Parity frontend containers also have no
direct host port.

Use the canonical `qiko.localhost` origins for browser work. Authentication cookies are scoped for
those origins, so direct `localhost:8000` requests are for diagnostics rather than browser login
flows.

The host Next.js processes intentionally bind to `0.0.0.0` on ports 3000 and 3001 so Caddy in
Docker can reach them. Run host frontend mode only on a trusted workstation and trusted network.
Keep the host firewall enabled and block inbound access to ports 3000 and 3001 from other devices;
the supported browser entry point remains Caddy on its loopback-only port.

## Clone and first setup

```bash
git clone <repository-url> platform
cd platform
./scripts/dev.sh setup
```

`setup` does all of the following:

1. Creates `.env` from `.env.example` only when `.env` does not already exist. The new file is
   created with owner-only permissions.
2. Leaves an existing `.env` untouched.
3. Validates Docker Compose 2 or newer, Python 3, Node.js 20 or newer, and pnpm 9.12.0.
4. Installs the frontend workspace dependencies with
   `pnpm --dir frontend install --frozen-lockfile`.

Review `.env` locally in your editor before startup. Do not print it into shared terminal output,
paste it into tickets or chat, or commit it. Confirm that it contains local-only values and that
`ENVIRONMENT=dev`, `USE_DB_STORES=true`, `TASK_BACKEND=arq`, `AI_PROVIDER=stub`,
`EMAIL_BACKEND=console`, and the four `QIKO_DEV_*_PORT` values are appropriate for your machine.
Do not replace empty integration values with shared credentials.

The backend runtime dependencies are installed into the qiko-core image when `up` or `parity`
builds it. The frontend dependencies were installed by `setup`.

## Normal host development

Use two terminals from the repository root.

Terminal 1 starts the persistent backend stack, waits up to 180 seconds for it, and applies
`alembic upgrade head`:

```bash
./scripts/dev.sh up
```

Terminal 2 starts Creator and Admin on the host with `NEXT_PUBLIC_API_BASE=/api/v1` and the correct
cross-application Creator origin:

```bash
./scripts/dev.sh frontend
```

Open:

- Creator: `http://qiko.localhost:8080`
- Admin: `http://admin.qiko.localhost:8080`

Do not browse directly to ports 3000 or 3001 for authentication work. Caddy provides the intended
same-origin API routing and cookie behavior.

## Container parity mode

Run parity before handoff and whenever Dockerfiles, build arguments, routing, or runtime behavior
might differ from the host edit loop:

```bash
./scripts/dev.sh parity
```

This builds and starts the full container stack, applies migrations, and runs the local HTTP
contract. A successful contract prints one `PASS` line for Creator, Admin, health at both supported
paths, docs, and OpenAPI. The parity stack remains running for inspection.

To return to host frontend mode, stop the project, start the host backend stack again, and start the
host frontends in the second terminal:

```bash
./scripts/dev.sh down
./scripts/dev.sh up
./scripts/dev.sh frontend
```

## Lifecycle commands

Before the first full local check, create the locked backend development environment without
changing the lock file:

```bash
cd qiko-core
uv sync --frozen --extra dev
cd ..
```

Then use the lifecycle commands from the repository root:

```bash
./scripts/dev.sh status
./scripts/dev.sh logs
./scripts/dev.sh logs qiko-core worker
./scripts/dev.sh logs -f qiko-core worker
./scripts/dev.sh check
./scripts/dev.sh down
```

- `status` shows the `qiko-dev` service state.
- `logs` shows the last 200 lines. It accepts only `-f` or `--follow` and these service names:
  `qiko-core`, `worker`, `creator`, `admin`, `db`, `redis`, and `caddy`.
- `check` first validates both Compose configurations, requires the five host-mode services to be
  running, checks Postgres and Redis, requires Alembic to be at a head, and checks the local HTTP
  contract. It then requires `uv`, exact pnpm 9.12.0, and the locked `qiko-core/.venv`; runs the full
  OpenAPI drift check without regenerating artifacts; runs only the focused bootstrap and OpenAPI
  backend tests with coverage disabled; lints the changed backend and root Python files; runs the
  Creator and Admin tests; and runs workspace lint. Full backend pytest with coverage and frontend
  builds remain CI and parity responsibilities rather than being duplicated by this command.
- `down` stops the project and removes orphan containers while preserving Postgres and Redis
  volumes.

## Data, migrations, worker, and queues

Local data is durable across `down` and `up` because `USE_DB_STORES=true` uses Postgres. Async work
uses `TASK_BACKEND=arq`; qiko-core enqueues jobs in Redis and the separate `worker` service executes
them. Postgres and Redis stay on the internal `app-net` network.

`up`, `parity`, and the recreate phase of `reset` automatically run:

```text
alembic upgrade head
```

After changing SQLAlchemy models, rebuild qiko-core, generate the migration in its container, and
copy the generated versions back to the working tree before another build replaces the container.
Export `DOCKER_BIN` once as shown in Prerequisites before using these direct Compose commands.

```bash
./scripts/dev.sh up
"$DOCKER_BIN" compose --env-file .env -p qiko-dev \
  -f docker-compose.yml -f docker-compose.dev.yml \
  exec -T qiko-core alembic revision --autogenerate -m "describe change"
"$DOCKER_BIN" compose --env-file .env -p qiko-dev \
  -f docker-compose.yml -f docker-compose.dev.yml \
  cp qiko-core:/app/alembic/versions/. qiko-core/alembic/versions/
# Review the generated migration before applying it.
./scripts/dev.sh up
```

The copy step is required because local source is not bind-mounted into qiko-core. Review every
autogenerated migration before applying or committing it. Check the current revision with:

```bash
"$DOCKER_BIN" compose --env-file .env -p qiko-dev \
  -f docker-compose.yml -f docker-compose.dev.yml \
  exec -T qiko-core alembic current
```

Use `./scripts/dev.sh logs -f worker` to observe queued work and
`./scripts/dev.sh logs -f qiko-core` for request or enqueue failures.

## Bootstrap a local Admin

Start the backend first, then bootstrap one identity that is both a tenant owner and a platform
Admin:

```bash
./scripts/dev.sh bootstrap-admin \
  --tenant local-org \
  --display-name "Local Admin" \
  --email admin@example.test
```

The three value arguments are required. The tenant identifier must contain 1 to 64 lowercase
letters, digits, or internal hyphens, with no leading or trailing hyphen. The command prompts for the
local Admin password and confirmation in an interactive terminal. Input is silent and never placed
in a command argument. Passwords must contain 8 to 256 characters, cannot be entirely whitespace,
and cannot contain control characters.

The command is idempotent for the same tenant and normalized email. It does not change an existing
password unless `--reset-password` is supplied:

```bash
./scripts/dev.sh bootstrap-admin \
  --tenant local-org \
  --display-name "Local Admin" \
  --email admin@example.test \
  --reset-password
```

Do not use `--password`, `--password=...`, or `--password-stdin`; the wrapper rejects password
arguments and performs the silent prompt itself.

## Admin login and MFA acceptance flow

1. Open `http://admin.qiko.localhost:8080/login` and sign in with the bootstrapped local Admin. Leave
   **Authenticator or backup code** empty before MFA is enabled.
2. Open **Security**, select **Enable 2FA**, and scan the QR code with a TOTP authenticator.
3. Enter the current password and the six-digit authenticator code, then select
   **Verify & complete setup**.
4. Save every displayed one-time backup code in a temporary local password manager entry. The codes
   are not shown again. Do not put them in repository files, screenshots, tickets, or chat.
5. MFA enrollment revokes the existing session. Use **Sign out** if the shell is still visible, then
   return to `/login`.
6. Sign in with email, password, and a current six-digit TOTP in **Authenticator or backup code**.
7. Sign out from the Admin navigation and verify that the session returns to `/login`.
8. Sign in once with one saved backup code in the same field. A backup code is consumed after one
   successful use. Sign out again.
9. To replace the remaining codes, sign in with TOTP, open **Security**, enter the current password
   and current authenticator code, then select **Generate new backup codes**. Generation immediately
   replaces every old backup code and revokes the current session. Save the displayed replacement
   codes, then sign in again.

## Creator signup with console email

The local `EMAIL_BACKEND=console` path does not deliver an external email. In debug development,
the signup response includes the six-digit `verification_code` that represents the console email.

1. Open browser developer tools and select the **Network** panel.
2. Open `http://qiko.localhost:8080/signup`.
3. Create an account using local test data such as `creator@example.test`, satisfy the password
   rules, and accept the displayed policies.
4. Select the successful `POST /api/v1/auth/signup` request in the Network panel. Read the
   `verification_code` from its JSON response. Treat the code as temporary local authentication
   data and do not share or record it.
5. On the redirected `/verify-email` page, enter that code, choose the local password, accept the
   policies, and select **Verify email**.
6. Sign in at `/login`, confirm the Creator shell loads, then sign out.

If the response does not contain `verification_code` after reusing an address, an unexpired pending
signup may already exist in Postgres. Restarting the backend does not clear that durable row. Use a
fresh unique local address, or wait for the documented 10-minute verification expiry and submit the
signup again. If a fresh address also omits the code, confirm the local `.env` settings in your
editor. Do not switch to an external mail service for this acceptance flow.

## Debugging

Start with these commands:

```bash
./scripts/dev.sh status
./scripts/dev.sh logs qiko-core worker db redis caddy
./scripts/dev.sh check
```

Common failures:

- **Docker was not found:** start Docker Desktop. On macOS, `dev.sh` uses the bundled CLI fallback;
  otherwise set `DOCKER_BIN` to an executable Docker CLI.
- **Docker daemon connection failure:** Docker Desktop or Docker Engine is not running even though
  the CLI exists.
- **pnpm version failure:** activate exactly pnpm 9.12.0, then rerun `./scripts/dev.sh setup`.
- **Caddy returns 502 in host mode:** keep `./scripts/dev.sh frontend` running in the second terminal
  and inspect its Next.js output.
- **A configured port is occupied:** stop the conflicting process or update the corresponding
  `QIKO_DEV_*_PORT` once in `.env`, then restart both backend and frontend commands.
- **Creator or Admin login loops:** use the canonical `qiko.localhost` URL, not a direct Next.js or
  API port. Clear only the local `.qiko.localhost` cookies if stale local cookies remain.
- **Postgres or Redis is not ready:** inspect `./scripts/dev.sh logs db redis`, then rerun
  `./scripts/dev.sh up`. Do not delete volumes as a first response.
- **Alembic is not at head:** inspect `./scripts/dev.sh logs qiko-core`, review the migration error,
  and rerun `./scripts/dev.sh up` after correcting it.
- **Queued work does not complete:** confirm `worker` is running with `status`, then follow both
  `worker` and `qiko-core` logs. Local tasks are not expected to run inline.
- **Stub responses appear:** that is the supported local AI behavior.
- **`check` cannot resolve a hostname:** both `qiko.localhost` and `admin.qiko.localhost` must resolve
  to loopback. Remove proxy or hosts-file overrides that send them elsewhere.

## OpenAPI synchronization

FastAPI serves the runtime schema at `/openapi.json`. The checked-in canonical artifacts are
`qiko-core/openapi.json` and `frontend/packages/api-client/openapi.json`; generated TypeScript types
are in `frontend/packages/api-client/src/schema.d.ts`.

After an API contract change:

```bash
cd qiko-core
uv sync --frozen --extra dev
uv run python ../scripts/sync_openapi.py
cd ../frontend
pnpm --filter @qiko/api-client generate
cd ../qiko-core
uv run python ../scripts/sync_openapi.py --check
cd ..
```

The final check prints drifted artifact paths and exits nonzero if synchronization is incomplete.
Review all generated diffs rather than editing generated artifacts by hand.

## Tests and quality checks

Use the same primary commands as CI:

```bash
cd qiko-core
uv sync --frozen --extra dev
uv run ruff check . ../scripts/sync_openapi.py
uv run python ../scripts/sync_openapi.py --check
uv run pytest

cd ../frontend
pnpm -r lint
pnpm --filter creator test
pnpm --filter admin test
pnpm --filter @qiko/api-client generate
pnpm -r build
cd ..
```

`pytest` enforces the repository's 80 percent coverage gate. After generating the API client, verify
that only intended OpenAPI and generated type changes remain in the diff.

## Safe local reset

Reset is destructive only to the `qiko-dev` Postgres and Redis volumes. It requires an interactive
terminal and exact confirmation, then recreates the stack, applies migrations, and prompts for the
new local Admin tenant, display name, email, and silent password:

```bash
./scripts/dev.sh reset
```

At the prompt, type exactly:

```text
DELETE qiko-dev volumes
```

Use reset only when local data can be discarded. Prefer `./scripts/dev.sh down` for normal stopping
because it preserves volumes. Do not bypass the guarded reset with a direct volume-deleting Compose
command.

## Pre-handoff acceptance checklist

Complete every applicable item before handing off a local-development change:

- [ ] A clean clone can run `./scripts/dev.sh setup`; it creates or preserves `.env`, validates the
      supported tools, and completes the frozen frontend dependency install.
- [ ] `.env` was reviewed only locally, remains uncommitted, uses `ENVIRONMENT=dev`, persistent DB
      stores, arq, stub AI, console email, and contains no shared credentials.
- [ ] `./scripts/dev.sh up` completes, waits for the five host services, and applies migrations.
- [ ] `./scripts/dev.sh frontend` serves both applications through Caddy at the canonical Creator
      and Admin origins.
- [ ] `./scripts/dev.sh status` reports `qiko-core`, `worker`, `db`, `redis`, and `caddy` running.
- [ ] `./scripts/dev.sh check` passes Compose validation, Postgres, Redis, Alembic head, local HTTP,
      non-mutating OpenAPI drift, focused bootstrap/OpenAPI backend tests, changed-Python lint,
      Creator/Admin tests, and workspace lint.
- [ ] Postgres-backed data survives `./scripts/dev.sh down` followed by `./scripts/dev.sh up`.
- [ ] A queued operation is handled by the arq worker, with no unexpected qiko-core, worker,
      Postgres, Redis, or Caddy errors in logs.
- [ ] Admin bootstrap works with `--tenant`, `--display-name`, and `--email`; password input is
      silent and absent from shell history and logs.
- [ ] Admin MFA enrollment was completed, backup codes were stored safely, the revoked session was
      exited, TOTP login works, one backup-code login works, and logout returns to `/login`.
- [ ] Creator signup works with a reserved local test email, the console-email verification code is
      obtained from the local signup response, verification completes, login works, and logout works.
- [ ] `./scripts/dev.sh parity` builds the same Dockerfiles and complete stack, migrates successfully,
      and prints all HTTP contract `PASS` lines.
- [ ] Backend lint, OpenAPI drift check, backend tests with coverage, frontend lint, Creator tests,
      Admin tests, API client generation, and frontend builds pass.
- [ ] If the API changed, both OpenAPI JSON artifacts and `schema.d.ts` are synchronized and their
      diffs were reviewed.
- [ ] If reset behavior changed, `./scripts/dev.sh reset` was tested with its exact confirmation and
      bootstrap prompts. No unguarded volume deletion command was used.
- [ ] `git status` and the final diff contain only intended files, no `.env`, no credentials, no
      local backup codes, and no generated test leftovers.
- [ ] `./scripts/dev.sh down` was used when the local stack no longer needed to remain running.
