# Build + serve the admin Next.js app from the frontend monorepo.
# Build context is the `frontend/` directory (see docker-compose.yml).
FROM node:20-slim AS base
WORKDIR /app
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable

COPY . .
RUN pnpm install --frozen-lockfile && pnpm --filter admin build

EXPOSE 3001
CMD ["pnpm", "--filter", "admin", "start"]
