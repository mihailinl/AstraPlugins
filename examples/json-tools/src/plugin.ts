/**
 * JSON Tools — the reference TypeScript plugin.
 *
 * Written in the object form so the parameters of each tool are declared once,
 * as an `s` schema: the SDK emits the JSON Schema the model reads, validates
 * what the model sends, and hands the handler an argument whose TypeScript type
 * came from that same declaration. There is no `String(args.json ?? "")` line
 * anywhere below, and there is no way for the schema and the handler to
 * disagree about a key's name or type.
 *
 * The definition is exported rather than run here; `index.ts` is the two-line
 * entrypoint and `test/plugin.test.mjs` drives this object through the SDK's
 * harness at both levels.
 */

import { plugin, tool, action, s, Field, BadArguments } from "astra-plugin-sdk";
import type { PluginContext } from "astra-plugin-sdk";

/** The config this plugin reads. One key, and the daemon renders it. */
const CONFIG = s.object({
  default_indent: s.integer({ minimum: 0, maximum: 10, default: 2 }).optional(),
});

/** Indent to use when the caller did not say. */
function defaultIndent(config: Record<string, unknown>): number {
  const value = config.default_indent;
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 2;
}

let operations = 0;

export const app = plugin({
  id: "json-tools",
  configSchema: CONFIG,

  tools: {
    json_format: tool({
      description: "Pretty-print JSON with configurable indentation.",
      input: s.object({
        json: s.string({ description: "JSON string to format" }),
        indent: s.integer({
          description: "Indentation spaces; defaults to the plugin's setting",
          minimum: 0,
          maximum: 10,
        }).optional(),
      }),
      run: async ({ json, indent }, ctx) => {
        operations++;
        // `json` really is a string and `indent` really is `number | undefined`:
        // the SDK rejected anything else before this line ran, in-band, as a
        // BAD_ARGUMENTS result the model can read and correct.
        const parsed = await parseAnnouncing(json, "json", ctx);
        return JSON.stringify(parsed, null, indent ?? defaultIndent(ctx.config));
      },
    }),

    json_query: tool({
      description: "Query JSON with a dot-path (e.g. 'data.users[0].name').",
      input: s.object({
        json: s.string({ description: "JSON string to query" }),
        path: s.string({ description: "Dot-path expression", minLength: 1 }),
      }),
      run: async ({ json, path }, ctx) => {
        operations++;
        return render(queryPath(await parseAnnouncing(json, "json", ctx), path));
      },
    }),

    json_diff: tool({
      description: "Compare two JSON documents and list what changed.",
      input: s.object({
        a: s.string({ description: "First JSON" }),
        b: s.string({ description: "Second JSON" }),
      }),
      run: async ({ a, b }, ctx) => {
        operations++;
        const diffs = diffObjects(
          await parseAnnouncing(a, "a", ctx),
          await parseAnnouncing(b, "b", ctx),
          "",
        );
        return diffs.length === 0 ? "Documents are identical" : JSON.stringify(diffs, null, 2);
      },
    }),
  },

  actions: {
    json_transform: action({
      label: "JSON Transform",
      iconSvg:
        '<svg viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
      // `fields` is what the command editor renders; `params` is what the
      // handler is typed against. They describe the same four values, and the
      // suite asserts that they do — a field the handler does not read, or a
      // param no field can produce, is a step that silently does nothing.
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
        Field.textareaWithVariables("input_json", "Input JSON", { placeholder: '{"key": "value"}' }),
        Field.text("path", "JSON Path", {
          placeholder: "data.users[0].name",
          description: "Dot-path to extract (Extract Path only)",
          conditions: [Field.condition("operation", "equals", "extract_path")],
        }),
        Field.text("store_in", "Store Result In", {
          placeholder: "variable_name",
          description: "Variable to publish the result as",
        }),
      ],
      params: s.object({
        operation: s.enum(["format", "minify", "sort_keys", "extract_path"] as const),
        input_json: s.string(),
        path: s.string().optional(),
        store_in: s.string().optional(),
      }),
      ai: { description: "Transform JSON: format, minify, sort keys, or extract a path", primaryField: "input_json" },
      run: async ({ operation, input_json, path, store_in }, ctx) => {
        operations++;
        const parsed = await parseAnnouncing(input_json, "input_json", ctx);
        const indent = defaultIndent(ctx.config);
        let result: string;
        switch (operation) {
          case "format":
            result = JSON.stringify(parsed, null, indent);
            break;
          case "minify":
            result = JSON.stringify(parsed);
            break;
          case "sort_keys":
            result = JSON.stringify(sortKeys(parsed), null, indent);
            break;
          case "extract_path":
            if (!path) throw new BadArguments({ message: "`path` is required for Extract Path." });
            result = render(queryPath(parsed, path));
            break;
        }
        // Publishing the variable is the step's whole point in a command, so a
        // daemon that refuses `set_variable` must not look like success.
        if (store_in) await ctx.setVariable(store_in, result);
        return result;
      },
    }),
  },

  triggers: {
    // Fired by `parseAnnouncing` when a tool is handed JSON it cannot parse —
    // but only while a command is actually listening for it. See
    // `parseAnnouncing` for why the check is `ctx.activeTriggers` and not a
    // flag of our own.
    on_invalid_json: {
      label: "Invalid JSON Detected",
      iconSvg:
        '<svg viewBox="0 0 24 24"><path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>',
      fields: [
        Field.text("source", "Source Label", {
          placeholder: "API response",
          description: "Where the invalid JSON came from",
        }),
      ],
    },
  },

  onStart: (ctx) => {
    void ctx.info(`json-tools ready (indent ${defaultIndent(ctx.config)})`);
  },

  healthCheck: () => ({ healthy: true, status: `ok — ${operations} operations processed` }),
});

