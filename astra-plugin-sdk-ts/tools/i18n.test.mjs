/**
 * `I18n`, held to `testdata/i18n/vectors.json` — the same file the other two
 * SDKs read.
 *
 * `I18n` shipped in three languages and had never had a test. It disagreed with
 * itself three ways, silently, and this SDK owned two of the three: `tf` used
 * `String.replace` with a string needle, so it replaced only the FIRST
 * occurrence of each placeholder; and the loader accepted any object, so a
 * nested `{"config": {"token": {"title": "…"}}}` loaded here and was dropped
 * whole by the daemon, leaving every `$config.token.title` on screen as itself.
 *
 * A per-SDK test would have pinned this implementation to itself. This one
 * reads the shared vectors, so the question it answers is not "does TypeScript
 * still do what TypeScript did" but "do the three still do the same thing".
 * Coupling C17; the other half is `tools/gen-i18n.mjs` at the repository root,
 * which generates the plural tables from `spec/i18n.yaml`.
 *
 * Runs against the compiled `dist/` (see the `pretest` script), because that is
 * what a plugin actually loads.
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { after, test } from "node:test";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));

const { I18n, key } = require("../dist/i18n.js");
const plural = require("../dist/generated/plural.js");

/**
 * Floors, not counts. Each is well under what the file carries today, so adding
 * a case is free and losing most of them is not. Written before the mutation
 * that proved this test can fail, which is the only order in which a floor
 * means anything.
 */
const MIN_FIXTURES = 5;
const MIN_LOADS = 5;
const MIN_CASES = 30;
const MIN_PLURAL = 35;

/**
 * `testdata/` sits at the repository root, two levels up from `tools/`. It is
 * not inside the published npm tarball — these vectors are shared with the Rust
 * and Python SDKs and with nothing that installs this package — so a run from a
 * checkout is the only run that can execute them.
 */
const VECTORS = path.resolve(HERE, "..", "..", "testdata", "i18n", "vectors.json");

if (!fs.existsSync(VECTORS)) {
  throw new Error(
    `${VECTORS} is missing. This test proves the three SDKs agree about i18n; ` +
      `without the shared vectors it proves nothing, so it fails rather than skipping.`
  );
}
const doc = JSON.parse(fs.readFileSync(VECTORS, "utf8"));

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "astra-i18n-"));
after(() => fs.rmSync(scratch, { recursive: true, force: true }));

/** Write a fixture's files into a directory of its own and return it. */
function materialise(name) {
  if (name === "MISSING") return path.join(scratch, "never-created");
  const dir = path.join(scratch, name);
  fs.mkdirSync(dir, { recursive: true });
  const fixture = doc.fixtures[name];
  assert.ok(fixture, `no fixture named ${name}`);
  for (const [filename, text] of Object.entries(fixture.files)) {
    fs.writeFileSync(path.join(dir, filename), text, "utf8");
  }
  return dir;
}

test("the vector file is the one this test was written against", () => {
  assert.equal(
    doc.schema,
    "astra.i18n.vectors/1",
    "the vectors file changed shape; this reader has not"
  );
  assert.ok(
    Object.keys(doc.fixtures).length >= MIN_FIXTURES,
    `${Object.keys(doc.fixtures).length} fixture(s), floor is ${MIN_FIXTURES}`
  );
  for (const [field, floor] of [
    ["loads", MIN_LOADS],
    ["cases", MIN_CASES],
    ["plural", MIN_PLURAL],
  ]) {
    assert.ok(
      Array.isArray(doc[field]) && doc[field].length >= floor,
      `${doc[field]?.length} \`${field}\` vector(s), floor is ${floor}`
    );
  }
});

test("loading a fixture gives the shared answer", () => {
  let ran = 0;
  for (const vector of doc.loads) {
    const i18n = new I18n(materialise(vector.fixture));
    assert.deepEqual(i18n.availableLanguages, vector.languages, vector.name);
    assert.equal(
      i18n.loadErrors.length,
      vector.error_count,
      `${vector.name}: load errors were ${JSON.stringify(i18n.loadErrors)}`
    );
    const blob = i18n.loadErrors.join("\n");
    for (const needle of vector.errors_contain) {
      assert.ok(
        blob.includes(needle),
        `${vector.name}: no load error mentions ${needle}: ${JSON.stringify(i18n.loadErrors)}`
      );
    }
    ran += 1;
  }
  assert.ok(ran >= MIN_LOADS, `only ${ran} load vector(s) ran, floor is ${MIN_LOADS}`);
});

test("every case gives the shared answer", () => {
  let ran = 0;
  for (const c of doc.cases) {
    const i18n = new I18n(materialise(c.fixture));
    i18n.setLanguage(c.language);

    let got;
    switch (c.call) {
      case "t":
        got = i18n.t(c.key);
        break;
      case "has":
        got = i18n.has(c.key);
        break;
      case "tf":
        got = i18n.tf(c.key, ...c.args);
        break;
      case "ta":
        got = i18n.ta(c.key, c.named);
        break;
      case "tn":
        got = i18n.tn(c.key, c.n, c.named);
        break;
      case "count_prefixed":
        got = i18n.countPrefixed(c.key);
        break;
      case "key":
        got = key(c.key);
        break;
      default:
        throw new Error(
          `${c.name}: the vectors use a call this test does not implement: ${c.call}. ` +
            `Implement it here rather than dropping the case, or the vector is carried ` +
            `by two SDKs and not by three.`
        );
    }
    assert.deepEqual(got, c.expect, c.name);
    ran += 1;
  }
  assert.ok(ran >= MIN_CASES, `only ${ran} case(s) ran, floor is ${MIN_CASES}`);
});

test("the generated plural table gives the shared answer", () => {
  let ran = 0;
  for (const vector of doc.plural) {
    assert.equal(
      plural.category(vector.language, vector.n),
      vector.expect,
      `${vector.language} n=${vector.n}`
    );
    ran += 1;
  }
  assert.ok(ran >= MIN_PLURAL, `only ${ran} plural vector(s) ran, floor is ${MIN_PLURAL}`);
});

test("every declared language ends in `other`", () => {
  // `tn` falls back `<key>.<category>` -> `<key>.other` -> `<key>`, so a
  // language whose table did not end in `other` would have counts that resolve
  // to nothing at all.
  const langs = Object.keys(plural.CATEGORIES);
  assert.ok(
    langs.length >= 2,
    `the generated table holds ${langs.length} language(s) — that is a broken ` +
      `generator, not a shrunken vocabulary`
  );
  for (const lang of langs) {
    const categories = plural.CATEGORIES[lang];
    assert.equal(categories[categories.length - 1], "other", `${lang} does not end in other`);
    assert.ok(plural.isDeclared(lang));
  }
  assert.ok(!plural.isDeclared("zh-CN"));
});
