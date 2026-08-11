/**
 * §5.10: `console` reaches the daemon, and a crash leaves a record.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const {
  EXIT_UNCAUGHT,
  LogBridge,
  installConsoleBridge,
  installFatalHandlers,
  removeFatalHandlers,
  restoreConsole,
} = require("../dist/logging.js");
const { RecordingHost } = require("../dist/testing/index.js");

/** Wait for the bridge's pump, which runs on a macrotask. */
const settle = () => new Promise((r) => setTimeout(r, 10));

test("console.* reaches PluginLog at the right level, and still prints", async () => {
  const host = new RecordingHost();
  const printed = [];
  const fake = {
    log: (...a) => printed.push(["log", a]),
    info: (...a) => printed.push(["info", a]),
    debug: (...a) => printed.push(["debug", a]),
    warn: (...a) => printed.push(["warn", a]),
    error: (...a) => printed.push(["error", a]),
  };
  installConsoleBridge(() => host, { console: fake });
  try {
    fake.log("hello", 1, { a: 2 });
    fake.warn("careful");
    fake.error(new Error("boom"));
    fake.debug("noisy");
    await settle();
  } finally {
    restoreConsole(fake);
  }

  assert.deepEqual(
    host.logs().map((l) => l.level),
    ["info", "warn", "error", "debug"]
  );
  assert.equal(host.logs()[0].message, 'hello 1 {"a":2}');
  assert.match(host.logs()[2].message, /boom/);
  // The original console is still the local dev loop's output AND the daemon's
  // readiness signal; forwarding must not replace it.
  assert.equal(printed.length, 4);
});

test("a host that logs cannot make the bridge spin", async () => {
  // grpc-js logs. A grpc log forwarded over a grpc call that logs again is a
  // busy loop that ends as a hung plugin, so the guard is not optional.
  let forwards = 0;
  const fake = { log() {}, info() {}, debug() {}, warn() {}, error() {} };
  const host = {
    async log() {
      forwards++;
      fake.log("the transport says something");
    },
  };
  installConsoleBridge(() => host, { console: fake });
  try {
    fake.log("one line");
    await settle();
  } finally {
    restoreConsole(fake);
  }
  assert.equal(forwards, 1, "the line the forward itself produced must be dropped");
});

test("the queue is bounded, and a drop is reported rather than silent", async () => {
  const host = new RecordingHost();
  let live = null;
  const bridge = new LogBridge(() => live, 4);
  for (let i = 0; i < 10; i++) bridge.emit("info", `line ${i}`);
  assert.equal(bridge.pending(), 4, "an unbounded buffer in front of a stalled daemon is an OOM");
  assert.equal(bridge.droppedCount(), 6);

  live = host;
  await bridge.flush(500);
  const messages = host.logs().map((l) => l.message);
  assert.equal(messages.length, 4);
  assert.match(messages[0], /^line 6/, "the OLDEST lines are the ones dropped");
  assert.match(messages[0], /6 earlier log line\(s\) dropped/);
});

test("lines emitted before the daemon exists are kept, not lost", async () => {
  const host = new RecordingHost();
  let live = null;
  const bridge = new LogBridge(() => live, 16);
  bridge.emit("error", "failed to read config");
  await settle();
  assert.equal(host.logs().length, 0);
  live = host;
  bridge.emit("info", "registered");
  await settle();
  assert.deepEqual(
    host.logs().map((l) => l.message),
    ["failed to read config", "registered"]
  );
});

test("an uncaught exception is logged at error level and exits non-zero", async () => {
  const host = new RecordingHost();
  const exits = [];
  const handlers = installFatalHandlers(() => host, { exit: (code) => exits.push(code) });
  try {
    assert.ok(
      process.listeners("uncaughtException").includes(handlers.uncaughtException),
      "the handler must really be registered on the process, not just returned"
    );
    handlers.uncaughtException(new Error("kaboom"));
    await settle();
  } finally {
    removeFatalHandlers();
  }
  assert.ok(
    !process.listeners("uncaughtException").includes(handlers.uncaughtException),
    "removeFatalHandlers must unregister, or the next suite inherits this plugin's crash handler"
  );
  assert.deepEqual(exits, [EXIT_UNCAUGHT]);
  assert.notEqual(EXIT_UNCAUGHT, 0, "a crash must not look like an orderly stop");
  assert.equal(host.logs()[0].level, "error");
  assert.match(host.logs()[0].message, /FATAL uncaughtException: Error: kaboom/);
});

test("an unhandled rejection is treated exactly the same", async () => {
  const host = new RecordingHost();
  const exits = [];
  const handlers = installFatalHandlers(() => host, { exit: (code) => exits.push(code) });
  try {
    handlers.unhandledRejection("a string nobody caught");
    await settle();
  } finally {
    removeFatalHandlers();
  }
  assert.deepEqual(exits, [EXIT_UNCAUGHT]);
  assert.match(host.logs()[0].message, /FATAL unhandledRejection: a string nobody caught/);
});

test("a crash with no daemon still exits non-zero", async () => {
  const exits = [];
  const handlers = installFatalHandlers(() => null, { exit: (code) => exits.push(code) });
  try {
    handlers.uncaughtException(new Error("early"));
    await settle();
  } finally {
    removeFatalHandlers();
  }
  assert.deepEqual(exits, [EXIT_UNCAUGHT]);
});
