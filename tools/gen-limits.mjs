#!/usr/bin/env node
/**
 * Generates the shared-limit constants in all three SDKs — and the daemon's
 * assertion block — from the one true `spec/limits.yaml`.
 *
 * Why this exists: the streaming-STT audio channel had to be 500 on both ends.
 * It was 500 in the daemon and 32 in the Rust SDK, and the mismatch silently
 * truncated every utterance to its first fraction. The coupling was documented
 * in a prose comment on both sides — a contract no compiler, test or grep ever
 * checked. This generator turns that class of comment into data with one
 * source, generated readers, and a daemon-side `assert!` that fails the build
 * when the two sides disagree.
 *
 * Outputs (all carry a DO NOT EDIT banner):
 *   astra-plugin-sdk/src/limits.rs
 *   astra-plugin-sdk-python/astra_plugin_sdk/limits.py
 *   astra-plugin-sdk-ts/src/generated/limits.ts
 *   <astra>/astra-daemon/src/plugins/voice_capability.rs   (marked block only)
 *
 * The Astra checkout is found via `$ASTRA_RS_DIR`, else `../Astra/astra-rs`
 * next to this repo. When it is absent the daemon block is skipped with a
 * notice — AstraPlugins CI has no Astra checkout, and must still be able to
 * regenerate and verify its own three files.
 *
 * Usage:
 *   node tools/gen-limits.mjs            # write
 *   node tools/gen-limits.mjs --check    # write nothing; exit 1 on any drift
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..");

const SPEC_REL = "spec/limits.yaml";
const SPEC_PATH = join(REPO_ROOT, SPEC_REL);

/** Limits the SDKs and the daemon are both entitled to find. Deleting one from
 *  the spec is a breaking change, so it fails here rather than downstream. */
const REQUIRED = [
  "stt_audio_channel_capacity",
  "plugin_start_timeout_secs",
  "plugin_stop_grace_secs",
  "max_extract_bytes",
  "max_archive_entries",
];

const CHECK_ONLY = process.argv.includes("--check");

function fail(message) {
  console.error(`gen-limits: ${message}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Parse. A deliberately tiny YAML subset — see the format note in limits.yaml.
// Anything outside it is an error, not a best-effort guess: a limits file that
// half-parses is how a shared constant goes missing without anyone noticing.
// ---------------------------------------------------------------------------

let specSource;
try {
  specSource = readFileSync(SPEC_PATH, "utf8");
} catch (err) {
  fail(`cannot read ${SPEC_REL} at ${SPEC_PATH} (${err.code ?? err.message})`);
}

const KEY_RE = /^([a-z][a-z0-9_]*):[ \t]*([0-9][0-9_]*)[ \t]*(?:#[ \t]*(.*?))?[ \t]*$/;

/** @type {{name: string, value: number, literal: string, doc: string[]}[]} */
const limits = [];
const seen = new Set();
let pendingDoc = [];

specSource.split(/\r?\n/).forEach((line, i) => {
  const lineNo = i + 1;
  if (line.trim() === "") {
    pendingDoc = [];
    return;
  }
  if (line.startsWith("#")) {
    pendingDoc.push(line.replace(/^#[ \t]?/, "").trimEnd());
    return;
  }
  const m = KEY_RE.exec(line);
  if (!m) {
    fail(
      `${SPEC_REL}:${lineNo}: not a \`key: <non-negative integer>\` line and not a comment:\n` +
        `    ${line}\n` +
        `  The format is deliberately flat — no nesting, no quotes, no strings.`
    );
  }
  const [, name, literal, trailing] = m;
  if (seen.has(name)) fail(`${SPEC_REL}:${lineNo}: duplicate key \`${name}\``);
  seen.add(name);
  const value = Number(literal.replaceAll("_", ""));
  if (!Number.isSafeInteger(value)) {
    fail(
      `${SPEC_REL}:${lineNo}: \`${name}\` = ${literal} exceeds 2^53-1 and cannot round-trip ` +
        `through the TypeScript SDK as a number. Limits this large need a bigint emitter first.`
    );
  }
  const doc = pendingDoc.slice();
  if (trailing) doc.push(trailing.trim());
  if (doc.length === 0) fail(`${SPEC_REL}:${lineNo}: \`${name}\` has no doc comment above it`);
  limits.push({ name, value, literal, doc });
  pendingDoc = [];
});

