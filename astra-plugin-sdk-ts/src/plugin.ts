// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Base Plugin class — extend this to build an Astra plugin.
 */

import * as grpc from "@grpc/grpc-js";
import { HostClient } from "./host-client.js";
import { EXIT_PROTOCOL_INCOMPATIBLE, ProtocolMismatchError } from "./protocol.js";
import { service } from "./proto-loader.js";
import { addServiceChecked, type HandlerMap } from "./service-contract.js";
import { causeFromCall, withCause } from "./causality.js";
import { assertNoReservedNames } from "./reserved.js";
import { capabilityAuthMode, guardHandlers } from "./capability-auth.js";
import type {
  ToolDef,
  ToolResult,
  VoiceInfo,
  AudioData,
  SttEvent,
  AiModelInfo,
  ActionResult,
  ActionTypeDef,
  TriggerTypeDef,
  UiContribution,
  UiCallResult,
  FieldDef,
  AiChunk,
  AiCompleteRequest,
  AudioChunk,
  SttLoadStatus,
  SttOptions,
  StateChangedEvent,
  CommandTriggeredEvent,
  CommandCompletedEvent,
} from "./types.js";
import { PluginError } from "./errors.js";
import { STT_AUDIO_CHANNEL_CAPACITY } from "./generated/limits.js";
import { DaemonClient } from "./daemon-client.js";
import type { Host } from "./host.js";
import { PluginContextImpl, type PluginContext } from "./context.js";
import { installConsoleBridge, installFatalHandlers } from "./logging.js";

/**
 * The daemon's word for "this plugin does not have that hook".
 *
 * `optional_hook` on the daemon side reads `UNIMPLEMENTED` as absence, not as a
 * fault, and that equivalence is the protocol's forward-compat contract. Every
 * un-overridden hook below throws this, so "not implemented" is one sentence in
 * one place rather than a shape each handler invents.
 */
export class HookUnimplemented extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HookUnimplemented";
  }
}

// ── wire projections ─────────────────────────────────────────────────────────
//
// The descriptor is loaded with `keepCase: false`, so every wire field is
// lowerCamelCase (`config_fields` -> `configFields`). A snake_case key is
// dropped by protobufjs without a word, which is how three handlers once sent
// the daemon empty lists. These four functions are the only place the SDK
// spells a wire field name for the §5.4 hooks.

function sttEventWire(ev: SttEvent) {
  return {
    text: ev.text,
    isFinal: ev.isFinal ?? true,
    confidence: ev.confidence ?? 1.0,
    language: ev.language ?? "",
  };
}

function audioChunkWire(chunk: AudioChunk) {
  return {
    data: chunk.data,
    isLast: chunk.isLast ?? false,
    sampleRate: chunk.sampleRate ?? 0,
  };
}

/**
 * One `AiChunk` as the `oneof` it really is.
 *
 * A chunk that sets two things is a chunk the daemon reads one of, so the
 * precedence is fixed here (error, tool call, thinking, done, text) rather than
 * left to protobufjs' last-write-wins over the object's key order.
 */
function aiChunkWire(chunk: AiChunk) {
  if (chunk.error) return { error: chunk.error };
  if (chunk.toolCall) return { toolCall: chunk.toolCall };
  if (chunk.thinking) return { thinkingDelta: chunk.thinking };
  if (chunk.done) return { done: true };
  return { textDelta: chunk.text ?? "" };
}

function aiRequestFromWire(request: any): AiCompleteRequest {
  return {
    messages: (request.messages ?? []).map((m: any) => ({
      role: m.role ?? "",
      content: m.content ?? "",
      toolCallId: m.toolCallId ?? "",
      toolCalls: m.toolCalls ?? [],
    })),
    tools: request.tools ?? [],
    systemPrompt: request.systemPrompt ?? "",
    temperature: request.temperature ?? 0,
    maxTokens: request.maxTokens ?? 0,
    model: request.model ?? "",
    reasoningEffort: request.reasoningEffort ?? "",
    showReasoning: !!request.showReasoning,
  };
}

export abstract class Plugin {
  /**
   * The daemon, once registered.
   *
   * Typed as the `Host` interface rather than as `HostClient`: that is the seam
   * the level-1 test harness installs `RecordingHost` through, and the reason
   * nothing in the SDK constructs a `HostClient` except `run()`.
   */
  host: Host | null = null;

  /** Full daemon API client. Only available if `isClient()` returns true. */
  daemon: DaemonClient | null = null;

  /** Current plugin config (populated after registration). */
  config: Record<string, unknown> = {};

  /** Current daemon UI language (e.g. "en", "ru", "uk"). */
  language: string = "en";

  /** Set of active trigger types (auto-updated by daemon). */
  activeTriggers: Set<string> = new Set();

  /** This plugin's id, as the daemon spawned it. `""` until `run()` parses argv. */
  pluginId: string = "";

  private server: grpc.Server | null = null;
  /** Set by `stopServing`; stops the two reconnect loops from resurrecting. */
  private stopped = false;
  private readyResolve: (() => void) | null = null;
  private readyReject: ((reason: unknown) => void) | null = null;

  /**
   * Settles when `run()` has registered and finished the start lifecycle.
   *
   * @internal The level-2 harness needs it: `Register` returns before the
   * plugin has applied the config and language from the response, so a test
   * that asserted on `plugin.config` right after registration was reading a
   * value that had not arrived yet. Racy assertions are worse than absent ones.
   */
  readonly ready: Promise<void> = new Promise<void>((resolve, reject) => {
    this.readyResolve = resolve;
    this.readyReject = reject;
  });
  private readonly context: PluginContext = new PluginContextImpl(this);

  /**
   * The handle handlers are given.
   *
   * One object for the lifetime of the plugin, reading through to the live
   * config/language/host — so a background task may capture it once at
   * `onStart` and still see the current config an hour later.
   */
  ctx(): PluginContext {
    return this.context;
  }

