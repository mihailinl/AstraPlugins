// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Reading a `.astra` file into the commands a plugin offers with
 * `ctx.proposeCommand()`.
 *
 * A `.astra` file is what Astra's Commands page exports (and what dragging a
 * command out of the list writes) — `{format: "astra-commands", version,
 * commands: [...]}`, or a group's `{format: "astra-group", version, group:
 * {name}, commands: [...]}`. `proposeCommand` takes ONE command, so the usual
 * path is: build the command in Astra, export it, ship the file with the
 * plugin, and offer each command in it.
 *
 * The same helper is in all three SDKs, held to one set of vectors
 * (`testdata/astra-file/vectors.json`).
 */

/**
 * The members removed from every command: the file's own `source_id`, and the
 * LOCAL members of a portable command (Astra's
 * `astra-core/src/command/portable_schema.rs::LOCAL_FIELDS`) — this
 * installation's identity, switch, folder and provenance for it. The daemon
 * drops them from an offer anyway; removing them here keeps the offer to what
 * the person is asked about.
 */
export const ASTRA_FILE_LOCAL_FIELDS: readonly string[] = [
  "source_id",
  "id",
  "created_at",
  "updated_at",
  "group_id",
  "enabled",
  "marketplace_source",
  "catalogue_source",
  "plugin_source",
];

/** `1e400`: JSON.parse reads it as `Infinity`. */
class OutOfRange extends Error {}

/** An integer a double cannot hold exactly; JSON.parse would round it. */
class Inexact extends Error {
  constructor(readonly value: number) {
    super("inexact");
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * **The commands in a `.astra` file**, each ready to offer with
 * `ctx.proposeCommand()`.
 *
 * Reads the two formats Astra writes — `"astra-commands"` and `"astra-group"`
 * — and nothing else: text that is not JSON, a top level that is not an
 * object, another `format` (a single command on its own, or the pre-group
 * `"astra-command"`), a `version` that is not a number, a group file whose
 * `group` is not an object, `commands` that is not an array, or a command that
 * is not an object throws an `Error` that says which. Each command is returned
 * whole (a new object) except for its top-level local members — `source_id`,
 * `id`, `created_at`, `updated_at`, `group_id`, `enabled`,
 * `marketplace_source`, `catalogue_source` and `plugin_source`; nothing else
 * about it is checked here — that is the daemon's reader's job, and its
 * refusal names what is wrong.
 *
 * A member given twice collapses to the last one, as in the Rust and Python
 * helpers: the daemon's strict reader would refuse the duplicate, but this
 * helper parses and re-serialises, so what is offered is the last value alone.
 * A top-level `"__proto__"` member stays an ordinary key. A number is never
 * rounded: one out of range (`1e400`) is not JSON here, and an integer past
 * `Number.MAX_SAFE_INTEGER` (2^53 + 1, `1e300`) is refused, because a
 * JavaScript number cannot hold it exactly — the Rust and Python helpers read
 * those exactly instead.
 *
 * ```ts
 * import { readFileSync } from "node:fs";
 * const [morning] = commandsFromAstraFile(readFileSync("morning.astra", "utf8"));
 * const offered = await ctx.proposeCommand("morning-briefing", morning, "Reads you the news");
 * ```
 */
export function commandsFromAstraFile(text: string): Record<string, unknown>[] {
  let doc: unknown;
  try {
    doc = JSON.parse(text, (_key, v: unknown) => {
      if (typeof v === "number") {
        if (!Number.isFinite(v)) throw new OutOfRange(`a number is out of range`);
        if (Number.isInteger(v) && !Number.isSafeInteger(v)) throw new Inexact(v);
      }
      return v;
    });
  } catch (e) {
    if (e instanceof Inexact) {
      throw new Error(
        `not a .astra file: a number near ${e.value} is an integer a JavaScript number cannot hold exactly`
      );
    }
    throw new Error(`not a .astra file: it is not JSON (${(e as Error).message})`);
  }
  if (!isObject(doc)) throw new Error("not a .astra file: it is not a JSON object");
  const format = doc.format;
  if (format !== "astra-commands" && format !== "astra-group") {
    const found = "format" in doc ? JSON.stringify(format) : "missing";
    throw new Error(
      `not a .astra file: \`format\` must be "astra-commands" or "astra-group", not ${found}`
    );
  }
  if (typeof doc.version !== "number") {
    throw new Error("not a .astra file: `version` must be a number");
  }
  if (format === "astra-group" && !isObject(doc.group)) {
    throw new Error("not a .astra group file: `group` must be an object");
  }
  const commands = doc.commands;
  if (!Array.isArray(commands)) {
    throw new Error("not a .astra file: `commands` must be an array");
  }
  return commands.map((command: unknown, i: number) => {
    if (!isObject(command)) {
      throw new Error(`not a .astra file: commands[${i}] is not a JSON object`);
    }
    // `Object.fromEntries` defines each member as an own property, so a
    // `"__proto__"` member stays data; `out[k] = v` would set the prototype.
    return Object.fromEntries(
      Object.entries(command).filter(([k]) => !ASTRA_FILE_LOCAL_FIELDS.includes(k))
    );
  });
}
