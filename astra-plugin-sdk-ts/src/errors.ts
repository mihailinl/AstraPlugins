// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * The plugin error taxonomy — eight ways a handler can fail (production plan §5.2).
 *
 * # Why
 *
 * A tool that fails because the user never pasted an API key is not the same
 * event as a tool that fails because the model sent nonsense, and neither is the
 * same as the remote service being down. All three used to arrive at the daemon
 * as one `string error`, and the UI could do nothing with any of them but print
 * it. Each failure now carries a code the daemon can act on, plus the three
 * pieces of data that make a failure actionable rather than merely legible:
 *
 * - `configField` — which config key is missing; the UI deep-links to it
 * - `retryAfterMs` — how long to wait, so the AI loop backs off instead of
 *   hammering a rate limiter
 * - `docUrl` — where the author documented this failure
 *
 * # In-band, not a transport error
 *
 * A failed tool call is *data the AI loop must read*: "you have no API key
 * configured" is what the model needs in order to tell the user what to do. So
 * `CallTool` still answers `success: false` with the detail attached, and gRPC
 * `status` stays reserved for the call never reaching the handler.
 * `grpcStatus()` gives the fixed mapping for the streaming hooks, which have no
 * in-band failure slot at all.
 *
 * # Both halves on the wire
 *
 * Every response the SDK fills in from one of these carries the legacy
 * `error` string *and* `errorDetail`. A daemon that predates the structured
 * half drops the field and still shows a sentence; a current one gets the
 * machine-readable code. There is no negotiation to get wrong.
 *
 * # Idiom
 *
 * TypeScript gets classes that narrow. `code` is a string literal type on each
 * subclass, so a `switch` over `err.code` narrows to the subclass and reaches
 * `err.configField` with no cast — and `instanceof` works for people who prefer
 * it. The Rust SDK gets an enum and `?`; Python gets exceptions. The three are
 * the same eight variants with the same wire strings.
 *
 * @example
 * ```typescript
 * import { NotConfigured, RateLimited } from "astra-plugin-sdk";
 *
 * async callTool(name: string, argumentsJson: string) {
 *   if (!this.config.apiKey) throw new NotConfigured("api_key");
 *   if (this.overBudget()) throw new RateLimited({ retryAfterMs: 30_000 });
 *   ...
 * }
 * ```
 *
 * The SDK catches whatever a handler throws, so a plugin that never imports this
 * module keeps exactly the behaviour it had — the throw becomes `INTERNAL`.
 */

import * as grpc from "@grpc/grpc-js";
import { descriptor, PROTO_PACKAGE } from "./generated/index.js";

/** The eight codes. Identical strings in all three SDKs. */
export type PluginErrorCode =
  | "BAD_ARGUMENTS"
  | "NOT_FOUND"
  | "NOT_CONFIGURED"
  | "UNAUTHORIZED"
  | "RATE_LIMITED"
  | "UNAVAILABLE"
  | "TIMEOUT"
  | "INTERNAL";

/**
 * The structured half, shaped exactly like the proto message.
 *
 * `code` is the proto enum's *name* because the descriptor is loaded with
 * `enums: String` — `PLUGIN_ERROR_NOT_CONFIGURED`, not `6`.
 */
export interface PluginErrorDetail {
  code: string;
  message: string;
  hint: string;
  configField: string;
  retryAfterMs: number;
  docUrl: string;
}

/** Options every error accepts. */
export interface PluginErrorOptions {
  /** One sentence, for a human and for the model. */
  message?: string;
  /** Config key to deep-link to. Meaningful for `NOT_CONFIGURED`. */
  configField?: string;
  /** Wait this long before retrying. Meaningful for `RATE_LIMITED`. */
  retryAfterMs?: number;
  /** A page documenting this failure. Rendered as a link. */
  docUrl?: string;
}

/** Transport mapping, fixed. See `grpcStatus`. */
const GRPC_STATUS: Record<PluginErrorCode, grpc.status> = {
  BAD_ARGUMENTS: grpc.status.INVALID_ARGUMENT,
  NOT_FOUND: grpc.status.NOT_FOUND,
  NOT_CONFIGURED: grpc.status.FAILED_PRECONDITION,
  UNAUTHORIZED: grpc.status.PERMISSION_DENIED,
  RATE_LIMITED: grpc.status.RESOURCE_EXHAUSTED,
  UNAVAILABLE: grpc.status.UNAVAILABLE,
  TIMEOUT: grpc.status.DEADLINE_EXCEEDED,
  INTERNAL: grpc.status.INTERNAL,
};

