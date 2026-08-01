import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const repositoryRoot = resolve(process.cwd(), "../../..");

function repositorySource(path: string): string {
  const filePath = resolve(repositoryRoot, path);
  return existsSync(filePath) ? readFileSync(filePath, "utf8") : "";
}

test("local E2E allows the exact handled credential-flow consent response", () => {
  const localDevelopmentE2e = repositorySource("frontend/e2e/tests/local-development.spec.ts");

  assert.match(localDevelopmentE2e, /EXPECTED_CREATOR_ERROR_RESPONSES[\s\S]*?"POST \/api\/v1\/consent 401",/);
  assert.match(localDevelopmentE2e, /EXPECTED_CREATOR_ERROR_RESPONSES\.has\(globalSignature\)/);
});

test("local E2E activates the hydrated Creator Logout button from the keyboard", () => {
  const localDevelopmentE2e = repositorySource("frontend/e2e/tests/local-development.spec.ts");

  assert.match(
    localDevelopmentE2e,
    /getByText\(\/worker slots used\/i\)[\s\S]*?const creatorLogout = page\.getByRole\("button", \{ name: "Logout", exact: true \}\);\n\s+await expect\(creatorLogout\)\.toBeVisible\(\);\n\s+await creatorLogout\.focus\(\);\n\s+await expect\(creatorLogout\)\.toBeFocused\(\);\n\s+await creatorLogout\.press\("Enter"\);/,
  );
  assert.doesNotMatch(localDevelopmentE2e, /getByRole\("button", \{ name: "Logout", exact: true \}\)\.click\(/);
});

test("Next dev servers allow only their exact Caddy browser origins", () => {
  const creatorConfig = repositorySource("frontend/apps/creator/next.config.mjs");
  const adminConfig = repositorySource("frontend/apps/admin/next.config.mjs");

  assert.equal(creatorConfig.match(/\ballowedDevOrigins\s*:/g)?.length, 1);
  assert.match(creatorConfig, /allowedDevOrigins:\s*\["qiko\.localhost"\],/);
  assert.equal(adminConfig.match(/\ballowedDevOrigins\s*:/g)?.length, 1);
  assert.match(adminConfig, /allowedDevOrigins:\s*\["admin\.qiko\.localhost"\],/);
});

test("local infrastructure uses persistent services, Caddy and exact browser origins", () => {
  const devCompose = repositorySource("docker-compose.dev.yml");
  const parityCompose = repositorySource("docker-compose.dev.parity.yml");
  const envExample = repositorySource(".env.example");

  assert.match(devCompose, /USE_DB_STORES=true/);
  assert.match(devCompose, /TASK_BACKEND=arq/);
  assert.match(devCompose, /Caddyfile\.dev/);
  assert.match(devCompose, /127\.0\.0\.1:\$\{QIKO_DEV_HTTP_PORT:-8080\}:8080/);
  assert.match(devCompose, /ipv4_address: 172\.28\.30\.2/);
  assert.match(
    devCompose,
    /subnet: 172\.28\.30\.0\/24\n\s+ip_range: 172\.28\.30\.128\/25\n\s+gateway: 172\.28\.30\.1/,
  );
  assert.doesNotMatch(devCompose, /3000:3000|3001:3001|5432:5432|6379:6379/);
  assert.match(parityCompose, /CREATOR_UPSTREAM=creator:3000/);
  assert.match(parityCompose, /ADMIN_UPSTREAM=admin:3001/);
  assert.match(envExample, /http:\/\/qiko\.localhost:8080/);
  assert.match(envExample, /http:\/\/admin\.qiko\.localhost:8080/);
});

test("local lifecycle and documentation expose the supported setup and parity commands", () => {
  const devScript = repositorySource("scripts/dev.sh");
  const devPlaybook = repositorySource("docs/playbooks/dev.md");
  const rootReadme = repositorySource("README.md");

  assert.match(devScript, /qiko-core worker db redis caddy/);
  assert.match(devScript, /qiko-core worker creator admin db redis caddy/);
  assert.match(devPlaybook, /\.\/scripts\/dev\.sh setup/);
  assert.match(devPlaybook, /\.\/scripts\/dev\.sh parity/);
  assert.match(rootReadme, /docs\/playbooks\/dev\.md/);
});

test("local check and CI run the focused non-mutating contract gates", () => {
  const devScript = repositorySource("scripts/dev.sh");
  const workflow = repositorySource(".github/workflows/ci.yml");
  const devPlaybook = repositorySource("docs/playbooks/dev.md");
  const workflowLines = workflow.split("\n");

  function filterPaths(filterName: string): Set<string> {
    const start = workflowLines.indexOf(`            ${filterName}:`) + 1;
    assert.notEqual(start, 0, `${filterName} filter must exist`);
    const paths = new Set<string>();
    for (const line of workflowLines.slice(start)) {
      if (!line.startsWith("              - ")) break;
      paths.add(line.trim().slice(2).replace(/^'|'$/g, ""));
    }
    return paths;
  }

  assert.match(devScript, /qiko-core\/\.venv\/bin\/python/);
  assert.match(devScript, /scripts\/sync_openapi\.py" --check/);
  assert.match(devScript, /test_bootstrap_dev\.py/);
  assert.match(devScript, /test_openapi_sync\.py/);
  assert.match(devScript, /--no-cov/);
  assert.match(devScript, /scripts\/check_local_contract\.py/);
  assert.match(devScript, /--filter creator test/);
  assert.match(devScript, /--filter admin test/);
  assert.match(devScript, /-r lint/);
  assert.match(devScript, /run_local_contract_check\n\s+run_focused_quality_checks/);
  const focusedChecks = devScript.slice(
    devScript.indexOf("run_focused_quality_checks()"),
    devScript.indexOf("prompt_required()"),
  );
  assert.equal(
    focusedChecks.match(/"\$\{CORE_PYTHON\}" "\$\{REPO_ROOT\}\/scripts\/sync_openapi\.py" --check/g)?.length,
    1,
  );
  assert.doesNotMatch(focusedChecks, /pnpm[^\n]*build/);

  const backendPaths = filterPaths("backend");
  for (const path of ["scripts/check_local_contract.py", "scripts/sync_openapi.py"]) {
    assert.ok(backendPaths.has(path), `backend filter must include ${path}`);
  }
  const frontendPaths = filterPaths("frontend");
  for (const path of [
    "scripts/dev.sh",
    "scripts/check_local_contract.py",
    "scripts/sync_openapi.py",
    "Caddyfile.dev",
    "docker-compose.dev.yml",
    "docker-compose.dev.parity.yml",
  ]) {
    assert.ok(frontendPaths.has(path), `frontend filter must include ${path}`);
  }
  const composePaths = filterPaths("compose");
  assert.ok(composePaths.has("scripts/dev.sh"));
  assert.ok(composePaths.has("Caddyfile*"));
  assert.ok(composePaths.has("docker-compose*.yml"));

  const backendJob = workflow.slice(workflow.indexOf("\n  backend:\n"), workflow.indexOf("\n  frontend:\n"));
  assert.doesNotMatch(backendJob, /sync_openapi\.py --check/);
  assert.match(backendJob, /ruff check .*check_local_contract\.py/);
  assert.match(backendJob, /uv run pytest/);
  const frontendJob = workflow.slice(workflow.indexOf("\n  frontend:\n"));
  assert.match(frontendJob, /pnpm install --frozen-lockfile/);
  assert.match(frontendJob, /pnpm --filter creator test/);
  assert.match(frontendJob, /pnpm --filter admin test/);
  assert.match(frontendJob, /pnpm --filter @qiko\/api-client generate/);
  assert.match(frontendJob, /git diff --exit-code -- \.\.\/qiko-core\/openapi\.json packages\/api-client\/openapi\.json packages\/api-client\/src\/schema\.d\.ts/);
  assert.match(workflow, /docker compose --env-file \.env -p qiko-dev -f docker-compose\.yml -f docker-compose\.dev\.yml config --quiet/);
  assert.match(workflow, /bash -n scripts\/dev\.sh/);
  assert.match(devPlaybook, /trusted workstation/);
  assert.match(devPlaybook, /firewall[\s\S]*3000[\s\S]*3001/);
});

test("frontend and OpenAPI documentation use canonical cross-application contracts", () => {
  const rootReadme = repositorySource("README.md");
  const adminForgotPassword = repositorySource("frontend/apps/admin/app/forgot-password/page.tsx");

  assert.match(rootReadme, /\/openapi\.json/);
  assert.doesNotMatch(rootReadme, /\/api\/v1\/openapi\.json/);
  assert.match(adminForgotPassword, /NEXT_PUBLIC_CREATOR_BASE_URL/);
});

test("frontend Docker context excludes dependencies, generated output, and secret environments", () => {
  const dockerIgnore = new Set(
    repositorySource("frontend/.dockerignore")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line !== "" && !line.startsWith("#")),
  );

  for (const pattern of [
    "node_modules/",
    "**/node_modules/",
    ".next/",
    "**/.next/",
    ".turbo/",
    "**/.turbo/",
    "dist/",
    "**/dist/",
    "build/",
    "**/build/",
    ".node-test-build/",
    "**/.node-test-build/",
    "coverage/",
    "**/coverage/",
    "e2e/test-results/",
    "e2e/playwright-report/",
    "e2e/blob-report/",
    "e2e/.auth/",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "!.env.example",
    "!**/.env.example",
  ]) {
    assert.ok(dockerIgnore.has(pattern), `frontend/.dockerignore must contain ${pattern}`);
  }
});
