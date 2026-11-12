// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * `PluginContext` — the one handle a handler gets.
 *
 * The Rust SDK passes a cheap-clone `PluginContext` to every handler (§5.1);
 * this is the same idea in TypeScript, and it exists for the same two reasons.
 *
 * 1. A handler written in the `plugin({...})` form has no `this`. It still
 *    needs the config, the language, the active triggers and the host, so it
 *    gets them as its second argument.
 * 2. The convenience wrappers on `Plugin` (`logInfo`, `fireTrigger`, …) all
 *    silently do nothing when `host` is null — the shape of "not registered
 *    yet" that hides a real failure. `ctx.fireTrigger` throws instead, naming
 *    the lifecycle point, because a trigger that did not fire and said nothing
 *    is worse than one that threw.
 *
 * The context reads through to the live plugin, so a handler that captured it
 * during `onStart` still sees the config as it is now, not as it was then.
 */

import type {
  AiSettings,
  Host,
  SettingChange,
  SettingsChangeResult,
  SpeakResult,
  UserIdentity,
} from "./host.js";
import type { I18n } from "./i18n.js";
import type { AiImage, ChatChunk, ThemeContribution } from "./types.js";
import { currentInvocation, type Invocation } from "./invocation.js";
import { currentAttachments } from "./attachments.js";

/** What a handler is given. Cheap to hold: it reads through to the plugin. */
export interface PluginContext {
  /** The `plugin.id` from the manifest, as the daemon spawned us with. */
  readonly pluginId: string;
  /** The daemon's UI language: "en", "ru", "uk", … */
  readonly language: string;
  /** This plugin's config, as last delivered by `OnConfigChanged`. */
  readonly config: Record<string, unknown>;
  /** Trigger types some command is currently listening for. */
  readonly activeTriggers: ReadonlySet<string>;
  /** The daemon, or `null` before registration / in a level-1 harness with none. */
  readonly host: Host | null;
  /**
   * Which conversation made THIS call, when one did.
   *
   * Present only inside a tool call or an action that a conversation's turn
   * triggered. `undefined` everywhere else, and `undefined` is several
   * situations at once — see `./invocation.js` — none of which is a cue to
   * guess a conversation.
   *
   * Optional on purpose: a plugin written before this existed keeps compiling,
   * and one reading it has to handle the absent case, which is the common one.
   *
   * ```ts
   * async callTool(name: string, argsJson: string) {
   *   const id = this.ctx().invocation?.conversationId;
   *   if (id) this.remember(id);          // safe to store, across restarts
   *   return { result: "done" };
   * }
   * ```
   */
  readonly invocation?: Invocation;
  /**
   * The pictures the person attached to the message THIS tool call answers —
   * `{ mimeType, data: Buffer, filename }` each, in the order attached. Empty
   * everywhere else: outside a tool call, for a tool that did not declare
   * `wantsAttachments`, and whenever Astra sent none.
   *
   * Astra sends them only to a tool that declared `wantsAttachments`, of a
   * plugin granted `receive_attachments`, on a call made while answering a
   * message the person sent in a conversation, and only when built with the
   * `plugin-provider-slots` build feature (no release has it yet). At most
   * `limits.IMAGE_INPUT_MAX_IMAGES` (4) pictures and 20 MiB, the newest kept,
   * each under its bare file name. See `./attachments.js`.
   *
   * ```ts
   * describe_photo: tool({
   *   description: "Describe the picture the person attached.",
   *   wantsAttachments: true,
   *   run: (_args, ctx) => {
   *     const [photo] = ctx.attachments;
   *     if (!photo) return "No picture was attached.";
   *     return `${photo.filename}: ${photo.mimeType}, ${photo.data.length} bytes`;
   *   },
   * }),
   * ```
   */
  readonly attachments: readonly AiImage[];
  /**
   * This plugin's translations, for the **runtime** plane.
   *
   * Loaded from `locales/` on first use and kept on this context's current
   * language, so a handler never has to call `setLanguage` itself. For
   * anything the DAEMON renders — action labels, config-field titles, `[ui]`
   * labels — use `key()` instead; see the `i18n` module docs for why.
   */
  readonly i18n: I18n;

