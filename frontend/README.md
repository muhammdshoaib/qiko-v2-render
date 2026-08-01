# Qiko frontend (Next.js 15 monorepo)

pnpm + Turborepo workspace. Ported from the current React SPAs.

```
frontend/
├── apps/
│   ├── creator/     Creator / Studio (worker build, RFP packs, billing, onboarding)
│   └── admin/       Platform admin dashboard
├── packages/
│   ├── ui/          Shared shadcn / Radix / Tailwind design system + brand tokens
│   └── api-client/  Typed client generated from the qiko-core OpenAPI spec (not yet wired
│                    into either app -- both apps currently call qiko-core through their own
│                    local lib/api.ts fetch wrapper instead; see cleanup follow-ups)
└── e2e/             Playwright end-to-end tests across creator/admin
```

Both `apps/creator` and `apps/admin` are fully built out (not scaffolding) and are what is
deployed to preprod/live.

For local work, use the canonical guide rather than starting either app with a custom API URL:

- [Host frontend development](../docs/playbooks/dev.md#normal-host-development) runs both Next.js
  development servers on the host behind local Caddy and provides hot reload.
- [Container parity mode](../docs/playbooks/dev.md#container-parity-mode) builds both apps with the
  repository Dockerfiles and checks the complete local stack.

See `../docs/creating-a-worker.md` for how a worker is created and how a new Studio cockpit is added.