  /**
   * How this plugin stops. `process.exit`, and one seam for the tests.
   *
   * @internal `MockDaemon` replaces it, because a level-2 test drives a real
   * plugin in the test runner's own process and `Shutdown`'s
   * `setTimeout(process.exit, 100)` would otherwise end the run — silently, and
   * with the exit code of a plugin rather than of a test suite.
   */
  exitProcess(code: number): void {
    process.exit(code);
  }

  /**
   * Stop serving and release every socket, without exiting the process.
   *
   * @internal The level-2 harness runs a real plugin inside the test runner, so
   * something has to hand back the capability server's listener, the host
   * channel and the reconnect timers. A plugin normally does this by exiting;
   * a test process that did the same would report the plugin's exit code as
   * the suite's.
   */
  async stopServing(): Promise<void> {
    this.stopped = true;
    this.host?.close();
    this.daemon?.close();
    const server = this.server;
    this.server = null;
    if (!server) return;
    // `forceShutdown`, not `tryShutdown`: a plugin under test may have a bidi
    // stream still open, and `tryShutdown` waits for it — which is a hung test
    // run rather than a failed one.
    server.forceShutdown();
  }

  /** Parse CLI args, start gRPC server, register, serve until shutdown. */
  run(): void {
    // Nobody awaits `ready` in production, and an unawaited rejected promise is
    // a process-killing unhandled rejection. This marks it handled without
    // taking the rejection away from a harness that does await it.
    void this.ready.catch(() => undefined);
    const args = this.parseArgs();
    this.pluginId = args.pluginId;

    // A crash must be a log line and a non-zero exit, not a silent process
    // death: Node's default for an unhandled rejection is to print to stderr
    // that nobody is reading and exit 1 with no plugin-side record at all.
    installFatalHandlers(() => this.host);

    // The descriptor is checked against the protocol's `reserved` declarations
    // BEFORE the server binds. TypeScript answers a missing descriptor entry
    // with `undefined`, which is how three handlers were registered against a
    // stale descriptor and dropped for a whole release; a revived reserved
    // field is the same class of drift arriving from the other direction.
    assertNoReservedNames();

    const server = new grpc.Server();
    this.server = server;

    // SECURITY: the capability server is the daemon's way into this plugin's
    // tools, config and shutdown, and loopback separates it from nothing — any
    // process of the same user can dial the port. The guard demands the daemon
    // hand back the spawn-time `--auth-token`, which only it and this process
    // know. Staged; see `capability-auth.ts`.
    const mode = capabilityAuthMode();
    if (!args.authToken || mode === "off") {
      console.warn(
        "Capability server is unauthenticated — any local process can call this plugin. " +
          "(No --auth-token was passed, or the check is switched off.)"
      );
    }

    // Every `PluginCapabilityService` method must have a handler and every
    // handler must name a real method — `addServiceChecked` throws a
    // `ProtoContractError` here rather than letting grpc-js drop a misspelled
    // handler or answer a missing one with UNIMPLEMENTED at runtime. The guard
    // wraps handlers, never adds or removes keys, so it runs before the check
    // and the check still sees the real handler map.
    addServiceChecked(
      server,
      "PluginCapabilityService",
      service("PluginCapabilityService").service,
      guardHandlers(this.capabilityHandlers(), args.authToken, mode)
    );

    // Bind to random port
    server.bindAsync(
      "127.0.0.1:0",
      grpc.ServerCredentials.createInsecure(),
      async (err, port) => {
        if (err) {
          console.error("Failed to bind:", err);
          this.exitProcess(1);
          return;
        }

        console.log(`Plugin gRPC server listening on port ${port}`);

        const capabilities = await this.discoverCapabilities();
        console.log(`Registering with capabilities: ${capabilities.join(", ")}`);

        try {
          // `HostClient.register` performs the one unauthenticated bootstrap
          // call and hands back a client already carrying `x-session-token`.
          const { host, response } = await HostClient.register({
            daemonAddr: args.daemonAddr,
            pluginId: args.pluginId,
            port,
            capabilities,
            authToken: args.authToken,
          });
          this.host = host;

          // From here on `console.*` is also a `PluginLog`, so an author who
          // never calls `ctx.info` still shows up in the daemon's log pane —
          // which is the only place a user can see why a plugin misbehaved.
          // Installed after registration, deliberately: before it there is no
          // host to log to, and the daemon reads this process's first line of
          // stdout as the readiness signal.
          installConsoleBridge(() => this.host);

          // …and the registration line goes through it, so this plugin makes at
          // least one authenticated host call on every start rather than only
          // when the author happens to log something. `astra-plugin test`
          // asserts that a plugin talked to the daemon at all, precisely so a
          // host client that stopped sending `x-session-token` cannot pass
          // conformance while every inbound hook still answers.
          console.log(
            `Registered successfully. Daemon version: ${response.daemonVersion}`
          );

          // The daemon issues a session token to EVERY plugin (it gates the host
          // RPCs, not just the daemon API), so the token alone no longer means
          // "client capability" — gate on `isClient()` instead. Attach to the chat
          // firehose so `onConversationEvent` receives every chat event across
          // every conversation.
          if (this.isClient()) {
            this.daemon = new DaemonClient(args.daemonAddr, response.clientSessionToken);
            await this.daemon.connect();
            await this.onDaemonClientReady(this.daemon);
            this.startChatFirehose();
            console.log("DaemonClient connected (plugin has client capability)");
          }

          // Lifecycle, in the order all three SDKs use:
          //   bind → register → ctx → onConfigChanged → onLanguageChanged
          //   → onStart → serve
          // Config first because `onLanguageChanged` and `onStart` are both
          // entitled to read it; `onStart` last because it is the hook that may
          // open sockets and spawn timers, and it must not do that against a
          // half-initialised plugin.
          if (response.configJson) {
            try {
              this.config = JSON.parse(response.configJson);
            } catch {
              this.config = {};
            }
            await this.onConfigChanged(this.config);
          }

          if (response.language) {
            this.language = response.language;
            await this.onLanguageChanged(response.language);
          }

          await this.onStart(this.ctx());

          // Start event subscription
          this.readyResolve?.();
          const eventTypes = this.subscribedEvents();
          if (eventTypes.length > 0) {
            const excludeSource = this.sourceId();
            console.log(`Subscribing to events: ${eventTypes.join(", ")}${excludeSource ? ` (exclude: ${excludeSource})` : ""}`);
            this.startEventLoop(eventTypes, excludeSource);
          }
        } catch (e: any) {
          // A protocol mismatch is not a fault to retry or a stack to read. It
          // is one fact with one fix, and it gets EX_CONFIG so the daemon's log
          // of the exit code says "this machine is misconfigured" rather than
          // "the plugin crashed".
          this.readyReject?.(e);
          if (e instanceof ProtocolMismatchError) {
            console.error(e.message);
            this.exitProcess(EXIT_PROTOCOL_INCOMPATIBLE);
            return;
          }
          console.error("Registration failed:", e.message);
          this.exitProcess(1);
        }
      }
    );

    // Graceful shutdown
    const shutdown = () => {
      console.log("Shutting down...");
      this.onShutdown().then(() => {
        server.tryShutdown(() => this.exitProcess(0));
      });
    };
    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);
  }

  // ── Lifecycle ──

  /**
   * Called once, after registration and after the first config and language
   * have been delivered, before the plugin starts serving.
   *
   * This is where to open a connection, start a poller or seed a cache: `ctx`
   * is live and `this.config` is populated, which is not true in the
   * constructor. Throwing here fails the start loudly instead of leaving a
   * plugin that registered and does nothing.
   */
  async onStart(_ctx: PluginContext): Promise<void> {}

  // ── Client capability ──

  /** Override to return true if this plugin acts as a full daemon client. */
  isClient(): boolean {
    return false;
  }

  /** Called after registration with a DaemonClient (client plugins only). */
  async onDaemonClientReady(_client: DaemonClient): Promise<void> {}

  // ── Capability methods (override in subclass) ──

  async listTools(): Promise<ToolDef[]> {
    return [];
  }
  async callTool(_name: string, _argumentsJson: string): Promise<ToolResult> {
    return { success: false, error: "Not implemented", result: "" };
  }
  async ttsSynthesize(
    _text: string,
    _voiceId: string,
    _speed: number,
    _pitch: number
  ): Promise<AudioData> {
    throw new HookUnimplemented("TTS not implemented");
  }
  async ttsListVoices(): Promise<VoiceInfo[]> {
    return [];
  }
  async sttGetLanguages(): Promise<string[]> {
    return [];
  }
  /** Declare TTS settings the daemon should render on the Voice page.
   *
   * Each `FieldDef` becomes one input rendered by the daemon's generic
   * `DynamicField` component — no per-plugin frontend code. Use the
   * exported `fields` builder (`fields.text(...).withDefault(...)`) for
   * ergonomics. Return `[]` (the default) if the TTS provider has no
   * extra settings. */
  async ttsConfigFields(): Promise<FieldDef[]> {
    return [];
  }
  /** Declare STT settings; same contract as `ttsConfigFields`. */
  async sttConfigFields(): Promise<FieldDef[]> {
    return [];
  }
  /** Transcribe a complete utterance to text (non-streaming). The SDK
   * accumulates every audio chunk the daemon streams over `SttProcess` and
   * calls this once the stream ends. `options` carries the per-utterance
   * language hint and wake-word bias the daemon put on the first chunk.
   * Override for an STT plugin. */
  async sttTranscribe(
    _audio: Buffer,
    _sampleRate: number,
    _options?: SttOptions
  ): Promise<SttEvent> {
    throw new HookUnimplemented("STT not implemented");
  }

  /**
   * Transcribe live, emitting partial results as the audio arrives.
   *
   * The streaming half of `SttProcess`, as an async generator — which is what a
   * TypeScript author reaches for and what `for await` consumes. Implementing
   * it takes precedence over `sttTranscribe`, which the SDK otherwise emulates
   * by buffering the whole utterance.
   *
   * ```typescript
   * async *sttTranscribeStream(audio: AsyncIterable<AudioChunk>) {
   *   for await (const chunk of audio) {
   *     const partial = this.decoder.feed(chunk.data);
   *     if (partial) yield { text: partial, isFinal: false };
   *   }
   *   yield { text: this.decoder.finish(), isFinal: true };
   * }
   * ```
   *
   * Back-pressure is real: the SDK holds at most
   * `limits.STT_AUDIO_CHANNEL_CAPACITY` chunks, the same bound the daemon's
   * half of the bridge uses, and pauses the gRPC stream past that.
   */
  sttTranscribeStream(
    _audio: AsyncIterable<AudioChunk>,
    _options?: SttOptions
  ): AsyncIterable<SttEvent> {
    throw new HookUnimplemented("streaming STT not implemented");
  }

  // ── STT model lifecycle ──
  //
  // Optional in the strong sense: the daemon routes all three through
  // `optional_hook`, so a plugin that manages its own models simply does not
  // override them and the daemon behaves as it did before the hooks existed.
  // Implementing them is what makes idle-unload actually free VRAM.

  /** Load the recognizer model. `modelPath` is resolved by the daemon out of
   * its own catalog — a plugin that ships its own models ignores it. `useGpu`
   * is false on the daemon's degraded retry after a GPU load failed. */
  async sttLoad(_modelPath: string, _useGpu: boolean): Promise<void> {
    throw new HookUnimplemented("this plugin has no explicit STT model lifecycle");
  }

  /** Drop the recognizer model and free its memory. */
  async sttUnload(): Promise<void> {
    throw new HookUnimplemented("this plugin has no explicit STT model lifecycle");
  }

  /** Report whether the model is resident, so idle-unload can work. */
  async sttLoadState(): Promise<SttLoadStatus> {
    throw new HookUnimplemented("this plugin has no explicit STT model lifecycle");
  }

  /**
   * Synthesize as a chunk stream, for first-audio latency.
   *
   * An async generator: yield `AudioChunk`s (or bare `Buffer`s) as fast as the
   * engine produces them, and set `sampleRate` on the first. The SDK marks the
   * last chunk for you.
   *
   * NOTE: no daemon call site exists for `TtsSynthesizeStream` yet — the rpc is
   * declared and unrouted (`spec/hooks.yaml`). Implementing it costs nothing and
   * is what the three SDKs agreeing looks like, but do not expect it to be
   * exercised until the daemon's voice pipeline calls it.
   */
  ttsSynthesizeStream(
    _text: string,
    _voiceId: string,
    _speed: number,
    _pitch: number
  ): AsyncIterable<AudioChunk | Buffer> {
    throw new HookUnimplemented("streaming TTS not implemented");
  }

  /**
   * Activate a licensed voice with a one-time content-encryption key.
   *
   * `cek` is a raw secret: seal it under a machine-bound key, never write it out
   * in the clear, never log it. Most TTS plugins have no protected voice and
   * should not override this.
   *
   * Unlike the other optional hooks the daemon does NOT read a failure here as
   * "hook absent" — it propagates and the activation fails. Throw only when
   * activation really did not happen.
   */
  async ttsActivate(_cek: Buffer, _voiceId: string): Promise<void> {
    throw new HookUnimplemented("this plugin has no protected voice to activate");
  }

  /**
   * Stream a model completion. The whole of the `ai_provider` capability.
   *
   * An async generator: yield `AiChunk`s, or bare strings for plain text
   * deltas. The SDK appends the terminating `done` chunk when the generator
   * returns, so the last thing you yield can be content.
   *
   * ```typescript
   * async *aiComplete(req: AiCompleteRequest) {
   *   for await (const token of this.client.stream(req.messages, req.model)) {
   *     yield token;                              // a text delta
   *   }
   *   yield { toolCall: { id: "1", name: "get_time", argumentsJson: "{}" } };
   * }
   * ```
   */
  aiComplete(_request: AiCompleteRequest): AsyncIterable<AiChunk | string> {
    throw new HookUnimplemented("this plugin is not an AI provider");
  }

  /**
   * @deprecated The daemon has no call site — `all_ai_providers` builds every
   * plugin provider with `supports_model_discovery: false`, so the model picker
   * never asks. Kept so an existing plugin keeps compiling.
   */
  async aiGetModels(): Promise<{ models: AiModelInfo[]; defaultModel: string }> {
    return { models: [], defaultModel: "" };
  }
  async getActionTypes(): Promise<ActionTypeDef[]> {
    return [];
  }
  async executeAction(
    _actionType: string,
    _paramsJson: string
  ): Promise<ActionResult> {
    return { success: false, error: "Not implemented", result: "" };
  }
  async getTriggerTypes(): Promise<TriggerTypeDef[]> {
    return [];
  }
  async getUiContributions(): Promise<UiContribution[]> {
    return [];
  }
  /** Handle a call from this plugin's UI iframe (`CallFromUi`).
   *
   * Override this to implement UI→backend communication. `paramsJson` is the
   * raw JSON the iframe sent. Return either:
   *
   * - a `UiCallResult` (`{ resultJson, error }`) — used verbatim;
   * - a string — used as `resultJson` as-is;
   * - any other value — auto-serialized into `resultJson`;
   * - `null`/`undefined` — an empty success.
   *
   * A thrown error is reported in the response's `error` field. */
  async handleUiCall(method: string, _paramsJson: string): Promise<unknown> {
    return { error: `No UI call handler implemented (method: ${method})` };
  }
  async onConfigChanged(_config: Record<string, unknown>): Promise<void> {}
  /** Called when the daemon's UI language changes. Override to update locale. */
  async onLanguageChanged(_language: string): Promise<void> {}
  /** Called when active trigger types change. Override for custom logic. */
  async onActiveTriggers(_activeTypes: string[]): Promise<void> {}
  async onShutdown(): Promise<void> {}
  async healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return { healthy: true, status: "ok" };
  }

  // ── Events ──

  /** Source id hint used by this plugin. Display-only now — daemon no longer filters. */
  sourceId(): string { return ""; }

  /** Daemon host event types to subscribe to. Chat events are NOT here —
   * override `onConversationEvent` instead (fed by the chat firehose). */
  subscribedEvents(): string[] { return []; }

  /** Raw event handler (fallback for untyped daemon events). */
  async onEvent(_eventType: string, _payload: Record<string, unknown>): Promise<void> {}

  /** Called for every chat event in every conversation — tool calls, text
   * deltas, user messages, errors. Only fires for plugins with the `client`
   * capability. `event` is a decoded `ConversationEventMsg`. */
  async onConversationEvent(_convId: string, _event: Record<string, unknown>): Promise<void> {}

  async onStateChanged(_event: StateChangedEvent): Promise<void> {}

  async onCommandTriggered(_event: CommandTriggeredEvent): Promise<void> {}

  async onCommandCompleted(_event: CommandCompletedEvent): Promise<void> {}

  // ── Convenience methods ──

  /** Log an info message to the daemon. */
  async logInfo(msg: string): Promise<void> { if (this.host) await this.host.log("info", msg); }
  /** Log a warning message to the daemon. */
  async logWarn(msg: string): Promise<void> { if (this.host) await this.host.log("warn", msg); }
  /** Log an error message to the daemon. */
  async logError(msg: string): Promise<void> { if (this.host) await this.host.log("error", msg); }
  /** Fire a trigger with an optional payload object (auto-serialized). */
  async fireTrigger(triggerType: string, payload?: Record<string, unknown>): Promise<void> {
    if (this.host) await this.host.fireTrigger(triggerType, payload ? JSON.stringify(payload) : "{}");
  }
  /** Push an event to this plugin's UI contributions (the reverse of `handleUiCall`). */
  async pushToUi(event: string, payload?: Record<string, unknown>): Promise<void> {
    if (this.host) await this.host.pushToUi(event, payload ? JSON.stringify(payload) : "{}");
  }
  /** Publish a variable commands and other plugins can read. */
  async setVariable(name: string, value: string, scope: string = "session"): Promise<void> {
    if (this.host) await this.host.setVariable(name, value, scope);
  }

  // ── Internal ──

  private parseArgs(): { daemonAddr: string; pluginId: string; authToken: string } {
    const args = process.argv.slice(2);
    let daemonAddr = "";
    let pluginId = "";
    let authToken = "";
    for (const arg of args) {
      if (arg.startsWith("--daemon-addr=")) daemonAddr = arg.split("=", 2)[1];
      if (arg.startsWith("--plugin-id=")) pluginId = arg.split("=", 2)[1];
      if (arg.startsWith("--auth-token=")) authToken = arg.split("=", 2)[1];
    }
    if (!daemonAddr || !pluginId) {
      console.error("Usage: --daemon-addr=HOST:PORT --plugin-id=ID");
      this.exitProcess(1);
    }
    return { daemonAddr, pluginId, authToken };
  }

  /** Whether the subclass replaced one of `Plugin`'s own methods. */
  private overrides(name: keyof Plugin): boolean {
    return (this as any)[name] !== (Plugin.prototype as any)[name];
  }

  private async discoverCapabilities(): Promise<string[]> {
    const caps: string[] = [];
    if ((await this.listTools()).length > 0) caps.push("tools");
    if ((await this.ttsListVoices()).length > 0) caps.push("tts");
    if ((await this.sttGetLanguages()).length > 0) caps.push("stt");
    const { models } = await this.aiGetModels();
    // `aiComplete` decides this, not `aiGetModels`: `AiGetModels` is deprecated
    // and defaults to empty, so a provider that implemented the hook that
    // matters used to register without the capability that names it.
    if (models.length > 0 || this.overrides("aiComplete")) caps.push("ai_provider");
    if ((await this.getActionTypes()).length > 0) caps.push("actions");
    if ((await this.getTriggerTypes()).length > 0) caps.push("triggers");
    if ((await this.getUiContributions()).length > 0) caps.push("ui_contributions");
    if (this.isClient()) caps.push("client");
    return caps;
  }

  /**
   * The complete `PluginCapabilityService` handler map — one entry per method
   * the proto declares, checked against the descriptor by `addServiceChecked`.
   *
   * Every entry dispatches to a real method on `Plugin`. An un-overridden hook
   * throws `HookUnimplemented`, which `wrapHandler` and `failStream` turn into
   * the transport's "no such hook" status — the daemon's `optional_hook` reads
   * that as absence rather than as a fault. That is the whole reason no entry
   * here is a hard-coded stub: "this plugin does not do TTS" and "this SDK
   * cannot do TTS" have to be distinguishable, and they are only distinguishable
   * if the second one has stopped being true.
   */
  private capabilityHandlers(): HandlerMap {
    return {
      ListTools: this.wrapHandler(this.handleListTools.bind(this)),
      CallTool: this.wrapHandler(this.handleCallTool.bind(this)),
      TtsSynthesize: this.wrapHandler(this.handleTtsSynthesize.bind(this)),
      TtsListVoices: this.wrapHandler(this.handleTtsListVoices.bind(this)),
      TtsGetConfigFields: this.wrapHandler(this.handleTtsGetConfigFields.bind(this)),
      SttGetLanguages: this.wrapHandler(this.handleSttGetLanguages.bind(this)),
      SttGetConfigFields: this.wrapHandler(this.handleSttGetConfigFields.bind(this)),
      AiGetModels: this.wrapHandler(this.handleAiGetModels.bind(this)),
      ExecuteAction: this.wrapHandler(this.handleExecuteAction.bind(this)),
      GetPluginActionTypes: this.wrapHandler(this.handleGetActionTypes.bind(this)),
      GetPluginTriggerTypes: this.wrapHandler(this.handleGetTriggerTypes.bind(this)),
      GetUiContributions: this.wrapHandler(this.handleGetUiContributions.bind(this)),
      CallFromUi: this.wrapHandler(this.handleCallFromUi.bind(this)),
      OnConfigChanged: this.wrapHandler(this.handleOnConfigChanged.bind(this)),
      OnActiveTriggers: this.wrapHandler(this.handleOnActiveTriggers.bind(this)),
      OnLanguageChanged: this.wrapHandler(this.handleOnLanguageChanged.bind(this)),
      Shutdown: this.wrapHandler(this.handleShutdown.bind(this)),
      HealthCheck: this.wrapHandler(this.handleHealthCheck.bind(this)),
      TtsActivate: this.wrapHandler(this.handleTtsActivate.bind(this)),
      SttLoad: this.wrapHandler(this.handleSttLoad.bind(this)),
      SttUnload: this.wrapHandler(this.handleSttUnload.bind(this)),
      SttGetLoadState: this.wrapHandler(this.handleSttGetLoadState.bind(this)),
      // Streaming RPCs.
      TtsSynthesizeStream: this.wrapStream(this.handleTtsSynthesizeStream.bind(this)),
      SttProcess: this.wrapStream(this.handleSttProcess.bind(this)),
      AiComplete: this.wrapStream(this.handleAiComplete.bind(this)),
    } as unknown as HandlerMap;
  }

  /**
   * Unary handler wrapper. Three outcomes, three different answers:
   *
   * - `HookUnimplemented` → `UNIMPLEMENTED`, i.e. "this hook is absent".
   * - a `PluginError` → its fixed transport status. These hooks have no in-band
   *   failure slot, which is the one place `grpcStatus()` is right.
   * - anything else → `INTERNAL`, the honest answer for an unclassified throw.
   */
  private wrapHandler(handler: (call: any) => Promise<any>) {
    return (call: any, callback: grpc.sendUnaryData<any>) => {
      // Every unary capability call enters the invocation store here, not on
      // the three arms the daemon stamps today. A rule naming specific arms
      // goes stale in silence: a fourth stamped call site would produce a lease
      // this SDK receives and drops, with nothing anywhere reporting it. A call
      // with no lease enters no store at all, so this costs one map lookup.
      withCause(causeFromCall(call), () => handler(call))
        .then((result) => callback(null, result))
        .catch((err: unknown) => {
          if (err instanceof HookUnimplemented) {
            callback({ code: grpc.status.UNIMPLEMENTED, details: err.message });
            return;
          }
          callback(PluginError.from(err).toServiceError());
        });
    };
  }

  /**
   * The streaming counterpart of `wrapHandler`'s invocation store.
   *
   * The three streaming handlers are bound straight into the map because their
   * error path is `failStream`, not a callback — but they hand a context to
   * plugin code just as the unary ones do, so a trigger fired from inside one
   * must be attributed the same way.
   */
  private wrapStream(handler: (call: any) => unknown) {
    return (call: any) => withCause(causeFromCall(call), () => handler(call));
  }

  /** The same three outcomes, on a server-streaming call. */
  private failStream(call: any, err: unknown): void {
    if (err instanceof HookUnimplemented) {
      call.emit("error", { code: grpc.status.UNIMPLEMENTED, details: err.message });
      return;
    }
    call.emit("error", PluginError.from(err).toServiceError());
  }

  // ── gRPC handlers ──

  private async handleListTools(_call: any) {
    const tools = await this.listTools();
    return {
      tools: tools.map((t) => ({
        name: t.name,
        description: t.description,
        parametersJson: t.parametersJson,
      })),
    };
  }

  private async handleCallTool(call: any) {
    const { toolName, argumentsJson } = call.request;
    // In-band, never a gRPC error: a failed tool call is data the AI loop has
    // to read. "You have no API key configured" is the model's cue to tell the
    // user what to do, and a transport error hides it from the model entirely.
    try {
      const result = await this.callTool(toolName, argumentsJson);
      return {
        success: result.success,
        result: result.result,
        error: result.error || "",
        errorDetail: result.errorDetail,
      };
    } catch (e: unknown) {
      return PluginError.from(e).toResponse();
    }
  }

  private async handleTtsSynthesize(call: any) {
    const { text, voiceId, speed, pitch } = call.request;
    const audio = await this.ttsSynthesize(text, voiceId, speed, pitch);
    return {
      audioData: audio.data,
      format: audio.format,
      sampleRate: audio.sampleRate,
      durationMs: audio.durationMs,
    };
  }

  private async handleTtsListVoices(_call: any) {
    const voices = await this.ttsListVoices();
    return {
      voices: voices.map((v) => ({
        id: v.id,
        name: v.name,
        language: v.language,
        gender: v.gender,
        previewUrl: v.previewUrl || "",
      })),
    };
  }

  private async handleSttGetLanguages(_call: any) {
    const languages = await this.sttGetLanguages();
    return { languages };
  }

  // `PluginConfigFieldsResponse.config_fields` is loaded with `keepCase: false`,
  // so the wire object's key is `configFields`. A `config_fields` key is silently
  // dropped by protobufjs and the daemon sees an empty field list.

  private async handleTtsGetConfigFields(_call: any) {
    return { configFields: await this.ttsConfigFields() };
  }

  private async handleSttGetConfigFields(_call: any) {
    return { configFields: await this.sttConfigFields() };
  }

  /** Bidi-streaming `SttProcess`. Streams live into `sttTranscribeStream` when
   *  the plugin has one; otherwise buffers the utterance for `sttTranscribe`. */
  private handleSttProcess(call: any): void {
    if (this.overrides("sttTranscribeStream")) {
      void this.sttProcessStreaming(call);
      return;
    }

    const chunks: Buffer[] = [];
    let sampleRate = 0;
    let options: SttOptions | undefined;
    let finished = false;
    const finish = async () => {
      if (finished) return;
      finished = true;
      try {
        const ev = await this.sttTranscribe(Buffer.concat(chunks), sampleRate, options);
        call.write(sttEventWire(ev));
        call.end();
      } catch (e: unknown) {
        this.failStream(call, e);
      }
    };
    call.on("data", (chunk: any) => {
      if (sampleRate === 0 && chunk.sampleRate) sampleRate = chunk.sampleRate;
      // Per-utterance decoding options ride on the first chunk only.
      if (!options && chunk.options) options = chunk.options as SttOptions;
      if (chunk.data && chunk.data.length) chunks.push(Buffer.from(chunk.data));
      if (chunk.isLast) void finish();
    });
    call.on("end", () => {
      void finish();
    });
  }

  /**
   * The streaming half: an async queue between the inbound gRPC stream and the
   * plugin's generator.
   *
   * Bounded at `limits.STT_AUDIO_CHANNEL_CAPACITY`, the same number the
   * daemon's half of the bridge uses — the smaller of two channels in series is
   * the real capacity, and a smaller SDK-side buffer is exactly how streaming
   * STT once lost everything past the first fraction of an utterance. Past the
   * bound the gRPC stream is paused, so the sender feels the back-pressure
   * rather than the audio being dropped.
   */
  private async sttProcessStreaming(call: any): Promise<void> {
    const queue: AudioChunk[] = [];
    let waiting: (() => void) | null = null;
    let ended = false;
    let paused = false;
    let options: SttOptions | undefined;
    let sawFirst = false;

    const wake = () => {
      const w = waiting;
      waiting = null;
      w?.();
    };

    call.on("data", (chunk: any) => {
      if (!sawFirst) {
        sawFirst = true;
        if (chunk.options) options = chunk.options as SttOptions;
      }
      queue.push({
        data: chunk.data && chunk.data.length ? Buffer.from(chunk.data) : Buffer.alloc(0),
        isLast: !!chunk.isLast,
        sampleRate: chunk.sampleRate || 0,
      });
      if (queue.length >= STT_AUDIO_CHANNEL_CAPACITY && !paused) {
        paused = true;
        call.pause();
      }
      wake();
    });
    call.on("end", () => {
      ended = true;
      wake();
    });
    call.on("error", () => {
      ended = true;
      wake();
    });

    const self = this;
    async function* audio(): AsyncGenerator<AudioChunk> {
      for (;;) {
        while (queue.length === 0 && !ended) {
          await new Promise<void>((resolve) => {
            waiting = resolve;
          });
        }
        if (queue.length === 0) return;
        const chunk = queue.shift()!;
        if (paused && queue.length < STT_AUDIO_CHANNEL_CAPACITY) {
          paused = false;
          call.resume();
        }
        yield chunk;
        if (chunk.isLast) return;
      }
    }

    try {
      for await (const ev of self.sttTranscribeStream(audio(), options)) {
        call.write(sttEventWire(ev));
      }
      call.end();
    } catch (e: unknown) {
      this.failStream(call, e);
    }
  }

  /** Server-streaming TTS. Unrouted daemon-side today; see the hook doc. */
  private async handleTtsSynthesizeStream(call: any): Promise<void> {
    const { text, voiceId, speed, pitch } = call.request;
    try {
      // Held one behind, so `isLast` lands on the real last chunk instead of on
      // an empty trailing one. The daemon's reader stops at `isLast`; an author
      // who already set it keeps it.
      let pending: AudioChunk | null = null;
      for await (const value of this.ttsSynthesizeStream(text, voiceId, speed, pitch)) {
        const chunk: AudioChunk = Buffer.isBuffer(value) ? { data: value } : value;
        if (pending) call.write(audioChunkWire(pending));
        pending = chunk;
      }
      if (pending) call.write(audioChunkWire({ ...pending, isLast: true }));
      call.end();
    } catch (e: unknown) {
      this.failStream(call, e);
    }
  }

  private async handleTtsActivate(call: any) {
    const { cek, voiceId } = call.request;
    await this.ttsActivate(Buffer.from(cek ?? []), voiceId ?? "");
    return {};
  }

  private async handleSttLoad(call: any) {
    await this.sttLoad(call.request.modelPath ?? "", !!call.request.useGpu);
    return {};
  }

  private async handleSttUnload(_call: any) {
    await this.sttUnload();
    return {};
  }

  private async handleSttGetLoadState(_call: any) {
    const status = await this.sttLoadState();
    return { state: status.state, detail: status.detail ?? "" };
  }

  /** Server-streaming `AiComplete`. */
  private async handleAiComplete(call: any): Promise<void> {
    const req = aiRequestFromWire(call.request);
    let last: AiChunk | null = null;
    try {
      for await (const value of this.aiComplete(req)) {
        const chunk: AiChunk = typeof value === "string" ? { text: value } : value;
        last = chunk;
        call.write(aiChunkWire(chunk));
      }
    } catch (e: unknown) {
      if (e instanceof HookUnimplemented) {
        this.failStream(call, e);
        return;
      }
      // `PluginAiStreamChunk` HAS an in-band error slot, so the failure travels
      // as data the daemon's bridge already reads rather than as a transport
      // fault that would look like the plugin dying. The `error` oneof arm and
      // the structured `errorDetail` beside it are both set: the oneof is what
      // tells a receiver the stream ended badly, and an old daemon reads only
      // that.
      const err = PluginError.from(e);
      call.write({ error: err.toErrorString(), errorDetail: err.toDetail() });
      call.end();
      return;
    }
    // Terminate the stream for the author: a completion that never says `done`
    // leaves the daemon's reader waiting on a stream that has already closed,
    // and forgetting it is the easiest mistake to make here.
    if (!last || (!last.done && !last.error)) call.write({ done: true });
    call.end();
  }

  private async handleAiGetModels(_call: any) {
    const { models, defaultModel } = await this.aiGetModels();
    return {
      models: models.map((m) => ({ id: m.id, name: m.name })),
      defaultModel,
    };
  }

  private async handleExecuteAction(call: any) {
    const { actionType, paramsJson } = call.request;
    try {
      const result = await this.executeAction(actionType, paramsJson);
      return {
        success: result.success,
        result: result.result,
        error: result.error || "",
        errorDetail: result.errorDetail,
      };
    } catch (e: unknown) {
      return PluginError.from(e).toResponse();
    }
  }

  private async handleGetActionTypes(_call: any) {
    const types = await this.getActionTypes();
    return { types };
  }

  private async handleGetTriggerTypes(_call: any) {
    const types = await this.getTriggerTypes();
    return { types };
  }

  private async handleGetUiContributions(_call: any) {
    const contributions = await this.getUiContributions();
    return { contributions: contributions.map(c => ({
      id: c.id || "",
      slot: c.slot || "",
      cssTarget: c.cssTarget || "",
      position: c.position || "",
      url: c.url || "",
      label: c.label || "",
      iconSvg: c.iconSvg || "",
      width: c.width || 0,
      height: c.height || 0,
      transparent: c.transparent || false,
      pointerEvents: c.pointerEvents !== false,
      zIndex: c.zIndex || 0,
      props: c.props || {},
    })) };
  }

  private async handleCallFromUi(call: any) {
    const method: string = call.request.method ?? "";
    const paramsJson: string = call.request.paramsJson ?? "";

    let result: unknown;
    try {
      result = await this.handleUiCall(method, paramsJson);
    } catch (e: unknown) {
      // The daemon relays `errorDetail` on to the panel as
      // `CallPluginFromUiResponse.error_detail`, so a plugin's own UI can render
      // the same config-field link a tool failure would.
      const err = PluginError.from(e);
      return { resultJson: "", error: err.toErrorString(), errorDetail: err.toDetail() };
    }

    if (result === null || result === undefined) return { resultJson: "", error: "" };
    if (typeof result === "string") return { resultJson: result, error: "" };
    if (typeof result === "object" && ("resultJson" in result || "error" in result)) {
      const r = result as UiCallResult;
      return { resultJson: r.resultJson ?? "", error: r.error ?? "", errorDetail: r.errorDetail };
    }
    try {
      return { resultJson: JSON.stringify(result), error: "" };
    } catch (e: any) {
      return {
        resultJson: "",
        error: `handleUiCall returned a non-serializable result: ${e.message}`,
      };
    }
  }

  private async handleOnConfigChanged(call: any) {
    const configJson = call.request.configJson;
    try {
      this.config = JSON.parse(configJson);
    } catch {
      this.config = {};
    }
    await this.onConfigChanged(this.config);
    return {};
  }

  private async handleOnActiveTriggers(call: any) {
    const types: string[] = call.request.triggerTypes || [];
    this.activeTriggers = new Set(types);
    await this.onActiveTriggers(types);
    return {};
  }

  private async handleOnLanguageChanged(call: any) {
    const language: string = call.request.language || "en";
    this.language = language;
    await this.onLanguageChanged(language);
    return {};
  }

  private async handleShutdown(_call: any) {
    await this.onShutdown();
    const timer = setTimeout(() => this.exitProcess(0), 100);
    if (typeof timer.unref === "function") timer.unref();
    return {};
  }

  private async handleHealthCheck(_call: any) {
    const { healthy, status } = await this.healthCheck();
    return { healthy, status };
  }

  /** Attach to the chat firehose — runs for the lifetime of the plugin
   *  process, auto-reconnecting on error. Events for every conversation are
   *  dispatched to `onConversationEvent`. */
  private startChatFirehose(): void {
    const connect = () => {
      if (!this.daemon || this.stopped) return;
      const stream = this.daemon.subscribeChatEvents({});
      console.log("Chat firehose active");
      stream.on("data", async (fe: any) => {
        try {
          if (fe?.event) {
            await this.onConversationEvent(fe.conversationId, fe.event);
          }
        } catch (e) {
          console.warn(`onConversationEvent handler threw: ${e}`);
        }
      });
      stream.on("error", (err: Error) => {
        if (this.stopped) return;
        console.warn(`Chat firehose error: ${err.message}, reconnecting...`);
        this.reconnect(connect);
      });
      stream.on("end", () => {
        if (this.stopped) return;
        console.log("Chat firehose ended, reconnecting...");
        this.reconnect(connect);
      });
    };
    connect();
  }

  /**
   * Reconnect in two seconds, unless `stopServing` has run.
   *
   * `unref`'d: a pending reconnect must not be the reason a process that has
   * finished its work stays alive — which is precisely what kept the level-2
   * harness's test runner from ever exiting.
   */
  private reconnect(connect: () => void): void {
    if (this.stopped) return;
    const timer = setTimeout(() => {
      if (!this.stopped) connect();
    }, 2000);
    if (typeof timer.unref === "function") timer.unref();
  }

  private startEventLoop(eventTypes: string[], excludeSourceId: string): void {
    const connect = () => {
      const stream = this.host!.subscribeEvents(eventTypes, excludeSourceId);
      console.log("Event subscription active");
      stream.on("data", async (event: any) => {
        let payload: Record<string, unknown> = {};
        try {
          payload = event.payloadJson ? JSON.parse(event.payloadJson) : {};
        } catch { /* ignore parse errors */ }
        await this.dispatchEvent(event.eventType, payload);
      });
      stream.on("error", (err: Error) => {
        if (this.stopped) return;
        console.warn(`Event stream error: ${err.message}, reconnecting...`);
        this.reconnect(connect);
      });
      stream.on("end", () => {
        if (this.stopped) return;
        console.log("Event subscription ended, reconnecting...");
        this.reconnect(connect);
      });
    };
    connect();
  }

  /**
   * Decode one daemon event and hand it to the typed hook, then to `onEvent`.
   *
   * The payload keys are the daemon's, and the daemon's are **snake_case**:
   * `AstraEvent` is `#[serde(tag = "type", rename_all = "snake_case")]`, and
   * `rename_all` on an enum renames its *variants*, not their fields — so the
   * wire carries `{"type":"command_triggered","command_id":…,"command_name":…,
   * "trigger_text":…}` (`astra-core/src/event.rs`). This used to `as`-cast the
   * payload to a camelCase shape, which the compiler happily agreed was
   * `string` and which was `undefined` on every event forever.
   *
   * `@internal`, and not `private`, so the test harness delivers events through
   * this function instead of past it. A harness with its own dispatch would be
   * testing itself.
   */
  async dispatchEvent(eventType: string, payload: Record<string, unknown>): Promise<void> {
    const str = (key: string): string => {
      const value = payload[key];
      return typeof value === "string" ? value : "";
    };
    switch (eventType) {
      case "state_changed":
        await this.onStateChanged({ previous: str("previous"), current: str("current") });
        break;
      case "command_triggered":
        await this.onCommandTriggered({
          commandId: str("command_id"),
          commandName: str("command_name"),
          triggerText: str("trigger_text"),
        });
        break;
      case "command_completed":
        await this.onCommandCompleted({
          commandId: str("command_id"),
          commandName: str("command_name"),
          success: payload.success === true,
        });
        break;
    }
    await this.onEvent(eventType, payload);
  }
}