  /** Read one config key, with the type you assert and a fallback. */
  configValue<T>(key: string, fallback: T): T;

  log(level: string, message: string): Promise<void>;
  info(message: string): Promise<void>;
  warn(message: string): Promise<void>;
  error(message: string): Promise<void>;

  /** Fire one of this plugin's trigger types. Rejects if there is no host. */
  fireTrigger(triggerType: string, payload?: Record<string, unknown>): Promise<void>;
  setVariable(name: string, value: string, scope?: string): Promise<void>;
  pushToUi(event: string, payload?: Record<string, unknown>): Promise<void>;
  setThemeContribution(theme: ThemeContribution): Promise<void>;
  /**
   * Send a chat message as this plugin and stream the assistant's reply.
   *
   * **Where it lands.** An empty `conversationId` posts to this plugin's own
   * durable thread, which is the right default for anything that is not an
   * answer to a specific call. Pass one only when you were TOLD it: the chunks
   * of a reply you are streaming carry it, and so does `ctx.invocation` inside
   * a tool call or an action. An id from an invocation may be stored, across
   * restarts, and sent back later.
   *
   * **Never await this inside the call that told you the id.** It is a
   * deadlock, not a slow path. The conversation that invoked your tool is still
   * running the turn waiting for your answer; a message declares an intent for
   * the *next* turn, so it queues behind the one that cannot finish until you
   * return. Start it and do not await it:
   *
   * ```ts
   * const id = ctx.invocation?.conversationId;
   * if (id) void (async () => { for await (const _ of ctx.sendChatMessage("done", { conversationId: id })); })();
   * return { result: "started" };          // the turn can now finish
   * ```
   *
   * **Your text is text.** A message beginning `/` reaches the model as those
   * literal characters — a plugin cannot invoke a slash command by writing one,
   * nor supersede a person's turn. And the stream always ends: a line that
   * reached the conversation but that no turn will answer ends it with an error
   * chunk (`INTERNAL`, "this message reached the conversation, but no turn will
   * answer it") whose hint says not to resend.
   *
   * **When the conversation is gone** the send is refused, never redirected:
   * `NOT_FOUND` (`err.code === 5`) whose message begins `conversation_gone:`
   * means it was deleted — forget the id. `INVALID_ARGUMENT` means the id is
   * not a UUID, or names a chat an Astra surface owns. A message accepted and
   * then outlived by its chat ends the stream with an error chunk whose
   * `errorDetail.code` is `PLUGIN_ERROR_NOT_FOUND`. An older daemon says
   * `INTERNAL`, "chat processing failed: conversation … does not exist".
   */
  sendChatMessage(
    text: string,
    opts?: { conversationId?: string; voiceEnabled?: boolean }
  ): AsyncIterable<ChatChunk>;
  /**
   * The user's chat provider, model and endpoint — never a key. Needs the
   * `read_ai_settings` permission. Rejects with a clear error when there is no
   * host, or when the host predates the call (`Host.getAiSettings` is
   * optional), so a plugin never writes `host?.getAiSettings?.()` itself.
   */
  getAiSettings(): Promise<AiSettings>;
  /**
   * Say `text` aloud in Astra's voice and resolve with what became of it:
   * `"SPOKEN"`, `"STOPPED"` (silence was asked for — not an error) or
   * `"NOT_SPOKEN"` with `error` saying why (`PLUGIN_ERROR_RATE_LIMITED` carries
   * `retryAfterMs`). Needs the `speak` permission — high-risk, its own consent
   * checkbox — an account that opens Astra, and the person's reply voice on.
   * At most `limits.SPEAK_TEXT_MAX_CHARS` characters; the daemon refuses a
   * longer text, it never cuts one.
   *
   * ```ts
   * const said = await ctx.speak("The kettle has boiled.");
   * if (said.outcome === "NOT_SPOKEN" && said.error?.code === "PLUGIN_ERROR_RATE_LIMITED") {
   *   setTimeout(retry, said.error.retryAfterMs);
   * }
   * ```
   *
   * Rejects with a clear error when there is no host or the host predates the
   * call, like `getAiSettings`.
   */
  speak(text: string): Promise<SpeakResult>;
  /** Stop everything this plugin asked to be said, sounding and queued. Needs `speak`. */
  stopSpeaking(): Promise<void>;
  /**
   * Pseudonyms for this installation and the signed-in account, made for this
   * plugin alone (never a name, an email or the account's own id). Needs the
   * `read_user_identity` permission.
   */
  getUserIdentity(): Promise<UserIdentity>;
  /**
   * ASK the person to change some of Astra's settings, on a card they answer,
   * and resolve with what became of it: `"APPLIED"`, `"UNCHANGED"` (nobody was
   * asked), `"DECLINED"` (do not ask again unasked), `"TIMED_OUT"`, or
   * `"REFUSED"` with `code` (and `error.retryAfterMs` for `rate_limited`).
   * Only the settings the assistant itself may change can be asked for; all of
   * `changes` change, or none. Needs the `request_settings_change` permission
   * and an Astra built with the `plugin-requests` feature (else `"REFUSED"`,
   * `code` `not_compiled`). At most `limits.SETTINGS_CHANGE_MAX_CHANGES`
   * changes and a `reason` of at most `limits.SETTINGS_CHANGE_REASON_MAX_CHARS`
   * characters — the daemon refuses more, it never cuts.
   *
   * **It lasts until the person answers or the card expires** (Astra's
   * confirmation timeout, at least 30 s): never await it on a path that must
   * answer quickly.
   *
   * ```ts
   * const asked = await ctx.requestSettingsChange(
   *   [{ path: "ai.model", value: "gpt-4.1" }],
   *   "PrimeAI's tools are tuned for this model",
   * );
   * if (asked.outcome === "REFUSED" && asked.code === "rate_limited") {
   *   setTimeout(askLater, asked.error?.retryAfterMs ?? 120_000);
   * }
   * ```
   *
   * Rejects with a clear error when there is no host or the host predates the
   * call, like `speak`.
   */
  requestSettingsChange(changes: SettingChange[], reason: string): Promise<SettingsChangeResult>;
}

