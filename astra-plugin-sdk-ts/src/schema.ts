/**
 * `s` — the SDK's schema builder.
 *
 * A tool's parameters are declared twice in every plugin written before this
 * file existed: once as a JSON Schema string the model reads, and once as a
 * TypeScript type (or, more often, as `String(args.json ?? "")` and a prayer).
 * The two drift the moment one of them changes, and nothing notices — the
 * daemon hands `argumentsJson` straight through, so a tool whose schema
 * promises `indent: number` and whose code reads `args.indentation` fails at
 * the user, in a conversation, with a message the model then hallucinates
 * around.
 *
 * `s` collapses the two into one declaration:
 *
 * ```typescript
 * const input = s.object({
 *   json: s.string({ description: "JSON string to format" }),
 *   indent: s.integer({ minimum: 0, maximum: 10 }).optional(),
 * });
 *
 * input.toJSON();            // the JSON Schema the model is shown
 * type Args = Infer<typeof input>;   // { json: string; indent?: number }
 * ```
 *
 * The two halves are proved to agree, in both directions, by
 * `types-test/schema-agreement.ts`: every fixture that type-checks must
 * validate, and every fixture marked `@ts-expect-error` must fail validation.
 * A builder that emitted `required` for an optional key, or typed a required
 * key as optional, fails that test at compile time or at run time.
 *
 * The subset of JSON Schema here is deliberately small — draft-07 keywords that
 * every model provider accepts and that {@link validate} can honestly check.
 * Anything outside it is better expressed as a hand-written schema string, and
 * `ToolDef.parametersJson` still accepts one.
 */

import { BadArguments } from "./errors.js";

/** The JSON Schema keywords this builder emits and {@link validate} enforces. */
export interface JsonSchema {
  type?: "string" | "number" | "integer" | "boolean" | "object" | "array" | "null";
  description?: string;
  default?: unknown;
  enum?: readonly unknown[];
  const?: unknown;
  /** Object. */
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean;
  /** Array. */
  items?: JsonSchema;
  minItems?: number;
  maxItems?: number;
  /** Number. */
  minimum?: number;
  maximum?: number;
  /** String. */
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: string;
  /** Union, used by `.nullable()`. */
  anyOf?: JsonSchema[];
}

/** Options accepted by every builder. */
export interface SchemaOptions<T> {
  description?: string;
  /**
   * The JSON Schema `default`. Advisory: it is shown to the model and it is NOT
   * filled in at parse time, because a runtime that invented values would make
   * `Infer<>` a lie — `indent?: number` would never actually be `undefined`.
   */
  default?: T;
}

export interface StringOptions extends SchemaOptions<string> {
  minLength?: number;
  maxLength?: number;
  /** An ECMAScript regular expression source, per JSON Schema. */
  pattern?: string;
  format?: string;
}

export interface NumberOptions extends SchemaOptions<number> {
  minimum?: number;
  maximum?: number;
}

export interface ArrayOptions<T> extends SchemaOptions<T[]> {
  minItems?: number;
  maxItems?: number;
}

export interface ObjectOptions extends SchemaOptions<never> {
  /**
   * Whether keys the shape does not name are allowed. Defaults to `false`: a
   * model that invents an argument should be told, not silently obeyed.
   */
  additionalProperties?: boolean;
}

/**
 * A schema node, carrying the TypeScript type it describes.
 *
 * `__type` and `__optional` exist only in the type system (`declare` emits no
 * property). They are what makes `Schema<string>` and `Schema<number>`
 * different types — without them every schema would be structurally identical
 * and `Infer<>` would resolve to `unknown` everywhere, which is precisely the
 * failure this file exists to prevent.
 */
export class Schema<T, Opt extends boolean = false> {
  declare readonly __type: T;
  declare readonly __optional: Opt;

  constructor(
    /** The node as emitted, already frozen. */
    protected readonly node: JsonSchema,
    /** Whether an enclosing `s.object` may leave this key out. */
    readonly isOptional: Opt
  ) {}

  /** This node as JSON Schema. A fresh object each call — callers mutate. */
  toJSON(): JsonSchema {
    return structuredClone(this.node);
  }

  /** The JSON Schema text, ready for `ToolDef.parametersJson`. */
  toJsonString(indent = 0): string {
    return JSON.stringify(this.toJSON(), null, indent);
  }

  /** Mark the key optional in the enclosing object: not in `required`, `?` in the type. */
  optional(): Schema<T, true> {
    return new Schema<T, true>(this.node, true);
  }

