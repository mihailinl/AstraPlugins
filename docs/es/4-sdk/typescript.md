> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/4-sdk/typescript.md) es la referencia autorizada.

# El SDK de TypeScript

`astra-plugin-sdk` **0.5.0 — la versión que describe esta página**, y la que
sirve npm. `npm install astra-plugin-sdk` (o `bun add`) la resuelve; eso es
también lo que fija `astra-plugin new --lang typescript`. Toma 0.5.0 o más
nuevo: 0.4.0 no envía token de sesión y el daemon rechaza cada llamada al
host que hace.

El nombre del paquete no tiene scope — un nombre con scope anterior aparece
en proyectos antiguos y nunca se registró, así que `npm i` de él falla de
plano.

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

Un plugin de TypeScript se empaqueta como **`noarch`**: un paquete para
cada plataforma. Su `[entry]` es `command = "node"`,
`args = ["dist/index.js"]`, `runtimes = ["node"]`, y `astra-plugin build`
empaqueta `src/index.ts` en un único archivo CommonJS autocontenido — un
`.astraplugin` no lleva `node_modules`.

## La forma de un plugin

El plugin es un **valor**, exportado desde el módulo, y solo arranca
cuando este archivo es el punto de entrada del proceso. Eso es lo que
permite que una prueba lo impulse en proceso, sin daemon y sin socket.

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

Un objeto, una clave por cada cosa que hace tu plugin:

| Clave | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — pasos en el editor de comandos |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | Las definiciones de proveedor |
| `ui` | Contribuciones, y los métodos que tu iframe puede llamar de vuelta |
| `events` | Qué eventos del daemon quieres, y los handlers |
| `client` | `{ onReady(daemon, ctx) }` — solo para plugins `client`, y **el `daemon` que se entrega todavía no funciona**: ver abajo |
| `configSchema` | Un `s.object({...})` para tus ajustes |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Ciclo de vida |

`plugin()` devuelve `{ run(), instance, definition }`: `run()` es la
última línea de tu punto de entrada, `instance` es lo que impulsa el
harness de pruebas, y `definition` está ahí para herramientas que quieran
leer tus schemas.

## Schemas

`s` construye el JSON Schema y el tipo de TypeScript a la vez:

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

## Llamar a Astra

Usa los métodos de `ctx`. Todos son `async`, así que un plugin que aún no
está registrado obtiene una **promesa rechazada** en lugar de un throw
síncrono desde una función que devuelve una — que es precisamente la forma
que `try { await ctx.fireTrigger(...) } catch {}` no captura.

| `ctx.…` | Permiso |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | ninguno |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

Los wrappers toman un **objeto de payload** y lo convierten a string por
ti; `ctx.host` es el cliente crudo debajo, tipado `Host | null`, cuyos
`fireTrigger` / `pushToUi` toman un **string** JSON. `ctx.host` es también
donde viven `getConfig()`, `getDaemonInfo()`, `subscribeEvents()` y
`getPluginId()`.

`setVariable`, `pushToUi` y la ruta de llamada de UI existen y están
vinculadas; documentación anterior decía lo contrario porque llegaron
tarde.

## Errores

`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `TimeoutError`, `InternalError` — lanza uno y el SDK lo
mapea al mismo código de cable que producen los otros dos SDK.
`HookUnimplemented` es la forma de decir "este hook no existe", que es lo
que `UNIMPLEMENTED` significa en el cable.

Taxonomía y strings de cable: [`reference/errors.md`](../reference/errors.md).

## Pruebas

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

`Harness` impulsa el servicio de capabilities real en el proceso:
`listTools`, `callTool`, `schema`, `assertSchemaAccepts`,
`assertSchemaRejects`, `executeAction`, `callFromUi`, `synthesize`,
`sttStream`, `aiComplete`, `event`, `conversationEvent`, `configChanged`,
`healthCheck`, `fuzzConfig`. `RecordingHost` graba lo que tu plugin le dijo
a Astra. `MockDaemon` y `WirePlugin` son el par de nivel 2: un proceso
real sobre gRPC.

## Lo que este SDK todavía no puede hacer

- **El `daemon` que se entrega a `client.onReady` no es funcional.** El
  daemon registra cada plugin como `ClientType::PluginClient`, y su
  interceptor de autenticación rechaza esa identidad en cualquier ruta
  fuera de `/astra.PluginHostService/` con
  `permission_denied("plugin session tokens are scoped to
  PluginHostService")`. `client: true` no lo cambia. `host.sendChatMessage`
  es la única forma que funciona de impulsar un turno de IA. La mitad del
  lado del daemon no está construida, no está rota.
- **`UiPanel` es un alias obsoleto** de `UiContribution` — obsoleto desde
  0.5.0, eliminable a partir de 0.7.0.
- **`aiGetModels` está obsoleto** y nadie lo llama; no hay reemplazo.
- **`ttsSynthesizeStream` está vinculado pero no enrutado** — no existe
  punto de llamada en el daemon.
- **El proto no se mantiene aquí a mano.** Dos strings de proto vivían en
  su día en línea dentro de este SDK, se escribían en un directorio
  temporal y se cargaban desde ahí, y uno de ellos describía un servicio
  que había sido migrado — así que cada plugin cliente de TypeScript
  lanzaba una excepción durante el registro. Ahora hay un único `.proto`,
  vendorizado y verificado; no reintroduzcas una copia.

## Ver también

[Tabla de hooks para TypeScript](../hooks/typescript.md) ·
[paridad](../reference/parity.md) · [errores](../reference/errors.md) ·
[versionado](../versioning.md)
</content>
