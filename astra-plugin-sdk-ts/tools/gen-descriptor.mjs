#!/usr/bin/env node
/**
 * Generates `src/generated/descriptor.json` + `src/generated/index.ts` from the
 * canonical `proto/plugin.proto` at the repo root.
 *
 * The SDK used to carry two hand-maintained copies of the protocol as inline
 * template strings (`proto-loader.ts`, `daemon-client.ts`), write them to
 * `os.tmpdir()` and load them from there. They drifted: `ChatService` still
 * described the pre-event-sourcing API, and three `PluginCapabilityService`
 * methods the SDK registered handlers for did not exist in the descriptor at
 * all, so grpc-js dropped them silently. Generating the descriptor from the one
 * true `.proto` at build time makes that class of drift impossible.
 *
 * Run: `npm run generate` (also runs automatically via `prebuild`).
 */

import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const protobuf = require("protobufjs");

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(HERE, "..");
const REPO_ROOT = resolve(PKG_ROOT, "..");

/** Path of the one true proto, relative to the repo root. */
const PROTO_REL = "proto/plugin.proto";
const PROTO_PATH = join(REPO_ROOT, PROTO_REL);

const OUT_DIR = join(PKG_ROOT, "src", "generated");
const OUT_JSON = join(OUT_DIR, "descriptor.json");
const OUT_DESCRIPTOR_TS = join(OUT_DIR, "descriptor.ts");
const OUT_TS = join(OUT_DIR, "index.ts");

/** The gRPC package the SDK speaks. Everything lives under `package astra;`. */
const PACKAGE = "astra";

function fail(message) {
  console.error(`gen-descriptor: ${message}`);
  process.exit(1);
}

let protoSource;
try {
  protoSource = readFileSync(PROTO_PATH);
} catch (err) {
  fail(
    `cannot read ${PROTO_REL} at ${PROTO_PATH} (${err.code ?? err.message}).\n` +
      `  The TypeScript SDK is generated from the repo's canonical proto and cannot be\n` +
      `  built outside a checkout of AstraPlugins. There is deliberately no fallback copy:\n` +
      `  a stale second copy is the bug this generator exists to prevent.`
  );
}

const root = protobuf.loadSync(PROTO_PATH);
const descriptor = root.toJSON();

const pkg = descriptor.nested?.[PACKAGE]?.nested;
if (!pkg) fail(`${PROTO_REL} declares no \`package ${PACKAGE};\` namespace`);

/** service name -> declared method names, in declaration order. */
const serviceMethods = {};
for (const [name, node] of Object.entries(pkg)) {
  if (node && typeof node === "object" && node.methods) {
    serviceMethods[name] = Object.keys(node.methods);
  }
}
if (Object.keys(serviceMethods).length === 0) {
  fail(`${PROTO_REL} declares no services under \`${PACKAGE}\``);
}
for (const required of ["PluginHostService", "PluginCapabilityService"]) {
  if (!serviceMethods[required]) fail(`${PROTO_REL} is missing \`service ${required}\``);
}

/**
 * Every `reserved "name";` in the proto, keyed by the dotted path of the
 * message that declares it.
 *
 * A reserved name is a spelling a live daemon still associates with the OLD
 * field. `src/reserved.ts` asserts at startup that none of them has come back
 * as a live field — see the comment there for why that is the drift worth
 * catching rather than a curiosity.
 */
function collectReserved(nested, prefix, out) {
  for (const [name, node] of Object.entries(nested ?? {})) {
    if (!node || typeof node !== "object") continue;
    const path = prefix ? `${prefix}.${name}` : name;
    const names = (node.reserved ?? []).filter((r) => typeof r === "string");
    if (names.length > 0) out[path] = names;
    collectReserved(node.nested, path, out);
  }
  return out;
}

const reservedNames = collectReserved(descriptor.nested, "", {});

const protoSha256 = createHash("sha256").update(protoSource).digest("hex");

const BANNER = `/**
 * AUTO-GENERATED — DO NOT EDIT.
 *
 * Produced by \`tools/gen-descriptor.mjs\` from \`${PROTO_REL}\`.
 * Regenerate with \`npm run generate\`; \`npm run build\` does it for you.
 */`;

function unionType(typeName, doc, methods) {
  const members = methods.map((m) => `  | ${JSON.stringify(m)}`).join("\n");
  return `/** ${doc} */\nexport type ${typeName} =\n${members};\n`;
}

