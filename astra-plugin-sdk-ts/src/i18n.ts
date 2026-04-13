/**
 * Simple i18n helper for plugin localization.
 *
 * Plugins ship `locales/en.json`, `locales/ru.json`, etc. alongside `plugin.toml`.
 * Each file is a flat key-value JSON map:
 *
 * ```json
 * {
 *     "config.token.title": "API Token",
 *     "msg.hello": "Hello!"
 * }
 * ```
 *
 * @example
 * ```ts
 * import { I18n } from "astra-plugin-sdk";
 *
 * const i18n = new I18n("locales");
 * i18n.setLanguage("ru");
 * const text = i18n.t("msg.hello"); // Russian or English fallback
 * ```
 */

import * as fs from "fs";
import * as path from "path";

export class I18n {
  private locales: Map<string, Map<string, string>> = new Map();
  private _language = "en";

  constructor(localesDir: string) {
    if (fs.existsSync(localesDir)) {
      for (const file of fs.readdirSync(localesDir)) {
        if (file.endsWith(".json")) {
          const lang = path.basename(file, ".json");
          try {
            const data = JSON.parse(
              fs.readFileSync(path.join(localesDir, file), "utf-8")
            );
            if (typeof data === "object" && data !== null) {
              this.locales.set(lang, new Map(Object.entries(data)));
            }
          } catch {
            /* skip invalid files */
          }
        }
      }
    }
  }

  /** Set the active language. */
  setLanguage(lang: string): void {
    this._language = lang;
  }

  /** Get the current active language. */
  get language(): string {
    return this._language;
  }

  /** Get a translated string. Falls back to English, then to the key itself. */
  t(key: string): string {
    return (
      this.locales.get(this._language)?.get(key) ??
      this.locales.get("en")?.get(key) ??
      key
    );
  }

  /** Get a translated string with format arguments replaced.
   *  Placeholders use `{0}`, `{1}`, etc. */
  tf(key: string, ...args: string[]): string {
    let result = this.t(key);
    for (let i = 0; i < args.length; i++) {
      result = result.replace(`{${i}}`, args[i]);
    }
    return result;
  }

  /** Check if any locale files were loaded. */
  get hasLocales(): boolean {
    return this.locales.size > 0;
  }

  /** Get available language codes. */
  get availableLanguages(): string[] {
    return Array.from(this.locales.keys());
  }
}
