const assert = require("node:assert/strict");
const { existsSync } = require("node:fs");
const { resolve } = require("node:path");
const test = require("node:test");

const compiledModule = resolve(__dirname, "../lib/origins.js");
const originsModule = existsSync(compiledModule) ? "../lib/origins" : "../lib/origins.ts";
const { resolveCreatorOrigin } = require(originsModule);

test("configured local creator origin wins and normalizes a trailing slash", () => {
  const creatorOrigin = resolveCreatorOrigin(
    "http://localhost:3001",
    "http://qiko.localhost:8080/",
  );

  assert.equal(creatorOrigin, "http://qiko.localhost:8080");
  assert.notEqual(creatorOrigin, "http://localhost:3001");
});

test("known production and preprod admin origins map to their creator origins", () => {
  assert.equal(resolveCreatorOrigin("https://admin.qiko.ai"), "https://qiko.ai");
  assert.equal(resolveCreatorOrigin("https://admin.preprod.qiko.ai"), "https://preprod.qiko.ai");
});

test("ambiguous localhost without configuration fails closed", () => {
  assert.throws(
    () => resolveCreatorOrigin("http://localhost:3001"),
    /creator origin/i,
  );
});

test("configured creator URL must be a credential-free HTTP(S) origin", () => {
  const invalidConfiguredOrigins = [
    "http://user:password@qiko.localhost:8080",
    "ftp://qiko.localhost:8080",
    "http://qiko.localhost:8080/reset-password",
    "http://qiko.localhost:8080?tenant=qiko",
    "http://qiko.localhost:8080#reset",
  ];

  for (const configuredOrigin of invalidConfiguredOrigins) {
    assert.throws(
      () => resolveCreatorOrigin("https://admin.qiko.ai", configuredOrigin),
      /configured creator URL/i,
      configuredOrigin,
    );
  }
});
