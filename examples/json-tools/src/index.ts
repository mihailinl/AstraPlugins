import { Plugin, Field } from "@astra/plugin-sdk";
import type { ToolDef, ToolResult, ActionResult, ActionTypeDef, TriggerTypeDef } from "@astra/plugin-sdk";

class JsonTools extends Plugin {
  private defaultIndent = 2;
  private operationsCount = 0;

  // -- Tools --

  async listTools(): Promise<ToolDef[]> {
    return [
      {
        name: "json_format",
        description: "Pretty-print JSON with configurable indentation.",
        parametersJson: JSON.stringify({
          type: "object",
          properties: {
            json: { type: "string", description: "JSON string to format" },
            indent: { type: "number", description: "Indentation spaces", default: 2 },
          },
          required: ["json"],
        }),
      },
      {
        name: "json_query",
        description: "Query JSON with a dot-path (e.g., 'data.users[0].name').",
        parametersJson: JSON.stringify({
          type: "object",
          properties: {
            json: { type: "string", description: "JSON string to query" },
            path: { type: "string", description: "Dot-path expression" },
          },
          required: ["json", "path"],
        }),
      },
      {
        name: "json_diff",
        description: "Compare two JSON objects and return their differences.",
        parametersJson: JSON.stringify({
          type: "object",
          properties: {
            a: { type: "string", description: "First JSON" },
            b: { type: "string", description: "Second JSON" },
          },
          required: ["a", "b"],
        }),
      },
    ];
  }

  async callTool(name: string, argumentsJson: string): Promise<ToolResult> {
    let args: Record<string, unknown>;
    try {
      args = JSON.parse(argumentsJson || "{}");
    } catch {
      return { success: false, result: "", error: "Invalid JSON arguments" };
    }

    this.operationsCount++;

    switch (name) {
      case "json_format": {
        const jsonStr = String(args.json ?? "");
        const indent = Number(args.indent ?? this.defaultIndent);
        try {
          const parsed = JSON.parse(jsonStr);
          return { success: true, result: JSON.stringify(parsed, null, indent) };
        } catch (e: any) {
          return { success: false, result: "", error: `Invalid JSON: ${e.message}` };
        }
      }

      case "json_query": {
        const jsonStr = String(args.json ?? "");
        const path = String(args.path ?? "");
        try {
          const parsed = JSON.parse(jsonStr);
          const value = queryPath(parsed, path);
          return {
            success: true,
            result: typeof value === "object" ? JSON.stringify(value, null, 2) : String(value),
          };
        } catch (e: any) {
          return { success: false, result: "", error: e.message };
        }
      }

      case "json_diff": {
        const aStr = String(args.a ?? "");
        const bStr = String(args.b ?? "");
        try {
          const a = JSON.parse(aStr);
          const b = JSON.parse(bStr);
          const diffs = diffObjects(a, b, "");
          if (diffs.length === 0) {
            return { success: true, result: "Objects are identical" };
          }
          return { success: true, result: JSON.stringify(diffs, null, 2) };
        } catch (e: any) {
          return { success: false, result: "", error: `Invalid JSON: ${e.message}` };
        }
      }

      default:
        return { success: false, result: "", error: `Unknown tool: ${name}` };
    }
  }

  // -- Actions --

  async getActionTypes(): Promise<ActionTypeDef[]> {
    return [
      {
        type: "json_transform",
        label: "JSON Transform",
        iconSvg:
          '<svg viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
        fields: [
          Field.dropdown("operation", "Operation", {
            options: [
              ["format", "Pretty Format"],
              ["minify", "Minify"],
              ["sort_keys", "Sort Keys"],
              ["extract_path", "Extract Path"],
            ],
            default: "format",
          }),
          Field.textareaWithVariables("input_json", "Input JSON", {
            placeholder: '{"key": "value"}',
          }),
          Field.text("path", "JSON Path", {
            placeholder: "data.users[0].name",
            description: "Dot-path to extract (only for Extract Path operation)",
            conditions: [Field.condition("operation", "equals", "extract_path")],
          }),
          Field.text("store_in", "Store Result In", {
            placeholder: "variable_name",
            description: "Variable name to store the result",
          }),
        ],
        aiAvailable: true,
        aiDescription: "Transform JSON: format, minify, sort keys, or extract a path",
        aiPrimaryField: "input_json",
      },
    ];
  }

