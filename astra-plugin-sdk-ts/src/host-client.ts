// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * HostClient — plugin-side gRPC client for `astra.PluginHostService`.
 *
 * SECURITY: the daemon exempts exactly one path from authentication,
 * `/astra.PluginHostService/Register`
 * (`astra-daemon/src/server/auth_interceptor.rs`, `EXEMPT_PATHS`). Register
 * proves the plugin with the spawn-time `auth_token` carried in the request
 * body and hands back a per-plugin `client_session_token`; every other host RPC
 * must present that token as the `x-session-token` metadata header or the
 * daemon answers `unauthenticated`.
 *
 * So the class is built around the token rather than around the connection:
 * the constructor is private and the only way to obtain a `HostClient` is
 * `HostClient.register()`, which performs the bootstrap call itself and returns
 * a client that already holds the token. There is no reachable state in which a
 * host RPC can be issued without one.
 */

import * as grpc from "@grpc/grpc-js";
import { service } from "./proto-loader.js";
import { assertClientContract } from "./service-contract.js";
import {
  evaluateProtocol,
  ProtocolMismatchError,
  PROTOCOL_VERSION,
  SDK_NAME,
  SDK_VERSION,
} from "./protocol.js";
import type { ChatChunk, ThemeContribution } from "./types.js";
import type { DaemonInfo, Host } from "./host.js";
import { SESSION_TOKEN_HEADER, X_ASTRA_CAUSE } from "./generated/wire.js";
import { currentCause } from "./causality.js";

/** Re-exported so `import { DaemonInfo } from "astra-plugin-sdk"` keeps working. */
export type { DaemonInfo } from "./host.js";

/**
 * A gRPC readable stream as an `AsyncIterable`.
 *
 * grpc-js streams are Node `Readable`s, which are already async-iterable — but
 * a stream that ends in `error` throws out of the `for await` only if the
 * rejection is wired up, and the plain `Readable` iterator swallows a
 * `ServiceError` emitted after the last `data`. Adapting it explicitly is four
 * lines and makes the failure land where the author is looking.
 */
function streamToAsyncIterable<T>(stream: grpc.ClientReadableStream<T>): AsyncIterable<T> {
  const queue: T[] = [];
  let done = false;
  let failure: Error | null = null;
  let wake: (() => void) | null = null;
  const signal = () => {
    const w = wake;
    wake = null;
    w?.();
  };

  stream.on("data", (item: T) => {
    queue.push(item);
    signal();
  });
  stream.on("error", (err: Error) => {
    failure = err;
    done = true;
    signal();
  });
  stream.on("end", () => {
    done = true;
    signal();
  });

  return {
    async *[Symbol.asyncIterator]() {
      for (;;) {
        while (queue.length === 0 && !done) {
          await new Promise<void>((resolve) => {
            wake = resolve;
          });
        }
        while (queue.length > 0) yield queue.shift()!;
        if (failure) throw failure;
        if (done) return;
      }
    },
  };
}

/** Every host RPC this client issues. Verified against the descriptor at connect time. */
const REQUIRED_METHODS = [
  "Register",
  "SubscribeEvents",
  "FireTrigger",
  "GetPluginSelfConfig",
  "PluginLog",
  "GetDaemonInfo",
  "SetVariable",
  "PushToUi",
  "SendChatMessage",
  "SetThemeContribution",
] as const;

/** Structured detail for a refused registration. Present only when `success` is false. */
export interface RegisterErrorDetail {
  /** `PluginErrorCode`. A proto name (`enums: String`), or a number. */
  code: string | number;
  /** What went wrong. One sentence. */
  message: string;
  /** What to DO about it. One sentence. */
  hint: string;
}

/** The daemon's answer to `Register`. */
export interface RegisterResponse {
  success: boolean;
  error: string;
  /** Plugin's persisted config, as JSON. */
  configJson: string;
  daemonVersion: string;
  /** Per-plugin session token. Required on every subsequent host RPC. */
  clientSessionToken: string;
  /** Daemon UI language ("en", "ru", "uk", …). */
  language: string;
  /**
   * The protocol generation this daemon speaks, and the oldest it accepts.
   * Optional because a daemon that predates the handshake sends neither — which
   * is itself the signal that it is too old (see `evaluateProtocol`).
   */
  protocolVersion?: number;
  minSupportedProtocol?: number;
  errorDetail?: RegisterErrorDetail;
}

/** Registration was rejected, or produced no usable session. */
export class RegistrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RegistrationError";
  }
}