/** The live state a context reads through to. Implemented by `Plugin`. */
export interface ContextSource {
  readonly pluginId: string;
  readonly host: Host | null;
  readonly config: Record<string, unknown>;
  readonly language: string;
  readonly activeTriggers: Set<string>;
  readonly i18n: I18n;
}

/** Raised when a handler reaches for the daemon before there is one. */
export class NoHostError extends Error {
  constructor(what: string) {
    super(
      `${what} needs the daemon, and this plugin is not registered with one. ` +
        `Either it was called before \`onStart\`, or this is a level-1 test harness ` +
        `built without a host — pass \`new RecordingHost()\` if you meant to record the call.`
    );
    this.name = "NoHostError";
  }
}

/**
 * The error for a host that has no method for a call added after it was
 * written — the optional `Host` methods. Same sentence as `getAiSettings`'s.
 */
function predates(method: string, rpc: string): Error {
  return new Error(
    `this Host does not implement ${method} (${rpc}): ` +
      "it predates the call. Update the host, or catch this and fall back."
  );
}

/** The context implementation. One per plugin; it holds no state of its own. */
export class PluginContextImpl implements PluginContext {
  constructor(private readonly source: ContextSource) {}

  get pluginId(): string {
    return this.source.pluginId;
  }
  get language(): string {
    return this.source.language;
  }
  get config(): Record<string, unknown> {
    return this.source.config;
  }
  get activeTriggers(): ReadonlySet<string> {
    return this.source.activeTriggers;
  }
  get host(): Host | null {
    return this.source.host;
  }
  get i18n(): I18n {
    return this.source.i18n;
  }
  /**
   * Read through to the per-call store rather than held on the context.
   *
   * A `PluginContext` is built once and handed to every hook, so a field set at
   * construction would be the same value for concurrent calls from two
   * different chats. `AsyncLocalStorage` follows the await chain of the one
   * call being handled, which is the only scope that can be correct here.
   */
  get invocation(): Invocation | undefined {
    return currentInvocation();
  }
  /** Read through to the per-call store, for the reason `invocation` is. */
  get attachments(): readonly AiImage[] {
    return currentAttachments();
  }

