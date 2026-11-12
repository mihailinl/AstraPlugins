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
import type {
  AiSettings,
  DaemonInfo,
  Host,
  SettingChange,
  SettingsChangeOutcome,
  SettingsChangeResult,
  SpeakResult,
  SpeechOutcome,
  UserIdentity,
} from "./host.js";
import type { PluginErrorDetail } from "./errors.js";
import { SESSION_TOKEN_HEADER, X_ASTRA_CAUSE } from "./generated/wire.js";
import { currentCause } from "./causality.js";

/** Re-exported so `import { DaemonInfo } from "astra-plugin-sdk"` keeps working. */
export type { DaemonInfo } from "./host.js";

/**
 * `PluginSpeechOutcome` as the loader delivers it — the proto name (`enums:
 * String`), or the number should a loader option ever change — to the short
 * name `SpeakResult` carries. Anything else is `"UNSPECIFIED"`: an outcome this
 * SDK does not know is never guessed into one it does.
 */
const SPEECH_OUTCOMES: Readonly<Record<string, SpeechOutcome>> = {
  PLUGIN_SPEECH_OUTCOME_SPOKEN: "SPOKEN",
  PLUGIN_SPEECH_OUTCOME_STOPPED: "STOPPED",
  PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN: "NOT_SPOKEN",
  "1": "SPOKEN",
  "2": "STOPPED",
  "3": "NOT_SPOKEN",
};

/** `PluginSpeakResponse` off the wire, as the loader hands it over. */
interface WireSpeakResponse {
  outcome?: string | number;
  /** `null` when unset (`defaults: true`). */
  error?: Partial<PluginErrorDetail> | null;
}

/** A `PluginError` off the wire, every field present. */
function errorDetailFromWire(e: Partial<PluginErrorDetail>): PluginErrorDetail {
  return {
    code: String(e.code ?? ""),
    message: e.message ?? "",
    hint: e.hint ?? "",
    configField: e.configField ?? "",
    retryAfterMs: Number(e.retryAfterMs ?? 0),
    docUrl: e.docUrl ?? "",
  };
}

/**
 * The wire answer of `Speak` as a `SpeakResult`. Exported for the SDK's own
 * tests; `error` is present only when the daemon sent one, field for field.
 */
export function speakResultFromWire(res: WireSpeakResponse): SpeakResult {
  const outcome = SPEECH_OUTCOMES[String(res.outcome ?? "")] ?? "UNSPECIFIED";
  const e = res.error;
  if (!e) return { outcome };
  return { outcome, error: errorDetailFromWire(e) };
}

/**
 * `PluginSettingsChangeOutcome` as the loader delivers it, to the short name
 * `SettingsChangeResult` carries. Anything else is `"UNSPECIFIED"`, as for
 * speech.
 */
const SETTINGS_CHANGE_OUTCOMES: Readonly<Record<string, SettingsChangeOutcome>> = {
  PLUGIN_SETTINGS_CHANGE_OUTCOME_APPLIED: "APPLIED",
  PLUGIN_SETTINGS_CHANGE_OUTCOME_UNCHANGED: "UNCHANGED",
  PLUGIN_SETTINGS_CHANGE_OUTCOME_DECLINED: "DECLINED",
  PLUGIN_SETTINGS_CHANGE_OUTCOME_TIMED_OUT: "TIMED_OUT",
  PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED: "REFUSED",
  "1": "APPLIED",
  "2": "UNCHANGED",
  "3": "DECLINED",
  "4": "TIMED_OUT",
  "5": "REFUSED",
};

/** `PluginSettingsChangeResponse` off the wire, as the loader hands it over. */
interface WireSettingsChangeResponse {
  outcome?: string | number;
  refusedPath?: string;
  code?: string;
  /** `null` when unset (`defaults: true`). */
  error?: Partial<PluginErrorDetail> | null;
}

/**
 * The wire answer of `RequestSettingsChange` as a `SettingsChangeResult`.
 * Exported for the SDK's own tests; `error` is present only when the daemon
 * sent one, field for field.
 */
export function settingsChangeResultFromWire(
  res: WireSettingsChangeResponse
): SettingsChangeResult {
  const result: SettingsChangeResult = {
    outcome: SETTINGS_CHANGE_OUTCOMES[String(res.outcome ?? "")] ?? "UNSPECIFIED",
    code: res.code ?? "",
    refusedPath: res.refusedPath ?? "",
  };
  if (res.error) result.error = errorDetailFromWire(res.error);
  return result;
}

