# Vendored Swagger UI assets (app/static/docs-assets/)

| | |
|---|---|
| Package | `swagger-ui-dist` |
| Version | 5.17.14 |
| Source | `https://unpkg.com/swagger-ui-dist@5.17.14/<file>` |
| Vendored on | 2026-09-11 (JM2-1134) |

```
40170f0ee859d17f92131ba707329a88a070e4f66874d11365e9a77d232f6117  swagger-ui.css
c2e4a9ef08144839ff47c14202063ecfe4e59e70a4e7154a26bd50d880c88ba1  swagger-ui-bundle.js
```

## Why these files are in the repository

The Content Security Policy served by Caddy allows scripts from `'self'` and `'unsafe-inline'`
only, plus `https://js.stripe.com`:

```
script-src 'self' 'unsafe-inline' https://js.stripe.com
```

A CDN-hosted renderer therefore cannot execute at all. Serving the two files from the same
origin is the only option that works, and it also means the docs page keeps working if the
CDN is unreachable.

Vendoring was chosen over adding a Python package that ships the same assets: two reviewable
files carry less supply-chain surface than a dependency, and a dependency addition is a
separately approved action in this workspace.

## Upgrading

1. Refetch both files at the new version with the `unpkg.com` URLs above.
2. Recompute both hashes with `shasum -a 256` and replace them here, along with the version
   and the date.
3. Load `/api/v1/tenants/joseph-mews/docs`, supply a key, and confirm the spec renders and a
   try-it request still carries `X-Api-Key` and `X-Tenant-Id`.

The hashes exist so an upgrade is a reviewable change rather than a silent one. Nothing
verifies them automatically at runtime: the files are served from disk, so a change to them
is a change to the diff, which is where it should be caught.

## Why this file sits outside the served directory

`/api/v1/docs-assets` is a public mount, so anything inside it is readable without a key.
Keeping the version pin one level up means an anonymous caller cannot read the exact renderer
version straight off the server and match it against a future advisory.
