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
    return { id, label, fieldType: "number", min: opts?.min, max: opts?.max, step: opts?.step, defaultValue: opts?.default, description: opts?.description, conditions: opts?.conditions };
  },
  toggle(id: string, label: string, opts?: { default?: boolean; description?: string; conditions?: FieldDef["conditions"] }): FieldDef {
    return { id, label, fieldType: "toggle", defaultValue: opts?.default ? "true" : "false", description: opts?.description, conditions: opts?.conditions };
  },
  condition(fieldId: string, operator: string, value: string = ""): NonNullable<FieldDef["conditions"]>[0] {
    return { fieldId, operator, value };
  },
};
