/**
 * The proof that `s`'s two halves agree.
 *
 * A schema builder that emits JSON Schema *and* narrows a TypeScript type has
 * one failure mode that matters: the two disagreeing. `required: ["indent"]`
 * beside `indent?: number` means a model is told an argument is mandatory while
 * the handler is told it may be absent, and nothing in an ordinary test suite
 * notices — the runtime tests pass, the types compile, and the tool misbehaves
 * only when a model happens to omit the key.
 *
 * So the agreement is asserted from both directions, in one place:
 *
 * - **Type ⇒ schema.** Every value in `accepted` is annotated
 *   `Infer<typeof schema>`. It compiles only if the type allows it, and
 *   `tools/schema.test.mjs` then asserts the emitted JSON Schema *validates* it.
 *   A type looser than the schema fails at run time.
 * - **Schema ⇒ type.** Every value in `rejected` carries `@ts-expect-error`. It
 *   compiles only if the type *forbids* it — TypeScript reports an unused
 *   `@ts-expect-error` as an error — and the test asserts the JSON Schema
 *   rejects it too. A type wider than the schema fails at compile time; a
 *   schema wider than the type fails at run time.
 *
 * Neither half can pass by accident, and neither half can be quietly deleted:
 * the compile is a build step (`npm run typetest`) and the runtime half reads
 * this file's own exports.
 */

// From `dist`, not from `src`: the runtime half of this proof
// (`tools/schema.test.mjs`) validates with the SAME build that emitted these
// schemas. Compiling a second copy of the source for the type test would leave
// two implementations that could disagree, which is the one thing this file
// exists to rule out.
import { s, type Infer } from "../dist/index.js";

/** One case: a schema, values its type allows, and values its type forbids. */
export interface AgreementCase {
  name: string;
  schema: { toJSON(): unknown };
  accepted: unknown[];
  rejected: unknown[];
}

// ── 1. required vs optional ──────────────────────────────────────────────────

const formatArgs = s.object({
  json: s.string({ description: "JSON to format" }),
  indent: s.integer({ minimum: 0, maximum: 10 }).optional(),
});

type FormatArgs = Infer<typeof formatArgs>;

const formatAccepted: FormatArgs[] = [
  { json: "{}" },
  { json: "{}", indent: 4 },
  { json: "{}", indent: 0 },
];

const formatRejected: unknown[] = [
  // @ts-expect-error `json` is required, and the schema says so too.
  { indent: 2 } satisfies FormatArgs,
  // @ts-expect-error `json` is a string, not a number.
  { json: 4 } satisfies FormatArgs,
  // @ts-expect-error `indent` is a number, not a string.
  { json: "{}", indent: "4" } satisfies FormatArgs,
  // @ts-expect-error unknown keys are rejected by the type AND by
  // `additionalProperties: false`.
  { json: "{}", indentation: 4 } satisfies FormatArgs,
];

// ── 2. enums narrow to a union ───────────────────────────────────────────────

const transformArgs = s.object({
  operation: s.enum(["format", "minify", "sort_keys"] as const),
  input: s.string(),
});

type TransformArgs = Infer<typeof transformArgs>;

const transformAccepted: TransformArgs[] = [
  { operation: "format", input: "{}" },
  { operation: "sort_keys", input: "{}" },
];

const transformRejected: unknown[] = [
  // @ts-expect-error "pretty" is not one of the three the enum declares.
  { operation: "pretty", input: "{}" } satisfies TransformArgs,
];

// ── 3. arrays, nesting and nullability ───────────────────────────────────────

const diffArgs = s.object({
  documents: s.array(s.string(), { minItems: 2, maxItems: 2 }),
  options: s
    .object({
      ignoreOrder: s.boolean().optional(),
      label: s.string().nullable().optional(),
    })
    .optional(),
});

type DiffArgs = Infer<typeof diffArgs>;

const diffAccepted: DiffArgs[] = [
  { documents: ["{}", "{}"] },
  { documents: ["{}", "{}"], options: {} },
  { documents: ["{}", "{}"], options: { ignoreOrder: true, label: null } },
  { documents: ["{}", "{}"], options: { label: "run 1" } },
];

const diffRejected: unknown[] = [
  // @ts-expect-error `documents` is an array of strings.
  { documents: "{}" } satisfies DiffArgs,
  // @ts-expect-error `documents` holds strings, not numbers.
  { documents: [1, 2] } satisfies DiffArgs,
  // @ts-expect-error `ignoreOrder` is a boolean.
  { documents: ["{}", "{}"], options: { ignoreOrder: "yes" } } satisfies DiffArgs,
];

// ── 4. a tool that takes nothing ─────────────────────────────────────────────

const noArgs = s.object({});
type NoArgs = Infer<typeof noArgs>;

const noArgsAccepted: NoArgs[] = [{}];
const noArgsRejected: unknown[] = [
  // @ts-expect-error the object is closed: no keys at all are allowed.
  { anything: 1 } satisfies NoArgs,
];

/**
 * The cases, for `tools/schema.test.mjs`.
 *
 * `accepted` and `rejected` are the SAME arrays the annotations above bound, so
 * the runtime half cannot drift from the type half by editing one of them.
 */
export const CASES: AgreementCase[] = [
  { name: "required vs optional", schema: formatArgs, accepted: formatAccepted, rejected: formatRejected },
  { name: "enum union", schema: transformArgs, accepted: transformAccepted, rejected: transformRejected },
  { name: "arrays and nullability", schema: diffArgs, accepted: diffAccepted, rejected: diffRejected },
  { name: "no arguments", schema: noArgs, accepted: noArgsAccepted, rejected: noArgsRejected },
];

/**
 * The `required` list the type says each schema should have.
 *
 * Written out by hand, because the point is to pin the mapping rather than to
 * recompute it: `optional()` means "not in `required`", and if that ever stops
 * being true this is the line that says so.
 */
export const EXPECTED_REQUIRED: Record<string, string[]> = {
  "required vs optional": ["json"],
  "enum union": ["operation", "input"],
  "arrays and nullability": ["documents"],
  "no arguments": [],
};
