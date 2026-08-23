> Переклад. Джерело істини — [docs/en](../en/parity.md); за розбіжності відповідає англійська версія. Англійська сторінка згенерована `tools/parity/gen.py` з `spec/hooks.yaml`; ця перекладна копія не генерується автоматично і може відстати при зміні специфікації.

# Паритет хуків

Протокол **1** · **35** хуків · джерело істини [`spec/hooks.yaml`](../../spec/hooks.yaml).

*Хук* — це один RPC на одному з двох звернених до плагіна сервісів.
`PluginCapabilityService` працює **демон → плагін**: ваш плагін його
обслуговує, а демон у нього викликає. `PluginHostService` працює **плагін →
демон**: демон його обслуговує, а ваш плагін з нього викликає назовні.
`PluginService` тут не показаний — демон обслуговує його для інтерфейсу
Astra, і жоден плагін його ніколи не торкається.

| Колонка | Значення |
|---|---|
| **Capability** | Ключ `[capabilities]` у `plugin.toml`, до якого належить цей хук, або `core` для хуків, які є в кожного плагіна. |
| **Permission** | Лише для `PluginHostService`. Ключ `[permissions]`, яким демон закриває виклик (§5.6), або `none`, якщо будь-який плагін може викликати це завжди. **Це не те саме питання, що Capability:** можливість каже, частиною якої функції є виклик, дозвіл — це те, на що погодився користувач, а демон відповідає виходячи з *виданого* набору дозволів. Перевіряється проти `HOST_RPC_PERMISSIONS` демона правилом R6. |
| **Req** | `required` — можливість не працює без хука. `optional` — демон продовжує роботу, коли його немає. |
| **Routing** | `live` — демон реально його викликає, і точка виклику названа. `unrouted` — оголошений у proto, ніким не викликається. `deprecated` — виводиться з обігу. |
| **Точка виклику демона** | Файл, з якого демон викликає цей хук, або **немає**, якщо його не викликає ніхто. Номер рядка тут навмисно не друкується. Він живе у `spec/hooks.yaml`, де правило R5 звіряє його зі справжньою точкою виклику, а `--fix-provenance` переставляє його наново; на сторінці його не перевіряє ніщо, він гниє з кожним комітом демона, і згнилий вказівник читається точно так само, як правильний — один із них устиг з'їхати на точку виклику іншого rpc, і цього ніхто не помітив. Шукайте в названому тут файлі ім'я rpc у snake_case. |
| `stable` | SDK прив'язує цей rpc до обробника, який реально працює — перевірено проти його вихідника правилом R1 `tools/parity/check.py`, яке розв'язує ціль диспетчеризації (`.bind(this)` у TypeScript, метод сервісера в Python, `async fn` у Rust) і читає *саме це* тіло. Чи досягає прив'язка чогось, коли через неї прогонюють реальний процес плагіна, — це питання правила R7, а не R1. |
| `planned` | Зафіксовано, але не випущено. Дата — це дедлайн відстрочки; правило R4 валить збірку, щойно вона минає. |
| `n/a` | Не реалізовано і не зафіксовано. Зареєстрований обробник, чиє тіло відповідає лише `UNIMPLEMENTED`, вважається `n/a`, тому що на дроті це *і є* відсутній хук — R1 читає тіло обробника рівно для цього. |

## Знахідки

Виведені з рядків нижче, а не написані вручну. Кожна — це те, як код автора
плагіна ламається сьогодні.

1. **`TtsSynthesizeStream` не маршрутизований.** Proto його оголошує, і
   точки виклику в демона не існує — тим не менш він прив'язаний у Rust,
   Python, TypeScript. Або підключіть його, або виведіть з обігу; сьогодні
   це обіцянка, яку демон не виконує.
2. **`AiGetModels` застарів, але все ще прив'язаний** у Rust, Python,
   TypeScript. Тримайте прив'язки, щоб старий плагін продовжував
   отримувати `UNIMPLEMENTED`, а не помилку транспорту; нових не додавайте.

