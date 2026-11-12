// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * `Host` — everything a plugin can ask the daemon for.
 *
 * The interface exists so the daemon is replaceable. `HostClient` is the real
 * implementation and it cannot be constructed without a live socket, a spawn
 * token and a successful `Register` — which is correct for production and
 * useless for a test. `testing/RecordingHost` implements the same interface in
 * memory, so a plugin's handlers can be driven with no daemon at all, and the
 * calls they made can be read back and asserted on.
 *
 * This is the TypeScript half of §5.1's `Host` trait: the same seam, the same
 * reason. Nothing in the SDK depends on `HostClient` the class any more —
 * `Plugin.host` is a `Host`.
 */

import type * as grpc from "@grpc/grpc-js";
import type { PluginErrorDetail } from "./errors.js";
import type { ChatChunk, ThemeContribution } from "./types.js";

/** Info about the running daemon. */
export interface DaemonInfo {
  version: string;
  state: string;
  grpcPort: number;
  /**
   * The daemon's current UI language — `PluginDaemonInfoResponse.language`,
   * field 4.
   *
   * The wire has carried it since the field was added; this interface did not
   * declare it, so a TypeScript plugin asking the daemon what language it is
   * in got a value the type system said was not there. The Rust and Python
   * SDKs return the proto message itself and never had the gap.
   */
  language: string;
}

/**
 * The user's chat provider, model and endpoint, as Astra lets a plugin see
 * them — `PluginAiSettings`, the answer of `GetAiSettings`. Never a key.
 */
export interface AiSettings {
  /** The provider id; `openai_compatible` for an endpoint the user saved, `astra` for Astra's own service. */
  provider: string;
  model: string;
  /** The endpoint without userinfo, query or fragment. Empty for `astra`. */
  apiBaseUrl: string;
  /** The endpoint is on this machine (127.0.0.0/8, ::1, localhost). */
  isLoopback: boolean;
}

/**
 * What became of one `speak` — `PluginSpeechOutcome`, without its prefix.
 *
 * - `"SPOKEN"` — it was heard.
 * - `"STOPPED"` — silence was asked for before it finished: the wake word,
 *   reply voice turned off, Stop, this plugin's own `stopSpeaking()`. **Not an
 *   error**; do not say it again unasked.
 * - `"NOT_SPOKEN"` — it was not said; `SpeakResult.error` says why.
 * - `"UNSPECIFIED"` — an outcome this SDK does not know (a newer Astra), or
 *   none at all. Never invented as one of the three above.
 */
export type SpeechOutcome = "SPOKEN" | "STOPPED" | "NOT_SPOKEN" | "UNSPECIFIED";

/** The answer of `Speak`: `PluginSpeakResponse`. */
export interface SpeakResult {
  outcome: SpeechOutcome;
  /**
   * Set with `"NOT_SPOKEN"`, absent otherwise — the same `PluginErrorDetail` a
   * chat chunk's `errorDetail` carries. `code` is the proto name:
   * `PLUGIN_ERROR_BAD_ARGUMENTS` (empty, or longer than
   * `limits.SPEAK_TEXT_MAX_CHARS` characters — refused, never cut),
   * `PLUGIN_ERROR_RATE_LIMITED` with `retryAfterMs` (this plugin's speaking
   * time is used up), `PLUGIN_ERROR_UNAVAILABLE` (voice off, Astra locked, no
   * voice). Nothing refused is queued.
   */
  error?: PluginErrorDetail;
}

/**
 * Who is using Astra, as THIS plugin may know it — `PluginUserIdentity`, the
 * answer of `GetUserIdentity`. Both ids are pseudonyms made for this plugin
 * alone: another plugin reads different ones for the same person and machine
 * (against plugins that use this API honestly — native plugin code can read
 * Astra's files, and neither id is a secret). Never the account's own id, a
 * name, an email or a hardware serial.
 */
