// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * `RecordingHost` — the daemon, in memory.
 *
 * Implements the whole `Host` interface, records every call, and can be told to
 * fail any of them. It is what makes a level-1 test possible at all: a
 * `HostClient` cannot exist without a socket, a spawn token and a successful
 * `Register`, so before this the only way to assert "the plugin fired the
 * trigger" was to run a daemon.
 *
 * Nothing here is a stub that returns a plausible value and forgets the call.
 * Every method appends to a list the test can read, because the assertion that
 * matters is usually about what the plugin *did*, not about what it returned.
 */

import { Readable } from "node:stream";
import type * as grpc from "@grpc/grpc-js";
import type { Host, DaemonInfo } from "../host.js";
import type { ChatChunk, ThemeContribution } from "../types.js";

/** One line the plugin logged. */
export interface RecordedLog {
  level: string;
  message: string;
}

/** One trigger the plugin fired. `payload` is the parsed `payloadJson`. */
export interface RecordedTrigger {
  triggerType: string;
  payloadJson: string;
  payload: unknown;
}

/** One variable the plugin published. */
export interface RecordedVariable {
  name: string;
  value: string;
  scope: string;
}

/** One event the plugin pushed to its own iframes. */
export interface RecordedUiPush {
  event: string;
  payloadJson: string;
  payload: unknown;
}

/** One message the plugin sent into a conversation. */
export interface RecordedChat {
  text: string;
  conversationId: string;
  voiceEnabled: boolean;
}

/** Every host RPC name a test may inject a failure for. */
export type HostRpc =
  | "fireTrigger"
  | "log"
  | "getConfig"
  | "getDaemonInfo"
  | "setVariable"
  | "pushToUi"
  | "setThemeContribution"
  | "sendChatMessage"
  | "subscribeEvents";

function parseJson(json: string): unknown {
  try {
    return JSON.parse(json || "{}");
  } catch {
    return json;
  }
}

export class RecordingHost implements Host {
  private readonly triggers: RecordedTrigger[] = [];
  private readonly logLines: RecordedLog[] = [];
  private readonly vars: RecordedVariable[] = [];
  private readonly pushes: RecordedUiPush[] = [];
  private readonly themeCalls: ThemeContribution[] = [];
  private readonly chats: RecordedChat[] = [];
  private readonly streams: Readable[] = [];
  /** RPC -> the error to throw, and how many more times to throw it. */
  private readonly failures = new Map<HostRpc, { error: Error; times: number }>();
  private closed = false;

  constructor(
    private readonly pluginId = "test-plugin",
    /** What `getConfig()` answers with. */
    public configJson = "{}",
    /** What `getDaemonInfo()` answers with. */
    public daemonInfo: DaemonInfo = {
      version: "0.0.0-test",
      state: "running",
      grpcPort: 0,
      language: "en",
    }
  ) {}

  // ── failure injection ──

  /**
   * Make the next `times` calls to `rpc` reject with `error`.
   *
   * The point is not to be mean: a plugin that assumed `fireTrigger` always
   * succeeds swallows the failure and reports success to the user, and the only
   * way to see that in a test is to make it fail on purpose.
   */
  fail(rpc: HostRpc, error: Error = new Error(`${rpc} failed (injected)`), times = 1): this {
    this.failures.set(rpc, { error, times });
    return this;
  }

  /** Make every future call to `rpc` reject. */
  failAlways(rpc: HostRpc, error?: Error): this {
    return this.fail(rpc, error, Number.POSITIVE_INFINITY);
  }

  /** Stop failing `rpc`. */
  succeed(rpc: HostRpc): this {
    this.failures.delete(rpc);
    return this;
  }

  private check(rpc: HostRpc): void {
    if (this.closed) throw new Error(`RecordingHost is closed; ${rpc} was called after close()`);
    const failure = this.failures.get(rpc);
    if (!failure) return;
    failure.times -= 1;
    if (failure.times <= 0) this.failures.delete(rpc);
    throw failure.error;
  }

  // ── what the test reads ──

