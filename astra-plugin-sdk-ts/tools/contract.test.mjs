/**
 * Contract tests for the generated descriptor and the startup assertion.
 *
 * Runs against the compiled `dist/` (see the `pretest` script), because that is
 * what a plugin actually loads. Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { astraProto, service } = require("../dist/proto-loader.js");
const { assertServiceContract, ProtoContractError } = require("../dist/service-contract.js");
const { SERVICE_METHODS } = require("../dist/generated/index.js");
const { Plugin } = require("../dist/plugin.js");

class TestPlugin extends Plugin {}

/** The handler map `run()` would hand to `addService`. */
function handlers() {
  return new TestPlugin().capabilityHandlers();
}

test("descriptor carries the post-event-sourcing ChatService", () => {
  // The retired inline proto described the pre-migration ChatService, so these
  // four were `undefined` on the stub and every call threw a bare TypeError.
  for (const method of [
    "SubmitUserMessage",
    "SubscribeEvents",
    "RespondToConfirmation",
    "ClearConversation",
  ]) {
    assert.equal(
      typeof service("ChatService").prototype[method],
      "function",
      `ChatService.${method} missing from the generated descriptor`
    );
  }
  assert.ok(!("SendMessage" in astraProto.ChatService.prototype));
});

test("every PluginCapabilityService method has a handler", () => {
  assertServiceContract(
    "PluginCapabilityService",
    service("PluginCapabilityService").service,
    handlers()
  );
});

test("the four previously unroutable methods are registered", () => {
  const map = handlers();
  for (const method of [
    "TtsGetConfigFields",
    "SttGetConfigFields",
    "OnLanguageChanged",
    "CallFromUi",
  ]) {
    assert.ok(SERVICE_METHODS.PluginCapabilityService.includes(method), `${method} not in descriptor`);
    assert.equal(typeof map[method], "function", `${method} has no handler`);
  }
});

test("a missing handler is a named, actionable error", () => {
  const map = handlers();
  delete map.CallFromUi;
  assert.throws(
    () => assertServiceContract("PluginCapabilityService", service("PluginCapabilityService").service, map),
    (err) => {
      assert.ok(err instanceof ProtoContractError);
      assert.equal(err.name, "ProtoContractError");
      assert.match(err.message, /no handler registered for: CallFromUi/);
      return true;
    }
  );
});

test("a handler for a nonexistent method is a named, actionable error", () => {
  const map = handlers();
  map.TtsGetConfigFieldz = map.TtsGetConfigFields;
  assert.throws(
    () => assertServiceContract("PluginCapabilityService", service("PluginCapabilityService").service, map),
    (err) => {
      assert.ok(err instanceof ProtoContractError);
      assert.match(err.message, /no such method in the descriptor: TtsGetConfigFieldz/);
      return true;
    }
  );
});

test("an unknown service name fails loudly", () => {
  assert.throws(() => service("NoSuchService"), ProtoContractError);
});

test("config field responses use the camelCase wire key", async () => {
  const plugin = new TestPlugin();
  plugin.ttsConfigFields = async () => [{ id: "voice", label: "Voice", fieldType: "text" }];
  const res = await plugin.handleTtsGetConfigFields({});
  assert.ok("configFields" in res, "expected configFields, not config_fields");
  assert.equal(res.configFields.length, 1);
});

test("CallFromUi reports a handler error in the response body", async () => {
  const plugin = new TestPlugin();
  plugin.handleUiCall = async () => {
    throw new Error("boom");
  };
  const res = await plugin.handleCallFromUi({ request: { method: "x", paramsJson: "{}" } });
  assert.equal(res.error, "boom");
  assert.equal(res.resultJson, "");
});

test("CallFromUi serializes a plain payload", async () => {
  const plugin = new TestPlugin();
  plugin.handleUiCall = async () => ({ ok: true });
  const res = await plugin.handleCallFromUi({ request: { method: "x", paramsJson: "{}" } });
  assert.equal(res.resultJson, '{"ok":true}');
  assert.equal(res.error, "");
});

test("Field.number sets the has_* presence flags", () => {
  const { Field } = require("../dist/types.js");
  const bounded = Field.number("n", "N", { min: 0, max: 10, step: 0.5 });
  assert.deepEqual(
    { hasMin: bounded.hasMin, hasMax: bounded.hasMax, hasStep: bounded.hasStep },
    { hasMin: true, hasMax: true, hasStep: true }
  );
  const unbounded = Field.number("n", "N");
  assert.deepEqual(
    { hasMin: unbounded.hasMin, hasMax: unbounded.hasMax, hasStep: unbounded.hasStep },
    { hasMin: false, hasMax: false, hasStep: false }
  );
});