/**
 * The real daemon.
 *
 * `implements Host` is load-bearing, not decoration: it is the compile error
 * that fires if a host RPC is added here and not to the interface the test
 * harness's `RecordingHost` implements — which is how a hook gets a binding
 * that no test can reach.
 */
export class HostClient implements Host {
  private constructor(
    private readonly stub: grpc.Client & Record<string, Function>,
    private readonly pluginId: string,
    /** Carries `x-session-token`; attached to every call but `Register`. */
    private readonly metadata: grpc.Metadata
  ) {}

  /**
   * Connect, register, and return an authenticated client.
   *
   * The bootstrap `Register` call is the only one made without a session token.
   * Rejection — or a daemon that hands back no token — throws rather than
   * yielding a client whose every call would fail `unauthenticated`.
   */
  static async register(opts: {
    daemonAddr: string;
    pluginId: string;
    port: number;
    capabilities: string[];
    authToken?: string;
  }): Promise<{ host: HostClient; response: RegisterResponse }> {
    const PluginHostService = service("PluginHostService");
    const stub = new PluginHostService(
      opts.daemonAddr,
      grpc.credentials.createInsecure()
    ) as grpc.Client & Record<string, Function>;
    assertClientContract("PluginHostService", stub, REQUIRED_METHODS);

    let response: RegisterResponse;
    try {
      response = await new Promise<RegisterResponse>((resolve, reject) => {
        stub.Register(
          {
            pluginId: opts.pluginId,
            port: opts.port,
            capabilities: opts.capabilities,
            authToken: opts.authToken ?? "",
            // The handshake (production plan 1.3). Without this on the wire the
            // daemon cannot tell an old plugin from a new one, and its protocol
            // floor stops meaning anything.
            protocolVersion: PROTOCOL_VERSION,
            sdkName: SDK_NAME,
            sdkVersion: SDK_VERSION,
          },
          (err: grpc.ServiceError | null, res: RegisterResponse) => {
            if (err) reject(err);
            else resolve(res);
          }
        );
      });
    } catch (err) {
      stub.close();
      throw err;
    }

    // The protocol verdict comes BEFORE the generic refusal below: "your plugin
    // is too old for this Astra" is a different problem from "the daemon said
    // no", it has a different fix, and it gets its own exit code
    // (`EXIT_PROTOCOL_INCOMPATIBLE`) rather than being flattened into a message
    // the author has to interpret.
    const mismatch = evaluateProtocol(response);
    if (mismatch) {
      stub.close();
      throw new ProtocolMismatchError(mismatch);
    }

    if (!response.success) {
      stub.close();
      throw new RegistrationError(response.error || "daemon rejected the registration");
    }
    if (!response.clientSessionToken) {
      stub.close();
      throw new RegistrationError(
        "daemon returned an empty client_session_token — every host RPC would be rejected " +
          "as `unauthenticated`. This daemon predates the per-plugin session token; upgrade Astra."
      );
    }

    const metadata = new grpc.Metadata();
    metadata.set(SESSION_TOKEN_HEADER, response.clientSessionToken);
    return { host: new HostClient(stub, opts.pluginId, metadata), response };
  }

  /**
   * Fire a trigger, carrying the lease for the daemon call it came out of.
   *
   * **This is the transport, and the read belongs here rather than one level
   * up.** Both other ways to fire — `PluginContext.fireTrigger` and the
   * `Plugin.fireTrigger` wrapper an author is most likely to write — forward to
   * this method, and the wrapper routes to the process-global host. A read in
   * the context wrapper would leave that path unstamped, which is the one the
   * docs teach.
   *
   * The lease travels as call metadata rather than in the request body, because
   * `payloadJson`'s keys are injected verbatim as workflow variables
   * daemon-side: a reserved key would appear as `{__astra_cause}` in the user's
   * own variable picker.
   *
   * No ambient lease means no header. Never an empty one, never an invented
   * one, and never a failed fire: the daemon files an unattributed trigger as a
   * root event, which is where every plugin built before leases existed lands.
   */
  fireTrigger(triggerType: string, payloadJson: string = "{}"): Promise<void> {
    const cause = currentCause();
    const metadata = cause === undefined ? undefined : this.metadata.clone();
    if (metadata !== undefined && cause !== undefined) metadata.set(X_ASTRA_CAUSE, cause);
    return this.unary("FireTrigger", { triggerType, payloadJson }, metadata).then(
      () => undefined
    );
  }

  /** Log a message to the daemon. */
  log(level: string, message: string): Promise<void> {
    return this.unary("PluginLog", {
      pluginId: this.pluginId,
      level,
      message,
    }).then(() => undefined);
  }

