/**
 * The reference suite for a TypeScript plugin (§5.6).
 *
 * Read this alongside `src/plugin.ts`. It is meant to be copied: a plugin of
 * your own wants the same shape — a level-1 block that runs on every save, and
 * a short level-2 block that proves the thing really registers and answers over
 * gRPC.
 *
 * `pretest` bundles `src/plugin.ts` with the SDK left EXTERNAL, so the plugin
 * under test and the harness testing it are the same copy of the SDK. Bundling
 * it in would give two `Plugin` classes that look alike and share no state.
 *
 * Run: `bun run test` (or `npm test`).
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { app } = require("../dist/plugin.cjs");
const { Harness, MockDaemon, RecordingHost } = require("astra-plugin-sdk/testing");

// ── level 1: every tool, in process ──────────────────────────────────────────

/** A fresh harness per test: `operations` and config are per-plugin state. */
const start = (config = {}) => Harness.create(app).withConfig(config).start();

test("the three tools are declared with object-rooted schemas", async () => {
  const h = await start();
  assert.deepEqual(await h.toolNames(), ["json_format", "json_query", "json_diff"]);
  for (const name of await h.toolNames()) {
    const schema = await h.schema(name); // throws unless the root is an object
    assert.ok(Object.keys(schema.properties).length > 0, `${name} declares no parameters`);
    assert.equal(schema.additionalProperties, false);
  }
});

test("json_format honours the argument, then the setting, then 2", async () => {
  const h = await start({ default_indent: 4 });
  assert.equal((await h.callTool("json_format", { json: '{"a":1}', indent: 0 })).result, '{"a":1}');
  assert.equal((await h.callTool("json_format", { json: '{"a":1}' })).result, '{\n    "a": 1\n}');

  const plain = await Harness.create(app).start();
  assert.equal((await plain.callTool("json_format", { json: '{"a":1}' })).result, '{\n  "a": 1\n}');
});

test("a config the user typed as text does not become the indent", async () => {
  // The daemon delivers config it did not author. `"4"` is not 4.
  const h = await start({ default_indent: "4" });
  assert.equal((await h.callTool("json_format", { json: '{"a":1}' })).result, '{\n  "a": 1\n}');
});

test("malformed JSON is a BAD_ARGUMENTS naming the argument, not a crash", async () => {
  const h = await start();
  const res = await h.callTool("json_diff", { a: "{}", b: "{oops" });
  assert.equal(res.success, false);
  assert.match(res.error, /BAD_ARGUMENTS/);
  assert.match(res.error, /`b` is not valid JSON/);
});

test("a missing argument never reaches the handler", async () => {
  const h = await start();
  const res = await h.callTool("json_query", { json: "{}" });
  assert.equal(res.success, false);
  assert.match(res.error, /`path` is required/);
});

test("the schema and the handler agree about what is optional", async () => {
  const h = await start();
  await h.assertSchemaAccepts("json_format", { json: "{}" });
  await h.assertSchemaAccepts("json_format", { json: "{}", indent: 2 });
  await h.assertSchemaRejects("json_format", { json: "{}", indent: 99 });
  await h.assertSchemaRejects("json_format", { json: "{}", indentation: 2 });
  // And the schema's promise is kept at run time, not only on paper.
  assert.equal((await h.callTool("json_format", { json: "{}", indent: 99 })).success, false);
});

test("json_query walks a dot-path and reports a miss usefully", async () => {
  const h = await start();
  const doc = JSON.stringify({ data: { users: [{ name: "Ada" }] } });
  assert.equal((await h.callTool("json_query", { json: doc, path: "data.users[0].name" })).result, "Ada");
  const miss = await h.callTool("json_query", { json: doc, path: "data.teams[0].name" });
  assert.equal(miss.success, false);
  assert.match(miss.error, /Path 'data.teams\[0\].name' not found/);
});

test("json_diff reports added, removed and changed by path", async () => {
  const h = await start();
  const res = await h.callTool("json_diff", {
    a: JSON.stringify({ keep: 1, drop: 2, change: "x" }),
    b: JSON.stringify({ keep: 1, change: "y", add: 3 }),
  });
  assert.equal(res.success, true);
  assert.deepEqual(JSON.parse(res.result).map((d) => [d.path, d.type]).sort(), [
    ["add", "added"],
    ["change", "changed"],
    ["drop", "removed"],
  ]);
  assert.equal((await h.callTool("json_diff", { a: "{}", b: "{}" })).result, "Documents are identical");
});

test("the action's fields and its params describe the same four values", async () => {
  // A field the handler never reads is a control that does nothing; a param no
  // field can produce is a handler branch a command can never reach.
  const h = await start();
  const [type] = await h.actionTypes();
  const fields = type.fields.map((f) => f.id).sort();
  const params = Object.keys(app.definition.actions.json_transform.params.shape).sort();
  assert.deepEqual(fields, params);
  assert.equal(type.aiAvailable, true);
  assert.equal(type.aiPrimaryField, "input_json");
});

