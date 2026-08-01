const localAssetsAssert = require("node:assert/strict");
const { existsSync: localAssetsExistsSync, readFileSync: localAssetsReadFileSync } = require("node:fs");
const { resolve: localAssetsResolve } = require("node:path");
const localAssetsTest = require("node:test");

const localAssetsSourceRoot = localAssetsExistsSync(localAssetsResolve(__dirname, "../app"))
  ? localAssetsResolve(__dirname, "..")
  : localAssetsResolve(__dirname, "../..");

for (const page of ["login", "forgot-password"]) {
  localAssetsTest(`${page} uses the local Qiko logo`, () => {
    const source = localAssetsReadFileSync(localAssetsResolve(localAssetsSourceRoot, `app/${page}/page.tsx`), "utf8");

    localAssetsAssert.match(source, /src=["']\/qiko-logo\.webp["']/);
    localAssetsAssert.doesNotMatch(source, /https?:\/\/[^"']*qiko\.ai\/[^"']*logo[^"']*/i);
  });
}
