/**
 * Level 1 — the in-process harness.
 *
 * ```typescript
 * const h = await Harness.create(myPlugin).withConfig({ default_indent: 4 }).start();
 * const result = await h.callTool("json_format", { json: '{"a":1}' });
 * assert.equal(result.success, true);
 * assert.deepEqual(h.host.firedTriggers(), []);
 * ```
 *
 * No socket, no daemon, no port. What it does have is the SDK's real dispatch:
 * every method here goes through `capabilityHandlers()` and the same wire
 * projections a daemon would drive, so a handler that spells a wire field wrong
 * or answers a status where it should answer in-band fails here rather than on
 * a user's machine. See `calls.ts` for why that matters more than it sounds.
 *
 * What level 1 cannot see is in `MockDaemon` (level 2): handler registration
 * against the descriptor, protobuf encoding, the session-token interceptor and
 * the spawn-token guard. Both levels exist because neither is sufficient.
 */

import type { Plugin } from "../plugin.js";
import type {
  ActionResult,
  ActionTypeDef,
  AiChunk,
  AiCompleteRequest,
  AudioChunk,
  AudioData,
  FieldDef,
  SttEvent,
  SttLoadStatus,
  SttOptions,
  ToolDef,
  ToolResult,
  TriggerTypeDef,
  UiContribution,
  VoiceInfo,
} from "../types.js";
import type { HandlerMap } from "../service-contract.js";
import { validate, type JsonSchema, type ValidationIssue } from "../schema.js";
import { RecordingHost } from "./recording-host.js";
import {
  FakeDuplexCall,
  FakeWritableCall,
  invokeBidi,
  invokeServerStream,
  invokeUnary,
  type FakeStatus,
} from "./calls.js";
import { configFuzz, utteranceChunks } from "./fixtures.js";

/** Anything `Harness.create` accepts: a `Plugin`, or what `plugin()` returned. */
export type Testable = Plugin | { instance: Plugin };

/** A hook answered with a gRPC status instead of a response. */
export class HookStatusError extends Error {
  constructor(
    readonly method: string,
    readonly status: FakeStatus
  ) {
    super(`${method} answered status ${status.code}: ${status.details ?? "(no details)"}`);
    this.name = "HookStatusError";
  }
}

/** Raised by `assertSchemaAccepts` / `assertSchemaRejects`. */
export class SchemaAssertionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SchemaAssertionError";
  }
}

/** How a streaming STT run went. */
export interface SttRun {
  /** Every `SttEvent` the plugin emitted, in order. */
  events: SttEvent[];
  /** Chunks the harness handed to the SDK. */
  sent: number;
  /** Chunks the SDK's inbound bridge accepted before the stream ended. */
  delivered: number;
  /** Times the SDK applied back-pressure. Zero on a short utterance. */
  pauses: number;
  /** Non-null if the hook failed. */
  status: FakeStatus | null;
}

function plugin(target: Testable): Plugin {
  return "instance" in target ? target.instance : target;
}

/**
 * The level-1 harness. Build with `Harness.create`, configure, then `start()`.
 */
export class Harness {
  private started = false;
  private handlers: HandlerMap | null = null;
  private initialConfig: Record<string, unknown> = {};
  private initialLanguage = "en";
  private recordingHost: RecordingHost | null;

  private constructor(readonly plugin: Plugin) {
    this.recordingHost = new RecordingHost();
  }

  /** Wrap a plugin. Nothing runs until `start()`. */
  static create(target: Testable): Harness {
    return new Harness(plugin(target));
  }

  // ── configuration ──

  /** Config delivered before `onStart`, exactly as the daemon would. */
  withConfig(config: Record<string, unknown>): this {
    this.initialConfig = config;
    return this;
  }

  /** Daemon UI language delivered before `onStart`. */
  withLanguage(language: string): this {
    this.initialLanguage = language;
    return this;
  }

  /** Use a host you built — with failure injection already set up, usually. */
  withHost(host: RecordingHost): this {
    this.recordingHost = host;
    return this;
  }

  /**
   * Start with NO host at all.
   *
   * The daemon-less case is worth testing on purpose: `ctx.fireTrigger` throws
   * `NoHostError` here, and a plugin that fires triggers from a constructor or
   * a timer finds out in a test instead of in a log nobody reads.
   */
  withoutHost(): this {
    this.recordingHost = null;
    return this;
  }

  /** The recording host, or `null` if `withoutHost()` was used. */
  get host(): RecordingHost {
    if (!this.recordingHost) {
      throw new Error("this harness was built with `withoutHost()`; there is no RecordingHost");
    }
    return this.recordingHost;
  }

