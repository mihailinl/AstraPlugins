/**
 * The `webSearch` hook, through the SDK's real dispatch.
 *
 * What is under test is the wire projection: a refusal the plugin MEANT is a
 * successful call with `errorCode` set (the daemon falls back on `quota` and
 * gives up on a broken plugin, and it can only tell the two apart if they
 * arrive differently), the answer is cut to the requested count, and a plugin
 * that does not implement the hook answers UNIMPLEMENTED.
 *
 * Run: `bun run test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { Plugin, plugin, WebSearch } = require("../dist/index.js");
const { Harness } = require("../dist/testing/index.js");

function provider(seen = []) {
  return plugin({
    webSearch(req) {
      seen.push(req);
      if (req.query === "spent") return WebSearch.refuse("rate_limited", "slow down", 7);
      return Array.from({ length: 5 }, (_, i) => ({
        title: `hit ${i}`,
        url: `https://example.com/${i}`,
        published: "2026-10-01",
      }));
    },
  });
}

test("the request reaches the hook typed and the answer is cut to the count", async () => {
  const seen = [];
  const h = await Harness.create(provider(seen)).start();
  const res = await h.webSearch("rust", { count: 2, freshness: "week", country: "DE" });
  assert.equal(res.errorCode, undefined);
  assert.equal(res.hits.length, 2);
  assert.deepEqual(res.hits[0], {
    title: "hit 0",
    url: "https://example.com/0",
    snippet: "",
    published: "2026-10-01",
  });
  assert.deepEqual(seen[0], {
    query: "rust",
    count: 2,
    freshness: "week",
    country: "DE",
    language: "",
  });
});

test("a refusal the plugin meant is an answer, not a status", async () => {
  const h = await Harness.create(provider()).start();
  const status = await h.unaryStatus("WebSearch", { query: "spent", count: 3 });
  assert.equal(status, null, "a refusal must not fail the call");
  const res = await h.webSearch("spent");
  assert.deepEqual(res, {
    hits: [],
    errorCode: "rate_limited",
    errorMessage: "slow down",
    retryAfterSecs: 7,
  });
});

test("an absent webSearch answers UNIMPLEMENTED", async () => {
  const h = await Harness.create(plugin({ tools: {} })).start();
  const status = await h.unaryStatus("WebSearch", { query: "q", count: 1 });
  assert.equal(status.code, 12, "gRPC UNIMPLEMENTED");
});

test("an unknown freshness reads as no restriction and a zero count asks for one", async () => {
  const seen = [];
  const h = await Harness.create(provider(seen)).start();
  const res = await h.webSearch("q", { count: 0, freshness: "hour" });
  assert.equal(seen[0].freshness, "");
  assert.equal(seen[0].count, 1);
  assert.equal(res.hits.length, 1);
});

test("WebSearch.refuse refuses a code the daemon does not read", () => {
  assert.throws(() => WebSearch.refuse("out_of_coffee", "nope"), TypeError);
  assert.deepEqual(WebSearch.ERROR_CODES, [
    "quota",
    "rate_limited",
    "auth",
    "not_configured",
    "unavailable",
  ]);
});

test("defining webSearch is what registers the capability", async () => {
  const caps = await provider().instance.discoverCapabilities();
  assert.deepEqual(caps, ["web_search"]);

  class Classic extends Plugin {
    async webSearch() {
      return [];
    }
  }
  assert.ok((await new Classic().discoverCapabilities()).includes("web_search"));
  assert.ok(!(await new Plugin().discoverCapabilities()).includes("web_search"));
});