  /** Attach a description. Models read it; so do the humans debugging them. */
  describe(description: string): Schema<T, Opt> {
    return new Schema<T, Opt>({ ...this.node, description }, this.isOptional);
  }

  /** Widen to `T | null`, emitting `anyOf: [<node>, {type: "null"}]`. */
  nullable(): Schema<T | null, Opt> {
    return new Schema<T | null, Opt>(
      { anyOf: [stripAnnotations(this.node), { type: "null" }], ...annotations(this.node) },
      this.isOptional
    );
  }

  /** Validate `value` against this schema. Empty array means it conforms. */
  validate(value: unknown): ValidationIssue[] {
    return validate(this.node, value);
  }

  /**
   * Parse `argumentsJson` and validate it, or throw `BadArguments`.
   *
   * This is what the `plugin({...})` form calls before it reaches your handler,
   * so a handler's parameter really has the type `Infer<>` claims. Errors are
   * thrown, not returned, because `PluginError.from` already turns them into
   * the in-band `BAD_ARGUMENTS` result the AI loop reads.
   */
  parse(value: unknown): T {
    const issues = this.validate(value);
    if (issues.length > 0) throw badArguments(issues);
    return value as T;
  }

  /** {@link parse} over a JSON string, with the parse error reported the same way. */
  parseJson(json: string): T {
    let value: unknown;
    try {
      value = JSON.parse(json && json.trim() ? json : "{}");
    } catch (e) {
      throw badArguments([{ path: "", message: `is not valid JSON: ${(e as Error).message}` }]);
    }
    return this.parse(value);
  }
}

/** An object schema. Keeps its shape so a harness can report per-key detail. */
export class ObjectSchema<S extends Shape> extends Schema<InferShape<S>, false> {
  constructor(
    readonly shape: S,
    node: JsonSchema
  ) {
    super(node, false);
  }

  /** Narrowing override — `optional()` on an object still yields an object type. */
  override optional(): Schema<InferShape<S>, true> {
    return new Schema<InferShape<S>, true>(this.node, true);
  }

  /** The property names JSON Schema will mark `required`, in shape order. */
  requiredKeys(): string[] {
    return Object.entries(this.shape)
      .filter(([, v]) => !v.isOptional)
      .map(([k]) => k);
  }
}

/** Any schema, for constraints that do not care which. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnySchema = Schema<any, any>;

/** Any object schema — what a tool's `input` must be. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnyObjectSchema = ObjectSchema<any>;

/** The shape passed to `s.object`. */
export type Shape = Record<string, AnySchema>;

/** The TypeScript type a schema describes. */
export type Infer<S> = S extends Schema<infer T, boolean> ? T : never;

/** Flattens an intersection so editors show one object, not `A & B`. */
export type Simplify<T> = { [K in keyof T]: T[K] } & {};

type OptionalKeys<S extends Shape> = {
  [K in keyof S]-?: S[K] extends Schema<unknown, true> ? K : never;
}[keyof S];

type RequiredKeys<S extends Shape> = Exclude<keyof S, OptionalKeys<S>>;

/**
 * The object type a shape describes — optional keys really are `?`.
 *
 * The empty shape is special-cased to `Record<string, never>` rather than to
 * `{}`, because `{}` is TypeScript's "any non-nullish value" and would accept
 * `{ anything: 1 }` — while the emitted schema, with `additionalProperties:
 * false`, rejects it. That divergence is exactly what
 * `types-test/schema-agreement.ts` exists to catch, and it caught this one.
 */
export type InferShape<S extends Shape> = [keyof S] extends [never]
  ? Record<string, never>
  : Simplify<
      { [K in RequiredKeys<S>]: Infer<S[K]> } & { [K in OptionalKeys<S>]?: Infer<S[K]> }
    >;

// ── the builder ──────────────────────────────────────────────────────────────

function node(base: JsonSchema, opts?: SchemaOptions<unknown>): JsonSchema {
  const out: JsonSchema = { ...base };
  if (opts?.description !== undefined) out.description = opts.description;
  if (opts?.default !== undefined) out.default = opts.default;
  return out;
}

/** Annotation keywords, which survive `.nullable()` at the top level. */
function annotations(n: JsonSchema): JsonSchema {
  const out: JsonSchema = {};
  if (n.description !== undefined) out.description = n.description;
  if (n.default !== undefined) out.default = n.default;
  return out;
}

function stripAnnotations(n: JsonSchema): JsonSchema {
  const { description: _d, default: _v, ...rest } = n;
  return rest;
}

/**
 * The schema builder.
 *
 * Every method returns a fresh immutable node, so a shared sub-schema cannot be
 * mutated out from under another tool that reuses it.
 */
