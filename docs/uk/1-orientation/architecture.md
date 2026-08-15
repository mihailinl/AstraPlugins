# Архітектура

> Переклад. Джерело істини — [docs/en](../../en/1-orientation/architecture.md); за розбіжності відповідає англійська версія.

Як запускається процес плагіна, як він доводить, хто він такий, і який з двох
gRPC-сервісів несе який виклик.

## Модель процесів

<!-- doctest: illustrative reason="an ASCII diagram of the two services, not code" -->
```
   ┌──────────────────────────┐                  ┌──────────────────────────┐
   │      Astra daemon        │                  │     your plugin          │
   │                          │   spawns with    │     (a separate OS       │
   │  plugin manager ─────────┼──── argv ───────▶│      process, your       │
   │                          │                  │      user account)       │
   │                          │                  │                          │
   │  PluginHostService       │◀── plugin calls ─┤  HostClient              │
   │  (the daemon serves)     │   x-session-token│                          │
   │                          │                  │                          │
   │  capability client ──────┼── daemon calls ─▶│  PluginCapabilityService │
   │                          │   x-plugin-token │  (your plugin serves)    │
   └──────────────────────────┘                  └──────────────────────────┘
             both ends are gRPC over loopback TCP
```

Демон запускає процес із чотирма аргументами. Це точний командний рядок,
скопійований з реального запуску `astra-plugin test`:

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

SDK розбирає їх за вас. Цікавий тут `--auth-token`: це секрет, який демон
випустив для цього запуску, і використовується він в **обох** напрямках.

## Порядок запуску

SDK виконує фіксовану послідовність (`astra-plugin-sdk/src/runner.rs`):

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **bind перед register**, тому що порт повідомляється демону під час
  `Register`, і він може одразу передзвонити. Слухач уже піднятий, тому такі
  виклики стають у чергу прийому, а не відхиляються.
- **`on_config` перед `on_start`**, тому що плагіну, який запускає фоновий
  цикл, спершу потрібні його налаштування.
- **`on_start` перед `serve`**, і `Err` з нього перериває запуск: плагін, який
  не може виконувати свою роботу, не повинен бути тим, що демон вважає
  справним.

Дві цифри обмежують це, кожна оголошена один раз у
[`spec/limits.yaml`](../../../spec/limits.yaml) і згенерована в кожен SDK:

| Ліміт | Значення | Що відбувається, якщо не вкластися |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | Демон оголошує запуск невдалим і прибирає процес |
| `plugin_stop_grace_secs` | 5 | Після `Shutdown` групу процесів вбивають |

## Рукостискання

1. Демон запускає процес з `--auth-token=<токен запуску>`.
2. Плагін прив'язує gRPC-сервер до призначеного ОС loopback-порту.
3. Плагін викликає `PluginHostService.Register`, пред'являючи токен запуску,
   свій порт, версію протоколу і список можливостей.
4. Демон відповідає **токеном сесії**.
5. Кожен наступний виклик плагін → демон несе цей токен сесії в
   метаданому заголовку `x-session-token`. `Register` — єдиний звільнений від
   цього шлях (`astra-plugin-sdk/src/auth.rs`); будь-що інше без нього
   повертає `unauthenticated`.

Реєстрація в реальному запуску проти мок-демона, який піднімає
`astra-plugin test`:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### Зворотний напрямок

Напрямок демон → плагін використовує **той самий** токен запуску, що
надсилається плагіну назад у заголовку `x-plugin-token` при кожному виклику.
Ваш сервер можливостей перевіряє його, і SDK робить це за вас.

**Ви це не налаштовуєте.** Демон встановлює
`ASTRA_PLUGIN_CAPABILITY_AUTH=require` в оточенні вашого плагіна, що каже SDK
відхиляти будь-який виклик можливості без цього токена. Це демон оголошує про
свою власну половину, а не хтось звіряє номери версій: демон, достатньо
старий, щоб не надсилати заголовок, не встановлює й змінну, і SDK залишається
в режимі `CapabilityAuth::Warn` — **невірний** токен відхиляється,
**відсутній** приймається з одним попередженням, — тож ваш плагін там
продовжує працювати.

Це важливо, тому що loopback — не межа. Ваш сервер можливостей слухає на
`127.0.0.1` з призначеним ОС портом, і його може знайти будь-який процес, що
працює від вашого користувача. Без заголовка достатньо було його знайти, щоб
викликати `CallTool`, `OnConfigChanged` — перенаправивши базовий URL вашого
API на чужий хост, після чого ваш плагін надішле туди свої справжні облікові
дані — або `Shutdown`.

`astra-plugin test` встановлює ту саму змінну і пред'являє той самий токен,
тож те, що ви тестуєте локально, — це те, що виконується на машині
користувача.

## Два сервіси

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| Обслуговується | вашим плагіном | демоном |
| Викликається | демоном | вашим плагіном |
| Регулюється | `[capabilities]` | `[permissions]` |
| Хуків | 25 | 10 |

`PluginService` — третій сервіс у proto — обслуговується демоном для
інтерфейсу Astra. Плагін його ніколи не викликає; `astra-plugin dev` і
`astra-plugin logs` роблять це як локальний клієнт.

Кожен хук, з його можливістю, дозволом, тим, чи є він обов'язковим, і рядком
вихідного коду демона, що його викликає:
[таблиця паритету](../reference/parity.md).

## Здоров'я, завершення і перезапуски

- `HealthCheck` виконується кожні 15 с і **не** вважається опціональним: будь-яка
  помилка з нього, включно з `UNIMPLEMENTED`, позначає плагін як мертвий.
- На `Shutdown` відповідають, а потім виходять. Відстрочка — 5 с.
- Паніка всередині обробника перехоплюється і повертається як помилка, а не
  розкручується через gRPC-сервер (`astra-plugin-sdk/src/panics.rs`). Паніка
  все одно залишається багом; просто це не збій сервісу.

## Конфігурація

Налаштування плагіна — це JSON, який зберігає демон і який редагується в
інтерфейсі налаштувань Astra на основі JSON Schema з вашого розділу
`[config]`. Демон доставляє їх через `OnConfigChanged`, а плагін може також
запросити їх через `GetPluginSelfConfig` — один з чотирьох викликів, що не
потребують дозволу.

Перше корисне навантаження при свіжому встановленні — `{}`, тому типи
конфігурації SDK задають значення за замовчуванням для кожного поля. Див.
[поля налаштувань](../3-reference/config-fields.md).

Файл налаштувань — `<каталог конфігурації astra>/plugins/<id>/config.json`
(у [платформах](platforms.md) — точний каталог для кожної ОС). Він
**переживає оновлення** — оновлення це зупинка, встановлення, запуск, і раніше
встановлення робило `remove_dir_all` над каталогом, де жили налаштування
користувача; тепер демон зберігає файл і перевіряє це тестом
(`config_survives_update`, `astra-daemon/src/plugins/manager.rs`), і копія,
запакована в новий архів, не може його перезаписати. Він **не** переживає
видалення: `uninstall_plugin` завершується `remove_dir_all`. Усе, що повинно
пережити видалення, має зберігатися там, чим володієте ви.

## Де що лежить

| Що | Шлях |
|---|---|
| Схема `plugin.toml` | `astra-plugin-cli/vendor/astra-plugin-manifest/` — побайтово ідентична копія крейта, яким користується демон |
| Дріт | [`proto/plugin.proto`](../../../proto/plugin.proto), згенерований зріз `astra.proto` з Astra |
| Таблиця хуків | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| Спільні числа | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| Формат бандла | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
