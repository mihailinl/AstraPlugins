/**
 * The `image_provider` hooks, through the SDK's real dispatch and a socket.
 *
 * What is under test is the wire projection Astra reads (from `21790d761`): a
 * refusal the plugin MEANT is a successful call with `errorCode` set — the
 * daemon tries the person's own provider on `quota`, `rate_limited`,
 * `not_configured` and `unavailable`, stops on `refused`, and gives up on a
 * plugin that throws — the answer carries exactly one picture, and
 * `ImageGetModels` is optional: an absent one answers UNIMPLEMENTED, the
 * daemon's word for "no list".
 *
 * Run: `bun run test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);

const { Plugin, plugin, ImageGeneration } = require("../dist/index.js");
const { Harness, MockDaemon } = require("../dist/testing/index.js");

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 1, 2, 255]);
const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 7, 7, 7]);
const WEBP = Buffer.concat([Buffer.from("RIFF"), Buffer.from([16, 0, 0, 0]), Buffer.from("WEBPVP8 ")]);
const UNIMPLEMENTED = 12;

const cat = () => ({ mimeType: "image/jpeg", data: JPEG, filename: "cat.jpg" });

/** Draws a PNG, refuses by keyword, and reports what it was asked in the caption. */
function painter(seen = []) {
  return plugin({
    image: {
      generate(req) {
        seen.push(req);
        switch (req.prompt) {
          case "spent":
            return ImageGeneration.refuse("quota", "monthly allowance used");
          case "slow":
            return ImageGeneration.refuse("rate_limited", "slow down", 7);
          case "nope":
            return ImageGeneration.refuse("refused", "the prompt was declined");
          case "keyless":
            return ImageGeneration.refuse("not_configured", "no API key set");
          case "down":
            return ImageGeneration.refuse("unavailable", "the service is down");
          case "bytes":
            return JPEG;
          case "nothing":
            return undefined;
          case "broken":
            throw new Error("the API answered garbage");
          default: {
            const inputs = req.inputImages.map((i) => `${i.mimeType}:${i.filename}:${i.data.length}`).join(",");
            return ImageGeneration.drawn(PNG, {
              caption: `ratio=${req.aspectRatio || "-"} model=${req.model} inputs=${inputs}`,
            });
          }
        }
      },
      models: {
        models: [
          { id: "draw-1", name: "Draw 1" },
          { id: "edit-1", name: "Edit 1", acceptsInputImages: true },
        ],
        defaultModel: "edit-1",
      },
    },
  });
}

/** Draws, and lists nothing: `models` is optional. */
const noList = () => plugin({ image: { generate: () => ImageGeneration.drawn(WEBP) } });

test("a picture's type is read from its bytes", () => {
  assert.equal(ImageGeneration.mimeTypeOf(PNG), "image/png");
  assert.equal(ImageGeneration.mimeTypeOf(JPEG), "image/jpeg");
  assert.equal(ImageGeneration.mimeTypeOf(WEBP), "image/webp");
  assert.equal(ImageGeneration.mimeTypeOf(Buffer.from("GIF89a")), "", "the daemon refuses a GIF");
  assert.equal(ImageGeneration.drawn(PNG).mimeType, "image/png");
  assert.equal(ImageGeneration.drawn(Buffer.from("???"), { mimeType: "image/png" }).mimeType, "image/png");
});

test("ImageGeneration.refuse refuses a code the daemon does not read", () => {
  assert.throws(() => ImageGeneration.refuse("out_of_ink", "nope"), TypeError);
  assert.deepEqual(ImageGeneration.ERROR_CODES, [
    "quota",
    "rate_limited",
    "not_configured",
    "unavailable",
    "refused",
  ]);
  assert.ok(ImageGeneration.ASPECT_RATIOS.includes("3:4"));
});

test("the request reaches the hook typed and one picture comes back", async () => {
  const seen = [];
  const h = await Harness.create(painter(seen)).start();
  const res = await h.imageGenerate("a fox", { aspectRatio: " 4:3 ", model: "edit-1", inputImages: [cat()] });
  assert.equal(res.errorCode, undefined);
  assert.deepEqual(Buffer.from(res.data), PNG);
  assert.equal(res.mimeType, "image/png");
  assert.equal(res.caption, "ratio=4:3 model=edit-1 inputs=image/jpeg:cat.jpg:7");
  assert.equal(seen[0].aspectRatio, "4:3", "trimmed");
  assert.equal(seen[0].inputImages.length, 1);
});