export interface UserIdentity {
  /** This installation of Astra, stable across restarts and updates; `""` while Astra has no installation key. */
  installId: string;
  /** A person is signed in to Astra. */
  signedIn: boolean;
  /** …and their account opens Astra. */
  authorized: boolean;
  /**
   * The signed-in account, the same on every device the person signs in on;
   * `""` unless `authorized`. The same value arrives on this plugin's
   * `auth_changed` events as `payload.account_id` (event payloads keep the
   * daemon's snake_case keys).
   */
  accountId: string;
}

export interface Host {
  /** Fire one of this plugin's declared trigger types. Needs `fire_trigger`. */
  fireTrigger(triggerType: string, payloadJson?: string): Promise<void>;

  /** Write one line to the daemon's per-plugin log. */
  log(level: string, message: string): Promise<void>;

  /** This plugin's persisted config, as JSON. */
  getConfig(): Promise<string>;

  /** Version, run state and gRPC port of the daemon on the other end. */
  getDaemonInfo(): Promise<DaemonInfo>;

  /**
   * The user's chat provider, model and endpoint — never a key. Needs
   * `read_ai_settings`. For a plugin that calls the user's model itself: ask
   * Astra, never read Astra's files for it. An Astra older than this RPC
   * answers `UNIMPLEMENTED`.
   *
   * Optional so a `Host` implemented before this method existed keeps
   * compiling (the change is additive). Plugin code does not test for it: it
   * calls `ctx.getAiSettings()`, which throws a clear error when the host
   * lacks it. The concrete `HostClient`, `RecordingHost` and the mock daemon
   * all implement it.
   */
  getAiSettings?(): Promise<AiSettings>;

  /**
   * Say `text` aloud in Astra's voice, and resolve once it was said, stopped
   * or refused — see `SpeakResult`. Needs `speak` (**high-risk**: the words are
   * heard as Astra's) and, besides the grant, an account that opens Astra. A
   * missing grant, an account that does not open Astra, or an Astra older than
   * this RPC (`UNIMPLEMENTED`) rejects like every host call. Reply voice off,
   * a locked Astra or a full speech queue resolve `NOT_SPOKEN` with
   * `UNAVAILABLE`.
   *
   * Optional, like `getAiSettings`, so a `Host` written before it keeps
   * compiling; plugin code calls `ctx.speak()`.
   */
  speak?(text: string): Promise<SpeakResult>;

  /**
   * Stop everything this plugin asked to be said, sounding and queued, and
   * nothing else Astra is saying. Needs `speak`. Optional; call
   * `ctx.stopSpeaking()`.
   */
  stopSpeaking?(): Promise<void>;

  /**
   * Pseudonyms for this installation and the signed-in account, made for this
   * plugin alone — see `UserIdentity`. Needs `read_user_identity`. Optional;
   * call `ctx.getUserIdentity()`.
   */
  getUserIdentity?(): Promise<UserIdentity>;

  /** Publish a variable commands and other plugins can read. Needs `set_variable`. */
  setVariable(name: string, value: string, scope?: string): Promise<void>;

  /** Push an event into this plugin's own iframes. Needs `push_to_ui`. */
  pushToUi(event: string, payloadJson?: string): Promise<void>;

  /** Repaint the active theme. Needs `set_theme_contribution` (Tier 1 only). */
  setThemeContribution(theme: ThemeContribution): Promise<void>;

  /**
   * Speak into the conversation as this plugin and read the reply back.
   * The only working path for a client plugin; needs `send_chat_message`.
   */
  sendChatMessage(
    text: string,
    opts?: { conversationId?: string; voiceEnabled?: boolean }
  ): AsyncIterable<ChatChunk>;

  /** Daemon event stream. Needs `subscribe_events`, which also filters the types. */
  subscribeEvents(eventTypes: string[], excludeSourceId?: string): grpc.ClientReadableStream<unknown>;

  /** The plugin id this host is bound to. */
  getPluginId(): string;

  /** Release the connection, if there is one. */
  close(): void;
}
