#!/usr/bin/env node
/**
 * Generates the shared cross-repo constants in all three SDKs — and the
 * daemon's mirror block — from the two spec files under `spec/`.
 *
 * Why this exists: the streaming-STT audio channel had to be 500 on both ends.
 * It was 500 in the daemon and 32 in the Rust SDK, and the mismatch silently
 * truncated every utterance to its first fraction. The coupling was documented
 * in a prose comment on both sides — a contract no compiler, test or grep ever
 * checked. This generator turns that class of comment into data with one
 * source, generated readers, and a daemon-side `assert!` that fails the build
 * when the two sides disagree.
 *
 * TWO INPUTS, ONE MECHANISM. `spec/limits.yaml` holds integers and
 * `spec/wire.yaml` holds gRPC metadata keys. They are separate files because
 * limits.yaml's format is a stated contract — one regex, no quotes, every
 * constant a `u64` — that a string value would end. They share one generator,
 * one `--check` and one block in the daemon, so the cost of the second file is
 * a second three-line regex and nothing else. The name of this script is
 * historical; it predates the second input.
 *
 * Outputs (all carry a DO NOT EDIT banner):
 *   astra-plugin-sdk/src/limits.rs
 *   astra-plugin-sdk/src/wire.rs
 *   astra-plugin-sdk-python/astra_plugin_sdk/limits.py
 *   astra-plugin-sdk-python/astra_plugin_sdk/wire.py
 *   astra-plugin-sdk-ts/src/generated/limits.ts
 *   astra-plugin-sdk-ts/src/generated/wire.ts
 *   <astra>/astra-daemon/src/plugins/voice_capability.rs   (marked block only)
 *
 * The Astra checkout is found via `$ASTRA_RS_DIR`, else `../Astra/astra-rs`
 * next to this repo. When it is absent the daemon block is skipped with a
 * notice — AstraPlugins CI has no Astra checkout, and must still be able to
 * regenerate and verify its own six files.
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

const LIMITS_REL = "spec/limits.yaml";
const WIRE_REL = "spec/wire.yaml";

/** Limits the SDKs and the daemon are both entitled to find. Deleting one from
 *  the spec is a breaking change, so it fails here rather than downstream. */
const REQUIRED_LIMITS = [
  "stt_audio_channel_capacity",
  "plugin_start_timeout_secs",
  "plugin_stop_grace_secs",
  "max_extract_bytes",
  "max_archive_entries",
  "lease_ttl_secs",
  "lease_fire_grace_secs",
  "lease_max_fires",
];

/** Metadata keys with the same guarantee. `x_astra_cause` is load-bearing for
 *  trigger attribution; the two token headers authenticate both directions. */
const REQUIRED_WIRE = ["x_astra_cause", "session_token_header", "plugin_token_header"];

const CHECK_ONLY = process.argv.includes("--check");

