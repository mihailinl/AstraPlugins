> Перевод. Источник истины — [docs/en](../en/parity.md); при расхождении верна английская версия. Английская страница сгенерирована `tools/parity/gen.py` из `spec/hooks.yaml`; эта переводная копия не генерируется автоматически и может отстать при изменении спецификации.

# Паритет хуков

Протокол **1** · **35** хуков · источник истины [`spec/hooks.yaml`](../../spec/hooks.yaml).

*Хук* — это один RPC на одном из двух обращённых к плагину сервисов.
`PluginCapabilityService` работает **демон → плагин**: ваш плагин его
обслуживает, а демон в него вызывает. `PluginHostService` работает **плагин
→ демон**: демон его обслуживает, а ваш плагин из него вызывает наружу.
`PluginService` здесь не показан — демон обслуживает его для интерфейса
Astra, и ни один плагин его никогда не трогает.

| Колонка | Значение |
|---|---|
| **Capability** | Ключ `[capabilities]` в `plugin.toml`, к которому относится этот хук, или `core` для хуков, которые есть у каждого плагина. |
| **Permission** | Только для `PluginHostService`. Ключ `[permissions]`, которым демон закрывает вызов (§5.6), или `none`, если любой плагин может вызывать его всегда. **Это не тот же вопрос, что Capability:** возможность говорит, частью какой функции является вызов, разрешение — это то, на что согласился пользователь, а демон отвечает исходя из *выданного* набора разрешений. Проверяется против `HOST_RPC_PERMISSIONS` демона правилом R6. |
| **Req** | `required` — возможность не работает без хука. `optional` — демон продолжает работу, когда его нет. |
| **Routing** | `live` — демон реально его вызывает, и точка вызова названа. `unrouted` — объявлен в proto, никем не вызывается. `deprecated` — выводится из обращения. |
| **Точка вызова демона** | Файл, из которого демон вызывает этот хук, или **нет**, если его не вызывает никто. Номер строки здесь намеренно не печатается. Он живёт в `spec/hooks.yaml`, где правило R5 сверяет его с настоящей точкой вызова, а `--fix-provenance` переставляет его заново; на странице его не проверяет ничто, он гниёт с каждым коммитом демона, и сгнивший указатель читается ровно так же, как верный — один из них успел съехать на точку вызова другого rpc, и этого никто не заметил. Ищите в названном здесь файле имя rpc в snake_case. |
| `stable` | SDK привязывает этот rpc к обработчику, который реально работает — проверено против его исходника правилом R1 `tools/parity/check.py`, которое разрешает цель диспетчеризации (`.bind(this)` в TypeScript, метод сервисёра в Python, `async fn` в Rust) и читает *именно это* тело. Достигает ли привязка чего-либо, когда через неё прогоняют реальный процесс плагина, — это вопрос правила R7, а не R1. |
| `planned` | Зафиксировано, но не выпущено. Дата — это дедлайн отсрочки; правило R4 роняет сборку, как только он проходит. |
| `n/a` | Не реализовано и не зафиксировано. Зарегистрированный обработчик, чьё тело отвечает только `UNIMPLEMENTED`, считается `n/a`, потому что на проводе это *и есть* отсутствующий хук — R1 читает тело обработчика ровно для этого. |

## Находки

Выведены из строк ниже, а не написаны вручную. Каждая — это то, как код
автора плагина ломается сегодня.

1. **`TtsSynthesizeStream` не маршрутизирован.** Proto его объявляет, и
   точки вызова у демона не существует — тем не менее он привязан в Rust,
   Python, TypeScript. Либо подключите его, либо выведите из обращения;
   сегодня это обещание, которое демон не выполняет.
2. **`AiGetModels` устарел, но всё ещё привязан** в Rust, Python,
   TypeScript. Держите привязки, чтобы старый плагин продолжал получать
   `UNIMPLEMENTED`, а не ошибку транспорта; новых не добавляйте.

## PluginCapabilityService — демон → плагин

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | Точка вызова демона |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **нет** |
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
| `AiGetModels` | `ai_provider` | optional | deprecated | unary | stable | stable | stable | **нет** |
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

## PluginHostService — плагин → демон

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | Точка вызова демона |
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

## Готовность возможностей

Может ли плагин, написанный на этом языке, вообще реализовать эту
возможность сегодня?

| Возможность | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | да | да | да |
| `tts` | да | да | да |
| `stt` | да | да | да |
| `ai_provider` | да | да | да |
| `actions` | да | да | да |
| `triggers` | да | да | да |
| `ui_contributions` | да | да | да |
| `core` | да | да | да |
| `event_handlers` | да | да | да |
| `client` | да | да | да |

## Покрытие проверкой соответствия

23 входящих хука, которые обязан упражнять прогон проверки соответствия —
каждый хук `демон → плагин`, который демон реально вызывает.
`astra-plugin test` вызывает каждый из них, подразумеваемый объявленными
возможностями плагина, и проверяет отсутствие `UNIMPLEMENTED` для
`required`; `optional`-хуки освобождены от этого, потому что
`Unimplemented → хука нет` — это контракт прямой совместимости, а иначе
заготовка, объявляющая всё подряд, была бы неотличима от сломанного
плагина. Машиночитаемая копия:
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

