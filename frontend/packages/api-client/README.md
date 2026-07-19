# @qiko/api-client

Typed TypeScript client generated from the qiko-core OpenAPI spec. FastAPI serves the schema at the
app root, `/openapi.json` (the API routers are mounted under `/api/v1`, but the schema document
itself is at the root path).

```bash
# regenerate the types against a running backend (schema change).
# Default target is http://localhost:8000/openapi.json; override with OPENAPI_URL.
pnpm --filter @qiko/api-client generate
```

`makeClient(baseUrl)` returns a fully typed client (openapi-fetch) that sends the httpOnly auth
cookies.

Status: this package is not yet wired into the apps. `apps/creator` and `apps/admin` currently call
qiko-core through their own `lib/api.ts` fetch wrapper (which also sends the auth cookies with
`credentials: "include"`). Adopting this generated client in place of the hand-rolled wrappers is a
planned cleanup.

`src/schema.d.ts` is generated (regenerated from the OpenAPI schema); it is not hand-edited.
