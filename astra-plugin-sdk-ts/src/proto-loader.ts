/**
 * Loads the Astra protocol from the descriptor generated at build time by
 * `tools/gen-descriptor.mjs` out of the repo's canonical `proto/plugin.proto`.
 *
 * There is no `.proto` text in this package's source and nothing is written to
 * disk at import time. The previous implementation embedded the protocol as an
 * inline template string, wrote it to `os.tmpdir()` and loaded it back — which
 * both drifted from the real proto and made the SDK unusable anywhere the temp
 * directory is read-only.
 */

import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import { descriptor, PROTO_PACKAGE, PROTO_SOURCE } from "./generated";
import { ProtoContractError } from "./service-contract";

/**
 * Field naming on the wire objects. `keepCase: false` means every message field
 * is lowerCamelCase in TypeScript (`config_fields` -> `configFields`); all three
 * SDKs' handlers depend on this.
 */
const LOAD_OPTIONS: protoLoader.Options = {
  keepCase: false,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
};

const packageDefinition = protoLoader.fromJSON(
  descriptor as unknown as Parameters<typeof protoLoader.fromJSON>[0],
  LOAD_OPTIONS
);

const protoDescriptor = grpc.loadPackageDefinition(packageDefinition) as unknown as Record<
  string,
  Record<string, unknown>
>;

const pkg = protoDescriptor[PROTO_PACKAGE];
if (!pkg) {
  throw new ProtoContractError(
    `generated descriptor has no \`${PROTO_PACKAGE}\` package — regenerate it with \`npm run generate\``
  );
}

/** Every service declared by `proto/plugin.proto`, under `package astra`. */
export const astraProto = pkg as Record<string, grpc.ServiceClientConstructor>;

/**
 * Look up a service constructor by name.
 *
 * @throws {ProtoContractError} naming the service and the source proto, rather
 *   than letting `new undefined(...)` surface as a bare `TypeError`.
 */
export function service(name: string): grpc.ServiceClientConstructor {
  const ctor = astraProto[name];
  if (typeof ctor !== "function") {
    throw new ProtoContractError(
      `${PROTO_SOURCE} declares no \`service ${name}\` under package \`${PROTO_PACKAGE}\`. ` +
        `Regenerate the descriptor with \`npm run generate\`.`
    );
  }
  return ctor;
}

export { packageDefinition };
