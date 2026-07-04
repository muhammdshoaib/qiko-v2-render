# Qiko frontend (Next.js 15 monorepo)

pnpm + Turborepo workspace. Ported from the current React SPAs.

```
frontend/
├── apps/
│   ├── creator/   Creator / Studio (IDG, Essential Living, Signal workers live here)
│   ├── admin/     Admin dashboard
│   └── signal/    Qiko Signal SaaS UI
└── packages/
    ├── ui/         Shared shadcn / Radix / Tailwind design system
    ├── api-client/ Typed client generated from the qiko-core OpenAPI spec
    └── config/     Shared TS / ESLint / Tailwind config
```

Scaffold only for now (workspace + Turbo). The apps and packages are built out in the
Creator app uplift phase; see `../../04-migration-plan.md` and `../../Qiko-Architecture-Uplift-Plan.pdf`.