  // ── lifecycle ──

  /**
   * Run the plugin's start-up in the daemon's order: host, config, language,
   * `onStart`. Returns the harness so `await Harness.create(p).start()` reads
   * as one expression.
   */
  async start(): Promise<this> {
    if (this.started) return this;
    this.started = true;
    const p = this.plugin as Plugin & { pluginId: string };
    p.host = this.recordingHost;
    if (!p.pluginId) p.pluginId = this.recordingHost?.getPluginId() ?? "test-plugin";
    // `capabilityHandlers` is `private`, and stays private: `tools/parity/check.py`
    // anchors its scan region on that exact declaration, and TypeScript's
    // `private` is a compile-time promise the SDK's own test harness may keep by
    // agreement rather than by the type system. Nothing outside this package
    // reaches it.
    this.handlers = (this.plugin as unknown as { capabilityHandlers(): HandlerMap })
      .capabilityHandlers();

    p.config = this.initialConfig;
    await this.plugin.onConfigChanged(this.initialConfig);
    p.language = this.initialLanguage;
    await this.plugin.onLanguageChanged(this.initialLanguage);
    await this.plugin.onStart(this.plugin.ctx());
    return this;
  }

  /** Deliver `OnConfigChanged`, through the real handler. */
  async configChanged(config: Record<string, unknown>): Promise<void> {
    await this.unary("OnConfigChanged", { configJson: JSON.stringify(config) });
  }

  /** Deliver `OnLanguageChanged`. */
  async languageChanged(language: string): Promise<void> {
    await this.unary("OnLanguageChanged", { language });
  }

  /** Deliver `OnActiveTriggers`. */
  async activeTriggers(triggerTypes: string[]): Promise<void> {
    await this.unary("OnActiveTriggers", { triggerTypes });
  }

