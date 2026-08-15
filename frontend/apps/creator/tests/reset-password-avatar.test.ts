import assert from "node:assert/strict";
import test from "node:test";

import { resetPasswordAvatar } from "../lib/avatarApi";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

test("a successful password reset is final and does not implicitly log in", async (t) => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = (async (input) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith("/auth/reset-password")) {
      return jsonResponse(200, { reset: true });
    }
    if (url.endsWith("/auth/login")) {
      return jsonResponse(401, { detail: "Invalid or missing 2FA code" });
    }
    return jsonResponse(404, { detail: "unexpected endpoint" });
  }) as typeof fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  const outcome = await resetPasswordAvatar({
    email: "mfa@example.test",
    otp: "123456",
    password: "new-secure-password",
  }).then(
    () => "resolved",
    (error: unknown) => `rejected: ${error instanceof Error ? error.message : String(error)}`,
  );

  assert.deepEqual({
    endpoints: calls.map((url) => url.slice(url.indexOf("/auth/"))),
    outcome,
  }, {
    endpoints: ["/auth/reset-password"],
    outcome: "resolved",
  });
});
