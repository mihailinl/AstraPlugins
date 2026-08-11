import type { PluginErrorDetail } from "./errors";

/** A tool definition exposed to the AI. */
export interface ToolDef {
  name: string;
  description: string;
  parametersJson: string;
}

/** Result of a tool call. */
export interface ToolResult {
  success: boolean;
  result: string;
  error?: string;
  /**
   * The structured half of a failure (§5.2). Set it by throwing a
   * `PluginError` — the SDK fills this in and the matching `error` string
   * together, so the two cannot disagree. Returning `{ success: false, error }`
   * still works and leaves this unset: the SDK will not invent a code it was
   * not given, because the daemon acts on codes and a wrong one is worse than
   * none.
   */
  errorDetail?: PluginErrorDetail;
}

/** A TTS voice provided by the plugin. */
export interface VoiceInfo {
  id: string;
  name: string;
  language: string;
  gender: string;
  previewUrl?: string;
}

/** Synthesized audio data. */
export interface AudioData {
  data: Buffer;
  format: string;
  sampleRate: number;
  durationMs: number;
}

/** A speech-recognition result returned by `sttTranscribe`. */
export interface SttEvent {
  text: string;
  /** `true` for a complete transcription, `false` for an interim result. */
  isFinal?: boolean;
  /** Recognition confidence in 0.0..=1.0. */
  confidence?: number;
  /** Detected language code (e.g. "en"), or empty if unknown. */
  language?: string;
}

/** An AI model info. */
export interface AiModelInfo {
  id: string;
  name: string;
}

/** Result of executing an action. */
export interface ActionResult {
  success: boolean;
  result: string;
  error?: string;
  /** Structured failure detail (§5.2); see `ToolResult.errorDetail`. */
  errorDetail?: PluginErrorDetail;
}

/** Field definition for action/trigger config. */
export interface FieldDef {
  id: string;
  label: string;
  fieldType: string;
  placeholder?: string;
  defaultValue?: string;
  min?: number;
  max?: number;
  step?: number;
  /** Whether `min` is meaningful. proto3 cannot tell an unset `double` from 0,
   * so the daemon reads these flags, not the values. `Field.number` sets them. */
  hasMin?: boolean;
  hasMax?: boolean;
  hasStep?: boolean;
  options?: { value: string; label: string }[];
  conditions?: { fieldId: string; operator: string; value: string }[];
  description?: string;
  group?: string;
  groupLabel?: string;
}

/** Action type definition. */
export interface ActionTypeDef {
  type: string;
  label: string;
  iconSvg?: string;
  fields: FieldDef[];
  aiAvailable?: boolean;
  aiDescription?: string;
  aiPrimaryField?: string;
}

/** Trigger type definition. */
export interface TriggerTypeDef {
  type: string;
  label: string;
  iconSvg?: string;
  fields: FieldDef[];
}

/** UI contribution definition — targets a named slot or CSS selector. */
export interface UiContribution {
  id: string;
  slot?: string;
  cssTarget?: string;
  position?: string;
  url: string;
  label?: string;
  iconSvg?: string;
  width?: number;
  height?: number;
  transparent?: boolean;
  pointerEvents?: boolean;
  zIndex?: number;
  props?: Record<string, string>;
}

/** @deprecated Use UiContribution instead */
export type UiPanel = UiContribution;

/** Explicit answer to a `CallFromUi` request — mirrors `PluginUiCallResponse`. */
export interface UiCallResult {
  /** JSON handed back to the iframe. */
  resultJson?: string;
  /** Non-empty means the call failed. */
  error?: string;
  /**
   * Structured failure detail (§5.2). The daemon relays it to the panel as
   * `CallPluginFromUiResponse.error_detail`, so a plugin's own UI can render
   * the same config-field link a tool failure would.
   */
  errorDetail?: PluginErrorDetail;
}

// ── §5.4 hook payloads ───────────────────────────────────────────────────────

/**
 * One slice of PCM, in either direction.
 *
 * `sampleRate` is read on the first chunk of a stream only — the protocol says
 * so, and repeating it costs nothing but says nothing either.
 */
