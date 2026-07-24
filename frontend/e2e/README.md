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
