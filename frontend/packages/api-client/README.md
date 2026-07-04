# @qiko/api-client

Typed TypeScript client generated from the qiko-core OpenAPI spec (FastAPI serves `/openapi.json`).

```bash
# regenerate the types (CI runs this on schema change)
OPENAPI_URL=https://preprod.qiko.ai/api/v1/openapi.json pnpm --filter @qiko/api-client generate
```

`makeClient(baseUrl)` returns a fully typed client (openapi-fetch) that sends the httpOnly auth
cookies. The creator, admin and signal apps import this instead of hand-rolled fetch wrappers,
removing the old duplicated clients and the dead tRPC layer.

`src/schema.d.ts` is generated (git-ignored / regenerated in CI); it is not hand-edited.
