#!/usr/bin/env node
/**
 * Generates the plural tables all three SDKs' `I18n::tn` selects with, from
 * `spec/i18n.yaml` — and refuses to run unless that file covers exactly the
 * codes `spec/locales.yaml` declares.
 *
 * Why this exists: `I18n` shipped in three languages with no test between
 * them, and re-reading the three found three silent disagreements — `tf`
 * replacing one occurrence in TypeScript and all of them elsewhere, `""`
 * treated as a miss in Python alone, and a nested object accepted by two of
 * the three when the daemon drops the whole file on it. `tn` would have been
 * the fourth and the worst: the Russian cardinal rule is four lines of modular
 * arithmetic, and three hand-written copies of it is three chances to put
 * "5 ходов" in the `few` bucket for a user nobody here can proof-read for.
 *
 * So the rules live in `spec/i18n.yaml` and the code is generated. This is
 * coupling C17, and its other half is `testdata/i18n/vectors.json`: the
 * generator makes the three implementations the SAME, the vectors prove they
 * are RIGHT. Neither replaces the other.
 *
 * Outputs (all carry a DO NOT EDIT banner):
 *   astra-plugin-sdk/src/plural.rs
 *   astra-plugin-sdk-python/astra_plugin_sdk/plural.py
 *   astra-plugin-sdk-ts/src/generated/plural.ts
 *
 * Usage:
 *   node tools/gen-i18n.mjs            # write
 *   node tools/gen-i18n.mjs --check    # write nothing; exit 1 on any drift
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..");

const I18N_REL = "spec/i18n.yaml";
const LOCALES_REL = "spec/locales.yaml";

/**
 * Semantic answers every SDK's `I18n` is written against. Deleting one from
 * the spec is a behaviour change in three languages at once, so it fails here
 * rather than in whichever SDK notices first.
 */
const REQUIRED_RULES = [
  "lookup_chain",
  "fallback_granularity",
  "empty_value",
  "non_string_value",
  "load_failure",
  "discover_chain",
  "tf_placeholder",
  "ta_placeholder",
  "tn_key_chain",
  "unknown_language_category",
  "declared_plane_marker",
];

/**
 * The fewest plural rows this reader will believe. Not the real count — a
 * floor, so that a format change which makes every line stop matching fails as
 * a broken parse instead of as a language set that shrank to nothing. Ten
 * codes cannot be covered by fewer than ten rows.
 */
const MIN_PLURAL_ROWS = 10;

/** Likewise for the vocabulary this is checked against. */
const MIN_LOCALE_CODES = 2;

const CHECK_ONLY = process.argv.includes("--check");

function fail(message) {
  console.error(`gen-i18n: ${message}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Parse
// ---------------------------------------------------------------------------

function read(rel) {
  const path = join(REPO_ROOT, rel);
  try {
    return readFileSync(path, "utf8");
  } catch (err) {
    fail(`cannot read ${rel} at ${path} (${err.code ?? err.message})`);
  }
}

/**
 * `spec/locales.yaml`'s codes, by the hand-parse that file's FORMAT paragraph
 * promises: split on whitespace, first field is the code. Three readers
 * implement it — this one, `tools/check-locales.py`, and the CLI's
 * `locales.rs` test — and none of them takes a dependency to do it.
 */
function localeCodes() {
  const codes = [];
  for (const raw of read(LOCALES_REL).split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    codes.push(line.split(/\s+/)[0]);
  }
  if (codes.length < MIN_LOCALE_CODES) {
    fail(
      `${LOCALES_REL} parsed to ${codes.length} code(s), fewer than ${MIN_LOCALE_CODES}.\n` +
        `  That is a broken parse, not a shrunken vocabulary — see that file's FORMAT paragraph.`
    );
  }
  return codes;
}

const RULE_RE = /^rule:[ \t]+([a-z][a-z0-9_]*)[ \t]*=[ \t]*(.+?)[ \t]*$/;
const PLURAL_RE = /^([a-z]{2})[ \t]+(zero|one|two|few|many|other)[ \t]+(.+?)[ \t]*$/;

