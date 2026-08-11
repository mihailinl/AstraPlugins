// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Authentication for the daemon → plugin direction.
 *
 * The plugin → daemon direction lives in `host-client.ts`: every host RPC after
 * `Register` carries an `x-session-token`. This is the mirror image — the guard
 * on the plugin's own `PluginCapabilityService`.
 *
 * SECURITY: that server listens on loopback TCP with an OS-assigned port and
 * used to accept anything that reached it. Loopback is not a boundary between
 * processes of the same user: any local process — including another installed
 * plugin, which the daemon's threat model explicitly treats as untrusted — can
 * scan for the port and call `OnConfigChanged` (repointing this plugin's API
 * base URL at an attacker-controlled host, after which it posts its real
 * credentials there), `CallTool` / `ExecuteAction` / `CallFromUi` (arbitrary
 * execution under this plugin's identity), or `Shutdown` (a one-RPC denial of
 * service).
 *
 * The secret needed to close that hole already existed: the daemon mints
 * `--auth-token` per spawn and passes it on argv, so it is shared by exactly the
 * daemon and this process. It was simply never checked on the way *in* — only
 * echoed once in the outbound `Register` body.
 *
 * The daemon now presents it on every call and says so, by setting
 * `ASTRA_PLUGIN_CAPABILITY_AUTH=require` in the plugin's environment. So a
 * plugin under a current daemon enforces without anyone configuring it. The
 * stages remain because enforcing unilaterally would break a plugin against a
 * daemon that does not send the header, and such a daemon has no way to announce
 * itself:
 *
 * | stage       | header absent         | header wrong |
 * |-------------|-----------------------|--------------|
 * | `warn`      | accepted, warned once | rejected     |
 * | `require`   | rejected              | rejected     |
 * | `off`       | accepted              | accepted     |
 *
 * `warn` is the default, and what an older daemon leaves a plugin in — the
 * variable's *absence* is the only signal such a daemon gives.
 */

import * as grpc from "@grpc/grpc-js";
import type { HandlerMap } from "./service-contract.js";

/**
 * Metadata header the plugin reads the daemon's copy of the spawn token from.
 * Must stay identical to the header the daemon attaches in
 * `astra-daemon/src/plugins/client.rs`.
 */
export const PLUGIN_TOKEN_HEADER = "x-plugin-token";

/**
 * How the daemon states the stage: `off`, `warn` or `require`. Set to `require`
 * on every spawn by `prepare_spawn` in `astra-daemon/src/plugins/instance.rs`;
 * absent under a daemon too old to send the header, which is what leaves a
 * plugin in `warn`. Overrides the value passed in code, which is what makes it
 * useful to both.
 */
export const CAPABILITY_AUTH_ENV = "ASTRA_PLUGIN_CAPABILITY_AUTH";

export type CapabilityAuthMode = "off" | "warn" | "require";

const SPELLINGS: Record<string, CapabilityAuthMode> = {
  off: "off",
  "0": "off",
  false: "off",
  warn: "warn",
  require: "require",
  "1": "require",
  true: "require",
};

/**
 * Resolve the stage from the environment.
 *
 * An unparseable value is a typo, not a request to weaken the check, so it warns
 * and keeps `fallback` rather than falling back to `off`.
 */
export function capabilityAuthMode(
  fallback: CapabilityAuthMode = "warn",
  env: NodeJS.ProcessEnv = process.env
): CapabilityAuthMode {
  const raw = env[CAPABILITY_AUTH_ENV];
  if (raw === undefined) return fallback;
  const mode = SPELLINGS[raw.trim().toLowerCase()];
  if (mode === undefined) {
    console.warn(
      `${CAPABILITY_AUTH_ENV}=${JSON.stringify(raw)} is not one of off|warn|require — ` +
        `keeping ${fallback}`
    );
    return fallback;
  }
  return mode;
}

/** A `ServiceError`-shaped rejection grpc-js turns into a gRPC status. */
function unauthenticated(details: string): grpc.ServiceError {
  return Object.assign(new Error(details), {
    code: grpc.status.UNAUTHENTICATED,
    details,
    metadata: new grpc.Metadata(),
  }) as grpc.ServiceError;
}

/** Constant-time-ish comparison: no early exit on the first differing byte. */
function secretsMatch(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/**
 * Wraps every handler in `handlers` with the spawn-token check.
 *
 * Returns the map unchanged when there is nothing to check — no `--auth-token`
 * (standalone, or `astra-plugin dev --standalone`), or the stage is `off`. A
 * plugin with no daemon must still be runnable.
 */
export function guardHandlers(
  handlers: HandlerMap,
  authToken: string,
  mode: CapabilityAuthMode = capabilityAuthMode()
): HandlerMap {
  if (!authToken || mode === "off") return handlers;

  // Accept-and-warn fires once, not once per RPC: the daemon calls into a plugin
  // constantly and a per-call warning would bury the log.
  let warned = false;

  /** `null` to let the call through, or the rejection to answer it with. */
  const verdict = (metadata: grpc.Metadata | undefined): grpc.ServiceError | null => {
    const presented = metadata?.get(PLUGIN_TOKEN_HEADER)[0];
    if (presented !== undefined) {
      // A binary header cannot be the token the daemon was given, so it is a
      // mismatch, not a decoding problem to report.
      const value = typeof presented === "string" ? presented : "";
      if (secretsMatch(value, authToken)) return null;
      // Deliberately says nothing about which part was wrong.
      return unauthenticated(
        "invalid plugin token — this RPC did not come from the daemon that spawned this plugin"
      );
    }
    if (mode === "require") {
      return unauthenticated(
        `missing ${PLUGIN_TOKEN_HEADER} — this plugin requires the daemon to ` +
          `authenticate capability calls`
      );
    }
    if (!warned) {
      warned = true;
      console.warn(
        `Capability call arrived without ${PLUGIN_TOKEN_HEADER}. This daemon predates ` +
          `bidirectional plugin auth, so any local process can reach this plugin's tools, ` +
          `config and shutdown. Accepting it for compatibility; set ` +
          `${CAPABILITY_AUTH_ENV}=require to refuse instead.`
      );
    }
    return null;
  };

  const guarded: HandlerMap = {};
  for (const [name, handler] of Object.entries(handlers)) {
    const inner = handler as (...args: unknown[]) => unknown;
    guarded[name] = function (this: unknown, ...args: unknown[]) {
      const call = args[0] as { metadata?: grpc.Metadata };
      const rejection = verdict(call?.metadata);
      if (rejection === null) return inner.apply(this, args);

      // Two shapes reach here. Unary and client-streaming handlers get a
      // callback and must not also touch the call; server-streaming and bidi
      // handlers report through the stream, whose constructor already installed
      // the 'error' listener that turns this into a status (grpc-js
      // `server-call.js`, `ServerWritableStreamImpl`/`ServerDuplexStreamImpl`).
      const last = args[args.length - 1];
      if (typeof last === "function") {
        (last as grpc.sendUnaryData<unknown>)(rejection, null);
      } else {
        (call as unknown as NodeJS.EventEmitter).emit("error", rejection);
      }
      return undefined;
    } as grpc.UntypedHandleCall;
  }
  return guarded;
}