export interface AudioChunk {
  data: Buffer;
  /** The SDK sets this on the last chunk it sends for you. */
  isLast?: boolean;
  sampleRate?: number;
  /** STT request stream, first chunk only. Never set on the TTS side. */
  options?: SttOptions;
}

/**
 * Per-utterance decoding options, carried on the first chunk of `SttProcess`.
 * A recognizer ignores what it has no notion of; nothing here is required.
 */
export interface SttOptions {
  /** BCP-47-ish code, or "" for auto-detect. */
  language?: string;
  /** Decoding bias — wake-word spellings, names the user says a lot. */
  initialPrompt?: string;
}

/**
 * Mirrors `SttLoadStateResponse.State`.
 *
 * `NOT_NEEDED` is what the daemon assumes when the hook is absent, so a plugin
 * that answers it says the same thing as one that does not implement the hook.
 */
export type SttLoadState = "NOT_NEEDED" | "UNLOADED" | "LOADING" | "READY" | "FAILED";

/** What `sttLoadState` answers. `detail` explains a `FAILED`. */
export interface SttLoadStatus {
  state: SttLoadState;
  detail?: string;
}

/** What `sttLoad` is told: a daemon-resolved model path and the GPU toggle. */
export interface SttLoadRequest {
  /** Absolute path the daemon resolved, or "" for the provider's default. */
  modelPath: string;
  /** False on the daemon's degraded retry after a GPU load failed. */
  useGpu: boolean;
}

/** One tool call the model asked for, or that a provider is reporting. */
export interface AiToolCall {
  id: string;
  name: string;
  argumentsJson: string;
}

/** One conversation turn handed to a provider. */
export interface AiMessage {
  role: string; // "user" | "assistant" | "system" | "tool"
  content: string;
  toolCallId?: string;
  toolCalls?: AiToolCall[];
}

/** Everything the daemon knows about one completion. */
export interface AiCompleteRequest {
  messages: AiMessage[];
  tools: ToolDef[];
  systemPrompt: string;
  temperature: number;
  maxTokens: number;
  model: string;
  /**
   * `"" | "auto" | "off" | "low" | "medium" | "high" | "max"`.
   *
   * A string, not an enum, and the proto says why: an unrecognised enum value
   * arrives silently zeroed, making "this plugin is old" indistinguishable from
   * "the user chose auto". `""` means the daemon did not say, and that is not
   * the same as `"auto"`.
   */
  reasoningEffort: string;
  /**
   * Whether the user wants the reasoning shown. When false, do not spend tokens
   * producing `thinking` chunks nobody will read.
   */
  showReasoning: boolean;
}

/**
 * One piece of a streamed completion — exactly one kind per chunk.
 *
 * The wire field is a `oneof`, so a chunk that sets two things is a chunk the
 * daemon reads one of. The SDK resolves that with a fixed precedence (error,
 * tool call, thinking, done, text) rather than leaving it to chance.
 */
export interface AiChunk {
  /** A text delta. Yielding a bare `string` means this. */
  text?: string;
  /** A reasoning delta. Only worth producing when `showReasoning`. */
  thinking?: string;
  toolCall?: AiToolCall;
  /** The stream is over. The SDK appends one when your generator returns. */
  done?: boolean;
  /** The completion failed. Prefer throwing a `PluginError`. */
  error?: string;
}

/**
 * Colours, wallpaper and shader a plugin contributes to the active Astra theme.
 *
 * Gated on the `set_theme_contribution` permission, which Phase 4 classes
 * high-risk: this is a plugin repainting the user's whole application, so the
 * daemon refuses it below Tier 1 no matter what the manifest asks for.
 */
export interface ThemeContribution {
  themeName: string;
  themeDescription?: string;
  /** CSS custom properties, e.g. `{ "--accent": "#7c5cff" }`. */
  cssVariables?: Record<string, string>;
  /** Path relative to the plugin's `ui/` directory. */
  wallpaperPath?: string;
  wallpaperMode?: string; // "cover" | "contain" | "tile"
  wallpaperOpacity?: number;
  /** GLSL replacing the built-in Threads effect. */
  fragmentShader?: string;
  effectConfigJson?: string;
}