  /** Call `HealthCheck`. */
  async healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return (await this.unary("HealthCheck", {})) as { healthy: boolean; status: string };
  }

  /**
   * Call the plugin's `onShutdown` — NOT the `Shutdown` hook, which calls
   * `process.exit` a hundred milliseconds later and would take the test runner
   * with it. Level 2 exercises the real one in a child process.
   */
  async shutdown(): Promise<void> {
    await this.plugin.onShutdown();
    this.recordingHost?.close();
  }

  /**
   * Push every config in the fuzz set through `OnConfigChanged`, and report
   * which ones the plugin threw on.
   *
   * A plugin is not required to *like* any of them; it is required not to
   * crash, because the daemon delivers config it did not author and a throw
   * here marks the plugin unhealthy.
   */
  async fuzzConfig(): Promise<{ name: string; error: string }[]> {
    const failures: { name: string; error: string }[] = [];
    for (const { name, config } of configFuzz()) {
      try {
        await this.configChanged(config);
      } catch (e) {
        failures.push({ name, error: (e as Error).message });
      }
    }
    await this.configChanged(this.initialConfig);
    return failures;
  }

  // ── tools ──

  /** `ListTools`, as the daemon receives it. */
  async listTools(): Promise<ToolDef[]> {
    const res = (await this.unary("ListTools", {})) as { tools: ToolDef[] };
    return res.tools ?? [];
  }

  /** The declared tool names. */
  async toolNames(): Promise<string[]> {
    return (await this.listTools()).map((t) => t.name);
  }

  /**
   * One tool's parameter schema, parsed.
   *
   * Throws if the tool does not exist or its `parametersJson` is not an object
   * root — both of which reach the model as a tool it cannot call, with no
   * error anywhere.
   */
  async schema(toolName: string): Promise<JsonSchema> {
    const tool = (await this.listTools()).find((t) => t.name === toolName);
    if (!tool) {
      throw new SchemaAssertionError(
        `no tool named ${JSON.stringify(toolName)}; this plugin declares ` +
          `${(await this.toolNames()).map((n) => JSON.stringify(n)).join(", ") || "none"}`
      );
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(tool.parametersJson);
    } catch (e) {
      throw new SchemaAssertionError(
        `${toolName}.parametersJson is not valid JSON: ${(e as Error).message}`
      );
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new SchemaAssertionError(`${toolName}.parametersJson must have an object root`);
    }
    const schema = parsed as JsonSchema;
    if (schema.type !== "object") {
      throw new SchemaAssertionError(
        `${toolName}.parametersJson must declare \`"type": "object"\` — every model provider ` +
          `rejects a tool whose parameters are not an object`
      );
    }
    return schema;
  }

  /** `CallTool`, through the real handler. `args` may be an object or JSON. */
  async callTool(name: string, args: Record<string, unknown> | string = {}): Promise<ToolResult> {
    const argumentsJson = typeof args === "string" ? args : JSON.stringify(args);
    return (await this.unary("CallTool", { toolName: name, argumentsJson })) as ToolResult;
  }

  /**
   * Assert `args` conforms to the tool's declared schema.
   *
   * The type-level counterpart of `assert_schema_matches::<T>()` in Rust: TS
   * cannot compare a runtime schema with a compile-time type, so the honest
   * check is "this value, which the author's type produced, validates".
   *
   * @throws {SchemaAssertionError} listing every violation.
   */
  async assertSchemaAccepts(toolName: string, args: unknown): Promise<void> {
    const issues = validate(await this.schema(toolName), args);
    if (issues.length > 0) {
      throw new SchemaAssertionError(
        `${toolName} rejects arguments its type allows: ${formatIssues(issues)}`
      );
    }
  }

  /** Assert `args` does NOT conform — the half that catches an over-wide schema. */
  async assertSchemaRejects(toolName: string, args: unknown): Promise<void> {
    const issues = validate(await this.schema(toolName), args);
    if (issues.length === 0) {
      throw new SchemaAssertionError(
        `${toolName} accepts ${JSON.stringify(args)}, which the test says it should not. ` +
          `An over-wide schema is how a model learns to send arguments the handler cannot use`
      );
    }
  }

  // ── actions & triggers ──

  async actionTypes(): Promise<ActionTypeDef[]> {
    const res = (await this.unary("GetPluginActionTypes", {})) as { types: ActionTypeDef[] };
    return res.types ?? [];
  }

  async executeAction(
    actionType: string,
    params: Record<string, unknown> | string = {}
  ): Promise<ActionResult> {
    const paramsJson = typeof params === "string" ? params : JSON.stringify(params);
    return (await this.unary("ExecuteAction", { actionType, paramsJson })) as ActionResult;
  }

  async triggerTypes(): Promise<TriggerTypeDef[]> {
    const res = (await this.unary("GetPluginTriggerTypes", {})) as { types: TriggerTypeDef[] };
    return res.types ?? [];
  }

  // ── ui ──

  async uiContributions(): Promise<UiContribution[]> {
    const res = (await this.unary("GetUiContributions", {})) as { contributions: UiContribution[] };
    return res.contributions ?? [];
  }

  async callFromUi(
    method: string,
    params: Record<string, unknown> | string = {}
  ): Promise<{ resultJson: string; error: string }> {
    const paramsJson = typeof params === "string" ? params : JSON.stringify(params);
    return (await this.unary("CallFromUi", { method, paramsJson })) as {
      resultJson: string;
      error: string;
    };
  }

  // ── voice ──

  async voices(): Promise<VoiceInfo[]> {
    const res = (await this.unary("TtsListVoices", {})) as { voices: VoiceInfo[] };
    return res.voices ?? [];
  }

  async ttsConfigFields(): Promise<FieldDef[]> {
    const res = (await this.unary("TtsGetConfigFields", {})) as { configFields: FieldDef[] };
    return res.configFields ?? [];
  }

  async sttConfigFields(): Promise<FieldDef[]> {
    const res = (await this.unary("SttGetConfigFields", {})) as { configFields: FieldDef[] };
    return res.configFields ?? [];
  }

  async synthesize(
    text: string,
    opts: { voiceId?: string; speed?: number; pitch?: number } = {}
  ): Promise<AudioData> {
    const res = (await this.unary("TtsSynthesize", {
      text,
      voiceId: opts.voiceId ?? "",
      speed: opts.speed ?? 1,
      pitch: opts.pitch ?? 1,
    })) as { audioData: Buffer; format: string; sampleRate: number; durationMs: number };
    return {
      data: res.audioData,
      format: res.format,
      sampleRate: res.sampleRate,
      durationMs: res.durationMs,
    };
  }

  /** Server-streaming TTS. Returns the chunks as written. */
  async synthesizeStream(
    text: string,
    opts: { voiceId?: string; speed?: number; pitch?: number } = {}
  ): Promise<{ chunks: AudioChunk[]; status: FakeStatus | null }> {
    const call = await this.serverStream("TtsSynthesizeStream", {
      text,
      voiceId: opts.voiceId ?? "",
      speed: opts.speed ?? 1,
      pitch: opts.pitch ?? 1,
    });
    return { chunks: call.written as AudioChunk[], status: call.status };
  }

  async languages(): Promise<string[]> {
    const res = (await this.unary("SttGetLanguages", {})) as { languages: string[] };
    return res.languages ?? [];
  }

  async sttLoad(modelPath: string, useGpu = false): Promise<void> {
    await this.unary("SttLoad", { modelPath, useGpu });
  }

  async sttUnload(): Promise<void> {
    await this.unary("SttUnload", {});
  }

  async sttLoadState(): Promise<SttLoadStatus> {
    return (await this.unary("SttGetLoadState", {})) as SttLoadStatus;
  }

  /**
   * Drive `SttProcess` with a chunk stream.
   *
   * With no argument it uses the golden utterance from `fixtures.ts`, which is
   * longer than `STT_AUDIO_CHANNEL_CAPACITY` on purpose: a bridge that
   * truncates or reorders under back-pressure is the failure this fixture was
   * built to reproduce, and a two-second sample cannot reach it.
   */
  async sttStream(
    chunks: readonly AudioChunk[] = utteranceChunks(),
    options?: SttOptions
  ): Promise<SttRun> {
    const messages = chunks.map((c, i) => ({
      data: c.data,
      isLast: c.isLast ?? false,
      sampleRate: c.sampleRate ?? 0,
      options: i === 0 ? (options ?? c.options) : undefined,
    }));
    const call = await this.bidi("SttProcess", messages);
    return {
      events: call.written as SttEvent[],
      sent: messages.length,
      delivered: call.delivered,
      pauses: call.pauses,
      status: call.status,
    };
  }

  /** Server-streaming `AiComplete`. Returns the chunks as written. */
  async aiComplete(
    request: Partial<AiCompleteRequest> = {}
  ): Promise<{ chunks: AiChunk[]; status: FakeStatus | null }> {
    const call = await this.serverStream("AiComplete", {
      messages: request.messages ?? [{ role: "user", content: "hello" }],
      tools: request.tools ?? [],
      systemPrompt: request.systemPrompt ?? "",
      temperature: request.temperature ?? 0,
      maxTokens: request.maxTokens ?? 0,
      model: request.model ?? "",
      reasoningEffort: request.reasoningEffort ?? "",
      showReasoning: request.showReasoning ?? false,
    });
    return { chunks: call.written as AiChunk[], status: call.status };
  }

  // ── events ──

  /**
   * Push a daemon event, as `SubscribeEvents` would deliver it — payload keys
   * and all.
   *
   * Through `dispatchEvent`, not straight to `onEvent`: the typed hooks
   * (`onCommandTriggered` and friends) exist on the far side of that decode,
   * and a harness that skipped it would leave the only place the daemon's
   * snake_case keys are read untested — which is exactly how
   * `event.commandId` came to be `undefined` on every event.
   */
  async event(eventType: string, payload: Record<string, unknown> = {}): Promise<void> {
    await this.plugin.dispatchEvent(eventType, payload);
  }

  /** Push a chat firehose event, as `onConversationEvent` receives it. */
  async conversationEvent(
    conversationId: string,
    event: Record<string, unknown>
  ): Promise<void> {
    await this.plugin.onConversationEvent(conversationId, event);
  }

  // ── raw dispatch ──

  /** Call a unary hook by its proto name. Throws `HookStatusError` on a status. */
  async unary(method: string, request: unknown): Promise<unknown> {
    const outcome = await invokeUnary(this.handler(method) as never, request);
    if (outcome.error) throw new HookStatusError(method, outcome.error);
    return outcome.response;
  }

  /** Call a unary hook and return the status instead of throwing. */
  async unaryStatus(method: string, request: unknown): Promise<FakeStatus | null> {
    const outcome = await invokeUnary(this.handler(method) as never, request);
    return outcome.error ?? null;
  }

  /** Call a server-streaming hook by its proto name. */
  serverStream(method: string, request: unknown): Promise<FakeWritableCall> {
    return invokeServerStream(this.handler(method) as never, request);
  }

  /** Call a bidi hook by its proto name. */
  bidi(method: string, messages: readonly unknown[]): Promise<FakeDuplexCall> {
    return invokeBidi(this.handler(method) as never, messages);
  }

  private handler(method: string): unknown {
    if (!this.handlers) {
      throw new Error("harness not started — call `await harness.start()` first");
    }
    const handler = this.handlers[method];
    if (typeof handler !== "function") {
      throw new Error(
        `no handler for ${method}. The plugin's handler map has ` +
          `${Object.keys(this.handlers).length} entries; check the proto spelling`
      );
    }
    return handler;
  }
}

function formatIssues(issues: readonly ValidationIssue[]): string {
  return issues.map((i) => `${i.path || "(root)"} ${i.message}`).join("; ");
}
