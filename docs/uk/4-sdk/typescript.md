# TypeScript SDK

> Переклад. Джерело істини — [docs/en](../../en/4-sdk/typescript.md); за розбіжності відповідає англійська версія.

`astra-plugin-sdk` **0.5.0 — версія, яку описує ця сторінка**, і та, що
віддає npm. `npm install astra-plugin-sdk` (або `bun add`) її розв'язує; це
ж закріплює `astra-plugin new --lang typescript`. Беріть 0.5.0 або новіший:
0.4.0 не надсилає токен сесії, і демон відхиляє кожен виклик хоста, який
вона робить.

В імені пакета немає області видимості (scope) — раніше ім'я зі scope
трапляється у старих проєктах і ніколи не було зареєстроване, тож `npm i`
цього імені одразу провалюється.

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

TypeScript-плагін пакується як **`noarch`**: один бандл на всі платформи.
Його `[entry]` — це `command = "node"`, `args = ["dist/index.js"]`,
`runtimes = ["node"]`, а `astra-plugin build` збирає `src/index.ts` в один
самодостатній файл CommonJS — `.astraplugin` не постачає `node_modules`.

## Форма плагіна

Плагін — це **значення**, експортоване з модуля, і він запускається лише
тоді, коли цей файл є точкою входу процесу. Саме це дозволяє тесту
запустити його в тому самому процесі — без демона і без сокета.

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

Один об'єкт, один ключ на кожну річ, яку робить ваш плагін:

| Ключ | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — кроки в редакторі команд |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | Визначення провайдерів |
| `ui` | Внески, і методи, які може викликати назад ваш iframe |
| `events` | Які події демона вам потрібні, і обробники |
| `client` | `{ onReady(daemon, ctx) }` — лише для плагінів `client`, і **переданий `daemon` поки не працює**: див. нижче |
| `configSchema` | `s.object({...})` для ваших налаштувань |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Життєвий цикл |

`plugin()` повертає `{ run(), instance, definition }`: `run()` — це останній
рядок вашої точки входу, `instance` — те, чим керує тестовий harness, а
`definition` існує для інструментів, яким потрібно читати ваші схеми.

## Схеми

`s` будує JSON Schema і тип TypeScript одночасно:

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

## Виклики назовні, в Astra

Використовуйте методи на `ctx`. Кожен з них `async`, тож плагін, ще не
зареєстрований, отримує **відхилений promise**, а не синхронний throw з
функції, що повертає проміс, — а це саме те, чого не перехопить `try {
await ctx.fireTrigger(...) } catch {}`.

| `ctx.…` | Дозвіл |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | немає |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

Обгортки приймають **об'єкт корисного навантаження** і серіалізують його за
вас; `ctx.host` — це сирий клієнт під ними, типу `Host | null`, чиї
`fireTrigger` / `pushToUi` приймають JSON **рядок**. `ctx.host` — це ще й
місце, де живуть `getConfig()`, `getDaemonInfo()`, `subscribeEvents()` і
`getPluginId()`.

`setVariable`, `pushToUi` і шлях UI-виклику — все це існує і підключено;
старіша документація стверджувала протилежне, тому що вони з'явилися пізніше.

## Помилки

`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `TimeoutError`, `InternalError` — киньте одну, і SDK
відобразить її на той самий код дроту, що виробляють два інші SDK.
`HookUnimplemented` — це спосіб сказати «цього хука немає», а саме це на
дроті й означає `UNIMPLEMENTED`.

Таксономія і рядки дроту: [`reference/errors.md`](../reference/errors.md).

## Тестування

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

`Harness` керує справжнім сервісом можливостей у тому самому процесі:
`listTools`, `callTool`, `schema`, `assertSchemaAccepts`,
`assertSchemaRejects`, `executeAction`, `callFromUi`, `synthesize`,
`sttStream`, `aiComplete`, `event`, `conversationEvent`, `configChanged`,
`healthCheck`, `fuzzConfig`. `RecordingHost` записує те, що ваш плагін
повідомив Astra. `MockDaemon` і `WirePlugin` — це пара другого рівня:
справжній процес по gRPC.

## Чого цей SDK поки не вміє

- **`daemon`, переданий у `client.onReady`, нефункціональний.** Демон
  реєструє кожен плагін як `ClientType::PluginClient`, і його перехоплювач
  авторизації відхиляє цю ідентичність на будь-якому шляху поза
  `/astra.PluginHostService/` з `permission_denied("plugin session tokens
  are scoped to PluginHostService")`. `client: true` цього не міняє.
  `host.sendChatMessage` — єдиний робочий спосіб вести хід ШІ. Половина на
  боці демона не побудована, а не зламана.
- **`UiPanel` — застарілий псевдонім** для `UiContribution` — застарів у
  0.5.0, видаляється починаючи з 0.7.0.
- **`aiGetModels` застарів**, і його ніхто не викликає; заміни немає.
- **`ttsSynthesizeStream` прив'язаний, але не маршрутизований** — точки
  виклику в демона немає.
- **Proto тут не підтримується вручну.** Два рядки proto колись жили прямо
  всередині цього SDK, записувалися до тимчасового каталогу і завантажувалися
  звідти, і один з них описував сервіс, з якого вже мігрували — тож кожен
  TypeScript-плагін `client` кидав виняток при реєстрації. Тепер є один
  `.proto`, завендорений і звірюваний; не вводьте повторну копію.

## Див. також

[Таблиця хуків для TypeScript](../hooks/typescript.md) ·
[паритет](../reference/parity.md) · [помилки](../reference/errors.md) ·
[версіонування](../versioning.md)