  async executeAction(actionType: string, paramsJson: string): Promise<ActionResult> {
    if (actionType !== "json_transform") {
      return { success: false, result: "", error: `Unknown action: ${actionType}` };
    }

    let params: Record<string, unknown>;
    try {
      params = JSON.parse(paramsJson || "{}");
    } catch {
      return { success: false, result: "", error: "Invalid params JSON" };
    }

    const operation = String(params.operation ?? "format");
    const input = String(params.input_json ?? "");
    this.operationsCount++;

    try {
      const parsed = JSON.parse(input);

      switch (operation) {
        case "format":
          return { success: true, result: JSON.stringify(parsed, null, this.defaultIndent) };
        case "minify":
          return { success: true, result: JSON.stringify(parsed) };
        case "sort_keys":
          return { success: true, result: JSON.stringify(sortKeys(parsed), null, this.defaultIndent) };
        case "extract_path": {
          const path = String(params.path ?? "");
          const value = queryPath(parsed, path);
          return {
            success: true,
            result: typeof value === "object" ? JSON.stringify(value, null, 2) : String(value),
          };
        }
        default:
          return { success: false, result: "", error: `Unknown operation: ${operation}` };
      }
    } catch (e: any) {
      return { success: false, result: "", error: `Invalid JSON: ${e.message}` };
    }
  }

  // -- Triggers --

  async getTriggerTypes(): Promise<TriggerTypeDef[]> {
    return [
      {
        type: "on_invalid_json",
        label: "Invalid JSON Detected",
        iconSvg:
          '<svg viewBox="0 0 24 24"><path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
        fields: [
          Field.text("source", "Source Label", {
            placeholder: "API response",
            description: "Label identifying where the invalid JSON came from",
          }),
        ],
      },
    ];
  }

  // -- Lifecycle --

  async onConfigChanged(config: Record<string, unknown>): Promise<void> {
    if (typeof config.default_indent === "number") {
      this.defaultIndent = config.default_indent;
    }
  }

  async healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return { healthy: true, status: `ok — ${this.operationsCount} operations processed` };
  }
}

// -- Helpers --

function queryPath(obj: unknown, path: string): unknown {
  const parts = path.replace(/\[(\d+)\]/g, ".$1").split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (part === "") continue;
    if (current === null || current === undefined) {
      throw new Error(`Path '${path}' not found: hit null at '${part}'`);
    }
    if (typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      throw new Error(`Path '${path}' not found: '${part}' is not an object`);
    }
  }
  return current;
}

function sortKeys(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map(sortKeys);
  }
  if (obj !== null && typeof obj === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(obj as Record<string, unknown>).sort()) {
      sorted[key] = sortKeys((obj as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return obj;
}

interface Diff {
  path: string;
  type: "added" | "removed" | "changed";
  oldValue?: unknown;
  newValue?: unknown;
}

function diffObjects(a: unknown, b: unknown, prefix: string): Diff[] {
  const diffs: Diff[] = [];

  if (typeof a !== typeof b || Array.isArray(a) !== Array.isArray(b)) {
    diffs.push({ path: prefix || "(root)", type: "changed", oldValue: a, newValue: b });
    return diffs;
  }

  if (Array.isArray(a) && Array.isArray(b)) {
    const maxLen = Math.max(a.length, b.length);
    for (let i = 0; i < maxLen; i++) {
      const p = prefix ? `${prefix}[${i}]` : `[${i}]`;
      if (i >= a.length) {
        diffs.push({ path: p, type: "added", newValue: b[i] });
      } else if (i >= b.length) {
        diffs.push({ path: p, type: "removed", oldValue: a[i] });
      } else {
        diffs.push(...diffObjects(a[i], b[i], p));
      }
    }
    return diffs;
  }

  if (a !== null && b !== null && typeof a === "object" && typeof b === "object") {
    const aObj = a as Record<string, unknown>;
    const bObj = b as Record<string, unknown>;
    const allKeys = new Set([...Object.keys(aObj), ...Object.keys(bObj)]);
    for (const key of allKeys) {
      const p = prefix ? `${prefix}.${key}` : key;
      if (!(key in aObj)) {
        diffs.push({ path: p, type: "added", newValue: bObj[key] });
      } else if (!(key in bObj)) {
        diffs.push({ path: p, type: "removed", oldValue: aObj[key] });
      } else {
        diffs.push(...diffObjects(aObj[key], bObj[key], p));
      }
    }
    return diffs;
  }

  if (a !== b) {
    diffs.push({ path: prefix || "(root)", type: "changed", oldValue: a, newValue: b });
  }

  return diffs;
}

new JsonTools().run();