const serviceMethodEntries = Object.entries(serviceMethods)
  .map(([name, methods]) => {
    const list = methods.map((m) => JSON.stringify(m)).join(", ");
    return `  ${name}: [${list}],`;
  })
  .join("\n");

const reservedEntries = Object.entries(reservedNames)
  .map(([path, names]) => `  ${JSON.stringify(path)}: [${names.map((n) => JSON.stringify(n)).join(", ")}],`)
  .join("\n");

const ts = `${BANNER}

import { descriptorJson } from "./descriptor.js";

/**
 * A protobuf.js JSON namespace (\`protobuf.Root#toJSON()\`), narrowed to the one
 * property \`@grpc/proto-loader\`'s \`fromJSON()\` needs. Kept structural so the
 * SDK carries no runtime dependency on protobufjs' type declarations.
 */
export interface ProtoDescriptorJson {
  nested: Record<string, unknown>;
}

/** The compiled protocol descriptor. Load it with \`protoLoader.fromJSON()\`. */
export const descriptor: ProtoDescriptorJson = descriptorJson as ProtoDescriptorJson;

/**
 * \`reserved "name";\` declarations, keyed by the message that owns them.
 *
 * Checked at startup by \`src/reserved.ts\`: a reserved name that comes back as a
 * live field is a wire meaning colliding with the one a daemon in the field
 * still remembers.
 */
export const RESERVED_FIELD_NAMES: Readonly<Record<string, readonly string[]>> = {
${reservedEntries}
};

/** Repo-relative path of the proto this descriptor was generated from. */
export const PROTO_SOURCE = ${JSON.stringify(PROTO_REL)};

/** SHA-256 of that proto file, so a drifted descriptor is detectable in CI. */
export const PROTO_SHA256 = ${JSON.stringify(protoSha256)};

/** The protobuf package every Astra service lives in. */
export const PROTO_PACKAGE = ${JSON.stringify(PACKAGE)};

/**
 * Every service in the descriptor and the methods it declares, in declaration
 * order. The startup contract check in \`service-contract.ts\` compares handler
 * maps against this.
 */
export const SERVICE_METHODS = {
${serviceMethodEntries}
} as const satisfies Record<string, readonly string[]>;

/** Name of a service declared by \`${PROTO_REL}\`. */
export type ServiceName = keyof typeof SERVICE_METHODS;

${unionType(
  "PluginCapabilityMethod",
  "Every RPC the daemon may call on a plugin. A plugin must handle all of them.",
  serviceMethods.PluginCapabilityService
)}
${unionType(
  "PluginHostMethod",
  "Every RPC a plugin may call on the daemon.",
  serviceMethods.PluginHostService
)}`;

/**
 * The descriptor as a TypeScript module, not as a JSON import.
 *
 * `import x from "./descriptor.json"` compiles to a `require()` under CommonJS
 * and to a bare `import` under ESM — and Node's ESM loader refuses a JSON
 * specifier without an import attribute, so the dual-format build (task 5.8)
 * would ship an `import` that throws `ERR_IMPORT_ATTRIBUTE_MISSING` on first
 * use. A `.ts` module is the same bytes with no loader opinion attached.
 *
 * `descriptor.json` is still written, still shipped, and asserted byte-equal to
 * this module by `tools/contract.test.mjs` — it is what the repo's proto checks
 * and any non-TypeScript tool read.
 */
const descriptorTs = `${BANNER}

/** The protocol descriptor, as protobuf.Root#toJSON() produced it. */
export const descriptorJson: { nested: Record<string, unknown> } = ${JSON.stringify(
  descriptor,
  null,
  2
)};
`;

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(OUT_JSON, `${JSON.stringify(descriptor, null, 2)}\n`);
writeFileSync(OUT_DESCRIPTOR_TS, descriptorTs);
writeFileSync(OUT_TS, ts);

const serviceCount = Object.keys(serviceMethods).length;
const methodCount = Object.values(serviceMethods).reduce((n, m) => n + m.length, 0);
console.log(
  `gen-descriptor: ${PROTO_REL} (sha256 ${protoSha256.slice(0, 12)}…) -> ` +
    `src/generated/ — ${serviceCount} services, ${methodCount} methods`
);