// ── daemon → plugin authentication (src/capability-auth.ts) ──────────────────
//
// Exercised against a real grpc-js server because the deny path is shape
// sensitive: a rejection delivered the wrong way for a streaming method makes
// the call hang instead of failing, which no unit test on the wrapper catches.

const grpc = require("@grpc/grpc-js");
const { addServiceChecked } = require("../dist/service-contract.js");
const {
  guardHandlers,
  capabilityAuthMode,
  PLUGIN_TOKEN_HEADER,
} = require("../dist/capability-auth.js");

async function startGuarded(mode, token) {
  const server = new grpc.Server();
  addServiceChecked(
    server,
    "PluginCapabilityService",
    service("PluginCapabilityService").service,
    guardHandlers(new TestPlugin().capabilityHandlers(), token, mode)
  );
  const port = await new Promise((resolve, reject) =>
    server.bindAsync("127.0.0.1:0", grpc.ServerCredentials.createInsecure(), (err, p) =>
      err ? reject(err) : resolve(p)
    )
  );
  const Client = service("PluginCapabilityService");
  const client = new Client(`127.0.0.1:${port}`, grpc.credentials.createInsecure());
  return {
    client,
    close: () => {
      client.close();
      server.forceShutdown();
    },
  };
}

function metadata(token) {
  const md = new grpc.Metadata();
  if (token !== undefined) md.set(PLUGIN_TOKEN_HEADER, token);
  return md;
}

/** Unary `ListTools`, resolving to `{ ok }` or `{ code }`. */
function callUnary(client, token) {
  return new Promise((resolve) =>
    client.ListTools({}, metadata(token), (err, res) =>
      resolve(err ? { code: err.code, details: err.details } : { ok: res })
    )
  );
}

/** Bidi `SttProcess`, resolving the same way. Times out rather than hanging. */
function callBidi(client, token) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ code: "HUNG" }), 4000);
    const call = client.SttProcess(metadata(token));
    const done = (value) => {
      clearTimeout(timer);
      resolve(value);
    };
    call.on("data", () => {});
    call.on("error", (err) => done({ code: err.code, details: err.details }));
    call.on("end", () => done({ ok: true }));
    call.write({ data: Buffer.alloc(0), sampleRate: 16000, isLast: true });
    call.end();
  });
}

test("warn stage accepts a missing token and rejects a wrong one", async () => {
  const { client, close } = await startGuarded("warn", "s3cret");
  try {
    assert.ok((await callUnary(client, "s3cret")).ok, "right token must be accepted");
    assert.ok((await callUnary(client, undefined)).ok, "missing token is accepted in warn");
    assert.equal((await callUnary(client, "wrong")).code, grpc.status.UNAUTHENTICATED);
    // Streaming: the rejection must arrive as a status, not as silence.
    assert.equal((await callBidi(client, "wrong")).code, grpc.status.UNAUTHENTICATED);
  } finally {
    close();
  }
});

test("require stage rejects a call with no token, on both handler shapes", async () => {
  const { client, close } = await startGuarded("require", "s3cret");
  try {
    assert.equal((await callUnary(client, undefined)).code, grpc.status.UNAUTHENTICATED);
    assert.equal((await callBidi(client, undefined)).code, grpc.status.UNAUTHENTICATED);
    assert.ok((await callUnary(client, "s3cret")).ok);
  } finally {
    close();
  }
});

test("the guard is inert with no spawn token or mode=off", async () => {
  // A plugin run standalone has no shared secret with anyone, so it must still
  // serve rather than fail closed against a daemon that will never call it.
  const bare = await startGuarded("require", "");
  try {
    assert.ok((await callUnary(bare.client, undefined)).ok);
  } finally {
    bare.close();
  }
  const off = await startGuarded("off", "s3cret");
  try {
    assert.ok((await callUnary(off.client, "wrong")).ok);
  } finally {
    off.close();
  }
});

test("guardHandlers preserves the handler map's key set", () => {
  // `addServiceChecked` runs on the guarded map, so adding or dropping a key
  // here would turn the guard into the very drift the contract check exists to
  // catch.
  const raw = new TestPlugin().capabilityHandlers();
  assert.deepEqual(
    Object.keys(guardHandlers(raw, "s3cret", "require")).sort(),
    Object.keys(raw).sort()
  );
  assert.equal(guardHandlers(raw, "", "require"), raw, "no token: same object, no wrapping");
});

test("ASTRA_PLUGIN_CAPABILITY_AUTH spellings", () => {
  const mode = (value) => capabilityAuthMode("warn", { ASTRA_PLUGIN_CAPABILITY_AUTH: value });
  assert.equal(capabilityAuthMode("warn", {}), "warn");
  assert.equal(mode("require"), "require");
  assert.equal(mode(" OFF "), "off");
  // A typo must not silently weaken the check.
  assert.equal(mode("yes"), "warn");
});