## PluginCapabilityService — демон → плагін

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | Точка виклику демона |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **немає** |
| `TtsListVoices` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsGetConfigFields` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsActivate` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttProcess` | `stt` | required | live | bidi | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttGetLanguages` | `stt` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttGetConfigFields` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttLoad` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttUnload` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `SttGetLoadState` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `AiComplete` | `ai_provider` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/capability_bridge.rs` |
| `AiGetModels` | `ai_provider` | optional | deprecated | unary | stable | stable | stable | **немає** |
| `ExecuteAction` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `GetPluginActionTypes` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `GetPluginTriggerTypes` | `triggers` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `OnActiveTriggers` | `triggers` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `GetUiContributions` | `ui_contributions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `CallFromUi` | `ui_contributions` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `OnConfigChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `OnLanguageChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `Shutdown` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/instance.rs` |
| `HealthCheck` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |

## PluginHostService — плагін → демон

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | Точка виклику демона |
|---|---|---|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `GetPluginSelfConfig` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `PluginLog` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `GetDaemonInfo` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `SetVariable` | `core` | `set_variable` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `FireTrigger` | `triggers` | `fire_trigger` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `SendChatMessage` | `client` | `send_chat_message` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs` |

## Готовність можливостей

Чи може плагін, написаний цією мовою, взагалі реалізувати цю можливість
сьогодні?

| Можливість | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | так | так | так |
| `tts` | так | так | так |
| `stt` | так | так | так |
| `ai_provider` | так | так | так |
| `actions` | так | так | так |
| `triggers` | так | так | так |
| `ui_contributions` | так | так | так |
| `core` | так | так | так |
| `event_handlers` | так | так | так |
| `client` | так | так | так |

## Покриття перевіркою відповідності

23 вхідних хука, які зобов'язаний вправляти прогін перевірки
відповідності — кожен хук `демон → плагін`, який демон реально викликає.
`astra-plugin test` викликає кожен з них, передбачений оголошеними
можливостями плагіна, і перевіряє відсутність `UNIMPLEMENTED` для
`required`; `optional`-хуки звільнені від цього, тому що `Unimplemented →
хука немає` — це контракт прямої сумісності, а інакше заготовка, що
оголошує все підряд, була б невідмінна від зламаного плагіна.
Машинозчитувана копія:
[`spec/generated/conformance.json`](../../spec/generated/conformance.json).

| RPC | Capability | Req | Stream | Фаза |
|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | probe |
| `CallTool` | `tools` | required | unary | probe |
| `TtsSynthesize` | `tts` | required | unary | probe |
| `TtsListVoices` | `tts` | required | unary | probe |
| `TtsGetConfigFields` | `tts` | optional | unary | probe |
| `TtsActivate` | `tts` | optional | unary | probe |
| `SttProcess` | `stt` | required | bidi | probe |
| `SttGetLanguages` | `stt` | required | unary | probe |
| `SttGetConfigFields` | `stt` | optional | unary | probe |
| `SttLoad` | `stt` | optional | unary | probe |
| `SttUnload` | `stt` | optional | unary | probe |
| `SttGetLoadState` | `stt` | optional | unary | probe |
| `AiComplete` | `ai_provider` | required | server | probe |
| `ExecuteAction` | `actions` | required | unary | probe |
| `GetPluginActionTypes` | `actions` | required | unary | probe |
| `GetPluginTriggerTypes` | `triggers` | required | unary | probe |
| `OnActiveTriggers` | `triggers` | optional | unary | probe |
| `GetUiContributions` | `ui_contributions` | required | unary | probe |
| `CallFromUi` | `ui_contributions` | optional | unary | probe |
| `OnConfigChanged` | `core` | optional | unary | probe |
| `OnLanguageChanged` | `core` | optional | unary | probe |
| `HealthCheck` | `core` | required | unary | probe |
| `Shutdown` | `core` | required | unary | teardown |

## Примітки

- **`TtsSynthesizeStream`** — Синтезувати одне висловлювання як потік чанків, для затримки першого звуку. ЗНАХІДКА: точки виклику в демона в astra-rs не існує. Усі три SDK тепер його обслуговують, і ніхто його не викликає — розбіжність, для відлову якої існує цей файл, зникла, а немаршрутизований rpc — ні.
- **`TtsGetConfigFields`** — Додаткові поля налаштувань TTS, що рендеряться DynamicField на сторінці голосу. Маршрутизується через хелпер демона `optional_hook` (manager.rs:2878), тож UNIMPLEMENTED означає «відсутній», а справжній збій залишається збоєм.
- **`TtsActivate`** — Доставити ключ контенту ліцензованого голосу для одноразової прив'язки до машини. Proto стверджує, що UNIMPLEMENTED трактується як «активація не потрібна»; демон НЕ маршрутизує його через `optional_hook` — manager.rs:2664 пробрасує помилку, а vox_activation.rs:319 валить активацію. Неправий тут саме коментар у proto.
- **`SttProcess`** — Аудіо-чанки на вході, події транскрипту на виході; несе і одноразовий, і потоковий STT. Також вживу керується в manager.rs:2808. Місткість каналу на обох кінцях — spec/limits.yaml:stt_audio_channel_capacity.
- **`SttLoad`** — Завантажити модель розпізнавача, зі шляхом, визначеним демоном, і перемикачем GPU. manager.rs:2918 маршрутизує його через `optional_hook`, тому він опціональний.
- **`SttGetLoadState`** — Повідомити Loaded / NotLoaded / NotNeeded, щоб демон міг керувати idle-unload. manager.rs:2960 відображає відсутній хук у NotNeeded, що й було поведінкою до появи хука.
- **`AiComplete`** — Стрімити завершення моделі; єдиний спосіб для плагіна бути провайдером ШІ. Python і TypeScript прив'язують його як асинхронний генератор; Rust — як серверний потік, що живиться каналом, який чекає перший чанк, перш ніж відкрити відповідь, тож неперевизначений хук все одно може відповісти UNIMPLEMENTED. Усі три SDK прив'язують його починаючи з 5.4, тож `ai_provider` реалізовний будь-якою мовою.
- **`AiGetModels`** — Перелічити моделі, які може запускати цей провайдер. ЗНАХІДКА: реалізований у всіх трьох SDK, і його ніхто не викликає. `all_ai_providers` жорстко задає supports_model_discovery=false, тож вибір моделі ніколи не питає. Позначений як застарілий у proto; зберігайте прив'язки, нових не додавайте. Застарів у 0.6, видалений у 0.8, і заміни немає: ніщо в демоні не питає у плагіна, які в нього моделі, а AiComplete несе обрану модель прямо в запиті.
- **`OnActiveTriggers`** — Які з типів тригерів цього плагіна зараз слухає команда. manager.rs:2523 маршрутизує його через `optional_hook`.
- **`OnLanguageChanged`** — Змінилася мова інтерфейсу Astra; перемалюйте все, що бачить користувач. manager.rs:1133 маршрутизує його через `optional_hook`.
- **`Shutdown`** — Зупинитися чисто; групу процесів вбивають після пільгового періоду. Відстрочка — spec/limits.yaml:plugin_stop_grace_secs. Відповідайте, потім виходьте.
- **`HealthCheck`** — Проба живучості, кожні 15 с. Обов'язковий у найсильнішому сенсі: цей хук НЕ маршрутизується через `optional_hook`, тож будь-яка помилка — включно з UNIMPLEMENTED — позначає плагін мертвим (manager.rs:1464).
- **`Register`** — Рукостискання: пред'явити токен запуску, отримати токен сесії для цього плагіна. Єдиний шлях, звільнений від перехоплювача авторизації. Кожен наступний rpc хоста зобов'язаний нести повернутий токен як x-session-token.
- **`SendChatMessage`** — Надіслати повідомлення чату від імені цього плагіна і стрімити відповідь асистента назад. Токен сесії обмежений PluginHostService, тож шлях DaemonClient/ChatService, на який раніше вказували авторів SDK, — permission_denied — цей rpc єдиний робочий шлях. Прив'язаний у всіх трьох SDK починаючи з 5.4.
- **`PushToUi`** — Надіслати подію у власні iframe цього плагіна — зворотний шлях для CallFromUi. Тепер прив'язаний у всіх трьох. У Python три релізи був CallFromUi і не було PushToUi, тож Python UI-плагін можна було викликати, але він не міг відповісти асинхронно.
- **`SetThemeContribution`** — Внести кольори, шпалери і шейдер до активної теми Astra. Фаза 4 класифікує його як високоризиковий і відхиляє нижче рівня 1, тож прив'язка без виданого дозволу — це permission_denied, а не перефарбована тема. Прив'язаний у всіх трьох SDK починаючи з 5.4.