  configValue<T>(key: string, fallback: T): T {
    const value = this.source.config[key];
    return value === undefined || value === null ? fallback : (value as T);
  }

  private need(what: string): Host {
    const host = this.source.host;
    if (!host) throw new NoHostError(what);
    return host;
  }

  // `async`, every one of them, so a missing host arrives as a REJECTION.
  // `need()` throwing synchronously out of a method that returns a promise is
  // the shape `try { await ctx.fireTrigger(...) } catch {}` does not catch.
  async log(level: string, message: string): Promise<void> {
    await this.need("log").log(level, message);
  }
  async info(message: string): Promise<void> {
    await this.log("info", message);
  }
  async warn(message: string): Promise<void> {
    await this.log("warn", message);
  }
  async error(message: string): Promise<void> {
    await this.log("error", message);
  }

  async fireTrigger(triggerType: string, payload?: Record<string, unknown>): Promise<void> {
    await this.need("fireTrigger").fireTrigger(
      triggerType,
      payload ? JSON.stringify(payload) : "{}"
    );
  }

  async setVariable(name: string, value: string, scope = "session"): Promise<void> {
    await this.need("setVariable").setVariable(name, value, scope);
  }

  async pushToUi(event: string, payload?: Record<string, unknown>): Promise<void> {
    await this.need("pushToUi").pushToUi(event, payload ? JSON.stringify(payload) : "{}");
  }

  async getAiSettings(): Promise<AiSettings> {
    const host = this.need("getAiSettings");
    if (typeof host.getAiSettings !== "function") {
      throw new Error(
        "this Host does not implement getAiSettings (GetAiSettings): " +
          "it predates the call. Update the host, or catch this and fall back."
      );
    }
    return host.getAiSettings();
  }

  async speak(text: string): Promise<SpeakResult> {
    const host = this.need("speak");
    if (typeof host.speak !== "function") throw predates("speak", "Speak");
    return host.speak(text);
  }

  async stopSpeaking(): Promise<void> {
    const host = this.need("stopSpeaking");
    if (typeof host.stopSpeaking !== "function") throw predates("stopSpeaking", "StopSpeaking");
    await host.stopSpeaking();
  }

  async getUserIdentity(): Promise<UserIdentity> {
    const host = this.need("getUserIdentity");
    if (typeof host.getUserIdentity !== "function") {
      throw predates("getUserIdentity", "GetUserIdentity");
    }
    return host.getUserIdentity();
  }

  async requestSettingsChange(
    changes: SettingChange[],
    reason: string
  ): Promise<SettingsChangeResult> {
    const host = this.need("requestSettingsChange");
    if (typeof host.requestSettingsChange !== "function") {
      throw predates("requestSettingsChange", "RequestSettingsChange");
    }
    return host.requestSettingsChange(changes, reason);
  }

  async setThemeContribution(theme: ThemeContribution): Promise<void> {
    await this.need("setThemeContribution").setThemeContribution(theme);
  }

  sendChatMessage(
    text: string,
    opts?: { conversationId?: string; voiceEnabled?: boolean }
  ): AsyncIterable<ChatChunk> {
    return this.need("sendChatMessage").sendChatMessage(text, opts);
  }
}