/** `n % 10 in 2..4` and friends. The whole grammar; see the spec's FORMAT. */
const TERM_RE = /^n(?:[ \t]*%[ \t]*(\d+))?[ \t]+(==|!=|not in|in)[ \t]+(\d+)(?:\.\.(\d+))?$/;

function parseTerm(text, at) {
  if (text === "always") return { always: true };
  const m = TERM_RE.exec(text);
  if (!m) {
    fail(
      `${at}: \`${text}\` is not a term.\n` +
        `  The grammar is: always | n [% <int>] (== | != | in | not in) <int>[..<int>]\n` +
        `  Nothing else parses, on purpose: three SDKs have to agree about it.`
    );
  }
  const [, modulus, op, a, b] = m;
  const ranged = op === "in" || op === "not in";
  if (ranged && b === undefined) {
    fail(`${at}: \`${op}\` needs a range, as in \`n in 2..4\``);
  }
  if (!ranged && b !== undefined) {
    fail(`${at}: \`${op}\` takes one number, not a range`);
  }
  const lo = Number(a);
  const hi = b === undefined ? lo : Number(b);
  if (ranged && hi < lo) fail(`${at}: the range \`${a}..${b}\` runs backwards`);
  return { modulus: modulus === undefined ? null : Number(modulus), op, lo, hi };
}

/** One condition: a single term, or several joined by ONE of `&&` / `||`. */
function parseCondition(text, at) {
  const hasAnd = text.includes("&&");
  const hasOr = text.includes("||");
  if (hasAnd && hasOr) {
    fail(
      `${at}: \`${text}\` mixes && and ||.\n` +
        `  A condition is one term, or several joined by && , or several joined by ||.\n` +
        `  Precedence is not guessed here: three SDKs would have to agree about the guess.`
    );
  }
  const join = hasOr ? "||" : "&&";
  const terms = text
    .split(hasOr ? "||" : "&&")
    .map((t) => t.trim())
    .map((t) => parseTerm(t, at));
  if (terms.length > 1 && terms.some((t) => t.always)) {
    fail(`${at}: \`always\` cannot be joined to another term`);
  }
  return { join, terms };
}

function parseSpec() {
  const source = read(I18N_REL);
  const rules = new Map();
  /** code -> [{category, condition, at}], in file order. */
  const plurals = new Map();
  let rows = 0;

  source.split(/\r?\n/).forEach((raw, i) => {
    const at = `${I18N_REL}:${i + 1}`;
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;

    const rule = RULE_RE.exec(line);
    if (rule) {
      const [, name, value] = rule;
      if (rules.has(name)) fail(`${at}: duplicate rule \`${name}\``);
      rules.set(name, value);
      return;
    }

    const plural = PLURAL_RE.exec(line);
    if (plural) {
      const [, code, category, condition] = plural;
      if (!plurals.has(code)) plurals.set(code, []);
      const forCode = plurals.get(code);
      if (forCode.some((r) => r.category === category)) {
        fail(`${at}: \`${code}\` already has a \`${category}\` row`);
      }
      forCode.push({ category, condition: parseCondition(condition, at), at });
      rows += 1;
      return;
    }

    fail(
      `${at}: not a \`rule:\` line, not a plural row, and not a comment:\n` +
        `    ${raw}\n` +
        `  See the FORMAT paragraph in ${I18N_REL}.`
    );
  });

  const missing = REQUIRED_RULES.filter((k) => !rules.has(k));
  if (missing.length > 0) {
    fail(
      `${I18N_REL} is missing required rule(s): ${missing.join(", ")}\n` +
        `  Every SDK's I18n is written against these. If one is genuinely gone, remove it\n` +
        `  from REQUIRED_RULES in tools/gen-i18n.mjs in the same change, and say why.`
    );
  }
  if (rows < MIN_PLURAL_ROWS) {
    fail(
      `${I18N_REL} parsed to ${rows} plural row(s), fewer than ${MIN_PLURAL_ROWS}.\n` +
        `  Ten locale codes cannot be covered by fewer than ten rows, so this is a broken\n` +
        `  parse rather than a shrunken table — the rule did not change, the scan did.`
    );
  }

  for (const [code, forCode] of plurals) {
    const last = forCode[forCode.length - 1];
    if (last.category !== "other" || !last.condition.terms[0].always) {
      fail(
        `${last.at}: the last row for \`${code}\` is \`${last.category}\`, not \`other always\`.\n` +
          `  Every code ends the same way, so that <key>.other is always a legal thing for a\n` +
          `  translator to write and no count can fall off the end of the table.`
      );
    }
    for (const row of forCode.slice(0, -1)) {
      if (row.condition.terms[0].always) {
        fail(`${row.at}: \`always\` before the last row makes every row under it dead`);
      }
    }
  }

  return { rules, plurals, rows, sha256: createHash("sha256").update(source).digest("hex") };
}

