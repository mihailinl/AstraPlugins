/**
 * **A tool can ask for the pictures the person attached, and read them.**
 *
 * Two halves, each tested at both levels: a tool's `wantsAttachments` must
 * reach `ListTools` (absent or false on every other tool, so nothing changes
 * for a plugin that never heard of it), and the pictures on
 * `PluginCallToolRequest.attachments` must reach `ctx.attachments` with their
 * bytes, type and name intact.
 *
 * Level 2 matters for the second half the way it does for the invocation: the
 * field is read off a protobuf-decoded request, and `bytes` arriving as
 * something other than a `Buffer`, or a camelCase key read in snake_case,
 * produces a tool that silently never sees a picture.
 *
 * Run: `bun run test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { Plugin, plugin, tool, s, currentAttachments } = require("../dist/index.js");
const { Harness, MockDaemon } = require("../dist/testing/index.js");

const started = [];
async function daemon(opts) {
  const d = await MockDaemon.start(opts);
  started.push(d);
  return d;
}
after(async () => {
  for (const d of started) await d.stop();
});

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 1, 2, 255]);
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 7, 7, 7]);

/** Two tools: one asks for pictures and reports them, one never heard of them. */
function photos() {
  return plugin({
    tools: {
      describe: tool({
        description: "Describe the pictures the person attached.",
        input: s.object({}),
        wantsAttachments: true,
        run: (_args, ctx) =>
          JSON.stringify({
            viaCtx: ctx.attachments.map((a) => ({
              mimeType: a.mimeType,
              filename: a.filename,
              isBuffer: Buffer.isBuffer(a.data),
              bytes: [...a.data],
            })),
            ambientCount: currentAttachments().length,
          }),
      }),
      plain: tool({
        description: "Echo a string back.",
        input: s.object({ text: s.string() }),
        run: ({ text }, ctx) => `${text}:${ctx.attachments.length}`,
      }),
    },
  });
}

const sent = [
  { mimeType: "image/png", data: PNG, filename: "cat.png" },
  { mimeType: "image/jpeg", data: JPEG, filename: "dog.jpg" },
];

function expected() {
  return {
    viaCtx: [
      { mimeType: "image/png", filename: "cat.png", isBuffer: true, bytes: [...PNG] },
      { mimeType: "image/jpeg", filename: "dog.jpg", isBuffer: true, bytes: [...JPEG] },
    ],
    ambientCount: 2,
  };
}

// ── level 1 ──────────────────────────────────────────────────────────────────

test("wantsAttachments reaches ListTools, and is false on a tool that did not ask", async () => {
  const h = await Harness.create(photos()).start();
  const tools = await h.listTools();
  const byName = Object.fromEntries(tools.map((t) => [t.name, t.wantsAttachments]));
  assert.deepEqual(byName, { describe: true, plain: false });
});

test("attachments reach ctx.attachments with bytes, type and name intact", async () => {
  const h = await Harness.create(photos()).start();
  const r = await h.callTool("describe", {}, { conversationId: "conv-1", attachments: sent });
  assert.equal(r.success, true, r.error);
  assert.deepEqual(JSON.parse(r.result), expected());
});

test("a call that carries none hands the handler an empty list, never undefined", async () => {
  const h = await Harness.create(photos()).start();
  const r = await h.callTool("describe", {});
  assert.deepEqual(JSON.parse(r.result), { viaCtx: [], ambientCount: 0 });
});

test("a tool without the flag still works", async () => {
  const h = await Harness.create(photos()).start();
  const r = await h.callTool("plain", { text: "hi" });
  assert.deepEqual({ success: r.success, result: r.result }, { success: true, result: "hi:0" });
});

test("the class form declares the flag on its ToolDef and reads ctx().attachments", async () => {
  class Photos extends Plugin {
    async listTools() {
      return [
        { name: "count", description: "Count the pictures.", parametersJson: "{}", wantsAttachments: true },
        { name: "old", description: "Written before the flag.", parametersJson: "{}" },
      ];
    }
    async callTool(_name) {
      return { success: true, result: String(this.ctx().attachments.length) };
    }
  }
  const h = await Harness.create(new Photos()).start();
  const flags = (await h.listTools()).map((t) => [t.name, t.wantsAttachments]);
  assert.deepEqual(flags, [
    ["count", true],
    ["old", false],
  ]);
  const r = await h.callTool("count", {}, { conversationId: "conv-1", attachments: sent });
  assert.equal(r.result, "2");
});

// ── level 2 ──────────────────────────────────────────────────────────────────

test("over the wire: the flag is in ListTools", async () => {
  const d = await daemon();
  const wire = await d.launch(photos());
  const tools = await wire.listTools();
  const byName = Object.fromEntries(tools.map((t) => [t.name, t.wantsAttachments]));
  assert.deepEqual(byName, { describe: true, plain: false });
});

test("over the wire: the pictures reach the handler as Buffers, intact", async () => {
  const d = await daemon();
  const wire = await d.launch(photos());
  const r = await wire.callTool("describe", {}, { conversationId: "conv-7", attachments: sent });
  assert.equal(r.success, true, r.error);
  assert.deepEqual(JSON.parse(r.result), expected());
});

test("over the wire: concurrent calls do not read each other's pictures", async () => {
  // The reason this is a per-call store and not a field on the one context
  // every hook shares.
  const slow = plugin({
    tools: {
      first: tool({
        description: "Yields, then names its first picture.",
        input: s.object({}),
        wantsAttachments: true,
        run: async (_args, ctx) => {
          await new Promise((r) => setTimeout(r, 20));
          return ctx.attachments[0]?.filename ?? "none";
        },
      }),
    },
  });
  const d = await daemon();
  const wire = await d.launch(slow);
  const [a, b, c] = await Promise.all([
    wire.callTool("first", {}, { conversationId: "conv-A", attachments: [sent[0]] }),
    wire.callTool("first", {}, { conversationId: "conv-B", attachments: [sent[1]] }),
    wire.callTool("first", {}, { conversationId: "conv-C" }),
  ]);
  assert.equal(a.result, "cat.png");
  assert.equal(b.result, "dog.jpg");
  assert.equal(c.result, "none");
});

test("over the wire: a tool without the flag still works", async () => {
  const d = await daemon();
  const wire = await d.launch(photos());
  const r = await wire.callTool("plain", { text: "yo" });
  assert.deepEqual({ success: r.success, result: r.result }, { success: true, result: "yo:0" });
});
