import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = process.cwd();
const repositoryRoot = resolve(appRoot, "../../..");

function source(path: string): string {
  return readFileSync(resolve(appRoot, path), "utf8");
}

test("Signal keeps its existing actions and shows a Coming Soon badge on desktop and mobile", () => {
  const chrome = source("components/QikoSiteChrome.tsx");
  assert.ok((chrome.match(/Coming Soon/g) ?? []).length >= 2);
  assert.match(chrome, /onClick=\{onSignal\}/);
  assert.match(chrome, /closeMobileAnd\(onSignal\)/);
  assert.doesNotMatch(chrome, /coming-soon|disabled=|aria-disabled/);
  assert.doesNotMatch(chrome, /<a onClick=/);
  assert.match(chrome, /aria-haspopup="menu" aria-expanded=\{menu === "labs"\}/);
  assert.match(chrome, /width: 44, height: 44/);
});

test("Next hides framework disclosure and publishes security.txt", () => {
  const config = source("next.config.mjs");
  const securityPath = resolve(appRoot, "public/.well-known/security.txt");
  const middleware = source("middleware.ts");
  assert.match(config, /poweredByHeader:\s*false/);
  assert.match(middleware, /pathname === "\/\.well-known\/security\.txt"/);
  assert.equal(existsSync(securityPath), true);
  const security = readFileSync(securityPath, "utf8");
  assert.match(security, /Contact: mailto:support@qiko\.ai/);
  assert.match(security, /Canonical: https:\/\/qiko\.ai\/\.well-known\/security\.txt/);
  assert.match(security, /Expires: 2027-/);
});

test("CI validates Caddy changes through the compose security job", () => {
  const workflow = readFileSync(resolve(repositoryRoot, ".github/workflows/ci.yml"), "utf8");
  assert.match(workflow, /- 'Caddyfile\*'/);
  assert.match(workflow, /caddy validate --config/);
});

test("preprod and live expose one strict creator CSP without unsafe eval or broad HTTPS", () => {
  for (const filename of ["Caddyfile", "Caddyfile.live"]) {
    const caddy = readFileSync(resolve(repositoryRoot, filename), "utf8");
    assert.equal((caddy.match(/Content-Security-Policy/g) ?? []).length, 2, filename);
    assert.doesNotMatch(caddy, /unsafe-eval/, filename);
    assert.doesNotMatch(caddy, /connect-src[^\n]*\shttps:\s/, filename);
    assert.doesNotMatch(caddy, /cloudflareinsights/, filename);
    for (const directive of caddy.matchAll(/connect-src ([^;"\n]+)/g)) {
      assert.equal(directive[1].split(/\s+/).some((token) => token.includes("*")), false, filename);
    }
    assert.match(caddy, /default-src 'self'/, filename);
    assert.match(caddy, /object-src 'none'/, filename);
    assert.match(caddy, /frame-ancestors 'self'/, filename);
  }
  const live = readFileSync(resolve(repositoryRoot, "Caddyfile.live"), "utf8");
  assert.match(live, /@www host www\.qiko\.ai/);
  assert.match(live, /redir @www https:\/\/qiko\.ai\{uri\} permanent/);
  assert.match(live, /connect-src 'self' https:\/\/api\.stripe\.com/);
});
