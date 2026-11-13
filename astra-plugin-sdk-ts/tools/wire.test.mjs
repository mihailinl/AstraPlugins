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

const { plugin, tool, s, commandsFromAstraFile } = require("../dist/index.js");
const { MockDaemon, utteranceChunks, totalBytes } = require("../dist/testing/index.js");
const { PROTOCOL_VERSION, SDK_NAME, SDK_VERSION } = require("../dist/protocol.js");
const { PLUGIN_IMAGE_REQUEST_MAX_BYTES, PLUGIN_MAX_MESSAGE_BYTES } = require("../dist/generated/limits.js");

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
        { id: "warmth", label: "Warmth", fieldType: "number", min: 0, max: 1, hasMin: true, hasMax: true, advanced: true },
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

test("the concrete HostClient implements getAiSettings and ctx reaches it over the wire", async () => {
  const d = await daemon();
  const wire = await d.launch(demo());
  const got = await wire.plugin.ctx().getAiSettings();
  assert.equal(got.provider, "ollama");
  assert.equal(got.model, "mock-model");
  assert.equal(got.isLoopback, true);
  assert.ok(d.calls().some((c) => c.method === "GetAiSettings" && c.sessionToken === d.sessionToken));
});

/** Speaks from inside a tool call, then reports what Astra answered and who it is. */
function announcer() {
  return plugin({
    tools: {
      announce: tool({
        description: "Say something aloud.",
        input: s.object({ text: s.string() }),
        run: async ({ text }, ctx) => {
          const said = await ctx.speak(text);
          const who = await ctx.getUserIdentity();
          await ctx.stopSpeaking();
          return JSON.stringify({ said, who });
        },
      }),
    },
  });
}

test("speak, stopSpeaking and getUserIdentity from a leased call reach the daemon with the token", async () => {
  const d = await daemon();
  const wire = await d.launch(announcer());
  const res = await wire.callTool("announce", { text: "The kettle has boiled." }, { causedBy: "lease-speak" });
  assert.equal(res.success, true, res.error);
  const { said, who } = JSON.parse(res.result);
  assert.deepEqual(said, { outcome: "SPOKEN" });
  assert.deepEqual(who, {
    installId: "mock-install-pseudonym",
    signedIn: true,
    authorized: true,
    accountId: "mock-account-pseudonym",
  });
  for (const method of ["Speak", "GetUserIdentity", "StopSpeaking"]) {
    const calls = d.callsTo(method);
    assert.equal(calls.length, 1, `${method} reached the daemon once`);
    assert.equal(calls[0].sessionToken, d.sessionToken, `${method} went out without x-session-token`);
  }
  assert.deepEqual(d.spoken(), ["The kettle has boiled."]);
  // Speaking is not a fire: nothing here spends the lease.
  assert.deepEqual(d.firedTriggers(), []);
});

test("a NOT_SPOKEN answer crosses the wire with its PluginError whole", async () => {
  const d = await daemon();
  d.speakResponse = {
    outcome: "PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "this plugin has used its speaking time",
      hint: "wait `retry_after_ms`; what was refused is not queued",
      retryAfterMs: 1500,
    },
  };
  const wire = await d.launch(announcer());
  const said = await wire.plugin.ctx().speak("Again.");
  assert.deepEqual(said, {
    outcome: "NOT_SPOKEN",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "this plugin has used its speaking time",
      hint: "wait `retry_after_ms`; what was refused is not queued",
      configField: "",
      retryAfterMs: 1500,
      docUrl: "",
    },
  });
});

test("an outcome this SDK does not know reads as UNSPECIFIED, never as one it does", () => {
  const { speakResultFromWire } = require("../dist/host-client.js");
  assert.deepEqual(speakResultFromWire({ outcome: 3, error: null }), { outcome: "NOT_SPOKEN" });
  assert.deepEqual(speakResultFromWire({ outcome: "PLUGIN_SPEECH_OUTCOME_STOPPED" }), { outcome: "STOPPED" });
  assert.deepEqual(speakResultFromWire({ outcome: 7 }), { outcome: "UNSPECIFIED" });
  assert.deepEqual(speakResultFromWire({}), { outcome: "UNSPECIFIED" });
});

/** Asks for a model and a speed from inside a tool call, then reports what Astra answered. */
function tuner() {
  return plugin({
    tools: {
      tune: tool({
        description: "Ask for a model.",
        input: s.object({ model: s.string() }),
        run: async ({ model }, ctx) => {
          const asked = await ctx.requestSettingsChange(
            [
              { path: "ai.model", value: model },
              { path: "voice.tts_speed", value: 1.2 },
            ],
            "tuned for this model"
          );
          return JSON.stringify(asked);
        },
      }),
    },
  });
}

