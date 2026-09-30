import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appRoot = process.cwd();
const repositoryRoot = resolve(appRoot, "../../..");

function source(path: string): string {
  return readFileSync(resolve(appRoot, path), "utf8");
}

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

test("live and preprod agree on marketing and core API path ownership", () => {
  const marketingPaths = (text: string): Set<string> => {
    const line = /@marketing path ([^\n]+)/.exec(text);
    assert.ok(line, "missing @marketing path matcher");
    return new Set(line[1].trim().split(/\s+/));
  };
  const coreApiExclusions = (text: string): Set<string> => {
    const block = /@core_api \{[^}]*\}/.exec(text);
    assert.ok(block, "missing @core_api matcher");
    const notPath = /not path ([^\n]+)/.exec(block[0]);
    assert.ok(notPath, "@core_api must carry a not path exclusion list");
    return new Set(notPath[1].trim().split(/\s+/));
  };
  const caddys: Record<string, string> = {};
  for (const filename of ["Caddyfile", "Caddyfile.live"]) {
    caddys[filename] = readFileSync(resolve(repositoryRoot, filename), "utf8");
    const marketing = marketingPaths(caddys[filename]);
    const excluded = coreApiExclusions(caddys[filename]);
    for (const owned of ["/qiko-static/*", "/visibility", "/status", "/api/labs/contact"]) {
      assert.ok(marketing.has(owned), `${filename}: @marketing must own ${owned}`);
    }
    for (const foreign of ["/login", "/signup", "/dashboard", "/embed/*", "/widget.js"]) {
      assert.ok(!marketing.has(foreign), `${filename}: @marketing must not capture ${foreign}`);
    }
    const websiteApis = new Set([...marketing].filter((p) => p.startsWith("/api/")));
    assert.deepEqual([...excluded].sort(), [...websiteApis].sort(), `${filename}: @core_api exclusions must equal the website-owned API paths in @marketing`);
    const marketingHandle = caddys[filename].indexOf("handle @marketing");
    const coreApiHandle = caddys[filename].indexOf("handle @core_api");
    assert.ok(marketingHandle !== -1 && coreApiHandle !== -1, filename);
    assert.ok(marketingHandle < coreApiHandle, `${filename}: handle @marketing must be evaluated before handle @core_api`);
    const bareApi = caddys[filename].indexOf("handle /api/*");
    assert.ok(bareApi === -1 || bareApi > coreApiHandle, `${filename}: no bare handle /api/* may sit ahead of handle @core_api`);
  }
  const live = [...marketingPaths(caddys["Caddyfile.live"])].sort();
  const preprod = [...marketingPaths(caddys["Caddyfile"])].sort();
  assert.deepEqual(live, preprod, "live and preprod @marketing path lists must not drift");
});

test("preprod and live expose one strict creator CSP without unsafe eval or broad HTTPS", () => {
  for (const filename of ["Caddyfile", "Caddyfile.live"]) {
    const caddy = readFileSync(resolve(repositoryRoot, filename), "utf8");
    // 3 CSPs per file: the strict app CSP + the public embed-surface CSP on the creator site
    // (QIK-336: /embed + /widget.js are framable), plus the admin site's CSP.
    assert.equal((caddy.match(/Content-Security-Policy/g) ?? []).length, 3, filename);
    assert.doesNotMatch(caddy, /unsafe-eval/, filename);
    assert.doesNotMatch(caddy, /connect-src[^\n]*\shttps:\s/, filename);
    assert.doesNotMatch(caddy, /cloudflareinsights/, filename);
    for (const directive of caddy.matchAll(/connect-src ([^;"\n]+)/g)) {
      assert.equal(directive[1].split(/\s+/).some((token) => token.includes("*")), false, filename);
    }
    assert.match(caddy, /default-src 'self'/, filename);
    assert.match(caddy, /object-src 'none'/, filename);
    assert.match(caddy, /frame-ancestors 'self'/, filename);
    // frame-ancestors * is allowed in exactly ONE CSP header value (the public embed surface).
    assert.equal((caddy.match(/Content-Security-Policy "[^"]*frame-ancestors \*/g) ?? []).length, 1, filename);
    // #205 removed 'unsafe-inline' from script-src on the theory that neither app has any
    // inline <script> tag of its own. That missed that the App Router's OWN streaming/RSC
    // hydration mechanism injects several inline `self.__next_f.push(...)` <script> tags into
    // every page, on every Next.js app, regardless of what the app's own source contains --
    // CSP has no way to distinguish those from any other inline script. Deployed to preprod,
    // this blocked every one of those on every page load: Next.js could never hydrate, so
    // every page (creator, admin, marketing) rendered a permanently blank screen. Restored
    // here; a nonce-based CSP (Next.js supports emitting its own nonce'd scripts if the
    // response carries one) is the real fix for the original scan finding, tracked separately
    // since it needs middleware changes in three Next.js apps, not just this file.
    for (const directive of caddy.matchAll(/Content-Security-Policy "([^"]+)"/g)) {
      const scriptSrc = /script-src ([^;]+)/.exec(directive[1])?.[1] ?? "";
      assert.match(scriptSrc, /'unsafe-inline'/, `${filename}: ${directive[1]}`);
      assert.match(directive[1], /style-src 'self' 'unsafe-inline'/, filename);
    }
  }
  const live = readFileSync(resolve(repositoryRoot, "Caddyfile.live"), "utf8");
  assert.match(live, /@www host www\.qiko\.ai/);
  assert.match(live, /redir @www https:\/\/qiko\.ai\{uri\} permanent/);
  assert.match(live, /connect-src 'self' https:\/\/api\.stripe\.com/);
});

// An external security scan flagged www.preprod.qiko.ai (the marketing site's own standalone
// preprod vhost) for missing X-Frame-Options/Permissions-Policy. On live, the equivalent
// marketing paths are served under the qiko.ai app vhost's own @app header block (see the
// @marketing handle in Caddyfile.live), so they already inherit both headers from there; this
// vhost only exists as a *separate* block on preprod, so it needs its own copy to match.
test("preprod's marketing vhost sends X-Frame-Options and Permissions-Policy, matching live", () => {
  const caddy = readFileSync(resolve(repositoryRoot, "Caddyfile"), "utf8");
  const marketingBlock = caddy.slice(caddy.indexOf("www.preprod.qiko.ai {"), caddy.indexOf("\n}\n", caddy.indexOf("www.preprod.qiko.ai {")));
  assert.match(marketingBlock, /X-Frame-Options "SAMEORIGIN"/);
  assert.match(marketingBlock, /Permissions-Policy "[^"]+"/);
});
