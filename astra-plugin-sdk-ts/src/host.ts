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

/**
 * One setting a plugin asks to change: a dotted settings path the assistant
 * itself may change (`ai.model`, `voice.tts_speed`) and the value wanted —
 * any JSON value (`"gpt-4.1"`, `true`, `1.2`, an object), which the SDK
 * serialises into `PluginSettingChange.value_json`.
 */
export interface SettingChange {
  path: string;
  value: unknown;
}

/**
 * What became of one `requestSettingsChange` —
 * `PluginSettingsChangeOutcome`, without its prefix.
 *
 * - `"APPLIED"` — the person allowed it; the settings now hold what was asked
 *   for.
 * - `"UNCHANGED"` — they already held it. Nobody was asked.
 * - `"DECLINED"` — the person said no, now or to this plugin changing one of
 *   these settings before (Astra asks again about a setting only after it has
 *   changed some other way, or after a restart). **Do not ask again unasked.**
 * - `"TIMED_OUT"` — nobody answered before the card expired (no window open
 *   counts).
 * - `"REFUSED"` — not asked, or not applied; `SettingsChangeResult.code` says
 *   why.
 * - `"UNSPECIFIED"` — an outcome this SDK does not know (a newer Astra), or
 *   none at all. Never invented as one of the above.
 */
export type SettingsChangeOutcome =
  | "APPLIED"
  | "UNCHANGED"
  | "DECLINED"
  | "TIMED_OUT"
  | "REFUSED"
  | "UNSPECIFIED";

/** The answer of `RequestSettingsChange`: `PluginSettingsChangeResponse`. The current values are never in it. */
export interface SettingsChangeResult {
  outcome: SettingsChangeOutcome;
  /**
   * With `"REFUSED"`: why, as one word — `not_compiled` (this Astra was built
   * without the `plugin-requests` feature), `locked`, `invalid` (no changes, a
   * path twice, a value that is not JSON, or more than a card can show whole),
   * `too_many` (more than `limits.SETTINGS_CHANGE_MAX_CHANGES`),
   * `reason_too_long` (more than `limits.SETTINGS_CHANGE_REASON_MAX_CHARS`
   * characters — refused, never cut), `busy` (one of this plugin's requests is
   * already waiting), `rate_limited` (a burst of two, then one every two minutes;
   * `error.retryAfterMs` says when), `not_assistant_editable`,
   * `invalid_value`, `unknown_choice`, `needs_api_key`, `needs_stt_provider`,
   * `provider_unreachable`, `stale` (the settings changed while the card was
   * up), `stopped` (this plugin's authority ended first), `write_refused`.
   * `""` otherwise.
   */
  code: string;
  /** With `"REFUSED"`: the setting the refusal is about, when it is about one; `""` otherwise. */
  refusedPath: string;
  /**
   * With `"REFUSED"`, when the daemon sent one: the same `PluginErrorDetail` a
   * chat chunk's `errorDetail` carries — a sentence, and `retryAfterMs` for
   * `rate_limited`. Absent otherwise.
   */
  error?: PluginErrorDetail;
}

/**
 * What became of one `proposeCommand` — `PluginProposeCommandOutcome`, without
 * its prefix.
 *
 * - `"SAVED"` — the person kept it; `CommandOfferResult.enabled` says whether
 *   the command is on after it was kept (Astra may keep it switched off).
 *   Record it.
 * - `"UNCHANGED"` — what is kept under this key came from this very offer —
 *   also after the person edited it. Nobody was asked.
 * - `"DECLINED"` — the person said no, now or to this very command before
 *   (until Astra restarts). Record it: **do not offer it again unasked.**
 *   Astra's own memory of a no ends at a restart, and a command the person
 *   deleted is offered as new.
 * - `"TIMED_OUT"` — nobody answered before the card expired (no window open
 *   counts).
 * - `"REFUSED"` — not asked, or not kept; `CommandOfferResult.code` says why.
 * - `"UNSPECIFIED"` — an outcome this SDK does not know (a newer Astra), or
 *   none at all. Never invented as one of the above.
 */
export type CommandOfferOutcome =
  | "SAVED"
  | "UNCHANGED"
  | "DECLINED"
  | "TIMED_OUT"
  | "REFUSED"
  | "UNSPECIFIED";

/** The answer of `ProposeCommand`: `PluginProposeCommandResponse`. */
export interface CommandOfferResult {
  outcome: CommandOfferOutcome;
  /**
   * With `"SAVED"`: whether the command is on after it was kept (Astra may keep
   * it switched off). `false` otherwise.
   */
  enabled: boolean;
  /**
   * With `"REFUSED"`: why, as one word — `not_compiled` (this Astra was built
   * without the `plugin-requests` feature), `locked`, `invalid_key`,
   * `reason_too_long` (more than `limits.PROPOSE_COMMAND_REASON_MAX_CHARS`
   * characters — refused, never cut), `too_large` (more than
   * `limits.PROPOSE_COMMAND_MAX_BYTES` bytes of JSON), `invalid_command`
   * (`error.message` usually leads with the Workshop's own code:
   * `E_COMMAND_FORMAT`, `E_COMMAND_UNKNOWN_ACTION`, … — not when the card
   * itself cannot be shown), `foreign_plugin` (it uses another plugin's action
   * or trigger), `busy` (one of this plugin's offers is already waiting),
   * `rate_limited` (a burst of two, then one every two minutes;
   * `error.retryAfterMs` says when), `stopped` (this plugin's
   * authority ended first), `stale` (the command it updates changed or went
   * while the card was up), `write_refused`. `""` otherwise.
   */
  code: string;
  /**
   * With `"REFUSED"`, when the daemon sent one: the same `PluginErrorDetail` a
   * chat chunk's `errorDetail` carries — a sentence, and `retryAfterMs` for
   * `rate_limited`. Absent otherwise.
   */
  error?: PluginErrorDetail;
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

  /**
   * ASK the person to change some of Astra's settings — only the ones the
   * assistant itself may change — on a card they answer, and resolve with what
   * became of it (`SettingsChangeResult`). Needs `request_settings_change` and
   * an account that opens Astra; a missing grant, an account that does not
   * open Astra, or an Astra older than this RPC (`UNIMPLEMENTED`) rejects like
   * every host call. Lasts until the person answers or the card expires.
   *
   * Optional, like `speak`; plugin code calls `ctx.requestSettingsChange()`.
   */
  requestSettingsChange?(changes: SettingChange[], reason: string): Promise<SettingsChangeResult>;

  /**
   * OFFER the person one portable command to keep, under this plugin's own
   * `key`, on a card they answer; they keep it only from Astra's Workshop
   * sheet. Resolves with what became of it (`CommandOfferResult`). `command`
   * is the command as an object or as its JSON text. Needs `propose_commands`
   * (high-risk) and an account that opens Astra; a missing grant, an account
   * that does not open Astra, or an Astra older than this RPC
   * (`UNIMPLEMENTED`) rejects like every host call. Lasts until the person
   * answers or the card expires.
   *
   * Optional, like `speak`; plugin code calls `ctx.proposeCommand()`.
   */
  proposeCommand?(
    key: string,
    command: object | string,
    reason: string
  ): Promise<CommandOfferResult>;

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