const missing = REQUIRED.filter((k) => !seen.has(k));
if (missing.length > 0) {
  fail(
    `${SPEC_REL} is missing required limit(s): ${missing.join(", ")}\n` +
      `  These are load-bearing on both sides of the protocol. If one is genuinely gone, ` +
      `remove it from REQUIRED in tools/gen-limits.mjs in the same change.`
  );
}
if (limits.length === 0) fail(`${SPEC_REL} declares no limits`);

const specSha256 = createHash("sha256").update(specSource).digest("hex");

// ---------------------------------------------------------------------------
// Emit
// ---------------------------------------------------------------------------

const CONST = (name) => name.toUpperCase();
const plain = (l) => String(l.value);

/**
 * The MPL header every source file in this repository carries. Generated files
 * are shipped source too, so the generator has to emit it — otherwise the file
 * on disk and the file the generator would write can never agree again.
 */
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

function banner(commentPrefix, extra = "") {
  return [
    `${commentPrefix} AUTO-GENERATED — DO NOT EDIT.`,
    `${commentPrefix}`,
    `${commentPrefix} Produced by \`tools/gen-limits.mjs\` from \`${SPEC_REL}\`.`,
    `${commentPrefix} Regenerate with \`node tools/gen-limits.mjs\` at the repo root.`,
    `${commentPrefix} These numbers are shared with the Astra daemon; changing one here without`,
    `${commentPrefix} changing the spec is a silent protocol break, which is why this file is`,
    `${commentPrefix} generated and CI re-runs the generator with \`--check\`.`,
    extra ? `${commentPrefix}\n${commentPrefix} ${extra}` : null,
  ]
    .filter((l) => l !== null)
    .join("\n");
}

function rustFile() {
  const body = limits
    .map((l) => {
      const doc = l.doc.map((d) => (d ? `/// ${d}` : "///")).join("\n");
      return `${doc}\npub const ${CONST(l.name)}: u64 = ${l.literal};`;
    })
    .join("\n\n");
  const note =
    "Every limit is a `u64`, uniformly — cast at the use site (`… as usize`).\n" +
    "//! One rule beats a per-key type table that can drift on its own.";
  return `${license("//")}
${banner("//!", note)}

/// SHA-256 of the \`${SPEC_REL}\` these constants were generated from.
pub const SPEC_SHA256: &str = "${specSha256}";

${body}
`;
}

function pythonFile() {
  const body = limits
    .map((l) => {
      const doc = l.doc.map((d) => (d ? `#: ${d}` : "#:")).join("\n");
      return `${doc}\n${CONST(l.name)} = ${l.literal}`;
    })
    .join("\n\n");
  const all = ["SPEC_SHA256", ...limits.map((l) => CONST(l.name))]
    .map((n) => `    "${n}",`)
    .join("\n");
  return `${license("#")}
"""Shared numeric limits, generated from ${SPEC_REL}.

${banner("#").replace(/^# ?/gm, "")}
"""

#: SHA-256 of the \`\`${SPEC_REL}\`\` these constants were generated from.
SPEC_SHA256 = "${specSha256}"

${body}

__all__ = [
${all}
]
`;
}

function typescriptFile() {
  const body = limits
    .map((l) => {
      const doc =
        l.doc.length === 1
          ? `/** ${l.doc[0]} */`
          : `/**\n${l.doc.map((d) => (d ? ` * ${d}` : " *")).join("\n")}\n */`;
      return `${doc}\nexport const ${CONST(l.name)} = ${plain(l)};`;
    })
    .join("\n\n");
  return `${license("//")}
${banner(" *").replace(/^ \*/, "/**\n *")}
 */

/** SHA-256 of the \`${SPEC_REL}\` these constants were generated from. */
export const SPEC_SHA256 = "${specSha256}";

${body}
`;
}

