/**
 * The `music_provider` hooks, through the SDK's real dispatch.
 *
 * What is under test: what the plugin publishes is what the daemon would read;
 * a refusal the plugin MEANT (`MusicRefusal`) is a successful call with
 * `errorCode` set; answers are cut to the requested bound; and a plugin that is
 * not a music provider answers UNIMPLEMENTED.
 *
 * Run: `bun run test`.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

const { plugin, MusicPublisher, MusicRefusal } = require("../dist/index.js");
const { Harness } = require("../dist/testing/index.js");

function provider(controlled = []) {
  const publisher = new MusicPublisher();
  publisher.publish(
    [{ serviceId: "spotify", name: "Spotify", canSearch: true, canPlay: true }],
    [{ sessionKey: "spotify", serviceId: "spotify", status: "playing", title: "Song", controls: ["play", "like"] }],
  );
  return plugin({
    music: {
      publisher,
      control(req) {
        if (req.action === "like") throw new MusicRefusal("auth", "sign in to Spotify first");
        controlled.push(req);
      },
      search(req) {
        return Array.from({ length: 50 }, (_, i) => ({ itemRef: `spotify:track:${i}`, kind: "track", title: `${req.query} ${i}` }));
      },
      play(req) {
        return { item: { itemRef: req.itemRef || "spotify:track:9", kind: "track", title: "Nine" }, sessionKey: "spotify" };
      },
    },
  });
}

test("what the plugin publishes is what the daemon reads", async () => {
  const h = await Harness.create(provider()).start();
  const snapshot = h.musicSnapshot();
  assert.equal(snapshot.services[0].serviceId, "spotify");
  assert.equal(snapshot.sessions[0].title, "Song");
  assert.deepEqual(snapshot.sessions[0].controls, ["play", "like"]);
  assert.equal(snapshot.sessions[0].volumePercent, -1, "an unknown volume is -1, not 0");
});

test("a refusal the plugin meant is an answer, not a status", async () => {
  const controlled = [];
  const h = await Harness.create(provider(controlled)).start();
  const refused = await h.unary("MusicControl", { sessionKey: "spotify", action: "like" });
  assert.equal(refused.errorCode, "auth");
  assert.equal(refused.errorMessage, "sign in to Spotify first");
  const done = await h.unary("MusicControl", { sessionKey: "spotify", action: "play", value: "" });
  assert.equal(done.errorCode, undefined);
  assert.deepEqual(controlled, [{ sessionKey: "spotify", action: "play", value: "" }]);
});

test("answers are bounded and carry the plugin's own reference", async () => {
  const h = await Harness.create(provider()).start();
  const found = await h.unary("MusicSearch", { query: "believer", limit: 99 });
  assert.equal(found.items.length, 20, "cut to music_search_max_items");
  const played = await h.unary("MusicPlay", { itemRef: "spotify:track:5" });
  assert.equal(played.played.itemRef, "spotify:track:5");
  assert.equal(played.sessionKey, "spotify");
});

test("a plugin that is not a music provider says so", async () => {
  const h = await Harness.create(plugin({})).start();
  const status = await h.unaryStatus("MusicControl", { sessionKey: "x", action: "play" });
  assert.equal(status?.code, 12, "UNIMPLEMENTED");
});

test("a refusal code is checked where it is written", () => {
  assert.throws(() => new MusicRefusal("teleport", "no"), TypeError);
});

test("the publisher wakes a subscriber and beats when quiet", async () => {
  const publisher = new MusicPublisher();
  const stream = publisher.stream(30);
  assert.equal((await stream.next()).value.sessions.length, 0);
  publisher.publish([], [{ sessionKey: "a", serviceId: "yandex", status: "playing" }]);
  assert.equal((await stream.next()).value.sessions[0].sessionKey, "a");
  assert.equal((await stream.next()).value.sessions[0].sessionKey, "a", "the heartbeat re-sends the latest");
  await stream.return(undefined);
});

test("a session the plugin never reported never reaches the hook", async () => {
  // What `astra-plugin test` sends: a key nobody reports. A hook that ignores
  // the key would otherwise like the author's real track.
  const controlled = [];
  const h = await Harness.create(provider(controlled)).start();
  const refused = await h.unary("MusicControl", { sessionKey: "astra-plugin-test.probe", action: "play" });
  assert.equal(refused.errorCode, "not_found");
  assert.deepEqual(controlled, []);
  const played = await h.unary("MusicPlay", { query: "x", sessionKey: "nobody" });
  assert.equal(played.errorCode, "not_found");
  const chosen = await h.unary("MusicPlay", { query: "x" });
  assert.equal(chosen.errorCode, undefined, "an empty key is the plugin's own choice");
});

test("a quiet subscriber does not collect a waiter per heartbeat", async () => {
  const publisher = new MusicPublisher();
  const stream = publisher.stream(5);
  await stream.next();
  for (let i = 0; i < 10; i++) await stream.next();
  assert.ok(publisher.waiters.size <= 1, `waiters left behind: ${publisher.waiters.size}`);
  await stream.return(undefined);
});