export const s = {
  string(opts?: StringOptions): Schema<string> {
    const n = node({ type: "string" }, opts);
    if (opts?.minLength !== undefined) n.minLength = opts.minLength;
    if (opts?.maxLength !== undefined) n.maxLength = opts.maxLength;
    if (opts?.pattern !== undefined) n.pattern = opts.pattern;
    if (opts?.format !== undefined) n.format = opts.format;
    return new Schema<string>(n, false);
  },

  number(opts?: NumberOptions): Schema<number> {
    const n = node({ type: "number" }, opts);
    if (opts?.minimum !== undefined) n.minimum = opts.minimum;
    if (opts?.maximum !== undefined) n.maximum = opts.maximum;
    return new Schema<number>(n, false);
  },

  /** A whole number. `type: "integer"`, and {@link validate} rejects `1.5`. */
  integer(opts?: NumberOptions): Schema<number> {
    const n = node({ type: "integer" }, opts);
    if (opts?.minimum !== undefined) n.minimum = opts.minimum;
    if (opts?.maximum !== undefined) n.maximum = opts.maximum;
    return new Schema<number>(n, false);
  },

  boolean(opts?: SchemaOptions<boolean>): Schema<boolean> {
    return new Schema<boolean>(node({ type: "boolean" }, opts), false);
  },

  /**
   * A closed set of string values. Pass the array `as const` to get the union
   * type — `s.enum(["a", "b"] as const)` is `Schema<"a" | "b">`.
   */
  enum<const V extends readonly [string, ...string[]]>(
    values: V,
    opts?: SchemaOptions<V[number]>
  ): Schema<V[number]> {
    return new Schema<V[number]>(
      node({ type: "string", enum: [...values] }, opts),
      false
    );
  },

  /** Exactly one value. */
  literal<const V extends string | number | boolean>(
    value: V,
    opts?: SchemaOptions<V>
  ): Schema<V> {
    const type = typeof value === "string" ? "string" : typeof value === "number" ? "number" : "boolean";
    return new Schema<V>(node({ type, const: value, enum: [value] }, opts), false);
  },

  array<S extends AnySchema>(
    item: S,
    opts?: ArrayOptions<Infer<S>>
  ): Schema<Infer<S>[]> {
    const n = node({ type: "array", items: item.toJSON() }, opts);
    if (opts?.minItems !== undefined) n.minItems = opts.minItems;
    if (opts?.maxItems !== undefined) n.maxItems = opts.maxItems;
    return new Schema<Infer<S>[]>(n, false);
  },

  object<S extends Shape>(shape: S, opts?: ObjectOptions): ObjectSchema<S> {
    const properties: Record<string, JsonSchema> = {};
    const required: string[] = [];
    for (const [key, value] of Object.entries(shape)) {
      properties[key] = value.toJSON();
      if (!value.isOptional) required.push(key);
    }
    const n: JsonSchema = node({ type: "object", properties }, opts);
    // An empty `required` is omitted: draft-07 forbids an empty array, and some
    // providers reject the schema outright rather than ignoring it.
    if (required.length > 0) n.required = required;
    n.additionalProperties = opts?.additionalProperties ?? false;
    return new ObjectSchema<S>(shape, n);
  },

  /** An escape hatch: any JSON value, unchecked. */
  any(opts?: SchemaOptions<unknown>): Schema<unknown> {
    return new Schema<unknown>(node({}, opts), false);
  },

  /** A raw JSON Schema with the type you assert it has. Unvalidated by TS. */
  raw<T>(schema: JsonSchema): Schema<T> {
    return new Schema<T>(schema, false);
  },
};

// ── validation ───────────────────────────────────────────────────────────────

/** One reason a value does not conform. `path` is a JSON-Pointer-ish location. */
export interface ValidationIssue {
  /** `""` for the root, else `foo.bar[0]`. */
  path: string;
  /** Reads as a sentence after the path: "`indent` must be an integer". */
  message: string;
}

/** Render issues the way a tool's `BAD_ARGUMENTS` message should read. */
export function formatIssues(issues: readonly ValidationIssue[]): string {
  return issues
    .map((i) => (i.path ? `\`${i.path}\` ${i.message}` : `the arguments ${i.message}`))
    .join("; ");
}

function badArguments(issues: ValidationIssue[]): Error {
  return new BadArguments({ message: formatIssues(issues) });
}

function join(path: string, key: string | number): string {
  if (typeof key === "number") return `${path}[${key}]`;
  return path ? `${path}.${key}` : key;
}