// ── helpers ──────────────────────────────────────────────────────────────────

/**
 * `JSON.parse`, but the failure is a `BAD_ARGUMENTS` naming the argument.
 *
 * A raw `SyntaxError` would reach the model as "Unexpected token } in JSON at
 * position 7", which tells it nothing about which of its two arguments to fix.
 */
/**
 * `parse`, and — if some command is listening — announce the failure.
 *
 * `ctx.activeTriggers` is the set the daemon delivers on `OnActiveTriggers`:
 * the trigger types some command is subscribed to *right now*. Firing
 * unconditionally would be an RPC per bad document that nothing reads, so the
 * check is the point of the API. It is also the reason this is worth a test in
 * `test/plugin.test.mjs`: the set is written in one place in the SDK and read
 * here, and if the write ever stops happening this code goes quietly dead —
 * `has()` answers false forever and no error is raised anywhere.
 */
async function parseAnnouncing(
  text: string,
  argument: string,
  ctx: PluginContext,
): Promise<unknown> {
  try {
    return parse(text, argument);
  } catch (e) {
    if (ctx.activeTriggers.has("on_invalid_json")) {
      await ctx.fireTrigger("on_invalid_json", {
        source: argument,
        error: (e as Error).message,
      });
    }
    throw e;
  }
}

function parse(text: string, argument = "json"): unknown {
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new BadArguments({ message: `\`${argument}\` is not valid JSON: ${(e as Error).message}` });
  }
}

/** A value as the string a tool returns: JSON for structures, raw for scalars. */
function render(value: unknown): string {
  return typeof value === "object" && value !== null ? JSON.stringify(value, null, 2) : String(value);
}

function queryPath(obj: unknown, path: string): unknown {
  const parts = path.replace(/\[(\d+)\]/g, ".$1").split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (part === "") continue;
    if (current === null || current === undefined) {
      throw new BadArguments({ message: `Path '${path}' not found: hit null at '${part}'.` });
    }
    if (typeof current !== "object") {
      throw new BadArguments({ message: `Path '${path}' not found: '${part}' is not an object.` });
    }
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[key] = sortKeys((value as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return value;
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
    return [{ path: prefix || "(root)", type: "changed", oldValue: a, newValue: b }];
  }

  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
      const p = prefix ? `${prefix}[${i}]` : `[${i}]`;
      if (i >= a.length) diffs.push({ path: p, type: "added", newValue: b[i] });
      else if (i >= b.length) diffs.push({ path: p, type: "removed", oldValue: a[i] });
      else diffs.push(...diffObjects(a[i], b[i], p));
    }
    return diffs;
  }

  if (a !== null && b !== null && typeof a === "object" && typeof b === "object") {
    const aObj = a as Record<string, unknown>;
    const bObj = b as Record<string, unknown>;
    for (const key of new Set([...Object.keys(aObj), ...Object.keys(bObj)])) {
      const p = prefix ? `${prefix}.${key}` : key;
      if (!(key in aObj)) diffs.push({ path: p, type: "added", newValue: bObj[key] });
      else if (!(key in bObj)) diffs.push({ path: p, type: "removed", oldValue: aObj[key] });
      else diffs.push(...diffObjects(aObj[key], bObj[key], p));
    }
    return diffs;
  }

  if (a !== b) diffs.push({ path: prefix || "(root)", type: "changed", oldValue: a, newValue: b });
  return diffs;
}
