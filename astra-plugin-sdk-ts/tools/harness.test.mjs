/**
 * Level-1 harness tests: the harness itself, and the SDK behaviour it exposes.
 *
 * Each of these was written by breaking the thing it checks and watching it go
 * red; a test that cannot fail is worse than no test. The STT one is the
 * pointed example — with the SDK's queue bound lowered to 32, the utterance
 * arrives truncated and `full utterance survives back-pressure` fails, which is
 * the bug `spec/limits.yaml` was written to end.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { Plugin, plugin, tool, s, NotConfigured, RateLimited } = require("../dist/index.js");
const {
  Harness,
  RecordingHost,
  utteranceChunks,
  totalBytes,
  checksum,
  firehoseEvents,
} = require("../dist/testing/index.js");
const { STT_AUDIO_CHANNEL_CAPACITY } = require("../dist/generated/limits.js");

// ── a plugin to test the harness with ────────────────────────────────────────

function demo() {
  const seen = [];
  const app = plugin({
    tools: {
      echo: tool({
        description: "Echo a string back.",
        input: s.object({ text: s.string(), times: s.integer({ minimum: 1 }).optional() }),
        run: ({ text, times }) => text.repeat(times ?? 1),
      }),
      needs_key: tool({
        description: "Fails the way a misconfigured tool should.",
        input: s.object({}),
        run: () => {
          throw new NotConfigured("api_key", { message: "No API key configured." });
        },
      }),
    },
    triggers: {
      on_echo: { label: "Echoed" },
    },
    onConfigChanged: (config, ctx) => {
      seen.push(config);
      if (typeof config.watched === "string") void ctx.setVariable("watched", config.watched);
    },
    onStart: async (ctx) => {
      await ctx.info("started");
    },
    healthCheck: (ctx) => ({ healthy: true, status: `lang=${ctx.language}` }),
  });
  return { app, seen };
}

// ── the harness ──────────────────────────────────────────────────────────────

test("start() runs the daemon's lifecycle in the daemon's order", async () => {
  const { app, seen } = demo();
  const h = await Harness.create(app).withConfig({ watched: "v1" }).withLanguage("ru").start();

  assert.deepEqual(seen, [{ watched: "v1" }], "onConfigChanged must run before onStart");
  assert.equal(h.plugin.language, "ru");
  assert.deepEqual(h.host.logs(), [{ level: "info", message: "started" }]);
  assert.equal(h.host.variable("watched"), "v1");
  assert.deepEqual(await h.healthCheck(), { healthy: true, status: "lang=ru" });
});

test("tools go through the real CallTool handler", async () => {
  const h = await Harness.create(demo().app).start();
  assert.deepEqual(await h.toolNames(), ["echo", "needs_key"]);
  const ok = await h.callTool("echo", { text: "ab", times: 2 });
  assert.deepEqual({ success: ok.success, result: ok.result }, { success: true, result: "abab" });
});

test("a schema violation is an in-band BAD_ARGUMENTS, not a transport error", async () => {
  // In-band matters: the AI loop reads the tool result, and a gRPC status hides
  // the failure from the one reader that could correct it.
  const h = await Harness.create(demo().app).start();
  const res = await h.callTool("echo", { times: 2 });
  assert.equal(res.success, false);
  assert.match(res.error, /BAD_ARGUMENTS/);
  assert.match(res.error, /`text` is required/);
  assert.equal(res.errorDetail.code, "PLUGIN_ERROR_BAD_ARGUMENTS");
});

test("a thrown NotConfigured carries the config field to the UI", async () => {
  const h = await Harness.create(demo().app).start();
  const res = await h.callTool("needs_key", {});
  assert.equal(res.success, false);
  assert.equal(res.errorDetail.configField, "api_key");
  assert.match(res.error, /NOT_CONFIGURED/);
});

test("schema() enforces an object root and assertSchema* work both ways", async () => {
  const h = await Harness.create(demo().app).start();
  const schema = await h.schema("echo");
  assert.equal(schema.type, "object");
  assert.deepEqual(schema.required, ["text"]);
  await h.assertSchemaAccepts("echo", { text: "x" });
  await h.assertSchemaRejects("echo", { text: 1 });
  await assert.rejects(() => h.assertSchemaAccepts("echo", {}), /rejects arguments its type allows/);
  await assert.rejects(() => h.assertSchemaRejects("echo", { text: "x" }), /accepts/);
  await assert.rejects(() => h.schema("nope"), /no tool named "nope"/);
});

test("the recording host records, and can be told to fail", async () => {
  const host = new RecordingHost("demo");
  const h = await Harness.create(demo().app).withHost(host).start();

  await h.plugin.ctx().fireTrigger("on_echo", { text: "hi" });
  assert.deepEqual(host.firedTriggers()[0].payload, { text: "hi" });

  host.failAlways("fireTrigger", new Error("daemon said no"));
  await assert.rejects(() => h.plugin.ctx().fireTrigger("on_echo"), /daemon said no/);
});

test("without a host, a handler that reaches for the daemon says so", async () => {
  // Not a silent no-op: the convenience wrappers on `Plugin` swallow a missing
  // host, and a trigger that did not fire and said nothing is the failure that
  // takes an afternoon to find.
  const quiet = plugin({ triggers: { on_echo: { label: "Echoed" } } });
  const h = await Harness.create(quiet).withoutHost().start();
  await assert.rejects(() => h.plugin.ctx().fireTrigger("on_echo"), /not registered with one/);
});

test("the config fuzz set does not crash a well-behaved plugin", async () => {
  const h = await Harness.create(demo().app).start();
  assert.deepEqual(await h.fuzzConfig(), []);
});

test("the fuzz set catches a plugin that trusts its config's types", async () => {
  // The failure mode this exists for: `config.indent.toFixed()` on a config the
  // user typed as text.
  const brittle = plugin({
    onConfigChanged: (config) => {
      if ("indent" in config) String(config.indent).length && config.indent.toFixed(0);
    },
  });
  const failures = await Harness.create(brittle).start().then((h) => h.fuzzConfig());
  assert.ok(failures.length > 0, "a plugin that calls .toFixed() on a string must be caught");
  assert.ok(failures.some((f) => f.name === "wrong types"));
});

// ── streaming ────────────────────────────────────────────────────────────────

test("the full utterance survives back-pressure at the 500-slot bound", async () => {
  const received = [];
  const app = plugin({
    stt: {
      languages: ["en"],
      async *transcribeStream(audio) {
        for await (const chunk of audio) {
          received.push(chunk.data);
          // A slow provider: yielding to the loop is what lets the inbound
          // queue actually fill, which is the condition under test.
          await new Promise((r) => setImmediate(r));
        }
        yield { text: "done", isFinal: true };
      },
    },
  });

  const chunks = utteranceChunks();
  assert.ok(
    chunks.length > STT_AUDIO_CHANNEL_CAPACITY,
    `the golden utterance must exceed the ${STT_AUDIO_CHANNEL_CAPACITY}-slot bound; it has ${chunks.length}`
  );

  const h = await Harness.create(app).start();
  const run = await h.sttStream(chunks);

  assert.equal(run.status, null);
  assert.deepEqual(run.events, [{ text: "done", isFinal: true, confidence: 1, language: "" }]);
  assert.equal(received.length, chunks.length, "every chunk must reach the plugin");
  assert.equal(
    Buffer.concat(received).length,
    totalBytes(chunks),
    "the audio must arrive whole — a truncating bridge is how streaming STT lost every utterance"
  );
  assert.equal(
    checksum(received.map((data) => ({ data }))),
    checksum(chunks),
    "the audio must arrive in order"
  );
  assert.ok(run.pauses > 0, "back-pressure must have engaged; otherwise the bound is untested");
});

test("one-shot STT buffers the utterance and reads the options off the first chunk", async () => {
  let sawOptions;
  const app = plugin({
    stt: {
      languages: ["en"],
      transcribe: (audio, req, _ctx) => {
        sawOptions = req.options;
        return { text: `${audio.length} bytes at ${req.sampleRate}` };
      },
    },
  });
  const h = await Harness.create(app).start();
  const chunks = utteranceChunks({ seedMs: 200, liveMs: 100 });
  const run = await h.sttStream(chunks, { language: "ru", initialPrompt: "astra" });
  assert.deepEqual(sawOptions, { language: "ru", initialPrompt: "astra" });
  assert.equal(run.events[0].text, `${totalBytes(chunks)} bytes at 16000`);
});

test("AiComplete terminates the stream even when the author forgot to", async () => {
  const app = plugin({
    ai: {
      async *complete() {
        yield "one";
        yield "two";
      },
    },
  });
  const h = await Harness.create(app).start();
  const { chunks } = await h.aiComplete();
  assert.deepEqual(chunks, [{ textDelta: "one" }, { textDelta: "two" }, { done: true }]);
});

test("an AiComplete failure travels in-band, with the structured detail", async () => {
  const app = plugin({
    ai: {
      // eslint-disable-next-line require-yield
      async *complete() {
        throw new RateLimited({ message: "slow down", retryAfterMs: 3000 });
      },
    },
  });
  const h = await Harness.create(app).start();
  const { chunks, status } = await h.aiComplete();
  assert.equal(status, null, "a rate limit is data the daemon reads, not a transport fault");
  assert.match(chunks[0].error, /RATE_LIMITED/);
  assert.equal(chunks[0].errorDetail.retryAfterMs, 3000);
});

test("an absent hook answers UNIMPLEMENTED, which the daemon reads as absence", async () => {
  const h = await Harness.create(demo().app).start();
  const status = await h.unaryStatus("TtsSynthesize", { text: "hi" });
  assert.equal(status.code, 12, "gRPC UNIMPLEMENTED");
});

test("the object form claims only the hooks the definition supplies", async () => {
  // `Plugin.overrides()` decides two things: whether `SttProcess` streams or
  // buffers, and whether `ai_provider` is registered at all. A wrapper that
  // defined every hook on its prototype would answer yes to both for every
  // plugin — a class-based adapter's easiest and quietest bug.
  const bare = plugin({ tools: {} }).instance;
  const rich = plugin({
    stt: { languages: ["en"], async *transcribeStream() {} },
    ai: { async *complete() {} },
  }).instance;
  const overrides = (p, name) =>
    Object.getPrototypeOf(Object.getPrototypeOf(p)) &&
    p[name] !== Object.getPrototypeOf(Object.getPrototypeOf(p))[name];

  assert.equal(overrides(bare, "sttTranscribeStream"), false);
  assert.equal(overrides(bare, "aiComplete"), false);
  assert.equal(overrides(rich, "sttTranscribeStream"), true);
  assert.equal(overrides(rich, "aiComplete"), true);

  // And the capability list the daemon is told about follows from that.
  const caps = await rich.discoverCapabilities();
  assert.deepEqual([...caps].sort(), ["ai_provider", "stt"]);
  assert.deepEqual(await bare.discoverCapabilities(), []);
});

test("the firehose fixture reaches onConversationEvent", async () => {
  const seen = [];
  const app = plugin({
    client: {},
    events: { onConversation: (id, event) => void seen.push([id, Object.keys(event)[0]]) },
  });
  const h = await Harness.create(app).start();
  for (const { conversationId, event } of firehoseEvents()) {
    await h.conversationEvent(conversationId, event);
  }
  assert.equal(seen.length, 10);
  assert.deepEqual(seen[0], ["conv-1", "userMessage"]);
  assert.deepEqual(seen.at(-1), ["conv-2", "error"]);
});

test("OnActiveTriggers reaches the context, and only for the types it names", async () => {
  // The set exists so a handler can skip expensive work nothing is listening
  // for. Nothing observed it: `handleOnActiveTriggers` writes
  // `this.activeTriggers`, `ctx.activeTriggers` reads it, and no test ran both
  // halves — delete the write and every `ctx.activeTriggers.has(...)` in every
  // TypeScript plugin answers false forever, with the RPC still returning `{}`
  // and conformance still recording OnActiveTriggers as `accepted`.
  //
  // `has("on_y")` is asserted false in the same breath so the test tells
  // "written" apart from "always true".
  const app = plugin({
    tools: {
      listening: tool({
        description: "Report what the daemon says is being listened for.",
        input: s.object({ type: s.string() }),
        run: ({ type }, ctx) => String(ctx.activeTriggers.has(type)),
      }),
    },
    triggers: { on_x: { label: "X" }, on_y: { label: "Y" } },
  });

  const h = await Harness.create(app).start();
  assert.equal((await h.callTool("listening", { type: "on_x" })).result, "false");

  await h.activeTriggers(["on_x"]);
  assert.equal((await h.callTool("listening", { type: "on_x" })).result, "true");
  assert.equal(
    (await h.callTool("listening", { type: "on_y" })).result,
    "false",
    "a type the daemon did not name must not be in the set",
  );

  // And the set is replaced, not accumulated: a command the user deleted stops
  // being listened for.
  await h.activeTriggers(["on_y"]);
  assert.equal((await h.callTool("listening", { type: "on_x" })).result, "false");
  assert.equal((await h.callTool("listening", { type: "on_y" })).result, "true");
});

test("a daemon event is decoded from the daemon's own key names", async () => {
  // Most daemon payloads are `serde_json::to_string(&AstraEvent)` —
  // `astra-core/src/event.rs`, `#[serde(tag = "type", rename_all =
  // "snake_case")]`. `rename_all` renames the *variants*; the fields stay as
  // declared, which is snake_case. The SDK used to `as`-cast this object to a
  // camelCase shape, so `event.commandId` was `undefined` on every event
  // forever and the compiler agreed it was a `string`.
  //
  // The two `command_*` events are NARROWED by the daemon
  // (`plugins::event_view::for_plugin`) and written key by key. `trigger_text`
  // — the phrase the user typed or spoke — is not among those keys any more,
  // and two of the values below depend on WHO is reading: the payloads here are
  // what a plugin that did NOT fire this command receives, so `command_name` is
  // `""` and `fired_by` is null.
  const seen = [];
  class Listener extends Plugin {
    subscribedEvents() {
      return ["command_triggered", "command_completed", "state_changed"];
    }
    async onCommandTriggered(e) {
      seen.push(["triggered", e.commandId, e.commandName, e.triggerType, e.runId, e.firedBy]);
    }
    async onCommandCompleted(e) {
      seen.push(["completed", e.commandId, e.commandName, e.success]);
    }
    async onStateChanged(e) {
      seen.push(["state", e.previous, e.current]);
    }
  }

  const h = await Harness.create(new Listener()).start();
  await h.event("command_triggered", {
    type: "command_triggered",
    command_id: "cmd-1",
    command_name: "",
    trigger_type: "text",
    run_id: "5f0a1c62-0000-0000-0000-000000000001",
    fired_by: null,
  });
  await h.event("command_completed", {
    type: "command_completed",
    command_id: "cmd-1",
    command_name: "",
    success: true,
  });
  await h.event("state_changed", { type: "state_changed", previous: "idle", current: "listening" });

  assert.deepEqual(seen, [
    ["triggered", "cmd-1", "", "text", "5f0a1c62-0000-0000-0000-000000000001", null],
    ["completed", "cmd-1", "", true],
    ["state", "idle", "listening"],
  ]);
});