function fail(message) {
  console.error(`gen-limits: ${message}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Parse. A deliberately tiny YAML subset — see the format note in each spec
// file. Anything outside it is an error, not a best-effort guess: a spec that
// half-parses is how a shared constant goes missing without anyone noticing.
// ---------------------------------------------------------------------------

const INTEGER_VALUE = /[0-9][0-9_]*/;
const HEADER_VALUE = /[a-z0-9][a-z0-9._-]*/;

/**
 * Reads one spec file into `{name, value, literal, doc}` rows.
 *
 * `valueRe` decides what a value may look like and is spliced into the line
 * pattern, so a line the caller's grammar does not accept is reported as a
 * format error naming the file and line rather than being skipped.
 */
function parseSpec(rel, valueRe, required, refine) {
  const path = join(REPO_ROOT, rel);
  let source;
  try {
    source = readFileSync(path, "utf8");
  } catch (err) {
    fail(`cannot read ${rel} at ${path} (${err.code ?? err.message})`);
  }

  const lineRe = new RegExp(
    `^([a-z][a-z0-9_]*):[ \\t]*(${valueRe.source})[ \\t]*(?:#[ \\t]*(.*?))?[ \\t]*$`
  );

  const rows = [];
  const seen = new Set();
  let pendingDoc = [];

  source.split(/\r?\n/).forEach((line, i) => {
    const lineNo = i + 1;
    if (line.trim() === "") {
      pendingDoc = [];
      return;
    }
    if (line.startsWith("#")) {
      pendingDoc.push(line.replace(/^#[ \t]?/, "").trimEnd());
      return;
    }
    const m = lineRe.exec(line);
    if (!m) {
      fail(
        `${rel}:${lineNo}: not a \`key: <value>\` line and not a comment:\n` +
          `    ${line}\n` +
          `  The format is deliberately flat — no nesting, no quotes. A value here ` +
          `must match ${valueRe.source}.`
      );
    }
    const [, name, literal, trailing] = m;
    if (seen.has(name)) fail(`${rel}:${lineNo}: duplicate key \`${name}\``);
    seen.add(name);
    const doc = pendingDoc.slice();
    if (trailing) doc.push(trailing.trim());
    if (doc.length === 0) fail(`${rel}:${lineNo}: \`${name}\` has no doc comment above it`);
    rows.push(refine({ name, literal, doc }, `${rel}:${lineNo}`));
    pendingDoc = [];
  });

  const missing = required.filter((k) => !seen.has(k));
  if (missing.length > 0) {
    fail(
      `${rel} is missing required key(s): ${missing.join(", ")}\n` +
        `  These are load-bearing on both sides of the protocol. If one is genuinely gone, ` +
        `remove it from the REQUIRED list in tools/gen-limits.mjs in the same change.`
    );
  }
  if (rows.length === 0) fail(`${rel} declares nothing`);

  return { rows, sha256: createHash("sha256").update(source).digest("hex") };
}

const limitsSpec = parseSpec(LIMITS_REL, INTEGER_VALUE, REQUIRED_LIMITS, (row, at) => {
  const value = Number(row.literal.replaceAll("_", ""));
  if (!Number.isSafeInteger(value)) {
    fail(
      `${at}: \`${row.name}\` = ${row.literal} exceeds 2^53-1 and cannot round-trip ` +
        `through the TypeScript SDK as a number. Limits this large need a bigint emitter first.`
    );
  }
  return { ...row, value };
});

const wireSpec = parseSpec(WIRE_REL, HEADER_VALUE, REQUIRED_WIRE, (row, at) => {
  // gRPC reserves the `-bin` suffix for base64-encoded binary values. Nothing
  // here carries bytes, and a key that accidentally acquired the suffix would
  // change how every runtime encodes the value rather than failing outright.
  if (row.literal.endsWith("-bin")) {
    fail(
      `${at}: \`${row.name}\` = ${row.literal} ends in \`-bin\`, which gRPC reserves for ` +
        `base64-encoded binary metadata. Every value carried here is text.`
    );
  }
  return { ...row, value: row.literal };
});

const limits = limitsSpec.rows;
const wires = wireSpec.rows;

// ---------------------------------------------------------------------------
// Emit
// ---------------------------------------------------------------------------

const CONST = (name) => name.toUpperCase();
/** A header name as a source literal. The grammar admits no quote or escape. */
const quoted = (row) => `"${row.value}"`;

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

function banner(commentPrefix, specRel, subject, extra = "") {
  return [
    `${commentPrefix} AUTO-GENERATED — DO NOT EDIT.`,
    `${commentPrefix}`,
    `${commentPrefix} Produced by \`tools/gen-limits.mjs\` from \`${specRel}\`.`,
    `${commentPrefix} Regenerate with \`node tools/gen-limits.mjs\` at the repo root.`,
    `${commentPrefix} ${subject}`,
    `${commentPrefix} changing the spec is a silent protocol break, which is why this file is`,
    `${commentPrefix} generated and CI re-runs the generator with \`--check\`.`,
    extra ? `${commentPrefix}\n${commentPrefix} ${extra}` : null,
  ]
    .filter((l) => l !== null)
    .join("\n");
}

const LIMITS_SUBJECT = "These numbers are shared with the Astra daemon; changing one here without";
const WIRE_SUBJECT = "These keys are shared with the Astra daemon; changing one here without";

function rustLimits() {
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
${banner("//!", LIMITS_REL, LIMITS_SUBJECT, note)}

/// SHA-256 of the \`${LIMITS_REL}\` these constants were generated from.
pub const SPEC_SHA256: &str = "${limitsSpec.sha256}";

${body}
`;
}

function rustWire() {
  const body = wires
    .map((w) => {
      const doc = w.doc.map((d) => (d ? `/// ${d}` : "///")).join("\n");
      return `${doc}\npub const ${CONST(w.name)}: &str = ${quoted(w)};`;
    })
    .join("\n\n");
  const note =
    "gRPC metadata keys are lowercase-ASCII and case-insensitive at the\n" +
    "//! transport, so the constant's identifier and its value are not the same\n" +
    "//! string — always compare against the constant, never a retyped literal.";
  return `${license("//")}
${banner("//!", WIRE_REL, WIRE_SUBJECT, note)}

/// SHA-256 of the \`${WIRE_REL}\` these constants were generated from.
pub const SPEC_SHA256: &str = "${wireSpec.sha256}";

${body}
`;
}

function pythonFile(specRel, subject, rows, sha256, render) {
  const body = rows
    .map((r) => {
      const doc = r.doc.map((d) => (d ? `#: ${d}` : "#:")).join("\n");
      return `${doc}\n${CONST(r.name)} = ${render(r)}`;
    })
    .join("\n\n");
  const all = ["SPEC_SHA256", ...rows.map((r) => CONST(r.name))]
    .map((n) => `    "${n}",`)
    .join("\n");
  return `${license("#")}
"""Shared ${specRel === LIMITS_REL ? "numeric limits" : "wire constants"}, generated from ${specRel}.

${banner("#", specRel, subject).replace(/^# ?/gm, "")}
"""

#: SHA-256 of the \`\`${specRel}\`\` these constants were generated from.
SPEC_SHA256 = "${sha256}"

${body}

__all__ = [
${all}
]
`;
}

function typescriptFile(specRel, subject, rows, sha256, render) {
  const body = rows
    .map((r) => {
      const doc =
        r.doc.length === 1
          ? `/** ${r.doc[0]} */`
          : `/**\n${r.doc.map((d) => (d ? ` * ${d}` : " *")).join("\n")}\n */`;
      return `${doc}\nexport const ${CONST(r.name)} = ${render(r)};`;
    })
    .join("\n\n");
  return `${license("//")}
${banner(" *", specRel, subject).replace(/^ \*/, "/**\n *")}
 */

/** SHA-256 of the \`${specRel}\` these constants were generated from. */
export const SPEC_SHA256 = "${sha256}";

${body}
`;
}

/**
 * The block the daemon carries, between markers, inside a hand-written file.
 *
 * The markers still name `spec/limits.yaml` alone, though the block now mirrors
 * both specs. They are an anchor, not a label: renaming them would make this
 * generator look for text the daemon's file does not contain, and the daemon
 * lives in a repository this one cannot edit — so between the rename here and
 * the matching edit there, every full-mode CI run would `fail()` with "has no
 * generated block", which reads as sabotage rather than as a rename in flight.
 */
const DAEMON_BEGIN = "// BEGIN GENERATED spec/limits.yaml — tools/gen-limits.mjs";
const DAEMON_END = "// END GENERATED spec/limits.yaml";

function daemonBlock() {
  // `dead_code` allowed per item: the block mirrors the WHOLE spec, and not
  // every shared constant has a daemon-side site to assert against yet
  // (`plugin_start_timeout_secs` does not). A generated file that emits
  // warnings gets deleted by the next person tidying up.
  const numbers = limits
    .map((l) => {
      const doc = l.doc.map((d) => (d ? `/// ${d}` : "///")).join("\n");
      return `${doc}\n#[allow(dead_code)]\npub const SPEC_${CONST(l.name)}: u64 = ${l.literal};`;
    })
    .join("\n\n");
  const keys = wires
    .map((w) => {
      const doc = w.doc.map((d) => (d ? `/// ${d}` : "///")).join("\n");
      return `${doc}\n#[allow(dead_code)]\npub const SPEC_${CONST(w.name)}: &str = ${quoted(w)};`;
    })
    .join("\n\n");
  return `${DAEMON_BEGIN}
// Regenerate from a checkout of AstraPlugins: \`node tools/gen-limits.mjs\`.
// Editing these values by hand does not change the spec — it only moves the
// disagreement to the next person who regenerates.
${numbers}

// ── ${WIRE_REL} ─────────────────────────────────────────────────────────────
//
// The daemon has no reason to keep a second spelling of a metadata key: unlike
// a limit, a key has no daemon-side semantics to name it after. Use these
// constants directly and the two sides cannot disagree at all. Where a local
// constant already exists, pin it with the helper below rather than deleting
// it in the same change:
//
//     const _: () = assert!(spec_str_eq(SESSION_TOKEN_HEADER, SPEC_SESSION_TOKEN_HEADER));

/// Const-context string equality, for pinning a daemon constant to its mirror.
#[allow(dead_code)]
pub const fn spec_str_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    let mut i = 0;
    while i < a.len() {
        if a[i] != b[i] {
            return false;
        }
        i += 1;
    }
    true
}

${keys}
${DAEMON_END}`;
}

const outputs = [
  { path: join(REPO_ROOT, "astra-plugin-sdk", "src", "limits.rs"), content: rustLimits() },
  { path: join(REPO_ROOT, "astra-plugin-sdk", "src", "wire.rs"), content: rustWire() },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-python", "astra_plugin_sdk", "limits.py"),
    content: pythonFile(LIMITS_REL, LIMITS_SUBJECT, limits, limitsSpec.sha256, (l) => l.literal),
  },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-python", "astra_plugin_sdk", "wire.py"),
    content: pythonFile(WIRE_REL, WIRE_SUBJECT, wires, wireSpec.sha256, quoted),
  },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-ts", "src", "generated", "limits.ts"),
    content: typescriptFile(LIMITS_REL, LIMITS_SUBJECT, limits, limitsSpec.sha256, (l) =>
      String(l.value)
    ),
  },
  {
    path: join(REPO_ROOT, "astra-plugin-sdk-ts", "src", "generated", "wire.ts"),
    content: typescriptFile(WIRE_REL, WIRE_SUBJECT, wires, wireSpec.sha256, quoted),
  },
];

