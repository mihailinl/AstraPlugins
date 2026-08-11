/**
 * `plugin({...})` — the object form.
 *
 * `class extends Plugin` is still there and still works; this is the form for
 * the plugin that is mostly a bag of tools, which is most plugins. It exists
 * for two reasons that a base class cannot give:
 *
 * 1. **The shape is written once.** A tool declares its parameters as an `s`
 *    schema. The SDK emits the JSON Schema the model reads, validates the
 *    arguments the model sends, and hands the handler a parameter whose
 *    TypeScript type came from that same declaration. The `String(args.json ??
 *    "")` line at the top of every `callTool` — and the class of bug where the
 *    schema says `indent` and the code reads `indentation` — is gone.
 * 2. **A missing hook is missing, not empty.** The dispatcher installs an
 *    override only for what the definition provides, so `Plugin.overrides()`
 *    still answers truthfully. That matters: it is what decides whether
 *    `SttProcess` streams or buffers, and whether `ai_provider` is registered
 *    as a capability at all.
 *
 * ```typescript
 * import { plugin, tool, s } from "astra-plugin-sdk";
 *
 * plugin({
 *   tools: {
 *     json_format: tool({
 *       description: "Pretty-print JSON.",
 *       input: s.object({ json: s.string(), indent: s.integer().optional() }),
 *       run: ({ json, indent }) => JSON.stringify(JSON.parse(json), null, indent ?? 2),
 *     }),
 *   },
 * }).run();
 * ```
 *
 * `json` is a `string` and `indent` is a `number | undefined` because the schema
 * said so, and the handler is not reached at all unless the arguments conform.
 */

import { Plugin } from "./plugin.js";
import type { PluginContext } from "./context.js";
import type { DaemonClient } from "./daemon-client.js";
import type { AnyObjectSchema, Infer } from "./schema.js";
import type {
  ActionResult,
  ActionTypeDef,
  AiChunk,
  AiCompleteRequest,
  AiModelInfo,
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
} from "./types.js";

/** What a tool handler may return. Anything but a `ToolResult` is serialized. */
export type ToolOutcome = string | ToolResult | unknown;

/** One tool. Build it with {@link tool} so `run`'s argument is inferred. */
export interface ToolSpec<S extends AnyObjectSchema> {
  /** One sentence the model reads to decide whether to call this. */
  description: string;
  /** The parameters, as an `s.object`. Omit for a tool that takes none. */
  input?: S;
  run(args: Infer<S>, ctx: PluginContext): ToolOutcome | Promise<ToolOutcome>;
}

/** A tool after {@link tool} has erased its schema's type parameter. */
export interface ToolEntry {
  description: string;
  input?: AnyObjectSchema;
  run(args: never, ctx: PluginContext): ToolOutcome | Promise<ToolOutcome>;
}

/**
 * Declare one tool.
 *
 * The wrapper is what makes `run`'s first parameter `Infer<typeof input>`
 * instead of `unknown`: a generic is only inferred per call, and a bare object
 * literal inside `tools: { ... }` is one context for all of them.
 */
export function tool<S extends AnyObjectSchema>(spec: ToolSpec<S>): ToolEntry {
  return spec as unknown as ToolEntry;
}

/** One command-editor action. `run` receives the parsed params. */
export interface ActionSpec<S extends AnyObjectSchema> {
  label: string;
  iconSvg?: string;
  /** Rendered by the daemon's `DynamicField`. Use the `Field` builder. */
  fields?: FieldDef[];
  /**
   * Params schema. Optional — actions are configured by `fields`, and this is
   * for the handler's benefit: declare it and `run` gets a typed parameter and
   * validated input.
   */
  params?: S;
  /** Offer this action to the AI planner, described this way. */
  ai?: { description: string; primaryField?: string };
  run(params: Infer<S>, ctx: PluginContext): ToolOutcome | Promise<ToolOutcome>;
}

/** An action after {@link action} has erased its schema's type parameter. */
export interface ActionEntry {
  label: string;
  iconSvg?: string;
  fields?: FieldDef[];
  params?: AnyObjectSchema;
  ai?: { description: string; primaryField?: string };
  run(params: never, ctx: PluginContext): ToolOutcome | Promise<ToolOutcome>;
}

/** Declare one action. Same inference trick as {@link tool}. */
export function action<S extends AnyObjectSchema>(spec: ActionSpec<S>): ActionEntry {
  return spec as unknown as ActionEntry;
}

/** One trigger type a command can listen for. Fire it with `ctx.fireTrigger`. */
export interface TriggerEntry {
  label: string;
  iconSvg?: string;
  fields?: FieldDef[];
}

