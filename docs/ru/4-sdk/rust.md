# Rust SDK

> Перевод. Источник истины — [docs/en](../../en/4-sdk/rust.md); при расхождении верна английская версия.

`astra-plugin-sdk` 0.6.0. Одна зависимость, и всё, во что раскрываются
макросы, приходит через неё.

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 — первый релиз, чей `HostClient` прикрепляет `x-session-token`. Против
0.5 и старше демон отвечает `unauthenticated` на каждый вызов хоста, так что
не ослабляйте эту границу.

## Форма плагина

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` реализует `PluginCapability` из найденных хуков и выводит
из них объявленный набор возможностей — так что плагин не может заявить
возможность, которую не обслуживает его код. `astra-plugin check` сверяет
это с `plugin.toml`.

## Слой макросов

| | Для чего |
|---|---|
| `#[astra::plugin]` | На блоке `impl`. Превращает члены ниже в реализацию трейта |
| `#[tool]` | Функция, которую может вызвать модель. Doc-комментарий — её описание |
| `#[action(label = "…")]` | Шаг в редакторе команд |
| `#[hook]` | Любой другой метод `PluginCapability`, по имени |
| `#[ui_call]` | Метод, который может вызвать обратно ваш UI-вклад |
| `#[astra::args]` | На структуре аргументов инструмента |
| `#[astra::config]` | На вашей структуре настроек — `args` плюс `#[serde(default)]` |
| `astra::main!(Plugin::default())` | `main`, который его запускает |

**Почему `#[astra::args]`, а не `#[derive(Deserialize, JsonSchema)]`:**
дерайв serde раскрывается в `extern crate serde as _serde`, которое
резолвится в extern prelude и недостижимо через ре-экспорт. Обычный дерайв
поэтому потребовал бы `serde` в вашем собственном `Cargo.toml` — а как раз
об этом обещание об одной зависимости. `#[astra::args]` — это те же два
дерайва с `crate = "…"`, указывающим на копии SDK. Добавить `serde`
самостоятельно всё ещё можно; тогда `use serde::Deserialize;` затенит имя
из prelude.

Вы также можете реализовать `PluginCapability` вручную. Трейт публичный,
у каждого метода есть реализация по умолчанию, и макросы производят ровно
то, что вы бы написали сами.

## `PluginContext`

Каждому обработчику передаётся `&PluginContext`. Он никогда не `None`, его
дёшево клонировать в фоновую задачу, и это значит, что ничего не должно
лежать на вашей структуре за блокировкой.

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — десять RPC хоста. Присутствует всегда |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **`Some` только для плагинов `client`** |
| `ctx.language()` | Язык интерфейса Astra, обновляется через `OnLanguageChanged` |
| `ctx.active_triggers()` | Какие из ваших типов триггеров слушает сейчас команда |
| `ctx.plugin_id()` | Ваш id |

Из места, куда параметр не может дотянуться, — реализация `Drop`, коллбэк
из C-библиотеки, `std::thread`, запущенный при старте, — `astra_plugin_sdk::ctx()`
возвращает контекст работающего плагина, а `try_ctx()` — его версию, которая
может провалиться.

### `Host` — десять вызовов наружу