const spec = parseSpec();
const codes = localeCodes();

// The vocabulary and the plural table are two files that have to name the same
// ten strings. A code in one and not the other is silent in both directions: a
// language the daemon can be set to and `tn` has no rules for, or rules for a
// language a plugin may not ship a file named after.
{
  const declared = new Set(codes);
  const ruled = new Set(spec.plurals.keys());
  const onlySpec = [...ruled].filter((c) => !declared.has(c)).sort();
  const onlyVocab = [...declared].filter((c) => !ruled.has(c)).sort();
  if (onlySpec.length || onlyVocab.length) {
    fail(
      `${I18N_REL} and ${LOCALES_REL} do not name the same languages.\n` +
        `  plural rows for a code ${LOCALES_REL} does not declare: ${onlySpec.join(", ") || "—"}\n` +
        `  declared with no plural rows: ${onlyVocab.join(", ") || "—"}\n` +
        `  A language arrives in ${LOCALES_REL} first (see its HOW TO CHANGE THIS LIST), then\n` +
        `  gets at least a \`<code> other always\` row here. An absence here would otherwise be\n` +
        `  a silent \`other\` for every count in that language.`
    );
  }
}

/** Codes in `spec/locales.yaml` order, so the emitted tables read like it. */
const ORDERED = codes.map((code) => [code, spec.plurals.get(code)]);

// ---------------------------------------------------------------------------
// Emit
// ---------------------------------------------------------------------------

/** `{ n, mod }` as an expression in the target language. All three agree. */
function operand(term) {
  return term.modulus === null ? "n" : `n % ${term.modulus}`;
}

/**
 * One term as source, and whether it came out compound.
 *
 * `lo == 0` drops the lower bound. That is not tidiness: `n` is unsigned in
 * the Rust emitter (`unsigned_abs`), and `n >= 0` on a `u64` is a
 * `unused_comparisons` warning in every generated build — a generated file
 * that warns is a generated file somebody eventually "fixes" by hand.
 */
function termSource(term) {
  const x = operand(term);
  switch (term.op) {
    case "==":
      return { src: `${x} == ${term.lo}`, compound: false };
    case "!=":
      return { src: `${x} != ${term.lo}`, compound: false };
    case "in":
      return term.lo === 0
        ? { src: `${x} <= ${term.hi}`, compound: false }
        : { src: `${x} >= ${term.lo} && ${x} <= ${term.hi}`, compound: true };
    default:
      return term.lo === 0
        ? { src: `${x} > ${term.hi}`, compound: false }
        : { src: `${x} < ${term.lo} || ${x} > ${term.hi}`, compound: true };
  }
}

/**
 * A condition as source. Identical text in all three languages: the grammar
 * admits only `%`, comparisons and `&&`/`||`, which Rust, Python-with-`and`
 * substituted, and TypeScript all spell the same way apart from the
 * connectives — handled by `pythonise` below.
 *
 * Parentheses only where a compound term sits inside a join. A lone term is
 * never wrapped: `if (n <= 1)` in Rust is an `unused_parens` warning.
 */