export interface TtsDefinition {
  voices: VoiceInfo[] | ((ctx: PluginContext) => VoiceInfo[] | Promise<VoiceInfo[]>);
  synthesize?(
    req: { text: string; voiceId: string; speed: number; pitch: number },
    ctx: PluginContext
  ): AudioData | Promise<AudioData>;
  synthesizeStream?(
    req: { text: string; voiceId: string; speed: number; pitch: number },
    ctx: PluginContext
  ): AsyncIterable<AudioChunk | Buffer>;
  configFields?: FieldDef[] | ((ctx: PluginContext) => FieldDef[] | Promise<FieldDef[]>);
  /** A licensed voice's one-time content-encryption key. Seal it; never log it. */
  activate?(cek: Buffer, voiceId: string, ctx: PluginContext): void | Promise<void>;
}

export interface SttDefinition {
  languages: string[] | ((ctx: PluginContext) => string[] | Promise<string[]>);
  /** One-shot: the SDK buffers the utterance and calls this once. */
  transcribe?(
    audio: Buffer,
    req: { sampleRate: number; options?: SttOptions },
    ctx: PluginContext
  ): SttEvent | Promise<SttEvent>;
  /** Streaming: implementing this takes precedence over `transcribe`. */
  transcribeStream?(
    audio: AsyncIterable<AudioChunk>,
    options: SttOptions | undefined,
    ctx: PluginContext
  ): AsyncIterable<SttEvent>;
  configFields?: FieldDef[] | ((ctx: PluginContext) => FieldDef[] | Promise<FieldDef[]>);
  load?(req: { modelPath: string; useGpu: boolean }, ctx: PluginContext): void | Promise<void>;
  unload?(ctx: PluginContext): void | Promise<void>;
  loadState?(ctx: PluginContext): SttLoadStatus | Promise<SttLoadStatus>;
}

export interface AiDefinition {
  complete(req: AiCompleteRequest, ctx: PluginContext): AsyncIterable<AiChunk | string>;
  /** @deprecated The daemon never asks; see `Plugin.aiGetModels`. */
  models?: { models: AiModelInfo[]; defaultModel: string };
}

export interface UiDefinition {
  contributions: UiContribution[] | ((ctx: PluginContext) => UiContribution[] | Promise<UiContribution[]>);
  /** `CallFromUi` handlers, keyed by the method name the iframe sends. */
  onCall?: Record<string, (params: unknown, ctx: PluginContext) => ToolOutcome | Promise<ToolOutcome>>;
}

export interface EventsDefinition {
  /** Daemon event types to subscribe to. Gated by the `subscribe_events` permission. */
  subscribe?: string[];
  /** Display-only source hint. */
  sourceId?: string;
  on?(eventType: string, payload: Record<string, unknown>, ctx: PluginContext): void | Promise<void>;
  /** Every chat event in every conversation. `client` plugins only. */
  onConversation?(
    conversationId: string,
    event: Record<string, unknown>,
    ctx: PluginContext
  ): void | Promise<void>;
}

/** The whole plugin, as data. Every field is optional; an empty one is legal. */
export interface PluginDefinition {
  /** Documentation only — the daemon passes the real id on argv. */
  id?: string;
  /** The config this plugin expects. Used by the test harness and `astra-plugin test`. */
  configSchema?: AnyObjectSchema;

  tools?: Record<string, ToolEntry>;
  actions?: Record<string, ActionEntry>;
  triggers?: Record<string, TriggerEntry>;
  tts?: TtsDefinition;
  stt?: SttDefinition;
  ai?: AiDefinition;
  ui?: UiDefinition;
  events?: EventsDefinition;
  /** Declare the `client` capability and get a `DaemonClient` when it is ready. */
  client?: { onReady?(daemon: DaemonClient, ctx: PluginContext): void | Promise<void> };

  onStart?(ctx: PluginContext): void | Promise<void>;
  onShutdown?(ctx: PluginContext): void | Promise<void>;
  onConfigChanged?(config: Record<string, unknown>, ctx: PluginContext): void | Promise<void>;
  onLanguageChanged?(language: string, ctx: PluginContext): void | Promise<void>;
  onActiveTriggers?(types: string[], ctx: PluginContext): void | Promise<void>;
  healthCheck?(ctx: PluginContext): { healthy: boolean; status: string } | Promise<{ healthy: boolean; status: string }>;
}