/** The block the daemon carries, between markers, inside a hand-written file. */
const DAEMON_BEGIN = "// BEGIN GENERATED spec/limits.yaml — tools/gen-limits.mjs";
const DAEMON_END = "// END GENERATED spec/limits.yaml";

function daemonBlock() {
  const body = limits
    .map((l) => {
      const doc = l.doc.map((d) => (d ? `/// ${d}` : "///")).join("\n");
      // `dead_code` allowed per constant: the block mirrors the WHOLE spec, and
      // not every shared limit has a daemon-side site to assert against yet
      // (`plugin_start_timeout_secs` does not). A generated file that emits
      // warnings gets deleted by the next person tidying up.
      return `${doc}\n#[allow(dead_code)]\npub const SPEC_${CONST(l.name)}: u64 = ${l.literal};`;
    })
    .join("\n\n");
  return `${DAEMON_BEGIN}
// Regenerate from a checkout of AstraPlugins: \`node tools/gen-limits.mjs\`.
// Editing these numbers by hand does not change the spec — it only moves the
// disagreement to the next person who regenerates.
${body}
${DAEMON_END}`;
}

const outputs = [
  { path: join(REPO_ROOT, "astra-plugin-sdk", "src", "limits.rs"), content: rustFile() },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-python", "astra_plugin_sdk", "limits.py"),
    content: pythonFile(),
  },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-ts", "src", "generated", "limits.ts"),
    content: typescriptFile(),
  },
];

// The daemon half. Optional by location, mandatory by content: if the file is
// there, its marked block must end up byte-identical to `daemonBlock()`.
const ASTRA_RS = process.env.ASTRA_RS_DIR
  ? resolve(process.env.ASTRA_RS_DIR)
  : resolve(REPO_ROOT, "..", "Astra", "astra-rs");
const DAEMON_FILE = join(ASTRA_RS, "astra-daemon", "src", "plugins", "voice_capability.rs");

let daemonNote = `skipped (no Astra checkout at ${DAEMON_FILE}; set $ASTRA_RS_DIR)`;
if (existsSync(DAEMON_FILE)) {
  const src = readFileSync(DAEMON_FILE, "utf8");
  const begin = src.indexOf(DAEMON_BEGIN);
  const end = src.indexOf(DAEMON_END);
  if (begin === -1 || end === -1 || end < begin) {
    fail(
      `${DAEMON_FILE} has no generated block.\n` +
        `  Expected a region delimited by:\n    ${DAEMON_BEGIN}\n    ${DAEMON_END}\n` +
        `  Someone deleted it, and with it the only build-time check that the daemon's ` +
        `constants still agree with ${SPEC_REL}. Restore the markers.`
    );
  }
  const updated = src.slice(0, begin) + daemonBlock() + src.slice(end + DAEMON_END.length);
  outputs.push({ path: DAEMON_FILE, content: updated, whole: false });
  daemonNote = DAEMON_FILE;
}

let drifted = 0;
for (const out of outputs) {
  const existing = existsSync(out.path) ? readFileSync(out.path, "utf8") : null;
  if (existing === out.content) continue;
  drifted += 1;
  const label = out.path.startsWith(REPO_ROOT) ? relative(REPO_ROOT, out.path) : out.path;
  if (CHECK_ONLY) {
    console.error(`gen-limits: DRIFT — ${label} is not what ${SPEC_REL} generates`);
    continue;
  }
  mkdirSync(dirname(out.path), { recursive: true });
  writeFileSync(out.path, out.content);
  console.log(`gen-limits: wrote ${label}`);
}

if (CHECK_ONLY) {
  if (drifted > 0) {
    console.error(
      `gen-limits: ${drifted} file(s) out of date. Run \`node tools/gen-limits.mjs\` and commit.`
    );
    process.exit(1);
  }
  console.log(`gen-limits: OK — ${limits.length} limits, all generated files current`);
} else {
  console.log(
    `gen-limits: ${SPEC_REL} (sha256 ${specSha256.slice(0, 12)}…) -> ${limits.length} limits; ` +
      `daemon block: ${daemonNote}`
  );
}