test("requestSettingsChange from a leased call reaches the daemon with the token, values as JSON", async () => {
  const d = await daemon();
  const wire = await d.launch(tuner());
  const res = await wire.callTool("tune", { model: "gpt-4.1" }, { causedBy: "lease-tune" });
  assert.equal(res.success, true, res.error);
  assert.deepEqual(JSON.parse(res.result), { outcome: "APPLIED", code: "", refusedPath: "" });
  const calls = d.callsTo("RequestSettingsChange");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].sessionToken, d.sessionToken, "RequestSettingsChange went out without x-session-token");
  assert.deepEqual(d.settingsChangeRequests(), [
    {
      changes: [
        { path: "ai.model", valueJson: '"gpt-4.1"' },
        { path: "voice.tts_speed", valueJson: "1.2" },
      ],
      reason: "tuned for this model",
    },
  ]);
  // Asking is not a fire: made inside a leased call, it carries no lease.
  assert.equal(d.callsTo("RequestSettingsChange")[0].causedBy, undefined);
});

test("a REFUSED settings answer crosses the wire with its code, path and PluginError whole", async () => {
  const d = await daemon();
  d.settingsChangeResponse = {
    outcome: "PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED",
    refusedPath: "ai.model",
    code: "rate_limited",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "this plugin asked too often",
      retryAfterMs: 90000,
    },
  };
  const wire = await d.launch(tuner());
  const asked = await wire.plugin.ctx().requestSettingsChange([{ path: "ai.model", value: "m" }], "why");
  assert.deepEqual(asked, {
    outcome: "REFUSED",
    code: "rate_limited",
    refusedPath: "ai.model",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "this plugin asked too often",
      hint: "",
      configField: "",
      retryAfterMs: 90000,
      docUrl: "",
    },
  });
});

test("no settings limit is checked client-side: the daemon's refusal is what the plugin reads", async () => {
  const { SETTINGS_CHANGE_MAX_CHANGES, SETTINGS_CHANGE_REASON_MAX_CHARS } = require("../dist/generated/limits.js");
  const d = await daemon();
  d.settingsChangeResponse = { outcome: "PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED", code: "too_many" };
  const wire = await d.launch(tuner());
  const changes = Array.from({ length: SETTINGS_CHANGE_MAX_CHANGES + 1 }, (_, i) => ({ path: `p.${i}`, value: i }));
  // The same path twice, and a reason past the limit: sent as written.
  changes.push({ path: "p.0", value: "again" });
  const reason = "é".repeat(SETTINGS_CHANGE_REASON_MAX_CHARS + 60);
  const asked = await wire.plugin.ctx().requestSettingsChange(changes, reason);
  assert.deepEqual(asked, { outcome: "REFUSED", code: "too_many", refusedPath: "" });
  const [sent] = d.settingsChangeRequests();
  assert.equal(sent.changes.length, SETTINGS_CHANGE_MAX_CHANGES + 2);
  assert.equal(sent.reason, reason);
});

test("every settings outcome maps to its short name; one this SDK does not know is UNSPECIFIED", () => {
  const { settingsChangeResultFromWire } = require("../dist/host-client.js");
  const names = ["APPLIED", "UNCHANGED", "DECLINED", "TIMED_OUT", "REFUSED"];
  names.forEach((name, i) => {
    const want = { outcome: name, code: "", refusedPath: "" };
    assert.deepEqual(settingsChangeResultFromWire({ outcome: `PLUGIN_SETTINGS_CHANGE_OUTCOME_${name}` }), want);
    assert.deepEqual(settingsChangeResultFromWire({ outcome: i + 1, error: null }), want);
  });
  assert.deepEqual(settingsChangeResultFromWire({ outcome: 9 }), { outcome: "UNSPECIFIED", code: "", refusedPath: "" });
  assert.deepEqual(settingsChangeResultFromWire({}), { outcome: "UNSPECIFIED", code: "", refusedPath: "" });
});