/** What `plugin()` hands back. `run()` starts it; `instance` is what a harness drives. */
export interface PluginApp {
  /** Bind, register and serve. The last line of a plugin's entrypoint. */
  run(): void;
  /** The `Plugin` behind the definition — pass it to `Harness.create`. */
  readonly instance: Plugin;
  /** The definition as given, for tooling that wants to read the schemas. */
  readonly definition: PluginDefinition;
}

/** Turn whatever a handler returned into a `ToolResult`. */
function toResult(value: ToolOutcome): ToolResult {
  if (value === null || value === undefined) return { success: true, result: "" };
  if (typeof value === "string") return { success: true, result: value };
  if (typeof value === "object" && value !== null && "success" in value) {
    const r = value as ToolResult;
    return { success: r.success, result: r.result ?? "", error: r.error, errorDetail: r.errorDetail };
  }
  return { success: true, result: JSON.stringify(value) };
}

async function resolve<T>(
  value: T | ((ctx: PluginContext) => T | Promise<T>) | undefined,
  ctx: PluginContext,
  fallback: T
): Promise<T> {
  if (value === undefined) return fallback;
  if (typeof value === "function") return await (value as (c: PluginContext) => T | Promise<T>)(ctx);
  return value;
}

/**
 * The `Plugin` a definition becomes.
 *
 * Optional hooks are installed as INSTANCE properties, not as prototype
 * methods, and only when the definition supplies them. `Plugin.overrides()`
 * compares against `Plugin.prototype`, so an unconditional subclass method
 * would make every definition claim streaming STT and the `ai_provider`
 * capability — which is how a class-based wrapper quietly breaks the two
 * routing decisions that depend on that answer.
 */
class DefinedPlugin extends Plugin {
  constructor(readonly def: PluginDefinition) {
    super();

    const ctx = () => this.ctx();

    if (def.stt?.transcribe) {
      const fn = def.stt.transcribe;
      (this as Plugin).sttTranscribe = async (audio, sampleRate, options) =>
        await fn(audio, { sampleRate, options }, ctx());
    }
    if (def.stt?.transcribeStream) {
      const fn = def.stt.transcribeStream;
      (this as Plugin).sttTranscribeStream = (audio, options) => fn(audio, options, ctx());
    }
    if (def.stt?.load) {
      const fn = def.stt.load;
      (this as Plugin).sttLoad = async (modelPath, useGpu) => {
        await fn({ modelPath, useGpu }, ctx());
      };
    }
    if (def.stt?.unload) {
      const fn = def.stt.unload;
      (this as Plugin).sttUnload = async () => {
        await fn(ctx());
      };
    }
    if (def.stt?.loadState) {
      const fn = def.stt.loadState;
      (this as Plugin).sttLoadState = async () => await fn(ctx());
    }
    if (def.tts?.synthesize) {
      const fn = def.tts.synthesize;
      (this as Plugin).ttsSynthesize = async (text, voiceId, speed, pitch) =>
        await fn({ text, voiceId, speed, pitch }, ctx());
    }
    if (def.tts?.synthesizeStream) {
      const fn = def.tts.synthesizeStream;
      (this as Plugin).ttsSynthesizeStream = (text, voiceId, speed, pitch) =>
        fn({ text, voiceId, speed, pitch }, ctx());
    }
    if (def.tts?.activate) {
      const fn = def.tts.activate;
      (this as Plugin).ttsActivate = async (cek, voiceId) => {
        await fn(cek, voiceId, ctx());
      };
    }
    if (def.ai?.complete) {
      const fn = def.ai.complete;
      (this as Plugin).aiComplete = (req) => fn(req, ctx());
    }
  }

  // ── tools ──

  override async listTools(): Promise<ToolDef[]> {
    return Object.entries(this.def.tools ?? {}).map(([name, spec]) => ({
      name,
      description: spec.description,
      // A tool with no declared input still needs an object root: the daemon
      // and every model provider reject a bare `{}` schema-less parameter list.
      parametersJson: (spec.input?.toJsonString() ?? '{"type":"object","properties":{}}'),
    }));
  }

  override async callTool(name: string, argumentsJson: string): Promise<ToolResult> {
    const spec = this.def.tools?.[name];
    if (!spec) {
      const known = Object.keys(this.def.tools ?? {});
      return {
        success: false,
        result: "",
        error: `Unknown tool: ${name}${known.length ? ` (this plugin has ${known.join(", ")})` : ""}`,
      };
    }
    // Validation happens HERE, before the handler, so `Infer<>` is the truth
    // about the parameter rather than a hope about it. A violation throws
    // `BadArguments`, which `handleCallTool` turns into the in-band
    // BAD_ARGUMENTS result the AI loop can act on.
    const args = spec.input ? spec.input.parseJson(argumentsJson) : {};
    return toResult(await spec.run(args as never, this.ctx()));
  }