/**
 * The proto enum variant name for a code, resolved against the descriptor this
 * build was generated from.
 *
 * Resolved rather than hard-coded for the same reason the Python SDK resolves
 * it: the taxonomy's codes (4-11) share `PluginErrorCode` with the registration
 * refusals (1-3), so a hard-coded `"PLUGIN_ERROR_" + code` would keep compiling
 * against a descriptor that has the message and none of the eight variants, and
 * put a name on the wire that protobuf then serialises as 0. Resolving it means
 * the mismatch is visible here (`structuredErrorsSupported()` answers false) and
 * only the legacy string goes out — which is what an older daemon sees anyway.
 */
function resolveEnumNames(): Record<PluginErrorCode, string> | null {
  const nested = (descriptor.nested as Record<string, { nested?: Record<string, unknown> }>)[
    PROTO_PACKAGE
  ]?.nested;
  const enumType = nested?.["PluginErrorCode"] as { values?: Record<string, number> } | undefined;
  const values = enumType?.values;
  if (!values) return null;

  const out = {} as Record<PluginErrorCode, string>;
  for (const code of Object.keys(GRPC_STATUS) as PluginErrorCode[]) {
    const hit = Object.keys(values).find((name) => name.endsWith(code));
    if (!hit) return null;
    out[code] = hit;
  }
  return out;
}

const ENUM_NAMES = resolveEnumNames();

/**
 * Whether the descriptor this build carries can express the structured half.
 *
 * A plugin never needs to ask — the SDK attaches whatever the descriptor has.
 * Exported so the conformance harness can assert on it rather than inferring it
 * from an empty field.
 */
export function structuredErrorsSupported(): boolean {
  return ENUM_NAMES !== null;
}

/**
 * Base of the eight. `catch (e) { if (e instanceof PluginError) … }` catches
 * every taxonomy failure; `switch (e.code)` narrows to the exact one.
 */
export abstract class PluginError extends Error {
  /** The stable code. A literal type on each subclass, which is what narrows. */
  abstract readonly code: PluginErrorCode;

  /** Config key this failure points at, or `""`. A deep-link target. */
  readonly configField: string;
  /** How long to wait before retrying, or `0` for "not stated". */
  readonly retryAfterMs: number;
  /** A page documenting this failure, or `""`. */
  readonly docUrl: string;

  constructor(options: PluginErrorOptions = {}, defaultMessage = "The plugin failed") {
    super(options.message || defaultMessage);
    // `Error` breaks the prototype chain under ES5-targeted downlevelling, and
    // `instanceof` silently stops working. Restoring it here is the standard
    // fix and costs one line per construction.
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = new.target.name;
    this.configField = options.configField ?? "";
    this.retryAfterMs = options.retryAfterMs ?? 0;
    this.docUrl = options.docUrl ?? "";
  }

  /**
   * What to DO about it, or `""` when there is nothing useful to say.
   *
   * Only two of the eight can say anything an actor could follow; inventing
   * sentences for the rest would be noise in a log pane.
   */
  hint(): string {
    if (this.configField) {
      return `Set \`${this.configField}\` in this plugin's settings, then try again.`;
    }
    if (this.retryAfterMs > 0) {
      return `Retry in ${Math.max(1, Math.floor(this.retryAfterMs / 1000))} s.`;
    }
    return "";
  }

  /**
   * The legacy `error` string — the whole signal on an older daemon.
   *
   * `CODE: message (hint)`, the same shape the Rust SDK's `wire_string` and the
   * Python SDK's `to_error_string` produce. The AI loop reads this string, and
   * what the model sees must not depend on which language the plugin is in.
   */
  toErrorString(): string {
    const hint = this.hint();
    return hint ? `${this.code}: ${this.message} (${hint})` : `${this.code}: ${this.message}`;
  }

  /** The structured half, or `undefined` when this descriptor cannot carry it. */
  toDetail(): PluginErrorDetail | undefined {
    if (!ENUM_NAMES) return undefined;
    return {
      code: ENUM_NAMES[this.code],
      message: this.message,
      hint: this.hint(),
      configField: this.configField,
      retryAfterMs: this.retryAfterMs,
      docUrl: this.docUrl,
    };
  }

  /**
   * The failure as a `{ success, result, error, errorDetail }` wire object —
   * the shape `PluginCallToolResponse` and `PluginExecuteActionResponse` share.
   */
  toResponse(): {
    success: false;
    result: string;
    error: string;
    errorDetail?: PluginErrorDetail;
  } {
    return {
      success: false,
      result: "",
      error: this.toErrorString(),
      errorDetail: this.toDetail(),
    };
  }

