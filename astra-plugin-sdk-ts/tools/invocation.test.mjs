/**
 * **A tool call is told which conversation made it.**
 *
 * The id arrives in the request BODY, not in metadata, and that is why this
 * file sits beside `causality.test.mjs` rather than inside it. The lease says
 * *what run* is calling; the invocation says *which conversation* that run
 * belongs to. A call may carry either, both or neither, and neither may stand
 * in for the other — a run with a conversation and no lease is a real case
 * upstream, not a contradiction.
 *
 * Level 2 throughout: a real plugin behind a real gRPC handshake, so what is
 * asserted is what a daemon would actually deliver. A body field read with the
 * wrong casing, or read before `keepCase` has been applied, produces a plugin
 * that silently never knows where it was called from — no error anywhere, and
 * every existing test still green.
 *
 * Run: `npm test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { plugin, tool, s, currentInvocation } = require("../dist/index.js");
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

/** Reports what the handler saw, through both surfaces. */
function reporter() {
  return plugin({
    tools: {
      look: tool({
        description: "Reports where it was called from.",
        input: s.object({}),
        run: async (_args, ctx) =>
          JSON.stringify({
            viaCtx: ctx.invocation?.conversationId ?? null,
            viaAmbient: currentInvocation()?.conversationId ?? null,
          }),
      }),
    },
  });
}

test("a conversation in the request body reaches the handler", async () => {
  const d = await daemon();
  const wire = await d.launch(reporter());

  const r = await wire.callTool("look", {}, { conversationId: "conv-7" });

  assert.deepEqual(JSON.parse(r.result), { viaCtx: "conv-7", viaAmbient: "conv-7" });
});

test("no invocation at all means no conversation", async () => {
  const d = await daemon();
  const wire = await d.launch(reporter());

  const r = await wire.callTool("look");

  assert.deepEqual(JSON.parse(r.result), { viaCtx: null, viaAmbient: null });
});

test("an invocation naming nothing is the same answer as no invocation", async () => {
  // `""` is how a daemon spells "not from a conversation" in a message it still
  // sends. Handing a plugin `""` would give it an id that can never resolve.
  // And `keepCase: false` delivers an ABSENT sub-message as `null`, not
  // `undefined`, so a plain `?.` chain would leak a null through a type that
  // promises `undefined`.
  const d = await daemon();
  const wire = await d.launch(reporter());

  const r = await wire.callTool("look", {}, { conversationId: null });

  assert.deepEqual(JSON.parse(r.result), { viaCtx: null, viaAmbient: null });
});

test("a lease and an invocation on one call are read back independently", async () => {
  // The two are read at different moments from different halves of the same
  // RPC. A test carrying only one of them would not notice the second read
  // being dropped, or overwriting the first.
  const d = await daemon();
  const wire = await d.launch(reporter());

  const r = await wire.callTool("look", {}, { causedBy: "lease-xyz", conversationId: "conv-9" });

  assert.deepEqual(JSON.parse(r.result), { viaCtx: "conv-9", viaAmbient: "conv-9" });
});

test("concurrent calls from two chats do not read each other's conversation", async () => {
  // Why this is an AsyncLocalStorage store rather than a field on the context:
  // one PluginContext is built per plugin and handed to every hook, so a field
  // would be the same value for both of these.
  const slow = plugin({
    tools: {
      look: tool({
        description: "Yields, then reports.",
        input: s.object({}),
        run: async () => {
          await new Promise((r) => setTimeout(r, 20));
          return currentInvocation()?.conversationId ?? "none";
        },
      }),
    },
  });

  const d = await daemon();
  const wire = await d.launch(slow);

  const [a, b] = await Promise.all([
    wire.callTool("look", {}, { conversationId: "conv-A" }),
    wire.callTool("look", {}, { conversationId: "conv-B" }),
  ]);

  assert.equal(a.result, "conv-A");
  assert.equal(b.result, "conv-B");
});