  // ── actions & triggers ──

  override async getActionTypes(): Promise<ActionTypeDef[]> {
    return Object.entries(this.def.actions ?? {}).map(([type, spec]) => ({
      type,
      label: spec.label,
      iconSvg: spec.iconSvg,
      fields: spec.fields ?? [],
      aiAvailable: spec.ai !== undefined,
      aiDescription: spec.ai?.description,
      aiPrimaryField: spec.ai?.primaryField,
    }));
  }

  override async executeAction(actionType: string, paramsJson: string): Promise<ActionResult> {
    const spec = this.def.actions?.[actionType];
    if (!spec) {
      return { success: false, result: "", error: `Unknown action: ${actionType}` };
    }
    const params = spec.params
      ? spec.params.parseJson(paramsJson)
      : JSON.parse(paramsJson && paramsJson.trim() ? paramsJson : "{}");
    return toResult(await spec.run(params as never, this.ctx()));
  }

  override async getTriggerTypes(): Promise<TriggerTypeDef[]> {
    return Object.entries(this.def.triggers ?? {}).map(([type, spec]) => ({
      type,
      label: spec.label,
      iconSvg: spec.iconSvg,
      fields: spec.fields ?? [],
    }));
  }

  // ── voice ──

  override async ttsListVoices(): Promise<VoiceInfo[]> {
    return this.def.tts ? await resolve(this.def.tts.voices, this.ctx(), []) : [];
  }

  override async ttsConfigFields(): Promise<FieldDef[]> {
    return await resolve(this.def.tts?.configFields, this.ctx(), []);
  }

  override async sttGetLanguages(): Promise<string[]> {
    return this.def.stt ? await resolve(this.def.stt.languages, this.ctx(), []) : [];
  }

  override async sttConfigFields(): Promise<FieldDef[]> {
    return await resolve(this.def.stt?.configFields, this.ctx(), []);
  }

  override async aiGetModels(): Promise<{ models: AiModelInfo[]; defaultModel: string }> {
    return this.def.ai?.models ?? { models: [], defaultModel: "" };
  }

  // ── ui ──

  override async getUiContributions(): Promise<UiContribution[]> {
    return this.def.ui ? await resolve(this.def.ui.contributions, this.ctx(), []) : [];
  }

  override async handleUiCall(method: string, paramsJson: string): Promise<unknown> {
    const handler = this.def.ui?.onCall?.[method];
    if (!handler) return { error: `No UI call handler for method: ${method}` };
    const params = paramsJson && paramsJson.trim() ? JSON.parse(paramsJson) : {};
    return await handler(params, this.ctx());
  }

  // ── events ──

  override sourceId(): string {
    return this.def.events?.sourceId ?? "";
  }

  override subscribedEvents(): string[] {
    return this.def.events?.subscribe ?? [];
  }

  override async onEvent(eventType: string, payload: Record<string, unknown>): Promise<void> {
    await this.def.events?.on?.(eventType, payload, this.ctx());
  }

  override async onConversationEvent(
    conversationId: string,
    event: Record<string, unknown>
  ): Promise<void> {
    await this.def.events?.onConversation?.(conversationId, event, this.ctx());
  }

  // ── lifecycle ──

  override isClient(): boolean {
    return this.def.client !== undefined;
  }

  override async onDaemonClientReady(client: DaemonClient): Promise<void> {
    await this.def.client?.onReady?.(client, this.ctx());
  }

  override async onStart(): Promise<void> {
    await this.def.onStart?.(this.ctx());
  }

  override async onShutdown(): Promise<void> {
    await this.def.onShutdown?.(this.ctx());
  }

  override async onConfigChanged(config: Record<string, unknown>): Promise<void> {
    await this.def.onConfigChanged?.(config, this.ctx());
  }

  override async onLanguageChanged(language: string): Promise<void> {
    await this.def.onLanguageChanged?.(language, this.ctx());
  }

  override async onActiveTriggers(types: string[]): Promise<void> {
    await this.def.onActiveTriggers?.(types, this.ctx());
  }

  override async healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return (await this.def.healthCheck?.(this.ctx())) ?? { healthy: true, status: "ok" };
  }
}

/**
 * Build a plugin from a definition.
 *
 * The returned object is not started. Call `.run()` to serve, or hand
 * `.instance` to `Harness.create` to test it without a daemon.
 */
export function plugin(definition: PluginDefinition): PluginApp {
  const instance = new DefinedPlugin(definition);
  return {
    run: () => instance.run(),
    instance,
    definition,
  };
}