## Заметки

- **`TtsSynthesizeStream`** — Синтезировать одно высказывание как поток чанков, для задержки первого звука. НАХОДКА: точки вызова у демона в astra-rs не существует. Все три SDK теперь его обслуживают, и никто его не вызывает — расхождение, для отлова которого существует этот файл, исчезло, а немаршрутизированный rpc — нет.
- **`TtsGetConfigFields`** — Дополнительные поля настроек TTS, отрисовываемые DynamicField на странице голоса. Маршрутизируется через хелпер демона `optional_hook` (manager.rs:2878), так что UNIMPLEMENTED значит «отсутствует», а настоящий сбой остаётся сбоем.
- **`TtsActivate`** — Доставить ключ контента лицензированного голоса для одноразовой привязки к машине. Proto утверждает, что UNIMPLEMENTED трактуется как «активация не нужна»; демон НЕ маршрутизирует его через `optional_hook` — manager.rs:2664 пробрасывает ошибку, а vox_activation.rs:319 роняет активацию. Неправ здесь именно комментарий в proto.
- **`SttProcess`** — Аудио-чанки на входе, события транскрипта на выходе; несёт и одноразовый, и потоковый STT. Также вживую управляется в manager.rs:2808. Ёмкость канала на обоих концах — spec/limits.yaml:stt_audio_channel_capacity.
- **`SttLoad`** — Загрузить модель распознавателя, с путём, разрешённым демоном, и переключателем GPU. manager.rs:2918 маршрутизирует его через `optional_hook`, поэтому он опционален.
- **`SttGetLoadState`** — Сообщить Loaded / NotLoaded / NotNeeded, чтобы демон мог управлять idle-unload. manager.rs:2960 отображает отсутствующий хук в NotNeeded, что и было поведением до появления хука.
- **`AiComplete`** — Стримить завершение модели; единственный способ для плагина быть провайдером ИИ. Python и TypeScript привязывают его как асинхронный генератор; Rust — как серверный поток, питаемый каналом, который ждёт первый чанк, прежде чем открыть ответ, так что непереопределённый хук всё равно может ответить UNIMPLEMENTED. Все три SDK привязывают его начиная с 5.4, так что `ai_provider` реализуем на любом языке.
- **`AiGetModels`** — Перечислить модели, которые может запускать этот провайдер. НАХОДКА: реализован во всех трёх SDK, и его никто не вызывает. `all_ai_providers` жёстко задаёт supports_model_discovery=false, так что выбор модели никогда не спрашивает. Помечен как устаревший в proto; сохраняйте привязки, новых не добавляйте. Устарел в 0.6, удалён в 0.8, и замены нет: ничто в демоне не спрашивает у плагина, какие у него модели, а AiComplete несёт выбранную модель прямо в запросе.
- **`OnActiveTriggers`** — Какие из типов триггеров этого плагина сейчас слушает команда. manager.rs:2523 маршрутизирует его через `optional_hook`.
- **`OnLanguageChanged`** — Изменился язык интерфейса Astra; перерисуйте всё, что видит пользователь. manager.rs:1133 маршрутизирует его через `optional_hook`.
- **`Shutdown`** — Остановиться чисто; группа процессов убивается после льготного периода. Отсрочка — spec/limits.yaml:plugin_stop_grace_secs. Ответьте, затем выйдите.
- **`HealthCheck`** — Проба живости, каждые 15 с. Обязателен в самом сильном смысле: этот хук НЕ маршрутизируется через `optional_hook`, так что любая ошибка — включая UNIMPLEMENTED — помечает плагин мёртвым (manager.rs:1464).
- **`Register`** — Рукопожатие: предъявить токен запуска, получить токен сессии для этого плагина. Единственный путь, освобождённый от перехватчика авторизации. Каждый последующий rpc хоста обязан нести возвращённый токен как x-session-token.
- **`SendChatMessage`** — Отправить сообщение чата от имени этого плагина и стримить ответ ассистента обратно. Токен сессии ограничен PluginHostService, так что путь DaemonClient/ChatService, на который раньше указывали авторов SDK, — permission_denied — этот rpc единственный рабочий путь. Привязан во всех трёх SDK начиная с 5.4.
- **`PushToUi`** — Отправить событие в собственные iframe этого плагина — обратный путь для CallFromUi. Теперь привязан во всех трёх. У Python три релиза был CallFromUi и не было PushToUi, так что Python UI-плагин можно было вызвать, но он не мог ответить асинхронно.
- **`SetThemeContribution`** — Внести цвета, обои и шейдер в активную тему Astra. Фаза 4 классифицирует его как высокорисковый и отклоняет ниже уровня 1, так что привязка без выданного разрешения — это permission_denied, а не перекрашенная тема. Привязан во всех трёх SDK начиная с 5.4.
