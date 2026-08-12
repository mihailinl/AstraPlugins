/**
 * Level-2 tests: a real plugin, a real gRPC handshake, real protobuf.
 *
 * Every assertion here corresponds to a failure that was invisible at level 1
 * and shipped anyway — see the header of `src/testing/mock-daemon.ts`. The
 * session-token one is the sharpest: for three releases no SDK sent
 * `x-session-token`, every host RPC after `Register` was `unauthenticated` on a
 * user's machine, and every unit test in the repo was green.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { plugin, tool, s } = require("../dist/index.js");
const { MockDaemon, utteranceChunks, totalBytes } = require("../dist/testing/index.js");
const { PROTOCOL_VERSION, SDK_NAME, SDK_VERSION } = require("../dist/protocol.js");

/** Every daemon started here, torn down at the end even if a test threw. */
const started = [];
async function daemon(opts) {
  const d = await MockDaemon.start(opts);
  started.push(d);
  return d;
}
after(async () => {
  for (const d of started) await d.stop();
});

function demo() {
  return plugin({
    tools: {
      shout: tool({
        description: "Uppercase a string.",
        input: s.object({ text: s.string() }),
        run: async ({ text }, ctx) => {
          await ctx.info(`shouting ${text.length} chars`);
          await ctx.fireTrigger("shouted", { length: text.length });
          await ctx.setVariable("last_shout", text);
          return text.toUpperCase();
        },
      }),
    },
    triggers: { shouted: { label: "Shouted" } },
    tts: {
      voices: [{ id: "v1", name: "One", language: "en", gender: "neutral" }],
      configFields: [
        { id: "warmth", label: "Warmth", fieldType: "number", min: 0, max: 1, hasMin: true, hasMax: true },
      ],
      synthesize: () => ({ data: Buffer.from([1, 2, 3]), format: "wav", sampleRate: 16000, durationMs: 1 }),
    },
  });
}

test("the plugin registers, and the handshake carries what the daemon needs", async () => {
  const d = await daemon({ config: { indent: 4 }, language: "uk" });
  const wire = await d.launch(demo(), { pluginId: "demo" });

  const [reg] = d.registrations;
  assert.equal(reg.pluginId, "demo");
  assert.equal(reg.authToken, d.authToken, "the spawn token must be echoed back");
  assert.equal(reg.protocolVersion, PROTOCOL_VERSION);
  assert.equal(reg.sdkName, SDK_NAME);
  assert.equal(reg.sdkVersion, SDK_VERSION);
  assert.deepEqual([...reg.capabilities].sort(), ["tools", "triggers", "tts"]);
  assert.ok(reg.port > 0 && reg.port === wire.port);

  // The config and language from the Register response reached the plugin.
  assert.deepEqual(wire.plugin.config, { indent: 4 });
  assert.equal(wire.plugin.language, "uk");
});

test("every host RPC after Register carries the session token", async () => {
  const d = await daemon();
  const wire = await d.launch(demo());
  const res = await wire.callTool("shout", { text: "hey" });
  assert.equal(res.result, "HEY");

  const calls = d.calls();
  assert.ok(calls.length > 1);
  for (const call of calls) {
    if (call.method === "Register") {
      assert.equal(call.sessionToken, undefined, "Register is the one exempt path");
    } else {
      assert.equal(
        call.sessionToken,
        d.sessionToken,
        `${call.method} reached the daemon without x-session-token — it would be \`unauthenticated\``
      );
    }
  }
  // `causedBy: undefined` is the assertion, not noise: this tool was called
  // without an invocation lease, and the SDK must not invent one.
  assert.deepEqual(d.firedTriggers(), [
    { triggerType: "shouted", payloadJson: '{"length":3}', causedBy: undefined },
  ]);
  assert.deepEqual(d.variables(), [{ name: "last_shout", value: "hey", scope: "session" }]);
  assert.ok(d.logs().some((l) => l.level === "info" && l.message.includes("shouting 3 chars")));
});

