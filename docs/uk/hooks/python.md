> Переклад. Джерело істини — [docs/en](../../en/hooks/python.md); за розбіжності відповідає англійська версія. Англійська сторінка згенерована `tools/parity/gen.py` з `spec/hooks.yaml`; ця перекладна копія не генерується автоматично і може відстати при зміні специфікації.

# Python SDK — таблиця хуків

Протокол **1**. Кожен хук, який може прив'язати Python SDK, і чи робить це.
Згенеровано з [`spec/hooks.yaml`](../../../spec/hooks.yaml); міжмовний
огляд — [`parity.md`](../parity.md).

## PluginCapabilityService — демон → плагін

Ви їх реалізуєте; демон їх викликає.

| RPC | Можливість | Обов. | Потік | Статус | Що робить |
|---|---|---|---|---|---|
| `ListTools` | `tools` | обов'язковий | unary | stable | Схеми інструментів, які цей плагін пропонує моделі, читаються один раз при старті. |
| `CallTool` | `tools` | обов'язковий | unary | stable | Виконати один виклик інструмента від імені моделі і повернути його результат. |
| `TtsSynthesize` | `tts` | обов'язковий | unary | stable | Синтезувати одне висловлювання і повернути весь буфер. |
| `TtsSynthesizeStream` | `tts` | опціональний | server | stable | Синтезувати одне висловлювання як потік чанків, для затримки першого звуку. |
| `TtsListVoices` | `tts` | обов'язковий | unary | stable | Голоси, які цей провайдер показує у виборі налаштувань голосу. |
| `TtsGetConfigFields` | `tts` | опціональний | unary | stable | Додаткові поля налаштувань TTS, що рендеряться DynamicField на сторінці голосу. |
| `TtsActivate` | `tts` | опціональний | unary | stable | Доставити ключ контенту ліцензованого голосу для одноразової прив'язки до машини. |
| `SttProcess` | `stt` | обов'язковий | bidi | stable | Аудіо-чанки на вході, події транскрипту на виході; несе і одноразовий, і потоковий STT. |
| `SttGetLanguages` | `stt` | обов'язковий | unary | stable | Коди мов, які приймає цей розпізнавач. |
| `SttGetConfigFields` | `stt` | опціональний | unary | stable | Додаткові поля налаштувань STT, що рендеряться DynamicField на сторінці голосу. |
| `SttLoad` | `stt` | опціональний | unary | stable | Завантажити модель розпізнавача, зі шляхом, визначеним демоном, і перемикачем GPU. |
| `SttUnload` | `stt` | опціональний | unary | stable | Вивантажити модель розпізнавача, щоб idle-unload реально звільняв VRAM. |
| `SttGetLoadState` | `stt` | опціональний | unary | stable | Повідомити Loaded / NotLoaded / NotNeeded, щоб демон міг керувати idle-unload. |
| `AiComplete` | `ai_provider` | обов'язковий | server | stable | Стрімити завершення моделі; єдиний спосіб для плагіна бути провайдером ШІ. |
| `AiGetModels` | `ai_provider` | опціональний | unary | stable | Перелічити моделі, які може запускати цей провайдер. |
| `WebSearch` | `web_search` | обов'язковий | unary | stable | Answer one web search for the assistant's web_search tool, as a provider the user picks. |
| `MusicSubscribe` | `music_provider` | required | server | stable | Report what the music services the plugin reaches are playing, as a stream of WHOLE snapshots the media hub merges into the player widget, the island and the AI media tools. |
| `MusicControl` | `music_provider` | required | unary | stable | Carry out one verb on one session: play, pause, next, previous, seek, like, unlike, shuffle, repeat, volume. |
| `MusicGetQueue` | `music_provider` | optional | unary | stable | List a session's queue around the playing item, for the widget's queue panel and the AI's get_music_queue. |
| `MusicSearch` | `music_provider` | optional | unary | stable | Search a service's catalogue; items carry the plugin's own reference, handed back to MusicPlay. |
| `MusicPlay` | `music_provider` | optional | unary | stable | Start, or queue next / at the end, an item or the first match for words — what the AI's play_music and the widget's search rows call. |
| `ExecuteAction` | `actions` | обов'язковий | unary | stable | Виконати одну дію-крок команди, додану цим плагіном. |
| `GetPluginActionTypes` | `actions` | обов'язковий | unary | stable | Типи дій, які цей плагін додає до редактора команд, читаються при старті. |
| `GetPluginTriggerTypes` | `triggers` | обов'язковий | unary | stable | Типи тригерів, які цей плагін додає до редактора команд, читаються при старті. |
| `OnActiveTriggers` | `triggers` | опціональний | unary | stable | Які з типів тригерів цього плагіна зараз слухає команда. |
| `GetUiContributions` | `ui_contributions` | обов'язковий | unary | stable | Сторінки, слоти, оверлеї і ефекти, які цей плагін рендерить у вікні Astra. |
| `CallFromUi` | `ui_contributions` | опціональний | unary | stable | Виклик методу з власного iframe плагіна в його бекенд. |
| `OnConfigChanged` | `core` | опціональний | unary | stable | Користувач зберіг нові налаштування; ось увесь конфіг як JSON. |
| `OnLanguageChanged` | `core` | опціональний | unary | stable | Змінилася мова інтерфейсу Astra; перемалюйте все, що бачить користувач. |
| `Shutdown` | `core` | обов'язковий | unary | stable | Зупинитися чисто; групу процесів вбивають після пільгового періоду. |
| `HealthCheck` | `core` | обов'язковий | unary | stable | Проба живучості, кожні 15 с. |