test("setting values go out as JSON of any kind; a value JSON cannot hold throws", () => {
  const { settingValueJson, settingsChangeRequestToWire } = require("../dist/host-client.js");
  const json = (value) => settingValueJson({ path: "p", value });
  assert.equal(json("gpt-4.1"), '"gpt-4.1"');
  assert.equal(json(true), "true");
  assert.equal(json(1.2), "1.2");
  assert.equal(json(null), "null");
  assert.equal(json({ a: [1, "two"] }), '{"a":[1,"two"]}');
  assert.equal(json('say "hi"\n'), '"say \\"hi\\"\\n"');
  assert.equal(json("Алиса"), '"Алиса"');
  for (const bad of [Number.NaN, Number.NEGATIVE_INFINITY, undefined, Symbol("s"), [Number.NaN]]) {
    assert.throws(() => json(bad), TypeError);
  }
  assert.throws(() => json(10n), TypeError);
  assert.deepEqual(settingsChangeRequestToWire([{ path: "b", value: 1 }, { path: "a", value: 2 }], "r"), {
    changes: [
      { path: "b", valueJson: "1" },
      { path: "a", valueJson: "2" },
    ],
    reason: "r",
  });
});

/** Offers the first command of the `.astra` file it is given, then reports what Astra answered. */
function offerer() {
  return plugin({
    tools: {
      offer: tool({
        description: "Offer a command.",
        input: s.object({ file: s.string() }),
        run: async ({ file }, ctx) => {
          const [command] = commandsFromAstraFile(file);
          const offered = await ctx.proposeCommand("morning", command, "reads you the news");
          return JSON.stringify(offered);
        },
      }),
    },
  });
}

const MORNING_FILE = JSON.stringify({
  format: "astra-commands",
  version: 1,
  commands: [
    {
      name: "Good morning",
      triggers: [{ type: "text", phrases: ["good morning"] }],
      actions: [],
      enabled: true,
      source_id: "6f1c2a9e",
    },
  ],
});

test("proposeCommand from a leased call reaches the daemon with the token, the file's local members gone", async () => {
  const d = await daemon();
  const wire = await d.launch(offerer());
  const res = await wire.callTool("offer", { file: MORNING_FILE }, { causedBy: "lease-offer" });
  assert.equal(res.success, true, res.error);
  assert.deepEqual(JSON.parse(res.result), { outcome: "SAVED", enabled: true, code: "" });
  const calls = d.callsTo("ProposeCommand");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].sessionToken, d.sessionToken, "ProposeCommand went out without x-session-token");
  const [sent] = d.commandOffers();
  assert.equal(sent.key, "morning");
  assert.equal(sent.reason, "reads you the news");
  assert.deepEqual(JSON.parse(sent.commandJson), {
    name: "Good morning",
    triggers: [{ type: "text", phrases: ["good morning"] }],
    actions: [],
  });
  // Offering is not a fire: made inside a leased call, it carries no lease.
  assert.equal(calls[0].causedBy, undefined);
});

test("a REFUSED offer crosses the wire with its code and PluginError whole", async () => {
  const d = await daemon();
  d.commandOfferResponse = {
    outcome: "PLUGIN_PROPOSE_COMMAND_OUTCOME_REFUSED",
    code: "rate_limited",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "too many command offers",
      retryAfterMs: 120000,
    },
  };
  const wire = await d.launch(offerer());
  const offered = await wire.plugin.ctx().proposeCommand("morning", { name: "x" }, "why");
  assert.deepEqual(offered, {
    outcome: "REFUSED",
    enabled: false,
    code: "rate_limited",
    error: {
      code: "PLUGIN_ERROR_RATE_LIMITED",
      message: "too many command offers",
      hint: "",
      configField: "",
      retryAfterMs: 120000,
      docUrl: "",
    },
  });
});

test("no offer limit is checked client-side: the daemon's refusal is what the plugin reads", async () => {
  const { PROPOSE_COMMAND_MAX_BYTES, PROPOSE_COMMAND_REASON_MAX_CHARS } = require("../dist/generated/limits.js");
  const d = await daemon();
  d.commandOfferResponse = { outcome: "PLUGIN_PROPOSE_COMMAND_OUTCOME_REFUSED", code: "too_large" };
  const wire = await d.launch(offerer());
  const key = "not a key / ".repeat(10);
  const command = JSON.stringify({ name: "x".repeat(PROPOSE_COMMAND_MAX_BYTES) });
  const reason = "é".repeat(PROPOSE_COMMAND_REASON_MAX_CHARS + 60);
  const offered = await wire.plugin.ctx().proposeCommand(key, command, reason);
  assert.deepEqual(offered, { outcome: "REFUSED", enabled: false, code: "too_large" });
  const [sent] = d.commandOffers();
  assert.equal(sent.key, key);
  assert.equal(sent.commandJson, command, "a string command goes as it is");
  assert.equal(sent.reason, reason);
});