  /** Triggers fired, in order. */
  firedTriggers(): readonly RecordedTrigger[] {
    return this.triggers;
  }
  /** Log lines, in order — including whatever the console bridge forwarded. */
  logs(): readonly RecordedLog[] {
    return this.logLines;
  }
  /** Log lines at one level. */
  logsAt(level: string): readonly RecordedLog[] {
    return this.logLines.filter((l) => l.level === level);
  }
  /** Variables published, in order. Later writes to a name are separate entries. */
  variables(): readonly RecordedVariable[] {
    return this.vars;
  }
  /** The last value published for `name`, or `undefined`. */
  variable(name: string): string | undefined {
    for (let i = this.vars.length - 1; i >= 0; i--) if (this.vars[i].name === name) return this.vars[i].value;
    return undefined;
  }
  /** Events pushed to the plugin's own UI. */
  uiPushes(): readonly RecordedUiPush[] {
    return this.pushes;
  }
  /** Theme contributions made. */
  themes(): readonly ThemeContribution[] {
    return this.themeCalls;
  }
  /** Chat messages sent. */
  chatMessages(): readonly RecordedChat[] {
    return this.chats;
  }
  /** Forget everything recorded. Failure injections are kept. */
  clear(): void {
    this.triggers.length = 0;
    this.logLines.length = 0;
    this.vars.length = 0;
    this.pushes.length = 0;
    this.themeCalls.length = 0;
    this.chats.length = 0;
  }

  /** Chunks the next `sendChatMessage` will stream back. */
  chatReply: ChatChunk[] = [{ text: "ok", done: false }, { done: true }];

  /** Push one event to every open `subscribeEvents` stream. */
  emitEvent(eventType: string, payload: Record<string, unknown> = {}): void {
    for (const stream of this.streams) {
      stream.push({ eventType, payloadJson: JSON.stringify(payload) });
    }
  }

  /** End every open event stream, as a daemon shutdown would. */
  endEventStreams(): void {
    for (const stream of this.streams) stream.push(null);
    this.streams.length = 0;
  }

  // ── Host ──

  async fireTrigger(triggerType: string, payloadJson = "{}"): Promise<void> {
    this.check("fireTrigger");
    this.triggers.push({ triggerType, payloadJson, payload: parseJson(payloadJson) });
  }

  async log(level: string, message: string): Promise<void> {
    this.check("log");
    this.logLines.push({ level, message });
  }

  async getConfig(): Promise<string> {
    this.check("getConfig");
    return this.configJson;
  }

  async getDaemonInfo(): Promise<DaemonInfo> {
    this.check("getDaemonInfo");
    return this.daemonInfo;
  }

  async setVariable(name: string, value: string, scope = "session"): Promise<void> {
    this.check("setVariable");
    this.vars.push({ name, value, scope });
  }

  async pushToUi(event: string, payloadJson = "{}"): Promise<void> {
    this.check("pushToUi");
    this.pushes.push({ event, payloadJson, payload: parseJson(payloadJson) });
  }

  async setThemeContribution(theme: ThemeContribution): Promise<void> {
    this.check("setThemeContribution");
    this.themeCalls.push(theme);
  }

  sendChatMessage(
    text: string,
    opts: { conversationId?: string; voiceEnabled?: boolean } = {}
  ): AsyncIterable<ChatChunk> {
    this.check("sendChatMessage");
    this.chats.push({
      text,
      conversationId: opts.conversationId ?? "",
      voiceEnabled: opts.voiceEnabled ?? false,
    });
    const reply = this.chatReply;
    return {
      async *[Symbol.asyncIterator]() {
        for (const chunk of reply) yield chunk;
      },
    };
  }

  subscribeEvents(_eventTypes: string[], _excludeSourceId = ""): grpc.ClientReadableStream<unknown> {
    this.check("subscribeEvents");
    const stream = new Readable({ objectMode: true, read() {} });
    this.streams.push(stream);
    return stream as unknown as grpc.ClientReadableStream<unknown>;
  }

  getPluginId(): string {
    return this.pluginId;
  }

  close(): void {
    this.closed = true;
    this.endEventStreams();
  }
}