## PluginHostService — плагін → демон

Демон їх реалізує; ви їх викликаєте.

**Тут однієї можливості недостатньо.** Це виклики, які ви робите в демон, і
демон відповідає на них виходячи з *виданого* набору дозволів (§5.6).
Оголошення можливості каже, до якої функції належить виклик; оголошення
дозволу — це те, на що погоджується користувач. Плагін, що оголосив лише
можливість, отримає `permission_denied` на машині користувача. `none`
означає, що будь-який плагін може викликати це завжди.

| RPC | Можливість | Дозвіл | Обов. | Потік | Статус | Що робить |
|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | обов'язковий | unary | stable | Рукостискання: пред'явити токен запуску, отримати токен сесії для цього плагіна. |
| `GetPluginSelfConfig` | `core` | `none` | опціональний | unary | stable | Прочитати власні збережені налаштування цього плагіна. |
| `PluginLog` | `core` | `none` | опціональний | unary | stable | Записати рядок у буфер логів демона, який читає панель логів плагіна. |
| `GetDaemonInfo` | `core` | `none` | опціональний | unary | stable | Версія демона, стан і порт gRPC. |
| `SetVariable` | `core` | `set_variable` | опціональний | unary | stable | Опублікувати змінну, яку можуть читати команди та інші плагіни. |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | обов'язковий | server | stable | Відфільтрований потік подій демона; уся можливість event_handlers. |
| `FireTrigger` | `triggers` | `fire_trigger` | обов'язковий | unary | stable | Запустити один з типів тригерів цього плагіна і виконати всі команди, що слухають. |
| `SendChatMessage` | `client` | `send_chat_message` | обов'язковий | server | stable | Надіслати повідомлення чату від імені цього плагіна і стрімити відповідь асистента назад. |
| `PushToUi` | `ui_contributions` | `push_to_ui` | опціональний | unary | stable | Надіслати подію у власні iframe цього плагіна — зворотний шлях для CallFromUi. |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | опціональний | unary | stable | Внести кольори, шпалери і шейдер до активної теми Astra. |

## Прогалини

Немає. Python SDK прив'язує кожен хук зі специфікації.