function conditionSource(condition) {
  const parts = condition.terms.map(termSource);
  if (parts.length === 1) return parts[0].src;
  return parts.map((p) => (p.compound ? `(${p.src})` : p.src)).join(` ${condition.join} `);
}

const pythonise = (src) => src.replaceAll("&&", "and").replaceAll("||", "or");

function license(commentPrefix) {
  return [
    `${commentPrefix} This Source Code Form is subject to the terms of the Mozilla Public`,
    `${commentPrefix} License, v. 2.0. If a copy of the MPL was not distributed with this`,
    `${commentPrefix} file, You can obtain one at https://mozilla.org/MPL/2.0/.`,
    `${commentPrefix}`,
    `${commentPrefix} Copyright (C) 2026 Minice — https://minice.ai`,
    "",
  ].join("\n");
}

const BANNER_BODY = [
  "AUTO-GENERATED — DO NOT EDIT.",
  "",
  `Produced by \`tools/gen-i18n.mjs\` from \`${I18N_REL}\`.`,
  "Regenerate with `node tools/gen-i18n.mjs` at the repo root.",
  "",
  "The CLDR cardinal rules `I18n::tn` selects with. They are generated because",
  "the Russian and Ukrainian rules are four lines of modular arithmetic each,",
  "and three hand-written copies is three chances to put the wrong noun form in",
  "front of a user nobody in this repository can proof-read for. C17.",
  "",
  "`n` is the ABSOLUTE VALUE of the count, as CLDR defines the operand: `%` is",
  "truncated in Rust and JavaScript and floored in Python, so a signed `n`",
  "would sort the same count into different categories in different SDKs.",
];

/** The settled semantics, restated where an SDK author reads them. */
function ruleLines() {
  return [...spec.rules].map(([name, value]) => `${name}: ${value}`);
}

function banner(commentPrefix) {
  return [...BANNER_BODY, "", "Declared semantics, from the same file:", ...ruleLines()]
    .map((l) => (l ? `${commentPrefix} ${l}` : commentPrefix))
    .join("\n");
}

function categoriesOf(rows) {
  return rows.map((r) => r.category);
}

// ── Rust ───────────────────────────────────────────────────────────────────

function rustFile() {
  const table = ORDERED.map(
    ([code, rows]) =>
      `    ("${code}", &[${categoriesOf(rows)
        .map((c) => `"${c}"`)
        .join(", ")}]),`
  ).join("\n");

  const arms = ORDERED.map(([code, rows]) => {
    const body = rows
      .slice(0, -1)
      .map((r) => `            if ${conditionSource(r.condition)} {\n                return "${r.category}";\n            }`)
      .join("\n");
    return `        "${code}" => {\n${body ? body + "\n" : ""}            "other"\n        }`;
  }).join("\n");

  return `${license("//")}
${banner("//!")}

/// SHA-256 of the \`${I18N_REL}\` these rules were generated from.
pub const SPEC_SHA256: &str = "${spec.sha256}";

/// Every language's categories, in the order \`${I18N_REL}\` declares them.
///
/// The last entry is always \`"other"\`. A locale file is expected to carry
/// \`<base>.<category>\` for each of its language's entries and no others —
/// that is the parity rule \`astra-plugin check\` enforces.
pub const CATEGORIES: &[(&str, &[&str])] = &[
${table}
];

/// The categories \`lang\` uses, or \`["other"]\` for a language not declared.
pub fn categories(lang: &str) -> &'static [&'static str] {
    for (code, cats) in CATEGORIES {
        if *code == lang {
            return cats;
        }
    }
    &["other"]
}

/// Is \`lang\` one of the languages Astra can be set to?
///
/// The keys of [\`CATEGORIES\`] are generated from \`spec/locales.yaml\` and the
/// generator refuses to run unless the two files name exactly the same
/// languages — so this table doubles as the vocabulary, and \`I18n\` uses it to
/// say so when a plugin ships a \`locales/zh-CN.json\` that nothing can select.
pub fn is_declared(lang: &str) -> bool {
    CATEGORIES.iter().any(|(code, _)| *code == lang)
}

/// The CLDR cardinal category for \`n\` in \`lang\`.
///
/// \`n\` is taken as an absolute value: a count of -3 items is grammatically
/// three items. A language this table does not name gets \`"other"\`.
//
// \`n % 10 == 0\` rather than \`n.is_multiple_of(10)\`, which clippy's
// \`manual_is_multiple_of\` suggests: that method was stabilised in Rust 1.87
// and this crate's floor is 1.85 (edition 2024). A generated file that emits
// warnings is a generated file somebody eventually edits by hand, and raising
// an SDK's minimum toolchain to satisfy a lint is the wrong trade.
// \`unknown_lints\` first, because the lint does not exist on every clippy this
// crate is built with.
#[allow(unknown_lints, clippy::manual_is_multiple_of)]
pub fn category(lang: &str, n: i64) -> &'static str {
    let n = n.unsigned_abs();
    match lang {
${arms}
        _ => "other",
    }
}
`;
}

