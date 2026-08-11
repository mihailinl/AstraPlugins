#!/usr/bin/env node
/**
 * Two things `tsc` cannot do, run after both emits.
 *
 * 1. **`dist/esm/package.json`.** The package is `"type": "commonjs"`, so Node
 *    reads every `.js` under it as CommonJS — including the ES modules in
 *    `dist/esm/`, which would then fail on their first `import` statement. A
 *    `{"type": "module"}` marker in that directory is the standard, and only,
 *    way to say otherwise.
 *
 * 2. **`dist/generated/descriptor.json`.** The descriptor is imported as a
 *    TypeScript module (see `gen-descriptor.mjs` for why it cannot be a JSON
 *    import in a dual build), so tsc no longer copies the .json into the
 *    output. It is still shipped: `tools/check-proto.sh` and CI's tarball check
 *    both read it, and it is the copy any non-TypeScript tool wants.
 *
 * Run: `node tools/finish-build.mjs` (the `build` script does it for you).
 */

import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(HERE, "..");
const DIST = join(PKG_ROOT, "dist");
const ESM = join(DIST, "esm");

function fail(message) {
  console.error(`finish-build: ${message}`);
  process.exit(1);
}

if (!existsSync(join(DIST, "index.js"))) {
  fail("dist/index.js is missing — run `tsc` first (the `build` script does).");
}
if (!existsSync(join(ESM, "index.js"))) {
  fail("dist/esm/index.js is missing — run `tsc -p tsconfig.esm.json` first.");
}

writeFileSync(
  join(ESM, "package.json"),
  `${JSON.stringify(
    {
      // Not the package name: a nested package.json with a `name` would make
      // this directory look like a separate package to some resolvers.
      type: "module",
      sideEffects: false,
    },
    null,
    2
  )}\n`
);

const descriptorSrc = join(PKG_ROOT, "src", "generated", "descriptor.json");
if (!existsSync(descriptorSrc)) fail("src/generated/descriptor.json is missing — run `npm run generate`.");
mkdirSync(join(DIST, "generated"), { recursive: true });
copyFileSync(descriptorSrc, join(DIST, "generated", "descriptor.json"));

console.log("finish-build: dist/esm/package.json written, descriptor.json copied into dist/generated/");
