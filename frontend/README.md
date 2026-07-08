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

Both `apps/creator` and `apps/admin` are fully built out (not scaffolding) and are what's
deployed to preprod/live. See `../README.md` for setup/test/deploy instructions and
`../04-migration-plan.md` for the broader migration context.
