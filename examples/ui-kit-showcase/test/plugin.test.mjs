/**
 * Tests for Ui Kit Showcase.
 *
 * `pretest` bundles `src/index.ts` with the SDK left EXTERNAL, so the plugin
 * under test and the harness testing it share one copy of the SDK.
 *
 * Run: `npm test`.
 *
 * This is level 1: in process, no daemon, no socket, fast enough to run on
 * every save. When you want the other level — a real gRPC handshake, a real
 * session token, real protobuf encoding — reach for `MockDaemon` from the same
 * module and see `examples/json-tools/test/plugin.test.mjs`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { app } = require("../dist/plugin.cjs");
const { Harness } = require("astra-plugin-sdk/testing");

test("the plugin starts, and answers a health check", async () => {
  const h = await Harness.create(app).start();
  assert.equal((await h.healthCheck()).healthy, true);
});

test("no config the daemon can deliver crashes this plugin", async () => {
  // The daemon delivers config it did not author: the user's typing, and an
  // older version of this plugin's own schema. None of it may throw.
  const h = await Harness.create(app).start();
  assert.deepEqual(await h.fuzzConfig(), []);
});