test("a daemon that demands the token refuses a plugin that does not send one", async () => {
  // The mirror of the check above: prove the daemon side is not vacuous.
  const d = await daemon();
  const wire = await d.launch(demo());
  await assert.rejects(
    () =>
      new Promise((resolve, reject) => {
        const { service } = require("../dist/proto-loader.js");
        const stub = new (service("PluginHostService"))(
          d.address,
          require("@grpc/grpc-js").credentials.createInsecure()
        );
        stub.PluginLog({ pluginId: "x", level: "info", message: "hi" }, (err, res) =>
          err ? reject(err) : resolve(res)
        );
      }),
    /UNAUTHENTICATED|missing x-session-token/
  );
  assert.ok(wire.port > 0);
});

test("the capability server refuses a caller without the spawn token", async () => {
  // SECURITY: loopback is not a boundary between processes of the same user.
  // With ASTRA_PLUGIN_CAPABILITY_AUTH=require, a call with no `x-plugin-token`
  // is refused; the default `warn` stage accepts it and says so once.
  const before = process.env.ASTRA_PLUGIN_CAPABILITY_AUTH;
  process.env.ASTRA_PLUGIN_CAPABILITY_AUTH = "require";
  try {
    const d = await daemon();
    const wire = await d.launch(demo());
    assert.equal((await wire.listTools()).length, 1, "the daemon's own call is allowed");
    await assert.rejects(() => wire.unaryUnauthenticated("ListTools"), /UNAUTHENTICATED/);
  } finally {
    if (before === undefined) delete process.env.ASTRA_PLUGIN_CAPABILITY_AUTH;
    else process.env.ASTRA_PLUGIN_CAPABILITY_AUTH = before;
  }
});

test("config fields survive the wire under keepCase: false", async () => {
  // `PluginConfigFieldsResponse.config_fields` is `configFields` on the wire.
  // A snake_case key is dropped by protobufjs without a word and the daemon
  // renders an empty settings page — invisible at level 1, visible here.
  const d = await daemon();
  const wire = await d.launch(demo());
  const res = await wire.unary("TtsGetConfigFields");
  assert.equal(res.configFields.length, 1);
  assert.equal(res.configFields[0].id, "warmth");
  assert.equal(res.configFields[0].hasMax, true, "the presence flags must survive encoding");
});

test("a whole utterance survives a real bidi stream", async () => {
  const received = [];
  const app = plugin({
    stt: {
      languages: ["en"],
      async *transcribeStream(audio) {
        for await (const chunk of audio) {
          received.push(chunk.data);
          await new Promise((r) => setImmediate(r));
        }
        yield { text: "done", isFinal: true };
      },
    },
  });
  const d = await daemon();
  const wire = await d.launch(app);
  const chunks = utteranceChunks({ seedMs: 2000, liveMs: 4000 });
  const events = await wire.sttProcess(chunks);

  assert.deepEqual(
    events.map((e) => e.text),
    ["done"]
  );
  assert.equal(Buffer.concat(received).length, totalBytes(chunks));
});

test("a tool failure is data on the wire, not a gRPC status", async () => {
  const d = await daemon();
  const wire = await d.launch(demo());
  const res = await wire.callTool("shout", { text: 4 });
  assert.equal(res.success, false);
  assert.match(res.error, /BAD_ARGUMENTS/);
  assert.equal(res.errorDetail.code, "PLUGIN_ERROR_BAD_ARGUMENTS");
});

test("an unknown argv flag does not kill the plugin", async () => {
  // The daemon passes `--capabilities` (and will pass more). Python's argparse
  // used to EXIT on an unknown flag, which killed every plugin of that era;
  // `launch` always passes it, and this asserts the rest of argv still parses.
  const d = await daemon();
  const wire = await d.launch(demo(), { extraArgs: ["--something-new=1", "--flag"] });
  assert.equal((await wire.healthCheck()).healthy, true);
});
