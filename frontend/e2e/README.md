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

Run with `--workers 1` (or accept some flakiness) when running the full suite: the backend does
single-session revocation, so two tests logging into the *same* test account concurrently (across
different spec files, which Playwright may run in parallel workers) can invalidate each other's
session. Within a single spec file this is already handled with `test.describe.configure({ mode:
"serial" })`; it's only an issue across files sharing the same account.