| Метод | Разрешение |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | нет |
| `get_config` | нет |
| `get_daemon_info` | нет |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` принимает **три** аргумента — имя, значение и область
видимости. Подписки на события не на `Host`: объявите `subscribed_events()`,
и раннер сам владеет потоком (ниже).

`Host` — это трейт, так что тест может подставить `RecordingHost` и
проверить, что ваш плагин сообщил Astra.

### `Daemon` — присутствует в SDK, отклоняется демоном

> **`ctx.daemon()` сегодня не работает, ни для какого плагина.** Половина на
> стороне демона не построена. Каждый плагин — `client = true` или нет —
> регистрируется как `ClientType::PluginClient`, и перехватчик авторизации
> демона отклоняет эту идентичность на **любом** пути, не начинающемся с
> `/astra.PluginHostService/`, с `permission_denied("plugin session tokens
> are scoped to PluginHostService")`. `DaemonClient` подключается ровно с
> этим токеном (`astra-plugin-sdk/src/host_client.rs` передаёт
> `client_session_token` в `DaemonClient::connect`), так что каждый вызов
> ниже — `submit_user_message`, `subscribe_chat_events`, `speak`,
> `get_settings` — возвращает `permission_denied` во время выполнения. Канарейка
> в `consistency.rs` демона держит эту проверку области действия на месте,
> так что это осознанное решение, а не регрессия: обратная половина
> аутентификации не построена, а не сломана.
>
> **`Host::send_chat_message` — единственный рабочий способ вести ход ИИ**, и
> он работает для любого плагина, которому выдано `send_chat_message`.

Поверхность API, на случай когда сторона демона будет достроена: `ctx.daemon()`
— это `Some` только когда плагин объявляет `client = true` и `is_client()`
возвращает true. Он достаёт до семи сервисов — core, chat, voice, command,
config, media, monitor — с методами включая `submit_user_message`,
`subscribe_chat_events`, `stop_generation`, `list_conversations`, `speak`,
`start_listening`, `execute_command`, `get_settings`, `get_system_stats`. Это
`submit_user_message`, а не `send_message`.

## Ошибки

Обработчики возвращают `Result<_, ToolError>` (`ActionError` — псевдоним того
же типа). Ошибка отдельного вызова — это данные, которые читает и по которым
действует цикл ИИ, поэтому она едет в ответе, а не как статус gRPC.

| Вариант | Используйте, когда |
|---|---|
| `BadArguments(String)` | Модель может это исправить, вызвав по-другому |
| `NotFound(String)` | Неизвестный id, 404 |
| `NotConfigured { field, message }` | Отсутствует настройка. `field` — цель для глубокой ссылки |
| `Unauthorized(String)` | Учётные данные отклонены, или разрешение не было выдано |
| `RateLimited { retry_after, message }` | Квота вышестоящего сервиса. `None` значит «неизвестно», а не «немедленно» |
| `Unavailable(String)` | Зависимость недоступна; повторите позже без изменений |
| `Timeout(String)` | Кончилось время |
| `Internal(String)` | Баг. Модель ничего с этим не сделает |

`?` работает с `serde_json::Error`, `std::io::Error`, `tonic::Status` и
`anyhow::Error`. `with_doc_url(…)` оборачивает любую из них страницей,
документирующей именно этот сбой, которую UI отрисовывает как ссылку.

Полная таксономия, включая строки провода и написание в Python/TypeScript:
[`reference/errors.md`](../reference/errors.md).

## События

Объявите, что вам нужно; раннер подписывается, переподключается и
диспетчеризует.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

Типизированные события сегодня: `StateChangedEvent`, `CommandTriggeredEvent`,
`CommandCompletedEvent`. События чата — отдельный поток —
`on_conversation_event`, питаемый общим потоком демона, для плагинов
`client`.

`on_chat_sync` / `ChatSyncEvent` не существуют. Событие выведено из
обращения, и ни у одного SDK нет такого метода; если вы переносите код,
который его использовал, используйте `is_client()` плюс
`on_conversation_event`.

## Тестирование

Два уровня, оба поставляются вместе с SDK, так что ваш `Cargo.toml` остаётся
в одну строку.

| | Что запускает | Что может видеть |
|---|---|---|
| `testing::Harness` | хуки, в процессе, против `RecordingHost` | инструменты, действия, триггеры, конфиг, события, UI-вызовы и каждый вызов хоста, который вы сделали |
| `testing::WireHarness` | настоящий процесс, запущенный так же, как его запускает демон | регистрацию, токен сессии, потоковое аудио — всё, что видно только с провода |

`RecordingHost` даёт вам `fired_triggers()`, `logs()`, `variables()`,
`ui_pushes()`, `chat_messages()`, плюс `deny(rpc)`, `fail(rpc, err)` и
`fail_next(rpc, err)`, чтобы инсценировать сбои, с которыми столкнутся ваши
пользователи.

И на уровень выше обоих: `astra-plugin test` запускает ваш собранный
бинарник против мок-демона и прогоняет каждый хук, который подразумевают
ваши возможности. Ей неважно, на каком языке написан плагин.

## Чего этот SDK пока не умеет

- **`ctx.daemon()` / `DaemonClient` нефункциональны.** Демон ограничивает
  токен сессии каждого плагина `PluginHostService`, так что все семь
  сервисов отвечают `permission_denied` — включая плагины с `client =
  true`. Используйте `Host::send_chat_message`. См.
  [`Daemon`](#daemon--присутствует-в-sdk-отклоняется-демоном) выше.
- **`TtsSynthesizeStream` привязан, но не маршрутизирован.** SDK его
  обслуживает; точки вызова у демона нет. Реализуйте его, если хотите —
  никто его не вызовет, пока [таблица паритета](../reference/parity.md) не
  скажет `live`.
- **`AiGetModels` устарел** (0.6, удалён в 0.8), и его никто не вызывает:
  выбор модели жёстко задаёт `supports_model_discovery = false`. Замены нет;
  `AiComplete` несёт выбранную модель прямо в запросе.
- **Поверхность трейта 0.5 сохраняется как `astra_plugin_sdk::compat`**,
  устарела в 0.6 и удалена в 0.8. См. [переход на 0.6](../migration-0.6.md).
- **`PluginCapability::source_id()`** устарел: передавайте id в
  `Host::send_chat_message`, поскольку демон перестал фильтровать по id
  источника.
- **Входящей авторизации сервера возможностей не нужна настройка.** Демон
  предъявляет `x-plugin-token` при каждом вызове и устанавливает
  `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, так что SDK отклоняет вызов без
  него. Только демон, слишком старый, чтобы отправлять заголовок, оставляет
  вас на стадии `warn`; см. [архитектуру](../1-orientation/architecture.md).

## См. также

[Таблица хуков для Rust](../hooks/rust.md) · [паритет](../reference/parity.md) ·
[ошибки](../reference/errors.md) ·
[политика версионирования и устаревания](../versioning.md)
