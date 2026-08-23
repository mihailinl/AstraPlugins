// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Plugin localization: `locales/<code>.json`, and the two planes it serves.
 *
 * A plugin ships one flat JSON file per language beside `plugin.toml`:
 *
 * ```json
 * {
 *     "config.token.title": "API Token",
 *     "msg.done.one": "Handled {n} item",
 *     "msg.done.other": "Handled {n} items"
 * }
 * ```
 *
 * ## The two planes, which is the thing to get right
 *
 * **Runtime plane** — anything *this process* produces: chat text,
 * notifications, anything with a count in it. Resolve it here, at the moment
 * you produce it:
 *
 * ```ts
 * ctx.i18n.tn("msg.done", n, { n: String(n) });
 * ```
 *
 * **Declared plane** — anything the *daemon* renders: config-field titles,
 * action and trigger labels, `[ui]` contribution labels. Emit a marker with
 * {@link key} and let the daemon resolve it per request, from the same
 * `locales/` directory, in whatever language the user has set *now*:
 *
 * ```ts
 * key("action.roll.label");     // -> "$action.roll.label"
 * ```
 *
 * Never `t()` on the declared plane. The daemon caches a definition unresolved
 * and resolves it per request, so a label you resolved once is frozen in
 * whatever language won the race at startup.
 *
 * ## What this loader will and will not accept
 *
 * The daemon deserialises a locale file as `HashMap<String, String>` and drops
 * the **whole file** on any non-string value, silently, at install time. This
 * loader does the same, on purpose. Until 0.7 it accepted any object, so a
 * TypeScript author who wrote `{"config": {"token": {"title": "…"}}}` — the
 * shape every other JSON config invites — got a plugin whose own tests passed
 * while the daemon dropped the file and every `$config.token.title` rendered
 * literally on screen.
 *
 * `tf` also replaced only the FIRST occurrence of each placeholder until 0.7,
 * because `String.replace` with a string needle does. Russian and Ukrainian
 * repeat a noun in two cases routinely, so the second one rendered as `{0}`.
 *
 * Everything the loader could not use is reachable through
 * {@link I18n.loadErrors}, which `astra-plugin test` prints. Nothing here
 * throws: a plugin must start.
 *
 * ## Packaging
 *
 * `astra-plugin build` bundles TypeScript to one CJS file and packs `dist/`,
 * so `import en from "./locales/en.json"` gives you working runtime strings —
 * esbuild inlines them — and a settings page full of raw keys, because the
 * daemon reads `locales/` from disk. Keep one copy, on disk, and let this
 * class read it.
 *
 * The declared semantics are `spec/i18n.yaml`, the shared cases are
 * `testdata/i18n/vectors.json`, and all three SDKs are held to them by one
 * test each. This is coupling C17.
 */

import * as fs from "fs";
import * as path from "path";

import { category, isDeclared } from "./generated/plural.js";

/**
 * Environment variable naming the plugin's own install directory.
 *
 * The daemon does not set it yet — it is Ask 6 to the Astra half — which is
 * why {@link I18n.discover} falls through to `./locales`. That works today
 * only because the daemon spawns a plugin with its working directory set to
 * the install directory, a load-bearing fact stated in no repository and one
 * `[entry] cwd` from stopping being true.
 */
export const PLUGIN_DIR_ENV = "ASTRA_PLUGIN_DIR";

/**
 * Mark a string as a **declared-plane** locale key for the daemon to resolve.
 *
 * Returns `"$" + k`. A key that matches nothing is shown to the user exactly
 * as it stands, so every key passed here must exist in `locales/en.json` —
 * `astra-plugin check` is what tells you when one does not.
 */
export function key(k: string): string {
  return "$" + k;
}

function kindOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "an array";
  switch (typeof value) {
    case "boolean":
      return "a boolean";
    case "number":
      return "a number";
    case "string":
      return "a string";
    default:
      return "a nested object";
  }
}

/** A locale file's text as a flat string map. Throws with a usable sentence. */
function parseLocale(text: string): Map<string, string> {
  const data: unknown = JSON.parse(text);
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error(
      `the top level is ${kindOf(data)}, not an object. A locale file is a flat map ` +
        `of key to string.`
    );
  }
  const out = new Map<string, string>();
  for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
    if (typeof v !== "string") {
      throw new Error(
        `the value of \`${k}\` is ${kindOf(v)}, not a string. The daemon deserialises a ` +
          `locale file as a flat map of string to string and drops the WHOLE file on the ` +
          `first value that is not one — so on a user's machine every key in this file ` +
          `would render as itself while this plugin's own tests passed. Flatten it: ` +
          `"${k}.title": "…".`
      );
    }
    out.set(k, v);
  }
  return out;
}

function replaceAll(text: string, needle: string, value: string): string {
  return text.split(needle).join(value);
}

function substitute(text: string, args: Record<string, string>): string {
  for (const [name, value] of Object.entries(args)) {
    text = replaceAll(text, "{" + name + "}", value);
  }
  return text;
}

export class I18n {
  private locales: Map<string, Map<string, string>> = new Map();
  private _language = "en";
  private _errors: string[] = [];
  private _source: string | null = null;

