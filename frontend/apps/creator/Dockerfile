# Build + serve the creator Next.js app from the frontend monorepo.
# Build context is the `frontend/` directory (see docker-compose.yml).
FROM node:20-slim AS base
WORKDIR /app
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable

ARG NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

COPY . .
RUN pnpm install --frozen-lockfile && pnpm --filter creator build

EXPOSE 3000
CMD ["pnpm", "--filter", "creator", "start"]
