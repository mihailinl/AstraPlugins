/**
 * The startup assertion (§5.8) and the dual-format packaging.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const PKG_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const esmUrl = (rel) => pathToFileURL(join(PKG_ROOT, rel)).href;

const {
  assertNoReservedNames,
  descriptorProblems,
  RETIRED_NAMES,
} = require("../dist/reserved.js");
const { RESERVED_FIELD_NAMES, SERVICE_METHODS } = require("../dist/generated/index.js");
const { ProtoContractError } = require("../dist/service-contract.js");
const { astraProto } = require("../dist/proto-loader.js");

// ── the assertion ────────────────────────────────────────────────────────────

test("the shipped descriptor passes its own startup assertion", () => {
  assert.deepEqual(descriptorProblems(), []);
  assertNoReservedNames();
});

test("the reserved table is not empty, or the check is vacuous", () => {
  const total = Object.values(RESERVED_FIELD_NAMES).flat();
  assert.ok(total.length >= 7, `expected the proto's reserved names, got ${total.length}`);
  assert.deepEqual(RESERVED_FIELD_NAMES["astra.AiSettings"], ["use_thinking"]);
});

test("a revived reserved field is caught, named, and explained", () => {
  // The drift this exists for: a slice regenerated from an astra.proto where
  // `use_thinking` came back as a live field. A daemon in the field still reads
  // that name as the boolean the reasoning_effort scale replaced.
  const { descriptor } = require("../dist/generated/index.js");
  const ai = descriptor.nested.astra.nested.AiSettings;
  const saved = ai.fields.use_thinking;
  ai.fields.use_thinking = { type: "bool", id: 9 };
  try {
    const problems = descriptorProblems();
    assert.equal(problems.length, 1);
    assert.equal(problems[0].kind, "reserved-field");
    assert.equal(problems[0].where, "astra.AiSettings.use_thinking");
    assert.throws(() => assertNoReservedNames(), ProtoContractError);
    assert.throws(() => assertNoReservedNames(), /use_thinking.*is `reserved`/s);
  } finally {
    if (saved === undefined) delete ai.fields.use_thinking;
    else ai.fields.use_thinking = saved;
  }
  assert.deepEqual(descriptorProblems(), [], "the fixture must leave no trace");
});

test("a name Phase 1 retired is caught if it comes back", () => {
  const { descriptor } = require("../dist/generated/index.js");
  const astra = descriptor.nested.astra.nested;
  astra.RefreshTokenResponse = { fields: {} };
  try {
    const problems = descriptorProblems();
    assert.equal(problems.length, 1);
    assert.equal(problems[0].kind, "retired-name");
    assert.match(problems[0].detail, /removed from the plugin surface in Phase 1/);
  } finally {
    delete astra.RefreshTokenResponse;
  }
  assert.deepEqual(descriptorProblems(), []);
});

test("every retired name really is absent today", () => {
  // If one of these were present, the check above would be asserting on a
  // fixture rather than on a rule.
  const serialized = JSON.stringify(require("../dist/generated/index.js").descriptor);
  for (const name of RETIRED_NAMES) {
    assert.ok(!serialized.includes(`"${name}"`), `${name} is in the shipped descriptor`);
  }
});

test("a method that vanished from the loaded stub is caught before the server binds", () => {
  // TypeScript's own failure mode: `stub.SendChatMessage` on a stale descriptor
  // is `undefined`, and calling it is a bare TypeError from inside grpc-js.
  const proto = astraProto.PluginHostService.prototype;
  const saved = proto.SendChatMessage;
  delete proto.SendChatMessage;
  try {
    const problems = descriptorProblems();
    assert.equal(problems.length, 1);
    assert.equal(problems[0].kind, "missing-method");
    assert.equal(problems[0].where, "PluginHostService.SendChatMessage");
    assert.throws(() => assertNoReservedNames(), /undefined.*on the loaded stub/s);
  } finally {
    proto.SendChatMessage = saved;
  }
  assert.deepEqual(descriptorProblems(), []);
});

test("the assertion covers every generated method, not a sample", () => {
  const declared = Object.values(SERVICE_METHODS).reduce((n, m) => n + m.length, 0);
  assert.ok(declared > 150, `expected the whole surface, counted ${declared}`);
});

// ── packaging ────────────────────────────────────────────────────────────────

const pkg = JSON.parse(readFileSync(join(PKG_ROOT, "package.json"), "utf8"));

test("the published name is the unscoped one", () => {
  assert.equal(pkg.name, "astra-plugin-sdk");
});

test("the package declares CommonJS, an exports map and a Node floor", () => {
  assert.equal(pkg.type, "commonjs");
  assert.equal(pkg.engines.node, ">=20");
  assert.deepEqual(Object.keys(pkg.exports), [".", "./testing", "./package.json"]);
  for (const [subpath, entry] of Object.entries(pkg.exports)) {
    if (typeof entry === "string") continue;
    for (const condition of ["import", "require"]) {
      const target = entry[condition].default;
      const types = entry[condition].types;
      assert.ok(existsSync(join(PKG_ROOT, target)), `${subpath} ${condition} -> ${target} missing`);
      assert.ok(existsSync(join(PKG_ROOT, types)), `${subpath} ${condition} types -> ${types} missing`);
    }
  }
});

test("the ESM directory is marked as ESM, or Node reads it as CommonJS", () => {
  const marker = JSON.parse(readFileSync(join(PKG_ROOT, "dist/esm/package.json"), "utf8"));
  assert.equal(marker.type, "module");
  assert.match(readFileSync(join(PKG_ROOT, "dist/esm/index.js"), "utf8"), /^export /m);
  assert.match(readFileSync(join(PKG_ROOT, "dist/index.js"), "utf8"), /exports\./);
});

test("both formats really load, in the runtime that will load them", () => {
  // Not a file-shape check: `node -e` actually imports each build. A dual
  // package that type-checks and throws `ERR_REQUIRE_ESM` on first use is the
  // whole reason this test is a subprocess.
  const cjs = execFileSync(
    process.execPath,
    ["-e", 'const m = require("./dist/index.js"); console.log(typeof m.plugin, typeof m.s.object);'],
    { cwd: PKG_ROOT, encoding: "utf8" }
  ).trim();
  assert.equal(cjs, "function function");

  const esm = execFileSync(
    process.execPath,
    [
      "--input-type=module",
      "-e",
      // file:// URLs, not bare absolute paths: Node's ESM loader reads the "D:"
      // of a Windows path as a URL scheme and refuses it. Still the real build,
      // still resolved absolutely — a relative specifier here would depend on cwd.
      `import { plugin, s } from ${JSON.stringify(esmUrl("dist/esm/index.js"))};
       import { Harness } from ${JSON.stringify(esmUrl("dist/esm/testing/index.js"))};
       console.log(typeof plugin, typeof s.object, typeof Harness);`,
    ],
    { cwd: PKG_ROOT, encoding: "utf8" }
  ).trim();
  assert.equal(esm, "function function function");
});

test("the descriptor module and descriptor.json are the same bytes", () => {
  // `descriptor.json` is no longer what the SDK imports (a JSON import cannot
  // be loaded by Node's ESM resolver without an import attribute), but it is
  // still shipped and still read by the repo's proto checks. Equal or useless.
  const fromModule = require("../dist/generated/descriptor.js").descriptorJson;
  const fromJson = JSON.parse(readFileSync(join(PKG_ROOT, "src/generated/descriptor.json"), "utf8"));
  assert.deepEqual(fromModule, fromJson);
  assert.ok(existsSync(join(PKG_ROOT, "dist/generated/descriptor.json")), "the .json must ship");
});
