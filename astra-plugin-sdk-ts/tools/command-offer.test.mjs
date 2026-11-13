/**
 * `commandsFromAstraFile`, held to `testdata/astra-file/vectors.json` — the
 * same file the other two SDKs read.
 *
 * The helper splits a `.astra` file (what Astra's Commands page exports) into
 * the portable commands a plugin offers with `ctx.proposeCommand()`, one at a
 * time. A per-SDK test would pin this implementation to itself; this one reads
 * the shared vectors, so the question it answers is "do the three agree".
 *
 * The floors come first: a vectors file that failed to load, or that somebody
 * emptied, must fail as that and not pass as a clean run.
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));

const { commandsFromAstraFile } = require("../dist/index.js");
const { ASTRA_FILE_LOCAL_FIELDS } = require("../dist/command-offer.js");

/**
 * `testdata/` sits at the repository root, two levels up from `tools/`. It is
 * not inside the published npm tarball — the vectors are shared with the Rust
 * and Python SDKs — so a run from a checkout is the only run that can execute
 * them.
 */
const VECTORS = path.resolve(HERE, "..", "..", "testdata", "astra-file", "vectors.json");

if (!fs.existsSync(VECTORS)) {
  throw new Error(
    `${VECTORS} is missing. This test proves the three SDKs read a .astra file alike; ` +
      `without the shared vectors it proves nothing, so it fails rather than skipping.`
  );
}
const doc = JSON.parse(fs.readFileSync(VECTORS, "utf8"));

test("the vectors carry enough cases", () => {
  assert.ok(doc.accepted.length >= 3, "the vectors lost their accepted cases");
  assert.ok(doc.refused.length >= 10, "the vectors lost their refused cases");
  assert.ok(doc.unsafe_integers.length >= 2, "the vectors lost their unsafe integers");
});

test("the drop list is the vectors' own, exactly", () => {
  assert.deepEqual([...ASTRA_FILE_LOCAL_FIELDS], doc.local_fields);
});

for (const c of doc.accepted) {
  test(`accepted: ${c.name}`, () => {
    assert.deepEqual(commandsFromAstraFile(c.text), c.commands);
  });
}

for (const c of doc.refused) {
  test(`refused: ${c.name}`, () => {
    assert.throws(
      () => commandsFromAstraFile(c.text),
      (e) => {
        assert.ok(e instanceof Error);
        assert.ok(e.message.startsWith("not a .astra"), e.message);
        assert.ok(e.message.includes(c.mentions), `${e.message} does not mention ${c.mentions}`);
        return true;
      }
    );
  });
}

// Rust and Python read these exactly; a JavaScript number cannot, so this helper
// refuses them rather than offer a value nobody wrote (vectors.json says why).
for (const c of doc.unsafe_integers) {
  test(`refused here, read exactly elsewhere: ${c.name}`, () => {
    assert.throws(
      () => commandsFromAstraFile(c.text),
      (e) => {
        assert.ok(e.message.startsWith("not a .astra"), e.message);
        assert.ok(e.message.includes(c.ts_mentions), `${e.message} does not mention ${c.ts_mentions}`);
        return true;
      }
    );
  });
}

test("the largest safe integer is read as written", () => {
  const [command] = commandsFromAstraFile(
    '{"format":"astra-commands","version":1,"commands":[{"priority":9007199254740991}]}'
  );
  assert.equal(command.priority, Number.MAX_SAFE_INTEGER);
});

test("a __proto__ member is data on the command, never its prototype", () => {
  const [command] = commandsFromAstraFile(
    '{"format":"astra-commands","version":1,"commands":[{"name":"x","__proto__":{"polluted":true}}]}'
  );
  assert.equal(Object.getPrototypeOf(command), Object.prototype);
  assert.deepEqual(Object.keys(command), ["name", "__proto__"]);
  assert.equal(command.polluted, undefined);
});

test("every local member is removed, and only at the top level", () => {
  const command = Object.fromEntries(doc.local_fields.map((name) => [name, "x"]));
  command.name = "kept";
  command.actions = [{ id: "an action's own id", type: "noop" }];
  const text = JSON.stringify({ format: "astra-commands", version: 1, commands: [command] });
  assert.deepEqual(commandsFromAstraFile(text), [
    { name: "kept", actions: [{ id: "an action's own id", type: "noop" }] },
  ]);
});
