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

export interface Host {
  /** Fire one of this plugin's declared trigger types. Needs `fire_trigger`. */
  fireTrigger(triggerType: string, payloadJson?: string): Promise<void>;

  /** Write one line to the daemon's per-plugin log. */
  log(level: string, message: string): Promise<void>;

  /** This plugin's persisted config, as JSON. */
  getConfig(): Promise<string>;

  /** Version, run state and gRPC port of the daemon on the other end. */
  getDaemonInfo(): Promise<DaemonInfo>;

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
