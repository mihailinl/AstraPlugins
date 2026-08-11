// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * The plugin wire-protocol handshake.
 *
 * Before this existed there was no version anywhere in either direction, so an
 * old plugin meeting a new daemon (or the reverse) failed at the first RPC one
 * side did not have — with an error that named neither the cause nor the fix.
 * Registration now carries an integer both ways, and the mismatch is decided
 * once, at the handshake, by {@link evaluateProtocol}.
 */

import type { RegisterResponse } from "./host-client.js";

/**
 * The wire-protocol generation this SDK speaks.
 *
 * One integer, in four places that must agree: here, `proto/PROTO_VERSION`
 * (`protocol=`), the `// protocol: N` header of the generated `plugin.proto`,
 * and the daemon's `PLUGIN_PROTOCOL_VERSION`. The Rust and Python SDKs carry
 * the same constant under the same name.
 */
export const PROTOCOL_VERSION = 1;

/**
 * The oldest daemon protocol this SDK will serve.
 *
 * The mirror image of the daemon's own floor. A daemon below this would have
 * the SDK calling host RPCs it does not implement, so the plugin says so once
 * and exits instead of running half-broken.
 *
 * **`0` is allowed on purpose, and that is not the same as having no floor.**
 * Protocol 1 *is* the pre-handshake plugin surface: Astra v0.1.0 — the only
 * released Astra — has a byte-identical `PluginHostService`, already carries
 * every plugin-facing field this SDK sends, and already issues a per-plugin
 * session token to *every* plugin (`host_service.rs`, `SECURITY(B1)`). It
 * simply predates the `protocol_version` field, and proto3 delivers an absent
 * field as `0`. A floor of 1 would therefore refuse the one daemon that can
 * serve this SDK perfectly, on the grounds that it never learned to say so.
 *
 * The capability this SDK genuinely needs is checked directly rather than
 * inferred from an integer: `host-client.ts` fails closed on an empty
 * `clientSessionToken` right after {@link evaluateProtocol}, because that — not
 * a version number — is what decides whether any host RPC can succeed.
 *
 * Raise this to 2 in the release where the SDK starts calling something
 * protocol 1 does not have. The `< floor` branch below and its sentence stay
 * live for exactly that day; the `floor` argument rehearses it now.
 */
export const MIN_SUPPORTED_DAEMON_PROTOCOL = 0;

/** Reported to the daemon for support triage only; never gates anything. */
export const SDK_NAME = "astra-plugin-sdk-ts";

/**
 * This package's own release, alongside {@link SDK_NAME}.
 *
 * A literal rather than a `require("../package.json")`: this file is compiled
 * to `dist/` and also read by bundlers, and a runtime file read that silently
 * yields `""` is worse than a constant a test pins. `tools/protocol.test.mjs`
 * asserts it equals `package.json`'s `version`, so the two cannot drift.
 */
export const SDK_VERSION = "0.5.0";

/**
 * Exit code for a protocol mismatch: `EX_CONFIG` from `sysexits.h`.
 *
 * Deliberately not 1. The daemon logs a plugin's exit code, and "the
 * configuration of this machine is wrong" is exactly the right category —
 * nothing about retrying, restarting or the plugin's own logic will change the
 * outcome until somebody installs a different build.
 */
export const EXIT_PROTOCOL_INCOMPATIBLE = 78;

/**
 * A handshake that cannot proceed. `message` is the one sentence the plugin
 * prints before exiting {@link EXIT_PROTOCOL_INCOMPATIBLE}.
 *
 * Its own class, not a `RegistrationError`: "your plugin is too old for this
 * Astra" has a different fix from "the daemon said no", and the runner has to
 * be able to tell them apart to choose the exit code.
 */
export class ProtocolMismatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProtocolMismatchError";
  }
}

/**
 * `PluginErrorCode.PLUGIN_ERROR_PROTOCOL_TOO_OLD`, as the descriptor loader
 * delivers it. `proto-loader` runs with `enums: String`, so an enum arrives as
 * its proto name; the numeric form is accepted too, so a future loader option
 * change cannot silently turn this check into a no-op.
 */
const PROTOCOL_TOO_OLD: ReadonlySet<string | number> = new Set([
  "PLUGIN_ERROR_PROTOCOL_TOO_OLD",
  1,
]);

/**
 * Decide whether this SDK can serve the daemon that just answered `Register`.
 *
 * Returns `null` to proceed, or the one sentence the plugin should print before
 * exiting {@link EXIT_PROTOCOL_INCOMPATIBLE}.
 *
 * Pure, so the rule is testable without a daemon and a socket. Two ways it can
 * fail, and they are not the same failure:
 *
 * - **The daemon refused us** for being too old. It told us its floor, so the
 *   sentence can name the number this plugin has to reach.
 * - **The daemon is older than this SDK's floor.** Nothing refused anything —
 *   it is the SDK that would start calling RPCs the daemon lacks. Stop before
 *   doing that.
 *
 * Anything else (a refusal for a bad auth token, an unknown plugin id) is not a
 * protocol matter and is left to the caller's ordinary error path.
 *
 * `floor` defaults to {@link MIN_SUPPORTED_DAEMON_PROTOCOL} and exists so a test
 * can ask the real question — "what does an SDK whose floor is 2 see from a
 * daemon that reports 0?" — without waiting for the release that raises the
 * shipped floor. The mirror of the daemon's own `check_protocol_against`.
 */
export function evaluateProtocol(
  response: RegisterResponse,
  floor: number = MIN_SUPPORTED_DAEMON_PROTOCOL
): string | null {
  const detail = response.errorDetail;
  if (detail && PROTOCOL_TOO_OLD.has(detail.code)) {
    // The daemon's own words first — it knows its floor, and it is the side
    // that decided. The hint is what the author acts on.
    let sentence =
      detail.message ||
      `This plugin speaks Astra plugin protocol ${PROTOCOL_VERSION}, which this Astra no ` +
        `longer accepts (it needs ${response.minSupportedProtocol} or newer).`;
    if (detail.hint) sentence = `${sentence} ${detail.hint}`;
    return sentence;
  }

  // `?? 0` and not `!`: a daemon that predates the field sends nothing, and
  // `undefined < 2` is false — which would wave through exactly the daemon a
  // raised floor exists to catch. `0` is the honest reading of an absent proto3
  // field, and it is what the "did not report" sentence is written for.
  const daemonProtocol = response.protocolVersion ?? 0;
  if (daemonProtocol < floor) {
    const reported =
      daemonProtocol === 0
        ? "did not report a protocol version at all"
        : `speaks protocol ${daemonProtocol}`;
    return (
      `This Astra ${reported}, and this plugin needs protocol ${floor} or newer — update ` +
      `Astra, or install a build of this plugin made for the Astra you have.`
    );
  }

  return null;
}