// The daemon half. Optional by location, mandatory by content: if the file is
// there, its marked block must end up byte-identical to `daemonBlock()`.
const ASTRA_RS = process.env.ASTRA_RS_DIR
  ? resolve(process.env.ASTRA_RS_DIR)
  : resolve(REPO_ROOT, "..", "Astra", "astra-rs");
const DAEMON_FILE = join(ASTRA_RS, "astra-daemon", "src", "plugins", "voice_capability.rs");

let daemonNote = `No Astra checkout at ${DAEMON_FILE}; set $ASTRA_RS_DIR.`;
let daemonChecked = false;
if (existsSync(DAEMON_FILE)) {
  const src = readFileSync(DAEMON_FILE, "utf8");
  const begin = src.indexOf(DAEMON_BEGIN);
  const end = src.indexOf(DAEMON_END);
  if (begin === -1 || end === -1 || end < begin) {
    fail(
      `${DAEMON_FILE} has no generated block.\n` +
        `  Expected a region delimited by:\n    ${DAEMON_BEGIN}\n    ${DAEMON_END}\n` +
        `  Someone deleted it, and with it the only build-time check that the daemon's ` +
        `constants still agree with the spec. Restore the markers.`
    );
  }
  const updated = src.slice(0, begin) + daemonBlock() + src.slice(end + DAEMON_END.length);
  outputs.push({ path: DAEMON_FILE, content: updated, whole: false });
  daemonNote = DAEMON_FILE;
  daemonChecked = true;
}