/**
 * One `SettingChange`'s value as `PluginSettingChange.value_json` — what
 * `JSON.stringify` writes. A value JSON has no text for (`undefined`, a
 * function, a symbol) or a number it cannot hold (`NaN`, `Infinity`, which
 * `JSON.stringify` would quietly turn into `null`) throws a `TypeError` naming
 * the setting, before anything is sent; a `BigInt` throws `JSON.stringify`'s
 * own. Exported for the SDK's own tests and `RecordingHost`.
 */
export function settingValueJson(change: SettingChange): string {
  const json = JSON.stringify(change.value, (_key, v: unknown) => {
    if (typeof v === "number" && !Number.isFinite(v)) {
      throw new TypeError(`setting "${change.path}": ${v} is not a JSON number`);
    }
    return v;
  });
  if (json === undefined) {
    throw new TypeError(`setting "${change.path}": a ${typeof change.value} is not a JSON value`);
  }
  return json;
}

/**
 * The `PluginSettingsChangeRequest` `requestSettingsChange` sends, in the
 * loader's field names. Nothing but the values is checked: the count, a path
 * given twice and the reason's length are the daemon's to judge (`REFUSED`),
 * so this client can never disagree with the Astra it talks to.
 */
export function settingsChangeRequestToWire(
  changes: readonly SettingChange[],
  reason: string
): { changes: { path: string; valueJson: string }[]; reason: string } {
  return {
    changes: changes.map((c) => ({ path: c.path, valueJson: settingValueJson(c) })),
    reason,
  };
}

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
  "GetAiSettings",
  "Speak",
  "StopSpeaking",
  "GetUserIdentity",
  "RequestSettingsChange",
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

  /** The chat's provider, model and endpoint — never a key. Needs `read_ai_settings`. */
  getAiSettings(): Promise<AiSettings> {
    return this.unary<AiSettings>("GetAiSettings", {});
  }

  /**
   * Say `text` aloud in Astra's voice; resolves once it was said, stopped or
   * refused (`SpeakResult`). Needs `speak`. The daemon is the authority on the
   * limits — at most `limits.SPEAK_TEXT_MAX_CHARS` characters, refused rather
   * than cut, and a speaking-time budget whose refusal carries `retryAfterMs`
   * — so this client checks neither.
   */
  async speak(text: string): Promise<SpeakResult> {
    return speakResultFromWire(await this.unary<WireSpeakResponse>("Speak", { text }));
  }

  /** Stop everything this plugin asked to be said, sounding and queued. Needs `speak`. */
  stopSpeaking(): Promise<void> {
    return this.unary("StopSpeaking", {}).then(() => undefined);
  }

  /** Pseudonyms for this installation and the signed-in account. Needs `read_user_identity`. */
  getUserIdentity(): Promise<UserIdentity> {
    return this.unary<UserIdentity>("GetUserIdentity", {});
  }

  /**
   * Ask the person to change some of Astra's settings on a card, and resolve
   * with what became of it (`SettingsChangeResult`). Needs
   * `request_settings_change`. Each value goes out as JSON
   * (`settingValueJson`); the daemon is the authority on the limits — at most
   * `limits.SETTINGS_CHANGE_MAX_CHANGES` changes, each path once, and a reason
   * of at most `limits.SETTINGS_CHANGE_REASON_MAX_CHARS` characters, refused
   * rather than cut — so this client checks none of them.
   *
   * No deadline: the call lasts until the person answers or the card expires
   * (Astra's confirmation timeout, at least 30 s, and the person may set it
   * far longer); a deadline here would cut a request the person was reading.
   */
  async requestSettingsChange(
    changes: SettingChange[],
    reason: string
  ): Promise<SettingsChangeResult> {
    return settingsChangeResultFromWire(
      await this.unary<WireSettingsChangeResponse>(
        "RequestSettingsChange",
        settingsChangeRequestToWire(changes, reason)
      )
    );
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
   * **`conversationId`**
   *
   * Where the message lands. Pass the EMPTY STRING and it goes to this plugin's
   * own durable thread: one thread per plugin, kept across calls, so a series of
   * messages reads as one conversation. That is the right choice for almost every
   * plugin, and it is what you get by default.
   *
   * Pass an id ONLY to answer inside a conversation you were told about in this
   * same exchange — `PluginChatChunk.conversation_id`, on the chunks of a reply you
   * are streaming right now. Do NOT store one and send it back later. Threads
   * rotate and are pruned, so a stored id eventually names a conversation that is
   * gone, and what happens then depends on the age of the daemon the user is
   * running: older builds accept it silently and write the exchange where nobody
   * can see it, newer ones refuse it. Neither is something a plugin can recover
   * from. Leave it empty and let the daemon place the message.
   *
   * There is deliberately no way to ask which conversation the user is looking at.
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
