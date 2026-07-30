const { readdirSync, rmSync } = require("node:fs");
const { spawnSync } = require("node:child_process");
const { join } = require("node:path");

const outputDirectory = join(process.cwd(), ".node-test-build");
const tsc = process.platform === "win32"
  ? join(process.cwd(), "node_modules", ".bin", "tsc.cmd")
  : join(process.cwd(), "node_modules", ".bin", "tsc");

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exitCode = result.status ?? 1;
  return result.status === 0;
}

try {
  rmSync(outputDirectory, { recursive: true, force: true });
  if (!run(tsc, ["--project", "tests/tsconfig.node.json"])) return;
  const testDirectory = join(outputDirectory, "tests");
  const testFiles = readdirSync(testDirectory)
    .filter((name) => name.endsWith(".test.js"))
    .map((name) => join(testDirectory, name));
  run(process.execPath, ["--test", ...testFiles]);
} finally {
  rmSync(outputDirectory, { recursive: true, force: true });
}
