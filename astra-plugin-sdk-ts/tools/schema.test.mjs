/**
 * The runtime half of the schema-builder proof, plus the validator's own tests.
 *
 * `types-test/schema-agreement.ts` is the compile-time half: it only compiles
 * if the inferred TypeScript type accepts every `accepted` fixture and rejects
 * every `rejected` one. This file takes those same arrays — the very objects
 * the annotations bound — and runs them through the emitted JSON Schema. The
 * two halves together are the claim "the type and the schema agree", and either
 * one alone is worth very little.
 *
 * Run: `npm test` (`pretest` compiles both).
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { s, validate, formatIssues } = require("../dist/schema.js");
const { CASES, EXPECTED_REQUIRED } = require("../dist-typetest/schema-agreement.js");

test("every value the TYPE accepts, the SCHEMA validates", () => {
  assert.ok(CASES.length >= 4, "the agreement fixture set went missing");
  for (const { name, schema, accepted } of CASES) {
    assert.ok(accepted.length > 0, `${name}: no accepted fixtures — the case proves nothing`);
    for (const value of accepted) {
      const issues = validate(schema.toJSON(), value);
      assert.equal(
        issues.length,
        0,
        `${name}: the type allows ${JSON.stringify(value)} but the emitted schema rejects it — ` +
          `${formatIssues(issues)}`
      );
    }
  }
});

test("every value the TYPE rejects, the SCHEMA rejects too", () => {
  for (const { name, schema, rejected } of CASES) {
    assert.ok(rejected.length > 0, `${name}: no rejected fixtures — the case proves nothing`);
    for (const value of rejected) {
      const issues = validate(schema.toJSON(), value);
      assert.ok(
        issues.length > 0,
        `${name}: the type forbids ${JSON.stringify(value)} and the emitted schema accepts it. ` +
          `A schema wider than its type is how a model learns to send arguments the handler ` +
          `cannot use`
      );
    }
  }
});

test("`required` is exactly the non-optional keys", () => {
  for (const { name, schema } of CASES) {
    const emitted = schema.toJSON().required ?? [];
    assert.deepEqual(
      [...emitted].sort(),
      [...EXPECTED_REQUIRED[name]].sort(),
      `${name}: \`required\` does not match what \`.optional()\` said`
    );
  }
});

test("an object closes itself against unknown keys", () => {
  const schema = s.object({ a: s.string() });
  assert.equal(schema.toJSON().additionalProperties, false);
  assert.equal(validate(schema.toJSON(), { a: "x", b: 1 }).length, 1);
  // Opting back in is explicit.
  const open = s.object({ a: s.string() }, { additionalProperties: true });
  assert.equal(validate(open.toJSON(), { a: "x", b: 1 }).length, 0);
});

test("an empty `required` is omitted, not emitted as []", () => {
  // draft-07 forbids an empty `required` array, and some providers reject the
  // whole tool rather than ignoring it.
  const schema = s.object({ a: s.string().optional() }).toJSON();
  assert.ok(!("required" in schema), "an all-optional object must not carry `required`");
});

test("integer rejects a fraction; number does not", () => {
  assert.equal(validate(s.integer().toJSON(), 1.5).length, 1);
  assert.equal(validate(s.number().toJSON(), 1.5).length, 0);
});

test("bounds, lengths and patterns are enforced", () => {
  assert.equal(validate(s.integer({ minimum: 1, maximum: 3 }).toJSON(), 4).length, 1);
  assert.equal(validate(s.string({ minLength: 2 }).toJSON(), "x").length, 1);
  assert.equal(validate(s.string({ pattern: "^a+$" }).toJSON(), "b").length, 1);
  assert.equal(validate(s.array(s.string(), { minItems: 2 }).toJSON(), ["a"]).length, 1);
});

test("nullable emits anyOf and accepts null", () => {
  const schema = s.string().nullable().toJSON();
  assert.deepEqual(schema.anyOf, [{ type: "string" }, { type: "null" }]);
  assert.equal(validate(schema, null).length, 0);
  assert.equal(validate(schema, "x").length, 0);
  assert.equal(validate(schema, 1).length, 1);
});

test("`default` is advisory: parse does not invent the value", () => {
  // If parsing filled defaults in, `indent?: number` would never be undefined
  // and `Infer<>` would be a lie about the handler's parameter.
  const schema = s.object({ indent: s.integer({ default: 2 }).optional() });
  assert.equal(schema.toJSON().properties.indent.default, 2);
  assert.deepEqual(schema.parse({}), {});
});

test("parseJson throws BadArguments naming the offending key", () => {
  const schema = s.object({ json: s.string() });
  assert.throws(
    () => schema.parseJson('{"json": 4}'),
    (e) => e.code === "BAD_ARGUMENTS" && /`json`/.test(e.message)
  );
  assert.throws(
    () => schema.parseJson("{not json"),
    (e) => e.code === "BAD_ARGUMENTS" && /not valid JSON/.test(e.message)
  );
});

test("an explicit undefined counts as absent, as JSON has no other way to say it", () => {
  const schema = s.object({ a: s.string().optional() }).toJSON();
  assert.equal(validate(schema, { a: undefined }).length, 0);
});

test("a schema node cannot be mutated through toJSON", () => {
  const schema = s.object({ a: s.string() });
  const first = schema.toJSON();
  first.required = ["nonsense"];
  assert.deepEqual(schema.toJSON().required, ["a"]);
});