  /**
   * Load every `*.json` in `localesDir` as a locale named after its stem.
   *
   * Pass `null` for an empty instance with nothing to report.
   */
  constructor(localesDir: string | null) {
    if (localesDir === null) return;
    this._source = localesDir;

    let entries: string[];
    try {
      entries = fs.readdirSync(localesDir).sort();
    } catch (e) {
      this._errors.push(
        `${localesDir}: not readable (${(e as Error).message}). No locale file was ` +
          `loaded, so every t() call returns its key.`
      );
      return;
    }

    for (const file of entries) {
      if (!file.endsWith(".json")) continue;
      const lang = path.basename(file, ".json");
      const full = path.join(localesDir, file);
      let table: Map<string, string>;
      try {
        table = parseLocale(fs.readFileSync(full, "utf-8"));
      } catch (e) {
        this._errors.push(`${full}: ${(e as Error).message}`);
        continue;
      }
      if (!isDeclared(lang)) {
        // Not a refusal: the daemon loads this file too, keys it by this stem,
        // and never selects it. Saying so is the only signal the author will
        // ever get — otherwise the file is packed, digested, signed, shipped,
        // and read by nothing.
        this._errors.push(
          `${full}: \`${lang}\` is not a language Astra can be set to ` +
            `(spec/locales.yaml). The file loaded, and nothing will ever select it.`
        );
      }
      this.locales.set(lang, table);
    }
  }

  /**
   * Load the plugin's `locales/` without depending on the process CWD.
   *
   * `$ASTRA_PLUGIN_DIR/locales` when that variable names a directory, else
   * `./locales`. Two candidates, both owned by the plugin, and no third: a
   * TypeScript plugin runs as `node dist/index.js`, so an executable-relative
   * chain would stat `/usr/bin/locales` — a directory the plugin does not own
   * and has no business reading.
   */
  static discover(): I18n {
    const base = process.env[PLUGIN_DIR_ENV];
    if (base) {
      const candidate = path.join(base, "locales");
      try {
        if (fs.statSync(candidate).isDirectory()) return new I18n(candidate);
      } catch {
        /* fall through to ./locales */
      }
    }
    return new I18n("locales");
  }

  /** An I18n with no locale files loaded and nothing to report. */
  static empty(): I18n {
    return new I18n(null);
  }

  /**
   * Every file this loader could not use, and why.
   *
   * Never fatal. `astra-plugin test` prints these, so a misnamed or malformed
   * locale file is a line an author reads before they ship rather than a
   * settings page that is quietly English.
   */
  get loadErrors(): string[] {
    return [...this._errors];
  }

  /** The directory this instance read, or `null` for {@link I18n.empty}. */
  get sourceDir(): string | null {
    return this._source;
  }

  /** Set the active language. The SDK calls this for you; see `ctx.i18n`. */
  setLanguage(lang: string): void {
    this._language = lang;
  }

  /** Get the current active language. */
  get language(): string {
    return this._language;
  }

  /**
   * Active language, then `en`, PER KEY — not per file. `""` is a translation
   * and wins; `undefined` means no locale carries it.
   */
  private lookup(k: string): string | undefined {
    return this.locales.get(this._language)?.get(k) ?? this.locales.get("en")?.get(k);
  }

  /** Get a translated string. Falls back to English, then to the key itself. */
  t(k: string): string {
    return this.lookup(k) ?? k;
  }

  /** Is this key translated in the active language or in English? */
  has(k: string): boolean {
    return this.lookup(k) !== undefined;
  }

  /**
   * Get a translated string with positional arguments substituted.
   *
   * Placeholders are `{0}`, `{1}`, … and **every** occurrence is replaced.
   */
  tf(k: string, ...args: string[]): string {
    let result = this.t(k);
    for (let i = 0; i < args.length; i++) {
      result = replaceAll(result, `{${i}}`, args[i]);
    }
    return result;
  }

  /**
   * Get a translated string with **named** arguments substituted.
   *
   * Placeholders are `{name}`. A name with no argument is left exactly as it
   * stands — a half-formatted sentence is easier to see than a blank.
   */
  ta(k: string, args: Record<string, string>): string {
    return substitute(this.t(k), args);
  }

  /**
   * Get the plural form of `k` for `n`, with named arguments substituted.
   *
   * Resolves `<k>.<category>`, where the category comes from the active
   * language's CLDR cardinal rules (`spec/i18n.yaml`, generated into
   * `./generated/plural.js`), then falls back to `<k>.other`, then `<k>`, then
   * the key text.
   *
   * `{n}` is **not** substituted for you. Pass it: a count that formats itself
   * is a count the author cannot localise.
   */
  tn(k: string, n: number, args: Record<string, string> = {}): string {
    const cat = category(this._language, n);
    for (const candidate of [`${k}.${cat}`, `${k}.other`, k]) {
      const value = this.lookup(candidate);
      if (value !== undefined) return substitute(value, args);
    }
    return substitute(k, args);
  }

  /**
   * How many distinct keys begin with `prefix`, across the UNION of every
   * loaded locale.
   *
   * Union, not the active language: a locale the author has not finished
   * translating must not change a count the plugin's own logic depends on.
   */
  countPrefixed(prefix: string): number {
    const seen = new Set<string>();
    for (const table of this.locales.values()) {
      for (const k of table.keys()) {
        if (k.startsWith(prefix)) seen.add(k);
      }
    }
    return seen.size;
  }

  /** Check if any locale files were loaded. */
  get hasLocales(): boolean {
    return this.locales.size > 0;
  }

  /** Get available language codes, sorted. */
  get availableLanguages(): string[] {
    return [...this.locales.keys()].sort();
  }
}
