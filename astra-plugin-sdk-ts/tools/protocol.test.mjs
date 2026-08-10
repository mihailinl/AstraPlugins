/**
 * Tests for the protocol handshake (`src/protocol.ts`).
 *
 * Runs against the compiled `dist/` (see the `pretest` script), because that is
 * what a plugin actually loads. Run: `npm test`.
 *
 * The verdict is a pure function of the `Register` response, so these need no
 * daemon and no socket — which is the point of having split it out. What they
 * guard is that a plugin built against an Astra it cannot talk to says one
 * sentence and stops, instead of registering and then dying at the first RPC one
 * side does not have.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const {
  evaluateProtocol,
  EXIT_PROTOCOL_INCOMPATIBLE,
  MIN_SUPPORTED_DAEMON_PROTOCOL,
  PROTOCOL_VERSION,
  SDK_NAME,
  SDK_VERSION,
} = require("../dist/protocol.js");
const pkg = require("../package.json");

/** A daemon's `Register` answer, with the handshake fields filled in. */
function response(protocolVersion, minSupportedProtocol) {
  return {
    success: true,
    error: "",
    configJson: "{}",
    daemonVersion: "test",
    clientSessionToken: "tok",
    language: "en",
    protocolVersion,
    minSupportedProtocol,
  };
}

test("a daemon whose floor is two stops an SDK at one", () => {
  // THE acceptance case for 1.3.
  assert.equal(PROTOCOL_VERSION, 1, "this test is written for protocol 1");

  const resp = response(2, 2);
  resp.success = false;
  resp.error = "too old";
  resp.errorDetail = {
    code: "PLUGIN_ERROR_PROTOCOL_TOO_OLD",
    message:
      "Plugin 'dice-roller' speaks protocol 1; this daemon speaks 2 and accepts 2 or newer.",
    hint:
      "Rebuild the plugin against an Astra plugin SDK whose PROTOCOL_VERSION is at least 2, " +
      "then reinstall it.",
  };

  const sentence = evaluateProtocol(resp);
  assert.ok(sentence, "floor 2 must refuse an SDK at 1");
  assert.match(sentence, /2/);
  assert.match(
    sentence,
    /PROTOCOL_VERSION/,
    "the fix has to be in the sentence, not just the cause"
  );
  assert.equal(EXIT_PROTOCOL_INCOMPATIBLE, 78, "EX_CONFIG, so a retry loop is not implied");
});

test("the numeric enum form is recognised too", () => {
  // `proto-loader` runs with `enums: String` today. If that ever changes, this
  // check must not silently become a no-op that waves every old plugin through.
  const resp = response(2, 2);
  resp.success = false;
  resp.errorDetail = { code: 1, message: "too old", hint: "rebuild" };
  assert.ok(evaluateProtocol(resp));
});

/** A daemon from before the handshake: neither handshake field on the wire. */
function preHandshakeResponse() {
  return {
    success: true,
    error: "",
    configJson: "{}",
    daemonVersion: "old",
    clientSessionToken: "tok",
    language: "en",
  };
}

test("a daemon that reports no protocol is served", () => {
  // Astra v0.1.0, the released build: identical PluginHostService, every field
  // this SDK sends already present, a session token issued to every plugin. The
  // one thing it cannot do is name its own generation, and refusing it would
  // have made every plugin built with this SDK dead on the only Astra there is.
  assert.equal(
    MIN_SUPPORTED_DAEMON_PROTOCOL,
    0,
    "protocol 1 IS the pre-handshake surface; a floor of 1 refuses Astra v0.1.0"
  );
  assert.equal(evaluateProtocol(preHandshakeResponse()), null);
});

test("a floor of two refuses a daemon that reports no protocol", () => {
  // The refusal branch stays live, for the release that needs it.
  const sentence = evaluateProtocol(preHandshakeResponse(), 2);
  assert.ok(sentence, "an absent protocolVersion is below a floor of 2");
  assert.match(sentence, /did not report/);
  assert.match(sentence, /2/);
  assert.match(sentence, /update Astra/);

  // A daemon that DOES report, but below the floor, is named by number.
  const named = evaluateProtocol(response(1, 1), 2);
  assert.ok(named);
  assert.match(named, /speaks protocol 1/);
});

test("a newer daemon is served", () => {
  // `UNIMPLEMENTED` means "absent", so a daemon ahead of this SDK is not a
  // problem — it simply never calls the hooks this plugin does not have.
  assert.equal(evaluateProtocol(response(PROTOCOL_VERSION + 5, MIN_SUPPORTED_DAEMON_PROTOCOL)), null);
  assert.equal(evaluateProtocol(response(PROTOCOL_VERSION, MIN_SUPPORTED_DAEMON_PROTOCOL)), null);
});

test("a non-protocol refusal is not a protocol mismatch", () => {
  // Exiting 78 ("this machine is misconfigured") over a bad auth token would
  // send the author to fix the wrong thing.
  const resp = response(PROTOCOL_VERSION, MIN_SUPPORTED_DAEMON_PROTOCOL);
  resp.success = false;
  resp.error = "Invalid auth token";
  resp.errorDetail = { code: "PLUGIN_ERROR_AUTH", message: "Invalid auth token", hint: "" };
  assert.equal(evaluateProtocol(resp), null);
});

test("the reported SDK version tracks package.json", () => {
  assert.equal(SDK_NAME, "astra-plugin-sdk-ts");
  assert.equal(
    SDK_VERSION,
    pkg.version,
    "SDK_VERSION is a literal; it has to be bumped with package.json or the daemon's " +
      "support triage names the wrong release"
  );
});