function typeName(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "an array";
  switch (typeof value) {
    case "string":
      return "a string";
    case "number":
      return "a number";
    case "boolean":
      return "a boolean";
    case "undefined":
      return "missing";
    default:
      return "an object";
  }
}

/**
 * Validate `value` against `schema`, returning every reason it does not fit.
 *
 * Only the keywords {@link JsonSchema} declares are enforced — this is not a
 * general draft-07 implementation, and it says so rather than accepting a
 * schema it would silently ignore half of.
 */
export function validate(schema: JsonSchema, value: unknown, path = ""): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (schema.anyOf) {
    const ok = schema.anyOf.some((alt) => validate(alt, value, path).length === 0);
    if (!ok) {
      issues.push({ path, message: `does not match any allowed form (got ${typeName(value)})` });
    }
    return issues;
  }

  switch (schema.type) {
    case "string":
      if (typeof value !== "string") {
        return [{ path, message: `must be a string (got ${typeName(value)})` }];
      }
      if (schema.minLength !== undefined && value.length < schema.minLength) {
        issues.push({ path, message: `must be at least ${schema.minLength} characters` });
      }
      if (schema.maxLength !== undefined && value.length > schema.maxLength) {
        issues.push({ path, message: `must be at most ${schema.maxLength} characters` });
      }
      if (schema.pattern !== undefined && !new RegExp(schema.pattern).test(value)) {
        issues.push({ path, message: `must match /${schema.pattern}/` });
      }
      break;

    case "number":
    case "integer":
      if (typeof value !== "number" || Number.isNaN(value)) {
        return [{ path, message: `must be a number (got ${typeName(value)})` }];
      }
      if (schema.type === "integer" && !Number.isInteger(value)) {
        issues.push({ path, message: `must be a whole number` });
      }
      if (schema.minimum !== undefined && value < schema.minimum) {
        issues.push({ path, message: `must be >= ${schema.minimum}` });
      }
      if (schema.maximum !== undefined && value > schema.maximum) {
        issues.push({ path, message: `must be <= ${schema.maximum}` });
      }
      break;

    case "boolean":
      if (typeof value !== "boolean") {
        return [{ path, message: `must be true or false (got ${typeName(value)})` }];
      }
      break;

    case "null":
      if (value !== null) return [{ path, message: `must be null (got ${typeName(value)})` }];
      break;

    case "array": {
      if (!Array.isArray(value)) {
        return [{ path, message: `must be an array (got ${typeName(value)})` }];
      }
      if (schema.minItems !== undefined && value.length < schema.minItems) {
        issues.push({ path, message: `must have at least ${schema.minItems} items` });
      }
      if (schema.maxItems !== undefined && value.length > schema.maxItems) {
        issues.push({ path, message: `must have at most ${schema.maxItems} items` });
      }
      if (schema.items) {
        value.forEach((item, i) => {
          issues.push(...validate(schema.items!, item, join(path, i)));
        });
      }
      break;
    }

    case "object": {
      if (value === null || typeof value !== "object" || Array.isArray(value)) {
        return [{ path, message: `must be an object (got ${typeName(value)})` }];
      }
      const obj = value as Record<string, unknown>;
      for (const key of schema.required ?? []) {
        // `undefined` is absence in JavaScript, and JSON has no way to send it,
        // so an explicit `{ indent: undefined }` is treated as omitted rather
        // than as a present key of the wrong type.
        if (obj[key] === undefined) {
          issues.push({ path: join(path, key), message: "is required" });
        }
      }
      for (const [key, sub] of Object.entries(schema.properties ?? {})) {
        if (obj[key] === undefined) continue;
        issues.push(...validate(sub, obj[key], join(path, key)));
      }
      if (schema.additionalProperties === false) {
        const known = new Set(Object.keys(schema.properties ?? {}));
        for (const key of Object.keys(obj)) {
          if (!known.has(key) && obj[key] !== undefined) {
            issues.push({ path: join(path, key), message: "is not a known argument" });
          }
        }
      }
      break;
    }

    default:
      // No `type`: an `s.any()` node, or a `const`/`enum`-only node.
      break;
  }

  if (schema.enum && !schema.enum.some((v) => Object.is(v, value))) {
    issues.push({
      path,
      message: `must be one of ${schema.enum.map((v) => JSON.stringify(v)).join(", ")}`,
    });
  }
  if (schema.const !== undefined && !Object.is(schema.const, value)) {
    issues.push({ path, message: `must be ${JSON.stringify(schema.const)}` });
  }

  return issues;
}