// ── Python ─────────────────────────────────────────────────────────────────

function pythonFile() {
  const table = ORDERED.map(
    ([code, rows]) =>
      `    "${code}": (${categoriesOf(rows)
        .map((c) => `"${c}"`)
        .join(", ")}${categoriesOf(rows).length === 1 ? "," : ""}),`
  ).join("\n");

  const arms = ORDERED.map(([code, rows]) => {
    const body = rows
      .slice(0, -1)
      .map((r) => `        if ${pythonise(conditionSource(r.condition))}:\n            return "${r.category}"`)
      .join("\n");
    return `    if lang == "${code}":\n${body ? body + "\n" : ""}        return "other"`;
  }).join("\n");

  return `${license("#")}
"""CLDR cardinal plural rules, generated from ${I18N_REL}.

${banner("#").replace(/^# ?/gm, "")}
"""

from __future__ import annotations

#: SHA-256 of the \`\`${I18N_REL}\`\` these rules were generated from.
SPEC_SHA256 = "${spec.sha256}"

#: Every language's categories, in the order ${I18N_REL} declares them.
CATEGORIES: dict[str, tuple[str, ...]] = {
${table}
}


def categories(lang: str) -> tuple[str, ...]:
    """The categories \`\`lang\`\` uses, or \`\`("other",)\`\` if it is not declared."""
    return CATEGORIES.get(lang, ("other",))


def is_declared(lang: str) -> bool:
    """Is \`\`lang\`\` one of the languages Astra can be set to?

    The keys of :data:\`CATEGORIES\` are generated from \`\`spec/locales.yaml\`\` and
    the generator refuses to run unless the two files name exactly the same
    languages — so this table doubles as the vocabulary, and \`\`I18n\`\` uses it to
    say so when a plugin ships a \`\`locales/zh-CN.json\`\` that nothing can select.
    """
    return lang in CATEGORIES


def category(lang: str, n: int) -> str:
    """The CLDR cardinal category for \`\`n\`\` in \`\`lang\`\`.

    \`\`n\`\` is taken as an absolute value: a count of -3 items is grammatically
    three items. A language this table does not name gets \`\`"other"\`\`.
    """
    n = abs(int(n))
${arms}
    return "other"


__all__ = ["SPEC_SHA256", "CATEGORIES", "categories", "category", "is_declared"]
`;
}

// ── TypeScript ─────────────────────────────────────────────────────────────

