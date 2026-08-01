# @qiko/api-client

Typed TypeScript client generated from the qiko-core OpenAPI spec. FastAPI serves the schema at the
app root, `/openapi.json` (the API routers are mounted under `/api/v1`, but the schema document
itself is at the root path).

From the repository root, one file-based command synchronizes both checked-in OpenAPI JSON files
and regenerates `src/schema.d.ts` from `qiko-core/openapi.json`:

```bash
qiko-core/.venv/bin/python scripts/sync_openapi.py
```

Use the same command with `--check` to verify all three artifacts without modifying them. The
command uses the locally installed, lockfile-resolved `openapi-typescript` CLI and requires no
backend process or network access.

`makeClient(baseUrl)` returns a fully typed client (openapi-fetch) that sends the httpOnly auth
cookies.

Status: this package is not yet wired into the apps. `apps/creator` and `apps/admin` currently call
qiko-core through their own `lib/api.ts` fetch wrapper (which also sends the auth cookies with
`credentials: "include"`). Adopting this generated client in place of the hand-rolled wrappers is a
planned cleanup.

`src/schema.d.ts` is generated (regenerated from the OpenAPI schema); it is not hand-edited.