  /** Get this plugin's current config, as JSON. */
  async getConfig(): Promise<string> {
    const res = await this.unary<{ configJson: string }>("GetPluginSelfConfig", {
      pluginId: this.pluginId,
    });
    return res.configJson;
  }

  /** Get daemon info. */
  getDaemonInfo(): Promise<DaemonInfo> {
    return this.unary<DaemonInfo>("GetDaemonInfo", {});
  }

  /** Set a variable readable by commands and other plugins. */
  setVariable(name: string, value: string, scope: string = "global"): Promise<void> {
    return this.unary("SetVariable", {
      pluginId: this.pluginId,
      name,
      value,
      scope,
    }).then(() => undefined);
  }

  /** Push an event to this plugin's UI contributions. */
  pushToUi(event: string, payloadJson: string = "{}"): Promise<void> {
    return this.unary("PushToUi", {
      pluginId: this.pluginId,
      event,
      payloadJson,
    }).then(() => undefined);
  }

  /**
   * Contribute colours, wallpaper and shader to the active Astra theme.
   *
   * Requires the `set_theme_contribution` permission, which Phase 4 classes
   * high-risk: this repaints the user's whole application, so the daemon
   * refuses it below Tier 1 regardless of what the manifest asks for.
   */
  setThemeContribution(theme: ThemeContribution): Promise<void> {
    return this.unary("SetThemeContribution", {
      pluginId: this.pluginId,
      themeName: theme.themeName,
      themeDescription: theme.themeDescription ?? "",
      cssVariables: theme.cssVariables ?? {},
      wallpaperPath: theme.wallpaperPath ?? "",
      wallpaperMode: theme.wallpaperMode ?? "",
      wallpaperOpacity: theme.wallpaperOpacity ?? 1.0,
      fragmentShader: theme.fragmentShader ?? "",
      effectConfigJson: theme.effectConfigJson ?? "",
    }).then(() => undefined);
  }

  /**
   * Send a chat message as this plugin and stream the assistant's reply.
   *
   * Returns an `AsyncIterable`, so the call site is a `for await` and back-
   * pressure is the loop's — which is what a TypeScript author expects and what
   * a raw `ClientReadableStream` does not give without an adapter:
   *
   * ```typescript
   * for await (const chunk of host.sendChatMessage("hello")) {
   *   if (chunk.text) process.stdout.write(chunk.text);
   *   if (chunk.error) throw new Error(chunk.error);
   * }
   * ```
   *
   * This is the ONLY working path for a client plugin to talk to the
   * conversation. The session token is scoped to `PluginHostService`, so the
   * `DaemonClient`/`ChatService` route is `permission_denied` by construction.
   * Requires the `send_chat_message` permission.
   *
   * `conversationId` empty means the active conversation.
   */
  sendChatMessage(
    text: string,
    opts: { conversationId?: string; voiceEnabled?: boolean } = {}
  ): AsyncIterable<ChatChunk> {
    const stream: grpc.ClientReadableStream<ChatChunk> = this.stub.SendChatMessage(
      {
        text,
        sourceId: this.pluginId,
        conversationId: opts.conversationId ?? "",
        voiceEnabled: opts.voiceEnabled ?? false,
      },
      this.metadata
    );
    return streamToAsyncIterable(stream);
  }

  /** Subscribe to daemon events. Returns a gRPC readable stream. */
  subscribeEvents(eventTypes: string[], excludeSourceId: string = ""): grpc.ClientReadableStream<unknown> {
    return this.stub.SubscribeEvents(
      { pluginId: this.pluginId, eventTypes, excludeSourceId },
      this.metadata
    );
  }

  /** Get the plugin ID. */
  getPluginId(): string {
    return this.pluginId;
  }

  /** Close the underlying channel. */
  close(): void {
    this.stub.close();
  }

  /**
   * Every unary host RPC goes through here, so none can forget the token.
   *
   * `metadata` overrides the shared one for a single call. Only `FireTrigger`
   * uses it, to add the invocation lease — and it passes a CLONE, because
   * `this.metadata` is shared by every concurrent call and mutating it would
   * stamp one chat's lease onto another chat's RPC.
   */
  private unary<T>(method: string, request: object, metadata?: grpc.Metadata): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.stub[method](
        request,
        metadata ?? this.metadata,
        (err: grpc.ServiceError | null, response: T) => {
          if (err) reject(err);
          else resolve(response);
        }
      );
    });
  }
}
