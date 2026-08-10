/**
 * Base Plugin class — extend this to build an Astra plugin.
 */

import * as grpc from "@grpc/grpc-js";
import { HostClient } from "./host-client";
import { service } from "./proto-loader";
import { addServiceChecked, type HandlerMap } from "./service-contract";
import { capabilityAuthMode, guardHandlers } from "./capability-auth";
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
} from "./types";
import { DaemonClient } from "./daemon-client";

export abstract class Plugin {
  /** Client for calling daemon services. Available after registration. */
  host: HostClient | null = null;

  /** Full daemon API client. Only available if `isClient()` returns true. */
  daemon: DaemonClient | null = null;

  /** Current plugin config (populated after registration). */
  config: Record<string, unknown> = {};

  /** Current daemon UI language (e.g. "en", "ru", "uk"). */
  language: string = "en";

  /** Set of active trigger types (auto-updated by daemon). */
  activeTriggers: Set<string> = new Set();

  private server: grpc.Server | null = null;

  /** Parse CLI args, start gRPC server, register, serve until shutdown. */
  run(): void {
    const args = this.parseArgs();

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
          process.exit(1);
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

          // Pass initial language
          if (response.language) {
            this.language = response.language;
            await this.onLanguageChanged(response.language);
          }

          // Pass initial config
          if (response.configJson) {
            try {
              this.config = JSON.parse(response.configJson);
            } catch {
              this.config = {};
            }
            await this.onConfigChanged(this.config);
          }

          // Start event subscription
          const eventTypes = this.subscribedEvents();
          if (eventTypes.length > 0) {
            const excludeSource = this.sourceId();
            console.log(`Subscribing to events: ${eventTypes.join(", ")}${excludeSource ? ` (exclude: ${excludeSource})` : ""}`);
            this.startEventLoop(eventTypes, excludeSource);
          }
        } catch (e: any) {
          console.error("Registration failed:", e.message);
          process.exit(1);
        }
      }
    );

    // Graceful shutdown
    const shutdown = () => {
      console.log("Shutting down...");
      this.onShutdown().then(() => {
        server.tryShutdown(() => process.exit(0));
      });
    };
    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);
  }

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
    throw new Error("TTS not implemented");
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
   * calls this once the stream ends. Override for an STT plugin. */
  async sttTranscribe(_audio: Buffer, _sampleRate: number): Promise<SttEvent> {
    throw new Error("STT not implemented");
  }
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

  async onStateChanged(_event: { previous: string; current: string }): Promise<void> {}

  async onCommandTriggered(_event: { commandId: string; commandName: string; variables: Record<string, string> }): Promise<void> {}

  async onCommandCompleted(_event: { commandId: string; commandName: string; success: boolean }): Promise<void> {}

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
      process.exit(1);
    }
    return { daemonAddr, pluginId, authToken };
  }

  private async discoverCapabilities(): Promise<string[]> {
    const caps: string[] = [];
    if ((await this.listTools()).length > 0) caps.push("tools");
    if ((await this.ttsListVoices()).length > 0) caps.push("tts");
    if ((await this.sttGetLanguages()).length > 0) caps.push("stt");
    const { models } = await this.aiGetModels();
    if (models.length > 0) caps.push("ai_provider");
    if ((await this.getActionTypes()).length > 0) caps.push("actions");
    if ((await this.getTriggerTypes()).length > 0) caps.push("triggers");
    if ((await this.getUiContributions()).length > 0) caps.push("ui_contributions");
    if (this.isClient()) caps.push("client");
    return caps;
  }

  /**
   * The complete `PluginCapabilityService` handler map — one entry per method
   * the proto declares, checked against the descriptor by `addServiceChecked`.
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
      // Streaming RPCs — stubs
      TtsSynthesizeStream: (call: any) => {
        call.emit("error", {
          code: grpc.status.UNIMPLEMENTED,
          details: "Streaming TTS not implemented",
        });
      },
      SttProcess: this.handleSttProcess.bind(this),
      AiComplete: (call: any) => {
        call.emit("error", {
          code: grpc.status.UNIMPLEMENTED,
          details: "AI provider not implemented",
        });
      },
    } as unknown as HandlerMap;
  }

  private wrapHandler(handler: (call: any) => Promise<any>) {
    return (call: any, callback: grpc.sendUnaryData<any>) => {
      handler(call)
        .then((result) => callback(null, result))
        .catch((err: Error) =>
          callback({
            code: grpc.status.INTERNAL,
            details: err.message,
          })
        );
    };
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
    const result = await this.callTool(toolName, argumentsJson);
    return {
      success: result.success,
      result: result.result,
      error: result.error || "",
    };
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

  /** Bidi-streaming `SttProcess`: accumulate `PluginAudioChunk`s, then run
   *  the non-streaming `sttTranscribe` and emit a single `PluginSttEvent`. */
  private handleSttProcess(call: any): void {
    const chunks: Buffer[] = [];
    let sampleRate = 0;
    let finished = false;
    const finish = async () => {
      if (finished) return;
      finished = true;
      try {
        const ev = await this.sttTranscribe(Buffer.concat(chunks), sampleRate);
        call.write({
          text: ev.text,
          isFinal: ev.isFinal ?? true,
          confidence: ev.confidence ?? 1.0,
          language: ev.language ?? "",
        });
        call.end();
      } catch (e: any) {
        call.emit("error", { code: grpc.status.INTERNAL, details: e.message });
      }
    };
    call.on("data", (chunk: any) => {
      if (sampleRate === 0 && chunk.sampleRate) sampleRate = chunk.sampleRate;
      if (chunk.data && chunk.data.length) chunks.push(Buffer.from(chunk.data));
      if (chunk.isLast) void finish();
    });
    call.on("end", () => {
      void finish();
    });
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
    const result = await this.executeAction(actionType, paramsJson);
    return {
      success: result.success,
      result: result.result,
      error: result.error || "",
    };
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
    } catch (e: any) {
      return { resultJson: "", error: String(e?.message ?? e) };
    }

    if (result === null || result === undefined) return { resultJson: "", error: "" };
    if (typeof result === "string") return { resultJson: result, error: "" };
    if (typeof result === "object" && ("resultJson" in result || "error" in result)) {
      const r = result as UiCallResult;
      return { resultJson: r.resultJson ?? "", error: r.error ?? "" };
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
    setTimeout(() => process.exit(0), 100);
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
      if (!this.daemon) return;
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
        console.warn(`Chat firehose error: ${err.message}, reconnecting...`);
        setTimeout(connect, 2000);
      });
      stream.on("end", () => {
        console.log("Chat firehose ended, reconnecting...");
        setTimeout(connect, 2000);
      });
    };
    connect();
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
        console.warn(`Event stream error: ${err.message}, reconnecting...`);
        setTimeout(connect, 2000);
      });
      stream.on("end", () => {
        console.log("Event subscription ended, reconnecting...");
        setTimeout(connect, 2000);
      });
    };
    connect();
  }

  private async dispatchEvent(eventType: string, payload: Record<string, unknown>): Promise<void> {
    switch (eventType) {
      case "state_changed":
        await this.onStateChanged(payload as { previous: string; current: string });
        break;
      case "command_triggered":
        await this.onCommandTriggered(payload as { commandId: string; commandName: string; variables: Record<string, string> });
        break;
      case "command_completed":
        await this.onCommandCompleted(payload as { commandId: string; commandName: string; success: boolean });
        break;
    }
    await this.onEvent(eventType, payload);
  }
}
