/**
 * Base Plugin class — extend this to build an Astra plugin.
 */

import * as grpc from "@grpc/grpc-js";
import { HostClient } from "./host-client";
import { astraProto } from "./proto-loader";
import type {
  ToolDef,
  ToolResult,
  VoiceInfo,
  AudioData,
  AiModelInfo,
  ActionResult,
  ActionTypeDef,
  TriggerTypeDef,
  UiContribution,
} from "./types";
import { DaemonClient } from "./daemon-client";

const pluginProto = astraProto;

export abstract class Plugin {
  /** Client for calling daemon services. Available after registration. */
  host: HostClient | null = null;

  /** Full daemon API client. Only available if `isClient()` returns true. */
  daemon: DaemonClient | null = null;

  /** Current plugin config (populated after registration). */
  config: Record<string, unknown> = {};

  /** Set of active trigger types (auto-updated by daemon). */
  activeTriggers: Set<string> = new Set();

  private server: grpc.Server | null = null;

  /** Parse CLI args, start gRPC server, register, serve until shutdown. */
  run(): void {
    const args = this.parseArgs();

    const server = new grpc.Server();
    this.server = server;

    // Add PluginCapabilityService
    server.addService(pluginProto.PluginCapabilityService.service, {
      ListTools: this.wrapHandler(this.handleListTools.bind(this)),
      CallTool: this.wrapHandler(this.handleCallTool.bind(this)),
      TtsSynthesize: this.wrapHandler(this.handleTtsSynthesize.bind(this)),
      TtsListVoices: this.wrapHandler(this.handleTtsListVoices.bind(this)),
      SttGetLanguages: this.wrapHandler(this.handleSttGetLanguages.bind(this)),
      AiGetModels: this.wrapHandler(this.handleAiGetModels.bind(this)),
      ExecuteAction: this.wrapHandler(this.handleExecuteAction.bind(this)),
      GetPluginActionTypes: this.wrapHandler(this.handleGetActionTypes.bind(this)),
      GetPluginTriggerTypes: this.wrapHandler(this.handleGetTriggerTypes.bind(this)),
      GetUiContributions: this.wrapHandler(this.handleGetUiContributions.bind(this)),
      OnConfigChanged: this.wrapHandler(this.handleOnConfigChanged.bind(this)),
      OnActiveTriggers: this.wrapHandler(this.handleOnActiveTriggers.bind(this)),
      Shutdown: this.wrapHandler(this.handleShutdown.bind(this)),
      HealthCheck: this.wrapHandler(this.handleHealthCheck.bind(this)),
      // Streaming RPCs — stubs
      TtsSynthesizeStream: (call: any) => {
        call.emit("error", {
          code: grpc.status.UNIMPLEMENTED,
          details: "Streaming TTS not implemented",
        });
      },
      SttProcess: (call: any) => {
        call.emit("error", {
          code: grpc.status.UNIMPLEMENTED,
          details: "STT not implemented",
        });
      },
      AiComplete: (call: any) => {
        call.emit("error", {
          code: grpc.status.UNIMPLEMENTED,
          details: "AI provider not implemented",
        });
      },
    });

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

        // Connect to daemon and register
        this.host = new HostClient(args.daemonAddr, args.pluginId);
        await this.host.connect();

        const capabilities = await this.discoverCapabilities();
        console.log(`Registering with capabilities: ${capabilities.join(", ")}`);

        try {
          const response = await this.host.register(port, capabilities, args.authToken);
          if (!response.success) {
            console.error(`Registration failed: ${response.error}`);
            process.exit(1);
          }
          console.log(
            `Registered successfully. Daemon version: ${response.daemonVersion}`
          );

          // If plugin has client capability and received a session token, create DaemonClient
          if (response.clientSessionToken) {
            this.daemon = new DaemonClient(args.daemonAddr, response.clientSessionToken);
            await this.daemon.connect();
            await this.onDaemonClientReady(this.daemon);
            console.log("DaemonClient connected (plugin has client capability)");
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
  async onConfigChanged(_config: Record<string, unknown>): Promise<void> {}
  /** Called when active trigger types change. Override for custom logic. */
  async onActiveTriggers(_activeTypes: string[]): Promise<void> {}
  async onShutdown(): Promise<void> {}
  async healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return { healthy: true, status: "ok" };
  }

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

  private async handleShutdown(_call: any) {
    await this.onShutdown();
    setTimeout(() => process.exit(0), 100);
    return {};
  }

  private async handleHealthCheck(_call: any) {
    const { healthy, status } = await this.healthCheck();
    return { healthy, status };
  }
}
