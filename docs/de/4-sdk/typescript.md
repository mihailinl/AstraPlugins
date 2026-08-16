> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/4-sdk/typescript.md) maßgeblich.

# Das TypeScript-SDK

`astra-plugin-sdk` **0.5.0 — die Version, die diese Seite beschreibt**, und
die, die npm ausliefert. `npm install astra-plugin-sdk` (oder `bun add`)
löst sie auf; das ist auch, was `astra-plugin new --lang typescript` pinnt.
Nimm 0.5.0 oder neuer: 0.4.0 sendet kein Session-Token, und der Daemon
lehnt jeden Host-Aufruf ab, den es tätigt.

Der Paketname hat keinen Scope — ein früherer gescopter Name taucht in
alten Projekten auf und wurde nie registriert, sodass `npm i` davon
schlichtweg fehlschlägt.

<!-- doctest: illustrative reason="a package.json fragment; the scaffold containing it is what the ts-plugin blocks below type-check against" -->
```json
{
  "dependencies": {
    "astra-plugin-sdk": "^0.5.0",
    "@grpc/grpc-js": "^1.10.0",
    "@grpc/proto-loader": "^0.7.0"
  }
}
```

Ein TypeScript-Plugin wird als **`noarch`** verpackt: ein Bundle für jede
Plattform. Sein `[entry]` ist `command = "node"`,
`args = ["dist/index.js"]`, `runtimes = ["node"]`, und `astra-plugin build`
bündelt `src/index.ts` zu einer einzigen in sich geschlossenen
CommonJS-Datei — eine `.astraplugin` liefert kein `node_modules` aus.

## Die Form eines Plugins

Das Plugin ist ein **Wert**, aus dem Modul exportiert, und es startet nur,
wenn diese Datei der Prozess-Einstiegspunkt ist. Das ist es, was es einem
Test erlaubt, es in-process ohne Daemon und ohne Socket zu treiben.

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool, BadArguments } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    start_timer: tool({
      description:
        "Start a countdown. Use it when the user asks to be reminded in N minutes.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs, so `minutes` really is a number.
      input: s.object({
        minutes: s.number({ description: "How many minutes to wait" }),
        label: s.string({ description: "What the timer is for" }).optional(),
      }),
      run: async ({ minutes, label }, ctx) => {
        // Errors take an options object, not a bare string: the extra fields
        // are what the UI deep-links and retries on.
        if (minutes <= 0) throw new BadArguments({ message: "give me at least a minute" });
        // `ctx.info` / `ctx.fireTrigger` and not `ctx.host.*`: `ctx.host` is
        // `Host | null`, and these wrappers turn "no host" into a rejected
        // promise instead of a synchronous throw your `await` cannot catch.
        await ctx.info(`timer for ${minutes}m`);
        await ctx.fireTrigger("timer_started", { minutes, label });
        return `timer set for ${minutes} minutes`;
      },
    }),
  },

  triggers: {
    timer_started: { label: "Timer started" },
  },

  onConfigChanged: async (config, ctx) => {
    await ctx.info(`config has ${Object.keys(config).length} key(s)`);
  },
});

if (require.main === module) app.run();
```

## `plugin({...})`

Ein Objekt, ein Schlüssel pro Ding, das dein Plugin tut:

| Schlüssel | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — Schritte im Befehlseditor |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | Die Provider-Definitionen |
| `ui` | Contributions, und die Methoden, die dein iframe zurückrufen darf |
| `events` | Welche Daemon-Events du willst, und die Handler |
| `client` | `{ onReady(daemon, ctx) }` — nur für `client`-Plugins, und **das `daemon`, das übergeben wird, funktioniert noch nicht**: siehe unten |
| `configSchema` | Ein `s.object({...})` für deine Settings |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Lebenszyklus |

`plugin()` gibt `{ run(), instance, definition }` zurück: `run()` ist die
letzte Zeile deines Einstiegspunkts, `instance` ist das, was der
Test-Harness treibt, und `definition` ist für Tooling da, das deine
Schemas lesen will.

## Schemas

`s` baut JSON Schema und den TypeScript-Typ gleichzeitig:

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

const Query = s.object({
  text: s.string({ description: "What to search for" }),
  limit: s.number({ description: "How many results", minimum: 1, maximum: 50 }).optional(),
  fuzzy: s.boolean({ description: "Allow near matches" }).optional(),
  tags: s.array(s.string(), { description: "Restrict to these tags" }).optional(),
  mode: s.enum(["fast", "thorough"], { description: "How hard to look" }).optional(),
});

export const app = plugin({
  tools: {
    search: tool({
      description: "Search the user's notes.",
      input: Query,
      // `args` is typed from `Query`: `args.text` is a string, `args.limit` is
      // `number | undefined`, and a typo in either is a compile error.
      run: (args) => `searching for ${args.text} (limit ${args.limit ?? 10})`,
    }),
  },
});

if (require.main === module) app.run();
```

