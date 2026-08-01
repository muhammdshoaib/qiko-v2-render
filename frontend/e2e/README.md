# Critical-path E2E tests

Playwright smoke tests against a live environment (preprod by default). These are the checks
that should catch a broken sign-out, a locked-out admin panel, or a broken worker page before a
human does.

## Setup

```
cd frontend/e2e
pnpm install
pnpm exec playwright install --with-deps chromium
cp .env.example .env   # fill in test account credentials
```

## Run

```
pnpm test
```

Unauthenticated checks (landing page, login page render) always run. Authenticated checks
(login round-trip, sign-out, Studio, admin panel, IDG grounded answering) are skipped unless the
matching `*_TEST_EMAIL` / `*_TEST_PASSWORD` env vars are set -- never commit real credentials.

## Local development contract

Start either supported local stack mode first, then run only the local specification from
`frontend/e2e`:

```bash
QIKO_LOCAL=1 QIKO_DEV_HTTP_PORT=8080 \
  pnpm exec playwright test tests/local-development.spec.ts
```

`QIKO_LOCAL=1` is mandatory. Without that exact guard the local specification is skipped and the
existing suite still defaults to preprod. In local mode the Playwright config forces Creator to
`http://qiko.localhost:${QIKO_DEV_HTTP_PORT:-8080}` and Admin to
`http://admin.qiko.localhost:${QIKO_DEV_HTTP_PORT:-8080}`. It ignores `BASE_URL` and
`ADMIN_BASE_URL`, uses one worker with zero retries, selects only the list reporter, and disables
traces and screenshots. It does not make local execution the default or produce an HTML report. The
local tests block and report browser HTTP, WebSocket, and service-worker activity outside those two
origins using sanitized hostname-and-path diagnostics.

The public contract covers Creator and Admin routing, both health paths, docs, OpenAPI, exact
credentialed CORS preflights for both browser origins, the Admin forgot-password handoff to Creator,
and unauthenticated Admin API denial. The forgot-password check generates a unique reserved
`@example.test` address, so it does not send an email or expose a reset code.

The repeatable local API acceptance creates its own unique `@example.test` account and random strong
passwords. It exercises signup and email verification with the current Creator policy releases,
login, CSRF refresh and cookie rotation, logout and revoked-cookie replay, password reset, TOTP
enrollment, MFA login, and non-platform-admin denial through the Creator Caddy origin. It requires no
credential variables and never prints generated passwords, verification codes, reset codes, TOTP
secrets, or cookies. Each run leaves one disposable MFA-enabled local account in the local database;
unique identities make the check repeatable, and the guarded `./scripts/dev.sh reset` removes this
accumulated local test data when it is safe to discard.

To run the stateful identity flow, first use the guarded `./scripts/dev.sh reset` procedure, then
bootstrap a new disposable local platform Admin identity dedicated to exactly one test run. Supply
that freshly reset and bootstrapped identity only to this command:

```bash
(
  read -r -p 'Fresh local Admin email: ' LOCAL_ADMIN_EMAIL
  read -r -s -p 'Fresh local Admin password: ' LOCAL_ADMIN_PASSWORD
  printf '\n'
  export LOCAL_ADMIN_EMAIL LOCAL_ADMIN_PASSWORD
  set +e
  QIKO_LOCAL=1 QIKO_DEV_HTTP_PORT=8080 \
    pnpm exec playwright test tests/local-development.spec.ts \
    --grep 'enrolls local Admin MFA'
  status=$?
  unset LOCAL_ADMIN_PASSWORD LOCAL_ADMIN_EMAIL
  exit "$status"
)
```

Do not put real, shared, preprod, or production credentials in these variables. Never reuse a local
identity that another developer or test uses. The test does not invent credentials and skips unless
both local values are set. It verifies Creator login/logout before MFA, enrolls TOTP through the real
local API, verifies an Admin TOTP session and overview, then consumes one backup code and confirms
that it cannot be reused. This mutates the local account and MFA remains enabled.

The credential flow is intentionally single-use because its TOTP secret is never saved. After every
run, interrupted run, partial failure, or retry, perform the guarded `./scripts/dev.sh reset` from the
repository root and bootstrap a new disposable identity before running it again. Never bypass the
guarded reset with a direct Docker volume deletion command.

Local mode disables traces, screenshots, retries, and the HTML reporter so sensitive browser and API
state is not retained by Playwright. Treat any unexpected file under `test-results/local/` as
sensitive: do not commit, upload, or share it, and delete it immediately after review:

```bash
rm -rf frontend/e2e/test-results/local
```

Never run the stateful flow against preprod, production, or any shared account.

## Post-deploy password-reset acceptance

After deploying, run the route-mocked acceptance against the deployed Creator UI without sending an
email or mutating a real reset code:

```
RUN_PASSWORD_RESET_ACCEPTANCE=1 BASE_URL=https://<deployed-creator-host> \
  pnpm exec playwright test tests/creator.spec.ts --grep "sessionStorage is blocked"
```

This verifies the successful forgot-password response, navigation when the browser blocks the
`sessionStorage` property itself, the normalised query fallback, and the exact visible reset-form
copy. The forgot-password API response is fulfilled by Playwright, so the check sends no email.

Run with `--workers 1` (or accept some flakiness) when running the full suite: the backend does
single-session revocation, so two tests logging into the *same* test account concurrently (across
different spec files, which Playwright may run in parallel workers) can invalidate each other's
session. Within a single spec file this is already handled with `test.describe.configure({ mode:
"serial" })`; it's only an issue across files sharing the same account.