let drifted = 0;
for (const out of outputs) {
  const existing = existsSync(out.path) ? readFileSync(out.path, "utf8") : null;
  if (existing === out.content) continue;
  drifted += 1;
  const label = out.path.startsWith(REPO_ROOT) ? relative(REPO_ROOT, out.path) : out.path;
  if (CHECK_ONLY) {
    console.error(`gen-limits: DRIFT — ${label} is not what the spec generates`);
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
  // Say what was NOT compared. `--check` is the mode CI runs and the mode
  // AGENTS.md tells a contributor to run, and until now it answered "all
  // generated files current" whether or not the daemon block had been looked
  // at — the daemon block being the entire reason this generator exists. The
  // note existed; it was printed only on the write path, which nobody runs in
  // CI. An instruction that says "read the output" is worth nothing when the
  // output omits the half that was skipped, and it is worse than silence,
  // because someone who runs it comes away believing they checked.
  //
  // Exit stays 0 without a checkout on purpose: Astra is private, so a fork
  // cannot have one, and failing here would make the documented command
  // impossible to satisfy rather than honest about its reach.
  //
  // The wire-key count comes from this branch and is kept on both arms: it is
  // part of "what this run did compare", so dropping it from the honest arm
  // would make the incomplete run look like it inspected less than it did.
  if (daemonChecked) {
    console.log(
      `gen-limits: OK — ${limits.length} limits, ${wires.length} wire keys, all generated files current`
    );
  } else {
    console.log(
      `gen-limits: OK — ${limits.length} limits, ${wires.length} wire keys, the SDK files are current.\n` +
        `gen-limits: NOT CHECKED — the daemon's block. ${daemonNote}\n` +
        `gen-limits:              That is the cross-repo half: the STT channel capacity was ` +
        `500 in the daemon and 32 in the SDK, and this generator exists so the two cannot ` +
        `disagree again. This run did not compare them.`
    );
  }
} else {
  console.log(
    `gen-limits: ${LIMITS_REL} (sha256 ${limitsSpec.sha256.slice(0, 12)}…) -> ${limits.length} limits; ` +
      `${WIRE_REL} (sha256 ${wireSpec.sha256.slice(0, 12)}…) -> ${wires.length} keys; ` +
      `daemon block: ${daemonNote}`
  );
}