function typescriptFile() {
  const table = ORDERED.map(
    ([code, rows]) =>
      `  ${code}: [${categoriesOf(rows)
        .map((c) => `"${c}"`)
        .join(", ")}],`
  ).join("\n");

  const arms = ORDERED.map(([code, rows]) => {
    const body = rows
      .slice(0, -1)
      .map((r) => `      if (${conditionSource(r.condition)}) return "${r.category}";`)
      .join("\n");
    return `    case "${code}":\n${body ? body + "\n" : ""}      return "other";`;
  }).join("\n");

  return `${license("//")}
/**
${banner(" *")}
 */

/** SHA-256 of the \`${I18N_REL}\` these rules were generated from. */
export const SPEC_SHA256 = "${spec.sha256}";

/** Every language's categories, in the order \`${I18N_REL}\` declares them. */
export const CATEGORIES: Readonly<Record<string, readonly string[]>> = {
${table}
};

/** The categories \`lang\` uses, or \`["other"]\` for a language not declared. */
export function categories(lang: string): readonly string[] {
  return CATEGORIES[lang] ?? ["other"];
}

/**
 * Is \`lang\` one of the languages Astra can be set to?
 *
 * The keys of \`CATEGORIES\` are generated from \`spec/locales.yaml\` and the
 * generator refuses to run unless the two files name exactly the same
 * languages — so this table doubles as the vocabulary, and \`I18n\` uses it to
 * say so when a plugin ships a \`locales/zh-CN.json\` that nothing can select.
 */
export function isDeclared(lang: string): boolean {
  return Object.prototype.hasOwnProperty.call(CATEGORIES, lang);
}

/**
 * The CLDR cardinal category for \`n\` in \`lang\`.
 *
 * \`n\` is taken as an absolute value and truncated to an integer: a count of
 * -3 items is grammatically three items. A language this table does not name
 * gets \`"other"\`.
 */
export function category(lang: string, n: number): string {
  n = Math.abs(Math.trunc(n));
  switch (lang) {
${arms}
    default:
      return "other";
  }
}
`;
}

// ---------------------------------------------------------------------------
// Write / check
// ---------------------------------------------------------------------------

const outputs = [
  { path: join(REPO_ROOT, "astra-plugin-sdk", "src", "plural.rs"), content: rustFile() },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-python", "astra_plugin_sdk", "plural.py"),
    content: pythonFile(),
  },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-ts", "src", "generated", "plural.ts"),
    content: typescriptFile(),
  },
];

let drifted = 0;
for (const out of outputs) {
  const existing = existsSync(out.path) ? readFileSync(out.path, "utf8") : null;
  if (existing === out.content) continue;
  drifted += 1;
  const label = relative(REPO_ROOT, out.path);
  if (CHECK_ONLY) {
    console.error(`gen-i18n: DRIFT — ${label} is not what ${I18N_REL} generates`);
    continue;
  }
  mkdirSync(dirname(out.path), { recursive: true });
  writeFileSync(out.path, out.content);
  console.log(`gen-i18n: wrote ${label}`);
}

const summary =
  `${spec.rows} plural row(s) over ${ORDERED.length} language(s), ` +
  `${spec.rules.size} declared rule(s), ${outputs.length} generated file(s)`;

if (CHECK_ONLY) {
  if (drifted > 0) {
    console.error(
      `gen-i18n: ${drifted} file(s) out of date. Run \`node tools/gen-i18n.mjs\` and commit.`
    );
    process.exit(1);
  }
  // What this run did NOT do, said out loud, for the same reason
  // `gen-limits --check` says it: the generator can only prove the three SDKs
  // carry the same TABLE. Whether the table is RIGHT is
  // `testdata/i18n/vectors.json`, read by one test in each SDK, and those tests
  // run in the sdk-rust / sdk-python / sdk-ts jobs rather than here.
  console.log(`gen-i18n: OK — ${summary}, all current`);
  console.log(
    "gen-i18n: NOT CHECKED — that the rules are correct, or that any SDK still " +
      "reads its\ngen-i18n:              generated table. testdata/i18n/vectors.json and the " +
      "three\ngen-i18n:              tests that read it are the other half of C17."
  );
} else {
  console.log(
    `gen-i18n: ${I18N_REL} (sha256 ${spec.sha256.slice(0, 12)}…) -> ${summary}`
  );
}
