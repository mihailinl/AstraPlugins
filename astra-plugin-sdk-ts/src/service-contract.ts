// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Startup contract checks between a handler map and the compiled descriptor.
 *
 * grpc-js is silent about both halves of this mismatch: `Server#addService`
 * ignores implementation keys that the service definition does not know, and
 * installs an `UNIMPLEMENTED` stub for definition methods the implementation
 * does not provide. That is how `TtsGetConfigFields`, `SttGetConfigFields` and
 * `OnLanguageChanged` were registered against a stale inline descriptor for
 * three releases without a single warning, and how `CallFromUi` stayed
 * unimplemented. Both halves are checked here, in-process, before the server
 * binds — a typo is a crash on the plugin's first line of output, not an
 * `UNIMPLEMENTED` on a user's machine.
 */

import * as grpc from "@grpc/grpc-js";

/** Raised when a handler map and the generated descriptor disagree. */
export class ProtoContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProtoContractError";
  }
}

/** Handler map as accepted by `grpc.Server#addService`. */
export type HandlerMap = Record<string, grpc.UntypedHandleCall>;

/**
 * Every name `addService` would accept for `method` — the name as declared in
 * the proto, plus the lowerCamelCase alias grpc-js falls back to.
 */
function acceptedNames(method: string, def: grpc.MethodDefinition<unknown, unknown>): string[] {
  const original = (def as { originalName?: string }).originalName;
  return original && original !== method ? [method, original] : [method];
}

/**
 * Assert that `handlers` implements exactly `serviceDef` — no missing method,
 * no key the descriptor does not know.
 *
 * @throws {ProtoContractError} naming the offending method.
 */
export function assertServiceContract(
  serviceName: string,
  serviceDef: grpc.ServiceDefinition,
  handlers: HandlerMap
): void {
  const known = new Set<string>();
  const missing: string[] = [];

  for (const [method, def] of Object.entries(serviceDef)) {
    const names = acceptedNames(method, def as grpc.MethodDefinition<unknown, unknown>);
    for (const name of names) known.add(name);
    if (!names.some((name) => typeof handlers[name] === "function")) missing.push(method);
  }

  const unknown = Object.keys(handlers).filter((key) => !known.has(key));

  if (missing.length === 0 && unknown.length === 0) return;

  const problems: string[] = [];
  if (unknown.length > 0) {
    problems.push(
      `  no such method in the descriptor: ${unknown.join(", ")}\n` +
        `    grpc-js would drop these handlers silently. Check the spelling against\n` +
        `    proto/plugin.proto, or run \`npm run generate\` if the proto has changed.`
    );
  }
  if (missing.length > 0) {
    problems.push(
      `  no handler registered for: ${missing.join(", ")}\n` +
        `    grpc-js would answer these with UNIMPLEMENTED. Add an entry to the\n` +
        `    handler map for every method ${serviceName} declares.`
    );
  }

  throw new ProtoContractError(
    `${serviceName} handler map does not match proto/plugin.proto:\n${problems.join("\n")}`
  );
}

/**
 * `assertServiceContract` followed by `server.addService`. Use this instead of
 * calling `addService` directly so the check cannot be forgotten.
 */
export function addServiceChecked(
  server: grpc.Server,
  serviceName: string,
  serviceDef: grpc.ServiceDefinition,
  handlers: HandlerMap
): void {
  assertServiceContract(serviceName, serviceDef, handlers);
  server.addService(serviceDef, handlers as grpc.UntypedServiceImplementation);
}

/**
 * Assert that a generated client stub really exposes `methods`.
 *
 * The mirror image of the server-side check, and the one that used to bite
 * hardest: `DaemonClient` called `SubmitUserMessage`, `RespondToConfirmation`
 * and `ClearConversation` on a `ChatService` stub built from an inline
 * descriptor that predated the event-sourcing migration, so `client[method]`
 * was `undefined` and the plugin died with a bare `TypeError` mid-conversation.
 *
 * @throws {ProtoContractError} naming the offending method.
 */
export function assertClientContract(
  serviceName: string,
  client: object,
  methods: readonly string[]
): void {
  const missing = methods.filter(
    (method) => typeof (client as Record<string, unknown>)[method] !== "function"
  );
  if (missing.length === 0) return;

  throw new ProtoContractError(
    `${serviceName} stub is missing ${missing.length} method(s) the SDK calls: ` +
      `${missing.join(", ")}.\n` +
      `  The generated descriptor does not declare them. Regenerate it with\n` +
      `  \`npm run generate\`, and check that proto/plugin.proto is in sync with the daemon.`
  );
}