/** One chunk of the assistant's reply to `host.sendChatMessage`. */
export interface ChatChunk {
  /** A text delta, when this chunk carries one. */
  text?: string;
  /** True on the terminating chunk. */
  done?: boolean;
  /** Non-empty when the turn failed. */
  error?: string;
  messageId?: string;
  /** Structured failure detail (§5.2), set alongside `error`. */
  errorDetail?: PluginErrorDetail;
}

/** Builder for UI contributions. */
export const UiContrib = {
  /** Custom navigation page. */
  page(id: string, label: string, url: string, opts?: { iconSvg?: string }): UiContribution {
    return { id, slot: "page.custom", label, url, iconSvg: opts?.iconSvg, pointerEvents: true };
  },
  /** Named slot contribution. */
  slot(slot: string, url: string, opts?: { id?: string; label?: string; width?: number; height?: number }): UiContribution {
    return { id: opts?.id || slot, slot, url, label: opts?.label, width: opts?.width, height: opts?.height, pointerEvents: true };
  },
  /** Fullscreen background effect (transparent, no pointer events). */
  effect(url: string, opts?: { audio?: boolean; id?: string }): UiContribution {
    const props: Record<string, string> = {};
    if (opts?.audio) props.audio = "true";
    return { id: opts?.id || "effect", slot: "background.behind", url, transparent: true, pointerEvents: false, props };
  },
  /** CSS selector injection. */
  inject(cssTarget: string, position: string, url: string, opts?: { id?: string; width?: number; height?: number }): UiContribution {
    return { id: opts?.id || "inject", cssTarget, position, url, width: opts?.width, height: opts?.height, pointerEvents: true };
  },
  /** Floating overlay (companion, mini-app). */
  overlay(id: string, url: string, opts?: { width?: number; height?: number }): UiContribution {
    return { id, slot: "overlay.floating", url, transparent: true, pointerEvents: true, width: opts?.width || 200, height: opts?.height || 200 };
  },
};

// ── Field builder ──

/** Builder for action/trigger field definitions. */
export const Field = {
  text(id: string, label: string, opts?: { placeholder?: string; default?: string; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return { id, label, fieldType: "text", placeholder: opts?.placeholder, defaultValue: opts?.default, description: opts?.description, conditions: opts?.conditions };
  },
  textarea(id: string, label: string, opts?: { placeholder?: string; default?: string; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return { id, label, fieldType: "textarea", placeholder: opts?.placeholder, defaultValue: opts?.default, description: opts?.description, conditions: opts?.conditions };
  },
  textareaWithVariables(id: string, label: string, opts?: { placeholder?: string; default?: string; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return { id, label, fieldType: "textarea_with_variables", placeholder: opts?.placeholder, defaultValue: opts?.default, description: opts?.description, conditions: opts?.conditions };
  },
  dropdown(id: string, label: string, opts: { options: ([string, string] | string)[]; default?: string; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    const options = opts.options.map(o =>
      typeof o === "string" ? { value: o, label: o } : { value: o[0], label: o[1] }
    );
    return { id, label, fieldType: "dropdown", options, defaultValue: opts.default, description: opts.description, conditions: opts.conditions };
  },
  number(id: string, label: string, opts?: { min?: number; max?: number; step?: number; default?: string; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return {
      id, label, fieldType: "number",
      min: opts?.min, max: opts?.max, step: opts?.step,
      // Without these the daemon reads every bound as "unset" and renders an
      // unbounded input, because proto3 sends an absent double as 0.0.
      hasMin: opts?.min !== undefined, hasMax: opts?.max !== undefined, hasStep: opts?.step !== undefined,
      defaultValue: opts?.default, description: opts?.description, conditions: opts?.conditions,
    };
  },
  toggle(id: string, label: string, opts?: { default?: boolean; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return { id, label, fieldType: "toggle", defaultValue: opts?.default ? "true" : "false", description: opts?.description, conditions: opts?.conditions };
  },
  condition(fieldId: string, operator: string, value: string = ""): NonNullable<FieldDef["conditions"]>[0] {
    return { fieldId, operator, value };
  },
};