test("every offer outcome maps to its short name; one this SDK does not know is UNSPECIFIED", () => {
  const { commandOfferResultFromWire } = require("../dist/host-client.js");
  const names = ["SAVED", "UNCHANGED", "DECLINED", "TIMED_OUT", "REFUSED"];
  names.forEach((name, i) => {
    const want = { outcome: name, enabled: false, code: "" };
    assert.deepEqual(commandOfferResultFromWire({ outcome: `PLUGIN_PROPOSE_COMMAND_OUTCOME_${name}` }), want);
    assert.deepEqual(commandOfferResultFromWire({ outcome: i + 1, error: null }), want);
  });
  assert.deepEqual(commandOfferResultFromWire({ outcome: 1, enabled: true }), {
    outcome: "SAVED",
    enabled: true,
    code: "",
  });
  assert.deepEqual(commandOfferResultFromWire({ outcome: 9 }), { outcome: "UNSPECIFIED", enabled: false, code: "" });
  assert.deepEqual(commandOfferResultFromWire({}), { outcome: "UNSPECIFIED", enabled: false, code: "" });
});

test("a command goes out as compact JSON or as the text it already is; a command JSON cannot hold throws", () => {
  const { commandJson, proposeCommandRequestToWire } = require("../dist/host-client.js");
  assert.equal(commandJson({ name: "Утро", actions: [], x: { a: [1, null] } }), '{"name":"Утро","actions":[],"x":{"a":[1,null]}}');
  // An undefined MEMBER is absent, as JSON.stringify writes it: nothing is mangled.
  assert.equal(commandJson({ name: "x", description: undefined }), '{"name":"x"}');
  const text = '{ "name": "x" ,  "triggers": [] }';
  assert.equal(commandJson(text), text);
  for (const bad of [{ n: Number.NaN }, { n: [Number.NEGATIVE_INFINITY] }, { l: [undefined] }, { l: [Symbol("s")] }, [], undefined, null, 1, true]) {
    assert.throws(() => commandJson(bad), TypeError);
  }
  assert.throws(() => commandJson({ n: 10n }), TypeError);
  assert.deepEqual(proposeCommandRequestToWire("k", { name: "x" }, "r"), {
    key: "k",
    commandJson: '{"name":"x"}',
    reason: "r",
  });
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
  assert.equal(res.configFields[0].advanced, true, "a tuning knob stays one on the wire");
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

test("AiGetModels hints survive real protobuf, and a 20 MiB picture request reaches the hook", async () => {
  // grpc-js receives 4 MiB by default. An `AiComplete` to a model whose hints
  // say `acceptsImages` carries up to 20 MiB of pictures, so a capability
  // server left at the default refuses the request its own hint asked for —
  // RESOURCE_EXHAUSTED, before any hook runs. Measured red with the option
  // removed from `run()`.
  let pictureBytes = -1;
  const provider = plugin({
    ai: {
      models: {
        models: [
          { id: "vision", name: "Vision", hints: { acceptsImages: true, contextWindow: 128000 } },
          { id: "text", name: "Text" },
        ],
        defaultModel: "text",
        providerHints: { toolLoading: "all" },
      },
      async *complete(req) {
        pictureBytes = req.messages.flatMap((m) => m.images ?? []).reduce((n, i) => n + i.data.length, 0);
        yield `${req.model} ${pictureBytes}`;
      },
    },
  });
  const d = await daemon();
  const wire = await d.launch(provider);

  const list = await wire.unary("AiGetModels");
  assert.equal(list.defaultModel, "text");
  assert.equal(list.models[0].hints.acceptsImages, true);
  assert.equal(list.models[0].hints.contextWindow, 128000);
  assert.equal(list.models[0].hints.toolLoading, "");
  assert.equal(list.models[1].hints, null, "absent on the wire = the provider's hints");
  assert.equal(list.providerHints.toolLoading, "all");

  const size = PLUGIN_IMAGE_REQUEST_MAX_BYTES;
  assert.ok(PLUGIN_MAX_MESSAGE_BYTES > size + 1024 * 1024, "the limit leaves room for the rest of the request");
  const chunks = await wire.serverStream("AiComplete", {
    model: "vision",
    messages: [
      {
        role: "user",
        content: "what is this?",
        images: [{ mimeType: "image/png", data: Buffer.alloc(size), filename: "big.png" }],
      },
    ],
  });
  assert.equal(pictureBytes, size);
  assert.equal(chunks[0].textDelta, `vision ${size}`);
});