test("every refusal the plugin meant is an answer, not a status", async () => {
  const h = await Harness.create(painter()).start();
  for (const [prompt, code, message, retry] of [
    ["spent", "quota", "monthly allowance used", 0],
    ["slow", "rate_limited", "slow down", 7],
    ["nope", "refused", "the prompt was declined", 0],
    ["keyless", "not_configured", "no API key set", 0],
    ["down", "unavailable", "the service is down", 0],
  ]) {
    assert.equal(await h.unaryStatus("ImageGenerate", { prompt }), null, `${prompt} must not fail the call`);
    assert.deepEqual(await h.imageGenerate(prompt), {
      errorCode: code,
      errorMessage: message,
      retryAfterSecs: retry,
    });
  }
});

test("bare bytes are a picture; nothing at all, or a throw, is a status", async () => {
  const h = await Harness.create(painter()).start();
  const res = await h.imageGenerate("bytes");
  assert.equal(res.mimeType, "image/jpeg");
  for (const prompt of ["nothing", "broken"]) {
    const status = await h.unaryStatus("ImageGenerate", { prompt });
    assert.ok(status, `${prompt} must fail the call`);
    assert.notEqual(status.code, UNIMPLEMENTED, `${prompt} is a broken plugin, not an absent hook`);
  }
});

test("the model list says which model edits; an absent one is UNIMPLEMENTED", async () => {
  const h = await Harness.create(painter()).start();
  assert.deepEqual(await h.imageGetModels(), {
    models: [
      { id: "draw-1", name: "Draw 1", acceptsInputImages: false },
      { id: "edit-1", name: "Edit 1", acceptsInputImages: true },
    ],
    defaultModel: "edit-1",
  });

  const bare = await Harness.create(noList()).start();
  assert.equal((await bare.unaryStatus("ImageGetModels", {})).code, UNIMPLEMENTED);
  assert.equal((await bare.imageGenerate("x")).mimeType, "image/webp", "and it still draws");

  const none = await Harness.create(plugin({ tools: {} })).start();
  assert.equal((await none.unaryStatus("ImageGenerate", { prompt: "x" })).code, UNIMPLEMENTED);
});

test("defining image is what registers the capability", async () => {
  assert.deepEqual(await noList().instance.discoverCapabilities(), ["image_provider"]);

  class Classic extends Plugin {
    async imageGenerate() {
      return PNG;
    }
  }
  assert.ok((await new Classic().discoverCapabilities()).includes("image_provider"));
  assert.ok(!(await new Plugin().discoverCapabilities()).includes("image_provider"));
});

// ── over a socket ────────────────────────────────────────────────────────────

const started = [];
after(async () => {
  for (const d of started) await d.stop();
});

test("over the wire: one picture with its bytes, refusals in band, the model list", async () => {
  const d = await MockDaemon.start();
  started.push(d);
  const wire = await d.launch(painter());

  const drawn = await wire.unary("ImageGenerate", {
    prompt: "a fox",
    aspectRatio: "16:9",
    inputImages: [cat()],
  });
  assert.equal(drawn.images.length, 1);
  assert.deepEqual(Buffer.from(drawn.images[0].data), PNG);
  assert.equal(drawn.images[0].mimeType, "image/png");
  assert.equal(drawn.caption, "ratio=16:9 model= inputs=image/jpeg:cat.jpg:7");

  const refused = await wire.unary("ImageGenerate", { prompt: "spent" });
  assert.equal(refused.errorCode, "quota");
  assert.equal(refused.images.length, 0);

  const listed = await wire.unary("ImageGetModels");
  assert.equal(listed.defaultModel, "edit-1");
  assert.equal(listed.models[1].acceptsInputImages, true);
  await wire.close();
});

test("over the wire: an absent model list is UNIMPLEMENTED", async () => {
  const d = await MockDaemon.start();
  started.push(d);
  const wire = await d.launch(noList());
  await assert.rejects(wire.unary("ImageGetModels"), (e) => e.code === UNIMPLEMENTED);
  await wire.close();
});
