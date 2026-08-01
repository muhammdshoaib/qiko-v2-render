// Typed Qiko API client, generated from the qiko-core OpenAPI spec.
// Run `pnpm --filter @qiko/api-client generate` to refresh
// src/schema.d.ts, then import the typed client here. This replaces the hand-rolled clients
// and the dead tRPC code in the old SPAs.
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export function makeClient(baseUrl: string) {
  // credentials: 'include' so the httpOnly auth cookies (identity module) are sent.
  return createClient<paths>({ baseUrl, credentials: "include" });
}

export type { paths };