  /**
   * The transport status for this code.
   *
   * Use it only where the hook has no in-band failure slot — the streaming
   * hooks. On a unary hook it hides the failure from the AI loop, which is the
   * reader that most needs it.
   */
  grpcStatus(): grpc.status {
    return GRPC_STATUS[this.code];
  }

  /** This error as a `ServiceError`-shaped object for `callback(err)`. */
  toServiceError(): { code: grpc.status; details: string } {
    return { code: this.grpcStatus(), details: this.toErrorString() };
  }

  /**
   * Adopt anything a handler threw.
   *
   * Taxonomy errors pass through. A `TypeError`/`SyntaxError` — which is what
   * `JSON.parse` throws on the model's arguments — really is `BAD_ARGUMENTS`,
   * and calling it `INTERNAL` sends the reader to the wrong half of the system.
   * Everything else is `INTERNAL`, the honest answer for an unclassified throw.
   */
  static from(thrown: unknown): PluginError {
    if (thrown instanceof PluginError) return thrown;
    if (thrown instanceof SyntaxError || thrown instanceof TypeError) {
      return new BadArguments({ message: thrown.message });
    }
    if (thrown instanceof Error) return new InternalError({ message: thrown.message });
    return new InternalError({ message: String(thrown) });
  }
}

/** The arguments did not parse, or violate the tool's contract. Retry differently. */
export class BadArguments extends PluginError {
  readonly code = "BAD_ARGUMENTS" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Invalid arguments");
  }
}

/** The thing named by the arguments does not exist. */
export class NotFound extends PluginError {
  readonly code = "NOT_FOUND" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Not found");
  }
}

/**
 * A required setting is missing or empty.
 *
 * The one variant whose first argument is the field: `new NotConfigured("api_key")`
 * is the whole call, and the field is what lets the UI link straight at the
 * input the user has to fill in.
 */
export class NotConfigured extends PluginError {
  readonly code = "NOT_CONFIGURED" as const;
  constructor(configField: string, options: PluginErrorOptions = {}) {
    super(
      {
        ...options,
        configField,
        // The same sentence the Rust and Python SDKs produce.
        message: options.message || `required setting \`${configField}\` is not set`,
      },
      "Not configured"
    );
  }
}

/**
 * Credentials were present and refused. Distinct from `NOT_CONFIGURED`: a value
 * IS there, it is simply not accepted, and the user's next action differs.
 */
export class Unauthorized extends PluginError {
  readonly code = "UNAUTHORIZED" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Unauthorized");
  }
}

/** A quota was exhausted. Set `retryAfterMs` when the limit said when. */
export class RateLimited extends PluginError {
  readonly code = "RATE_LIMITED" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Rate limited");
  }
}

/** A dependency is down. Transient by assumption; a later call may succeed. */
export class Unavailable extends PluginError {
  readonly code = "UNAVAILABLE" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Temporarily unavailable");
  }
}

/** The plugin ran out of time waiting for something. */
export class Timeout extends PluginError {
  readonly code = "TIMEOUT" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "The operation timed out");
  }
}

/**
 * A bug in the plugin. Named `InternalError` rather than `Internal` because a
 * bare `Internal` in a `catch` reads like a namespace, not an error.
 */
export class InternalError extends PluginError {
  readonly code = "INTERNAL" as const;
  constructor(options: PluginErrorOptions = {}) {
    super(options, "Internal plugin error");
  }
}

/**
 * The discriminated union of every taxonomy error.
 *
 * Annotate a `catch` with this (or narrow to it with `instanceof PluginError`)
 * and `switch (err.code)` narrows each arm to the concrete class:
 *
 * ```typescript
 * function explain(err: AnyPluginError): string {
 *   switch (err.code) {
 *     case "NOT_CONFIGURED": return `open settings → ${err.configField}`;
 *     case "RATE_LIMITED":   return `wait ${err.retryAfterMs} ms`;
 *     default:               return err.message;
 *   }
 * }
 * ```
 */
export type AnyPluginError =
  | BadArguments
  | NotFound
  | NotConfigured
  | Unauthorized
  | RateLimited
  | Unavailable
  | Timeout
  | InternalError;

/** `ToolError` is what §5.2 calls the tool-facing type; actions fail identically. */
export type ToolError = AnyPluginError;
/** Actions and tools fail for the same reasons, so this is the same type. */
export type ActionError = AnyPluginError;