## Astra ansprechen

Benutze die Methoden auf `ctx`. Jede ist `async`, sodass ein Plugin, das
noch nicht registriert ist, ein **abgelehntes Promise** bekommt statt eines
synchronen Throws aus einer Funktion, die eines zurückgibt — genau die
Form, die `try { await ctx.fireTrigger(...) } catch {}` nicht auffängt.

| `ctx.…` | Permission |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | keine |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

Die Wrapper nehmen ein **Payload-Objekt** und stringifizieren es für dich;
`ctx.host` ist der rohe Client darunter, typisiert als `Host | null`,
dessen `fireTrigger` / `pushToUi` einen JSON-**String** nehmen. `ctx.host`
ist auch, wo `getConfig()`, `getDaemonInfo()`, `subscribeEvents()` und
`getPluginId()` leben.

`setVariable`, `pushToUi` und der UI-Aufrufpfad existieren alle und sind
gebunden; ältere Dokumentation sagte etwas anderes, weil sie spät kamen.

## Wohin die Ausgabe eines ausgelösten Triggers geht

Ein Trigger, den Sie während der Bearbeitung eines Aufrufs von Astra auslösen,
wird diesem Aufruf zugeordnet. Alles, was er bewirkt, landet damit in genau dem
Gespräch, das die Person gerade vor sich hat. **Sie schreiben dafür nichts**,
und es gilt über `await`, `setTimeout` und Promise-Ketten hinweg — auch über
`ctx.fireTrigger`, `ctx.host.fireTrigger` und `this.fireTrigger` auf einer
`Plugin`-Unterklasse, die alle denselben Transport erreichen.

<!-- doctest: illustrative reason="one property of a tool object, not a module: it needs the enclosing `plugin({ tools: { … } })` the ts-plugin blocks above type-check. The behaviour is executed by tools/causality.test.mjs, against a real gRPC handshake." -->
```ts
run: async ({ count }, ctx) => {
  const results = roll(count);
  await ctx.fireTrigger("on_roll_value", { value: results[0] });  // attributed
  return `rolled ${results}`;
},
```

Ein Trigger, der von irgendwo sonst ausgelöst wird, ist ein **Wurzelereignis**:
Der Daemon legt ihn im eigenen Automatisierungsstrang dieses Plugins ab, statt
ein Gespräch zu erraten. Das gilt für einen außerhalb eines Handlers gestarteten
Timer, für einen `child_process`, für einen `worker_threads`-Worker und für
einen von einem nativen Addon geplanten Rückruf. Das ist die richtige Antwort,
keine abgeschwächte — das falsche Gespräch ist schlimmer als gar keines.

`MockDaemon.firedTriggers()` meldet `causedBy` — `undefined` für ein
Wurzelereignis —, sodass Ihre eigenen Tests die beiden unterscheiden können, und
`wire.callTool(name, args, { causedBy })` stellt einen Aufruf so aus, wie der
Daemon es tun wird.

## Fehler

