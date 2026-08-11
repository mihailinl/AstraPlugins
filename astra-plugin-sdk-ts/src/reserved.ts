/**
 * The startup assertion TypeScript needs and the other two SDKs do not.
 *
 * Rust gets a compile error when a generated name goes missing. Python gets an
 * `AttributeError`, late but loud, the first time the missing thing is touched.
 * TypeScript gets `undefined` — `stub.SubmitUserMessage` on a stale descriptor
 * is not an error, it is a value, and calling it is a bare `TypeError` thrown
 * from inside grpc-js in the middle of a conversation. That is how three
 * `PluginCapabilityService` handlers were registered against a descriptor that
 * did not declare them and were silently dropped for a whole release.
 *
 * `assertNoReservedNames()` runs before the server binds and answers three
 * questions the descriptor cannot answer by itself:
 *
 * 1. **Is every service and method the SDK generated actually reachable?**
 *    `SERVICE_METHODS` is read out of protobuf.js' JSON; the runtime stubs come
 *    from `@grpc/proto-loader` plus `loadPackageDefinition`. Two pipelines, one
 *    source — and it is the second that has dropped things before. A name that
 *    survives one and not the other is exactly the `undefined` above.
 *
 * 2. **Has a field the protocol `reserved` come back?** A `reserved` name is a
 *    field number and spelling that a live daemon still remembers meaning
 *    something else. `AiSettings.use_thinking` was replaced by the
 *    `reasoning_effort` scale; a descriptor that declares it again is one where
 *    a boolean and a seven-value enum are wearing the same name on the wire.
 *
 * 3. **Has a name Phase 1 deleted come back?** See {@link RETIRED_NAMES}.
 *
 * All three are drift in the same direction: the descriptor stopped being the
 * daemon's protocol, and nothing said so.
 */

import { astraProto } from "./proto-loader.js";
import {
  descriptor,
  PROTO_SOURCE,
  RESERVED_FIELD_NAMES,
  SERVICE_METHODS,
} from "./generated/index.js";
import { ProtoContractError } from "./service-contract.js";

/**
 * Names Phase 1 cut out of the plugin surface, which must not come back.
 *
 * `AuthService.RefreshToken` and its response were removed because the plugin
 * surface has no business carrying the daemon's own login refresh; the five
 * `VoiceService` LLM-match RPCs and their four messages were removed because
 * the daemon no longer has the feature. All eleven were verified absent from
 * `proto/plugin.proto` when this list was written.
 *
 * A name reappearing here means the slice was regenerated from an `astra.proto`
 * that predates the cut — the descriptor is then a *different protocol* from the
 * one the daemon serves, and every hook is suspect, not just this one. Cheaper
 * to say so in one line at startup than to debug it from a user's log.
 */
export const RETIRED_NAMES: readonly string[] = [
  "RefreshToken",
  "RefreshTokenResponse",
  "GetLlmMatchModels",
  "DownloadLlmMatchModel",
  "GetLlmMatchDownloadProgress",
  "CancelLlmMatchDownload",
  "DeleteLlmMatchModel",
  "LlmMatchModelInfoMsg",
  "LlmMatchModelsResponse",
  "DownloadLlmMatchModelRequest",
  "DeleteLlmMatchModelRequest",
];

/** One thing the descriptor got wrong, as a sentence. */
export interface DescriptorProblem {
  kind: "missing-service" | "missing-method" | "reserved-field" | "retired-name";
  where: string;
  detail: string;
}

/** A protobuf.js JSON node, as far as this walk cares. */
interface Node {
  nested?: Record<string, Node>;
  fields?: Record<string, unknown>;
  methods?: Record<string, unknown>;
  reserved?: (string | number[])[];
}

/** Walk every namespace node in the descriptor, yielding `dotted.path` -> node. */
function* walk(nested: Record<string, Node> | undefined, prefix = ""): Generator<[string, Node]> {
  for (const [name, node] of Object.entries(nested ?? {})) {
    if (!node || typeof node !== "object") continue;
    const path = prefix ? `${prefix}.${name}` : name;
    yield [path, node];
    yield* walk(node.nested, path);
  }
}

/**
 * Every way the loaded descriptor disagrees with what this SDK was generated
 * for. Empty means it agrees.
 *
 * Separated from the throwing wrapper so a test can assert on the list rather
 * than on the wording of an exception.
 */
export function descriptorProblems(): DescriptorProblem[] {
  const problems: DescriptorProblem[] = [];

  // 1 — every generated name resolves to a real stub method.
  for (const [serviceName, methods] of Object.entries(SERVICE_METHODS)) {
    const ctor = astraProto[serviceName];
    if (typeof ctor !== "function") {
      problems.push({
        kind: "missing-service",
        where: serviceName,
        detail: `the descriptor declares \`service ${serviceName}\` but the loader produced no client for it`,
      });
      continue;
    }
    for (const method of methods) {
      if (typeof (ctor.prototype as Record<string, unknown>)[method] !== "function") {
        problems.push({
          kind: "missing-method",
          where: `${serviceName}.${method}`,
          detail:
            `\`${serviceName}.${method}\` is \`undefined\` on the loaded stub. Calling it would ` +
            `throw a bare TypeError from inside grpc-js`,
        });
      }
    }
  }

  // 2 — no message declares a field the protocol reserved.
  const nested = (descriptor as { nested?: Record<string, Node> }).nested;
  for (const [path, node] of walk(nested)) {
    const reservedHere = RESERVED_FIELD_NAMES[path];
    if (!reservedHere || !node.fields) continue;
    for (const name of reservedHere) {
      if (Object.prototype.hasOwnProperty.call(node.fields, name)) {
        problems.push({
          kind: "reserved-field",
          where: `${path}.${name}`,
          detail:
            `\`${name}\` is \`reserved\` in ${path} and the descriptor declares it as a live ` +
            `field. A daemon that still remembers the old meaning will read this wrong`,
        });
      }
    }
  }

  // 3 — no name Phase 1 retired has come back.
  const retired = new Set(RETIRED_NAMES);
  for (const [path, node] of walk(nested)) {
    const leaf = path.slice(path.lastIndexOf(".") + 1);
    if (retired.has(leaf)) {
      problems.push({
        kind: "retired-name",
        where: path,
        detail: `\`${leaf}\` was removed from the plugin surface in Phase 1 and is back`,
      });
    }
    for (const method of Object.keys(node.methods ?? {})) {
      if (retired.has(method)) {
        problems.push({
          kind: "retired-name",
          where: `${path}.${method}`,
          detail: `rpc \`${method}\` was removed from the plugin surface in Phase 1 and is back`,
        });
      }
    }
  }

  return problems;
}

/**
 * Throw unless the loaded descriptor is the protocol this SDK was built for.
 *
 * Called by `Plugin.run()` before the gRPC server binds, so the failure is the
 * plugin's first line of output rather than an `UNIMPLEMENTED` on a user's
 * machine three hooks later.
 *
 * @throws {ProtoContractError} listing every problem, not just the first.
 */
export function assertNoReservedNames(): void {
  const problems = descriptorProblems();
  if (problems.length === 0) return;
  const lines = problems.map((p) => `  ${p.where}: ${p.detail}.`).join("\n");
  throw new ProtoContractError(
    `the loaded protocol descriptor is not the one this SDK was generated for ` +
      `(${problems.length} problem(s)):\n${lines}\n` +
      `  Regenerate it from ${PROTO_SOURCE} with \`npm run generate\`, and check that the ` +
      `proto is in sync with the daemon.`
  );
}