test("the action transforms, and publishes its result as a variable", async () => {
  const host = new RecordingHost("json-tools");
  const h = await Harness.create(app).withHost(host).withConfig({ default_indent: 2 }).start();

  const res = await h.executeAction("json_transform", {
    operation: "sort_keys",
    input_json: '{"b":1,"a":2}',
    store_in: "sorted",
  });
  assert.equal(res.success, true);
  assert.equal(res.result, '{\n  "a": 2,\n  "b": 1\n}');
  assert.equal(host.variable("sorted"), res.result);

  assert.equal(
    (await h.executeAction("json_transform", { operation: "minify", input_json: '{ "a" : 1 }' })).result,
    '{"a":1}'
  );
});

test("a daemon that refuses set_variable is not reported as success", async () => {
  // Failure injection earns its place here: without it the action returns the
  // transformed string and the user never learns the variable was not written.
  const host = new RecordingHost("json-tools").failAlways("setVariable", new Error("permission denied"));
  const h = await Harness.create(app).withHost(host).start();
  const res = await h.executeAction("json_transform", {
    operation: "format",
    input_json: "{}",
    store_in: "out",
  });
  assert.equal(res.success, false);
  assert.match(res.error, /permission denied/);
});

test("extract_path without a path is refused before it does anything", async () => {
  const h = await start();
  const res = await h.executeAction("json_transform", {
    operation: "extract_path",
    input_json: '{"a":1}',
  });
  assert.equal(res.success, false);
  assert.match(res.error, /`path` is required/);
});

test("the declared trigger type is what a command can subscribe to", async () => {
  const h = await start();
  const [trigger] = await h.triggerTypes();
  assert.equal(trigger.type, "on_invalid_json");
  assert.deepEqual(trigger.fields.map((f) => f.id), ["source"]);
});

test("the trigger fires only while a command is listening for it", async () => {
  // `ctx.activeTriggers` is the whole reason this plugin does not fire an RPC
  // per malformed document. The set is written by the SDK in exactly one place
  // (`handleOnActiveTriggers`) and read here — so delete the write and this
  // plugin silently stops firing, with every other test still green: the RPC
  // still answers `{}`, the tool still returns its BAD_ARGUMENTS, and
  // conformance still records OnActiveTriggers as `accepted`.
  const host = new RecordingHost("json-tools");
  const h = await Harness.create(app).withHost(host).start();

  // Nothing subscribed yet: a bad document is still an error, and still silent.
  assert.equal((await h.callTool("json_format", { json: "{oops" })).success, false);
  assert.deepEqual(host.firedTriggers(), []);

  await h.activeTriggers(["on_invalid_json"]);
  assert.equal((await h.callTool("json_query", { json: "{oops", path: "a" })).success, false);
  assert.deepEqual(
    host.firedTriggers().map((t) => [t.triggerType, JSON.parse(t.payloadJson).source]),
    [["on_invalid_json", "json"]],
  );

  // A type the daemon did not name is not in the set — otherwise "it fires"
  // and "it always fires" would look the same.
  await h.activeTriggers(["on_something_else"]);
  assert.equal((await h.callTool("json_format", { json: "{oops" })).success, false);
  assert.equal(host.firedTriggers().length, 1, "the subscription was replaced, not added to");
});

test("a daemon that refuses fire_trigger does not swallow the parse error", async () => {
  // The tool's job is to report bad JSON to the model. A daemon that denies
  // the trigger must not turn that into a different error, or into success.
  const host = new RecordingHost("json-tools").failAlways("fireTrigger", new Error("permission denied"));
  const h = await Harness.create(app).withHost(host).start();
  await h.activeTriggers(["on_invalid_json"]);

  const res = await h.callTool("json_format", { json: "{oops" });
  assert.equal(res.success, false);
  assert.match(res.error, /permission denied/);
});

test("no config the daemon can deliver crashes this plugin", async () => {
  const h = await start();
  assert.deepEqual(await h.fuzzConfig(), []);
});

test("healthCheck counts the work it has done", async () => {
  const h = await start();
  await h.callTool("json_format", { json: "{}" });
  const { healthy, status } = await h.healthCheck();
  assert.equal(healthy, true);
  assert.match(status, /operations processed/);
});

// ── level 2: it really registers and really answers ──────────────────────────

const daemons = [];
after(async () => {
  for (const d of daemons) await d.stop();
});

test("it registers with the capabilities its manifest claims, and answers over gRPC", async () => {
  const daemon = await MockDaemon.start({ config: { default_indent: 3 } });
  daemons.push(daemon);
  const wire = await daemon.launch(app, { pluginId: "json-tools" });

  // plugin.toml declares tools, actions and triggers. What the plugin tells the
  // daemon at registration has to be the same list, or the daemon offers the
  // user a capability the plugin does not serve.
  assert.deepEqual([...daemon.registrations[0].capabilities].sort(), ["actions", "tools", "triggers"]);

  const tools = await wire.listTools();
  assert.deepEqual(tools.map((t) => t.name), ["json_format", "json_query", "json_diff"]);
  // The schema survived protobuf, and is still parseable JSON on the far side.
  assert.equal(JSON.parse(tools[0].parametersJson).type, "object");

  const res = await wire.callTool("json_format", { json: '{"a":1}' });
  assert.equal(res.result, '{\n   "a": 1\n}', "the config from Register must have been applied");

  assert.ok(daemon.logs().some((l) => l.message.includes("json-tools ready")));
  assert.equal((await wire.healthCheck()).healthy, true);
});