`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `TimeoutError`, `InternalError` — wirf einen davon, und das
SDK bildet ihn auf denselben Wire-Code ab, den die beiden anderen SDKs
erzeugen. `HookUnimplemented` ist der Weg, um „dieser Hook fehlt" zu
sagen, was `UNIMPLEMENTED` auf der Leitung bedeutet.

Taxonomie und Wire-Strings: [`reference/errors.md`](../reference/errors.md).

## Testen

<!-- doctest: illustrative reason="a test file, not a plugin: it imports ../dist/plugin.cjs, which only exists after that project's own pretest step bundles it. This is the file `astra-plugin new --lang typescript` writes, and CI runs it there." -->
```javascript
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

// `pretest` bundles src/index.ts with the SDK left EXTERNAL, so the plugin
// under test and the harness testing it share one copy of the SDK.
const { app } = require("../dist/plugin.cjs");
const { Harness } = require("astra-plugin-sdk/testing");

test("start_timer answers, and its schema matches its handler", async () => {
  const h = await Harness.create(app).start();

  assert.deepEqual(await h.toolNames(), ["start_timer"]);
  await h.assertSchemaAccepts("start_timer", { minutes: 5 });
  await h.assertSchemaRejects("start_timer", { minutes: "five" });

  const result = await h.callTool("start_timer", { minutes: 5 });
  assert.equal(result.success, true);
  assert.equal(result.result, "timer set for 5 minutes");
  assert.equal(h.host.firedTriggers()[0].triggerType, "timer_started");

  // An argument the schema forbids never reaches the handler: it comes back as
  // an in-band BAD_ARGUMENTS the assistant can read and correct.
  const bad = await h.callTool("start_timer", {});
  assert.equal(bad.success, false);
  assert.match(bad.error, /BAD_ARGUMENTS/);
});

test("no config the daemon can deliver crashes this plugin", async () => {
  // The daemon delivers config it did not author: the user's typing, and an
  // older version of this plugin's own schema. None of it may throw.
  const h = await Harness.create(app).start();
  assert.deepEqual(await h.fuzzConfig(), []);
});
```

`Harness` treibt den echten Capability-Service im Prozess:
`listTools`, `callTool`, `schema`, `assertSchemaAccepts`,
`assertSchemaRejects`, `executeAction`, `callFromUi`, `synthesize`,
`sttStream`, `aiComplete`, `event`, `conversationEvent`, `configChanged`,
`healthCheck`, `fuzzConfig`. `RecordingHost` zeichnet auf, was dein Plugin
Astra mitgeteilt hat. `MockDaemon` und `WirePlugin` sind das
Ebene-2-Paar: ein echter Prozess über gRPC.

## Was dieses SDK noch nicht kann

- **Das an `client.onReady` übergebene `daemon` ist funktionsunfähig.**
  Der Daemon registriert jedes Plugin als `ClientType::PluginClient`, und
  sein Auth-Interceptor lehnt diese Identität auf jedem Pfad außerhalb
  von `/astra.PluginHostService/` mit
  `permission_denied("plugin session tokens are scoped to
  PluginHostService")` ab. `client: true` ändert daran nichts.
  `host.sendChatMessage` ist der einzige funktionierende Weg, einen
  AI-Turn auszulösen. Die Daemon-seitige Hälfte ist ungebaut, nicht
  kaputt.
- **`UiPanel` ist ein veralteter Alias** für `UiContribution` — veraltet
  seit 0.5.0, entfernbar ab 0.7.0.
- **`aiGetModels` ist veraltet** und wird von niemandem aufgerufen; es
  gibt keinen Ersatz.
- **`ttsSynthesizeStream` ist gebunden und ungeroutet** — es gibt keine
  Aufrufstelle im Daemon.
- **Das Proto wird hier nicht von Hand gepflegt.** Zwei Proto-Strings
  lebten einst inline in diesem SDK, wurden in ein Temp-Verzeichnis
  geschrieben und von dort geladen, und einer davon beschrieb einen
  Dienst, der wegmigriert worden war — sodass jedes
  TypeScript-Client-Plugin bei der Registrierung warf. Es gibt jetzt eine
  einzige `.proto`, gevendort und geprüft; führe keine Kopie wieder ein.

## Siehe auch

[Hook-Tabelle für TypeScript](../hooks/typescript.md) ·
[Parität](../reference/parity.md) · [Fehler](../reference/errors.md) ·
[Versionierung](../versioning.md)
</content>
