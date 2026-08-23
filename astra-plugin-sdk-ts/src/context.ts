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

import type { Host } from "./host.js";
import type { I18n } from "./i18n.js";
import type { ChatChunk, ThemeContribution } from "./types.js";

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
  sendChatMessage(
    text: string,
    opts?: { conversationId?: string; voiceEnabled?: boolean }
  ): AsyncIterable<ChatChunk>;
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
