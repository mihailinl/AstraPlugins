# TypeScript SDK

> Перевод. Источник истины — [docs/en](../../en/4-sdk/typescript.md); при расхождении верна английская версия.

`astra-plugin-sdk` **0.5.0 — версия, которую описывает эта страница**, и та,
что отдаёт npm. `npm install astra-plugin-sdk` (или `bun add`) её разрешает;
это же закрепляет `astra-plugin new --lang typescript`. Берите 0.5.0 или
новее: 0.4.0 не отправляет токен сессии, и демон отклоняет каждый вызов
хоста, который она делает.

У имени пакета нет области видимости (scope) — более раннее имя со scope
встречается в старых проектах и никогда не было зарегистрировано, так что
`npm i` этого имени сразу проваливается.

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

TypeScript-плагин упаковывается как **`noarch`**: один бандл на все
платформы. Его `[entry]` — это `command = "node"`, `args =
["dist/index.js"]`, `runtimes = ["node"]`, а `astra-plugin build` собирает
`src/index.ts` в единый самодостаточный файл CommonJS — `.astraplugin` не
поставляет `node_modules`.

## Форма плагина

Плагин — это **значение**, экспортируемое из модуля, и он запускается,
только когда этот файл является точкой входа процесса. Именно это позволяет
тесту запустить его в том же процессе — без демона и без сокета.

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

Один объект, один ключ на каждую вещь, которую делает ваш плагин:

| Ключ | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — шаги в редакторе команд |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | Определения провайдеров |
| `ui` | Вклады, и методы, которые может вызвать обратно ваш iframe |
| `events` | Какие события демона вам нужны, и обработчики |
| `client` | `{ onReady(daemon, ctx) }` — только для плагинов `client`, и **переданный `daemon` пока не работает**: см. ниже |
| `configSchema` | `s.object({...})` для ваших настроек |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Жизненный цикл |

`plugin()` возвращает `{ run(), instance, definition }`: `run()` — это
последняя строка вашей точки входа, `instance` — то, чем управляет тестовый
harness, а `definition` существует для инструментов, которым нужно читать
ваши схемы.

## Схемы

`s` строит JSON Schema и тип TypeScript одновременно:

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

## Вызовы наружу, в Astra

Используйте методы на `ctx`. Каждый из них `async`, так что плагин, ещё не
зарегистрированный, получает **отклонённый promise**, а не синхронный throw
из функции, которая возвращает промис, — а это как раз то, что не
перехватывает `try { await ctx.fireTrigger(...) } catch {}`.

| `ctx.…` | Разрешение |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | нет |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

Обёртки принимают **объект полезной нагрузки** и сериализуют его за вас;
`ctx.host` — это сырой клиент под ними, типа `Host | null`, чьи
`fireTrigger` / `pushToUi` принимают JSON **строку**. `ctx.host` — это ещё и
место, где живут `getConfig()`, `getDaemonInfo()`, `subscribeEvents()` и
`getPluginId()`.

`setVariable`, `pushToUi` и путь UI-вызова — всё это существует и
подключено; более старая документация утверждала обратное, потому что они
появились позже.

## Ошибки

`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `TimeoutError`, `InternalError` — бросьте одну, и SDK
отобразит её на тот же код провода, что производят два других SDK.
`HookUnimplemented` — это способ сказать «этого хука нет», а именно это на
проводе и значит `UNIMPLEMENTED`.

Таксономия и строки провода: [`reference/errors.md`](../reference/errors.md).

## Тестирование

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

`Harness` управляет настоящим сервисом возможностей в том же процессе:
`listTools`, `callTool`, `schema`, `assertSchemaAccepts`,
`assertSchemaRejects`, `executeAction`, `callFromUi`, `synthesize`,
`sttStream`, `aiComplete`, `event`, `conversationEvent`, `configChanged`,
`healthCheck`, `fuzzConfig`. `RecordingHost` записывает то, что ваш плагин
сообщил Astra. `MockDaemon` и `WirePlugin` — это пара второго уровня:
настоящий процесс по gRPC.

## Чего этот SDK пока не умеет

- **`daemon`, переданный в `client.onReady`, нефункционален.** Демон
  регистрирует каждый плагин как `ClientType::PluginClient`, и его
  перехватчик авторизации отклоняет эту идентичность на любом пути вне
  `/astra.PluginHostService/` с `permission_denied("plugin session tokens
  are scoped to PluginHostService")`. `client: true` этого не меняет.
  `host.sendChatMessage` — единственный рабочий способ вести ход ИИ.
  Половина на стороне демона не построена, а не сломана.
- **`UiPanel` — устаревший псевдоним** для `UiContribution` — устарел в
  0.5.0, удаляем начиная с 0.7.0.
- **`aiGetModels` устарел**, и его никто не вызывает; замены нет.
- **`ttsSynthesizeStream` привязан, но не маршрутизирован** — точки вызова у
  демона нет.
- **Proto здесь не поддерживается вручную.** Две строки proto когда-то жили
  прямо внутри этого SDK, записывались во временный каталог и загружались
  оттуда, и одна из них описывала сервис, из которого уже мигрировали — так
  что каждый TypeScript-плагин `client` бросал исключение при регистрации.
  Теперь есть один `.proto`, завендоренный и сверяемый; не вводите повторную
  копию.

## См. также

[Таблица хуков для TypeScript](../hooks/typescript.md) ·
[паритет](../reference/parity.md) · [ошибки](../reference/errors.md) ·
[версионирование](../versioning.md)
