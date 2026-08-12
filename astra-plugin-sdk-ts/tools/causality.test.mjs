/**
 * **A trigger fired while handling a daemon call names the call that caused it.**
 *
 * The bug: a plugin action runs inside a command run a user started by typing
 * in a chat. The plugin fires a trigger, which starts a *second* command run —
 * and that run has no idea what caused it, so its output is filed into a
 * freshly auto-created conversation the user never sees. Two chats driving one
 * plugin at once are indistinguishable on the wire.
 *
 * The daemon carries a per-invocation lease as `x-astra-cause` call metadata;
 * the SDK echoes it on `FireTrigger`. In TypeScript the read lives in
 * `HostClient.fireTrigger` — the transport all three fire paths converge on —
 * with an `AsyncLocalStorage` store entered around every handler.
 *
 * These run at level 2: a real plugin, a real gRPC handshake, real metadata.
 * `MockDaemon.firedTriggers()` reports `causedBy` as it arrived on the socket,
 * so what is asserted here is what the daemon would actually see, not what the
 * SDK intended to send. Every link is invisible when it breaks: a lease that
 * never reaches the wire produces a working plugin whose output goes to the
 * wrong place, with no error anywhere.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { plugin, tool, s, Plugin } = require("../dist/index.js");
const { MockDaemon } = require("../dist/testing/index.js");

const started = [];
async function daemon(opts) {
  const d = await MockDaemon.start(opts);
  started.push(d);
  return d;
}
after(async () => {
  for (const d of started) await d.stop();
});

/** Waits for a detached fire to land, since the tool returns before it does. */
async function settle(d, n) {
  for (let i = 0; i < 200; i++) {
    if (d.firedTriggers().length >= n) return;
    await new Promise((r) => setTimeout(r, 10));
  }
  assert.fail(`expected ${n} fired trigger(s), saw ${d.firedTriggers().length}`);
}

/** Fires through the context handed to the tool — the documented path. */
function roller() {
  return plugin({
    tools: {
      roll_dice: tool({
        description: "Roll dice.",
        input: s.object({}),
        run: async (_args, ctx) => {
          await ctx.fireTrigger("on_roll_value", { value: "2" });
          return "1d5: [2] = 2";
        },
      }),
    },
    triggers: { on_roll_value: { label: "Rolled" } },
  });
}

test("a lease on a call comes back on the trigger it caused", async () => {
  const d = await daemon();
  const wire = await d.launch(roller());

  await wire.callTool("roll_dice", {}, { causedBy: "lease-abc" });
  await settle(d, 1);

  assert.deepEqual(d.firedTriggers(), [
    { triggerType: "on_roll_value", payloadJson: '{"value":"2"}', causedBy: "lease-abc" },
  ]);
});

test("a plugin that was never leased fires a root event", async () => {
  // The state every daemon in the field is in, and the one this must never
  // make worse. An empty header would be worse than none: the daemon has to
  // tell "sent no lease" from "sent a lease I cannot resolve", and only the
  // second is a bug.
  const d = await daemon();
  const wire = await d.launch(roller());

  await wire.callTool("roll_dice");
  await settle(d, 1);

  assert.equal(d.firedTriggers()[0].causedBy, undefined);
});

test("the cause survives an await inside the handler", async () => {
  // AsyncLocalStorage is chosen over a plain variable precisely because a
  // handler is allowed to suspend. A plain variable would be correct until two
  // calls overlapped, which is the scenario this whole design is about.
  const d = await daemon();
  const wire = await d.launch(
    plugin({
      tools: {
        slow: tool({
          description: "Fire after yielding.",
          input: s.object({}),
          run: async (_args, ctx) => {
            await new Promise((r) => setTimeout(r, 20));
            await ctx.fireTrigger("late", {});
            return "ok";
          },
        }),
      },
      triggers: { late: { label: "Late" } },
    })
  );

  await wire.callTool("slow", {}, { causedBy: "lease-slow" });
  await settle(d, 1);

  assert.equal(d.firedTriggers()[0].causedBy, "lease-slow");
});

test("concurrent calls do not collect each other's cause", async () => {
  const d = await daemon();
  const wire = await d.launch(
    plugin({
      tools: {
        slow: tool({
          description: "Sleep, then fire.",
          input: s.object({ ms: s.number(), name: s.string() }),
          run: async ({ ms, name }, ctx) => {
            await new Promise((r) => setTimeout(r, ms));
            await ctx.fireTrigger("done", { name });
            return name;
          },
        }),
      },
      triggers: { done: { label: "Done" } },
    })
  );

  // Deliberately interleaved: A starts first and finishes last, so a design
  // that kept one ambient slot would hand A's fire B's lease.
  await Promise.all([
    wire.callTool("slow", { ms: 40, name: "a" }, { causedBy: "chat-a" }),
    wire.callTool("slow", { ms: 5, name: "b" }, { causedBy: "chat-b" }),
  ]);
  await settle(d, 2);

  const byName = Object.fromEntries(
    d.firedTriggers().map((t) => [JSON.parse(t.payloadJson).name, t.causedBy])
  );
  assert.deepEqual(byName, { a: "chat-a", b: "chat-b" });
});

test("the cause reaches a fire made through the plugin object itself", async () => {
  // GAP 14, and the reason the read is in the transport rather than in the
  // context wrapper. `this.fireTrigger(..)` on the Plugin routes to the
  // process-global host, bypassing the per-call context entirely — and it is
  // the most idiomatic thing a subclass author writes.
  class Direct extends Plugin {
    async listTools() {
      return [{ name: "go", description: "Fire via the plugin object.", parametersJson: "{}" }];
    }
    async callTool() {
      await this.fireTrigger("on_roll_value", JSON.stringify({ via: "plugin" }));
      return "ok";
    }
  }

  const d = await daemon();
  const wire = await d.launch(new Direct());

  await wire.callTool("go", {}, { causedBy: "lease-direct" });
  await settle(d, 1);

  assert.equal(
    d.firedTriggers()[0].causedBy,
    "lease-direct",
    "a fire through Plugin.fireTrigger lost its cause — the read is in the wrong layer"
  );
});
