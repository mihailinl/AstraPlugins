# Rust SDK

> Переклад. Джерело істини — [docs/en](../../en/4-sdk/rust.md); за розбіжності відповідає англійська версія.

`astra-plugin-sdk` 0.6.0. Одна залежність, і все, у що розгортаються макроси,
приходить через неї.

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 — перший реліз, чий `HostClient` прикріплює `x-session-token`. Проти 0.5
і старіших демон відповідає `unauthenticated` на кожен виклик хоста, тож не
послаблюйте цю межу.

## Форма плагіна

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

`#[astra::plugin]` реалізує `PluginCapability` зі знайдених хуків і виводить
з них оголошений набір можливостей — тож плагін не може заявити можливість,
яку не обслуговує його код. `astra-plugin check` звіряє це з `plugin.toml`.

## Шар макросів

| | Для чого |
|---|---|
| `#[astra::plugin]` | На блоці `impl`. Перетворює члени нижче на реалізацію трейта |
| `#[tool]` | Функція, яку може викликати модель. Doc-коментар — її опис |
| `#[action(label = "…")]` | Крок у редакторі команд |
| `#[hook]` | Будь-який інший метод `PluginCapability`, за ім'ям |
| `#[ui_call]` | Метод, який може викликати назад ваш UI-внесок |
| `#[astra::args]` | На структурі аргументів інструмента |
| `#[astra::config]` | На вашій структурі налаштувань — `args` плюс `#[serde(default)]` |
| `astra::main!(Plugin::default())` | `main`, що його запускає |

**Чому `#[astra::args]`, а не `#[derive(Deserialize, JsonSchema)]`:** дерайв
serde розгортається в `extern crate serde as _serde`, яке розв'язується в
extern prelude і недосяжне через ре-експорт. Звичайний дерайв тому вимагав
би `serde` у вашому власному `Cargo.toml` — а саме про це обіцянка про одну
залежність. `#[astra::args]` — це ті самі два дерайви з `crate = "…"`, що
вказує на копії SDK. Додати `serde` самостійно все ще можна; тоді `use
serde::Deserialize;` затінить ім'я з prelude.

Ви також можете реалізувати `PluginCapability` вручну. Трейт публічний, у
кожного методу є реалізація за замовчуванням, і макроси виробляють рівно те,
що ви б написали самі.

## `PluginContext`

Кожному обробнику передається `&PluginContext`. Він ніколи не `None`, його
дешево клонувати у фонове завдання, і це означає, що нічого не повинно
лежати на вашій структурі за блокуванням.

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — десять RPC хоста. Присутній завжди |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **`Some` лише для плагінів `client`** |
| `ctx.language()` | Мова інтерфейсу Astra, оновлюється через `OnLanguageChanged` |
| `ctx.active_triggers()` | Які з ваших типів тригерів слухає зараз команда |
| `ctx.plugin_id()` | Ваш id |

З місця, куди параметр не може дотягнутися, — реалізація `Drop`, колбек з
C-бібліотеки, `std::thread`, запущений при старті, — `astra_plugin_sdk::ctx()`
повертає контекст працюючого плагіна, а `try_ctx()` — його версію, що може
провалитися.

### `Host` — десять викликів назовні

| Метод | Дозвіл |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | немає |
| `get_config` | немає |
| `get_daemon_info` | немає |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` приймає **три** аргументи — ім'я, значення і область
видимості. Підписки на події не на `Host`: оголосіть `subscribed_events()`,
і раннер сам володіє потоком (нижче).

`Host` — це трейт, тож тест може підставити `RecordingHost` і перевірити, що
ваш плагін повідомив Astra.

### `Daemon` — присутній у SDK, відхиляється демоном

> **`ctx.daemon()` сьогодні не працює, для жодного плагіна.** Половина на
> боці демона не побудована. Кожен плагін — `client = true` чи ні —
> реєструється як `ClientType::PluginClient`, і перехоплювач авторизації
> демона відхиляє цю ідентичність на **будь-якому** шляху, що не
> починається з `/astra.PluginHostService/`, з `permission_denied("plugin
> session tokens are scoped to PluginHostService")`. `DaemonClient`
> підключається рівно з цим токеном (`astra-plugin-sdk/src/host_client.rs`
> передає `client_session_token` в `DaemonClient::connect`), тож кожен
> виклик нижче — `submit_user_message`, `subscribe_chat_events`, `speak`,
> `get_settings` — повертає `permission_denied` під час виконання. Канарка в
> `consistency.rs` демона тримає цю перевірку області дії на місці, тож це
> навмисне рішення, а не регресія: зворотна половина автентифікації не
> побудована, а не зламана.
>
> **`Host::send_chat_message` — єдиний робочий спосіб вести хід ШІ**, і він
> працює для будь-якого плагіна, якому видано `send_chat_message`.

Поверхня API, на випадок коли сторона демона буде добудована: `ctx.daemon()`
— це `Some` лише коли плагін оголошує `client = true` і `is_client()`
повертає true. Він дістає до семи сервісів — core, chat, voice, command,
config, media, monitor — з методами включно з `submit_user_message`,
`subscribe_chat_events`, `stop_generation`, `list_conversations`, `speak`,
`start_listening`, `execute_command`, `get_settings`, `get_system_stats`. Це
`submit_user_message`, а не `send_message`.

## Помилки

Обробники повертають `Result<_, ToolError>` (`ActionError` — псевдонім того
самого типу). Помилка окремого виклику — це дані, які читає й за якими діє
цикл ШІ, тому вона їде у відповіді, а не як статус gRPC.

| Варіант | Використовуйте, коли |
|---|---|
| `BadArguments(String)` | Модель може це виправити, викликавши по-іншому |
| `NotFound(String)` | Невідомий id, 404 |
| `NotConfigured { field, message }` | Відсутнє налаштування. `field` — ціль для глибокого посилання |
| `Unauthorized(String)` | Облікові дані відхилені, або дозвіл не було видано |
| `RateLimited { retry_after, message }` | Квота вищерозташованого сервісу. `None` означає «невідомо», а не «негайно» |
| `Unavailable(String)` | Залежність недоступна; повторіть пізніше без змін |
| `Timeout(String)` | Закінчився час |
| `Internal(String)` | Баг. Модель нічого з цим не зробить |

`?` працює з `serde_json::Error`, `std::io::Error`, `tonic::Status` і
`anyhow::Error`. `with_doc_url(…)` огортає будь-яку з них сторінкою, що
документує саме цей збій, яку UI рендерить як посилання.

Повна таксономія, включно з рядками дроту й написанням у Python/TypeScript:
[`reference/errors.md`](../reference/errors.md).

## Події

Оголосіть, що вам потрібно; раннер підписується, перепідключається і
диспетчеризує.

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

Типізовані події сьогодні: `StateChangedEvent`, `CommandTriggeredEvent`,
`CommandCompletedEvent`. Події чату — окремий потік — `on_conversation_event`,
що живиться зі спільного потоку демона, для плагінів `client`.

`on_chat_sync` / `ChatSyncEvent` не існують. Подію виведено з обігу, і в
жодного SDK немає такого методу; якщо ви переносите код, що його
використовував, використовуйте `is_client()` плюс `on_conversation_event`.

## Тестування

Два рівні, обидва постачаються разом з SDK, тож ваш `Cargo.toml`
залишається в один рядок.

| | Що запускає | Що може бачити |
|---|---|---|
| `testing::Harness` | хуки, у процесі, проти `RecordingHost` | інструменти, дії, тригери, конфіг, події, UI-виклики і кожен виклик хоста, який ви зробили |
| `testing::WireHarness` | справжній процес, запущений так само, як його запускає демон | реєстрацію, токен сесії, потокове аудіо — усе, що видно лише з дроту |

`RecordingHost` дає вам `fired_triggers()`, `logs()`, `variables()`,
`ui_pushes()`, `chat_messages()`, плюс `deny(rpc)`, `fail(rpc, err)` і
`fail_next(rpc, err)`, щоб інсценувати збої, з якими зіткнуться ваші
користувачі.

І на рівень вище обох: `astra-plugin test` запускає ваш зібраний бінарник
проти мок-демона і прогонить кожен хук, який передбачають ваші можливості.
Їй байдуже, якою мовою написаний плагін.

## Чого цей SDK поки не вміє

- **`ctx.daemon()` / `DaemonClient` нефункціональні.** Демон обмежує токен
  сесії кожного плагіна `PluginHostService`, тож усі сім сервісів
  відповідають `permission_denied` — включно з плагінами з `client = true`.
  Використовуйте `Host::send_chat_message`. Див.
  [`Daemon`](#daemon--присутній-у-sdk-відхиляється-демоном) вище.
- **`TtsSynthesizeStream` прив'язаний, але не маршрутизований.** SDK його
  обслуговує; точки виклику в демона немає. Реалізуйте його, якщо хочете —
  ніхто його не викличе, поки [таблиця паритету](../reference/parity.md) не
  скаже `live`.
- **`AiGetModels` застарів** (0.6, видалений у 0.8), і його ніхто не
  викликає: вибір моделі жорстко задає `supports_model_discovery = false`.
  Заміни немає; `AiComplete` несе обрану модель прямо в запиті.
- **Поверхня трейта 0.5 зберігається як `astra_plugin_sdk::compat`**,
  застаріла в 0.6 і видалена в 0.8. Див. [перехід на 0.6](../migration-0.6.md).
- **`PluginCapability::source_id()`** застарів: передавайте id в
  `Host::send_chat_message`, оскільки демон перестав фільтрувати за id
  джерела.
- **Вхідній авторизації сервера можливостей не потрібне налаштування.**
  Демон пред'являє `x-plugin-token` при кожному виклику і встановлює
  `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, тож SDK відхиляє виклик без нього.
  Лише демон, надто старий, щоб надсилати заголовок, залишає вас на стадії
  `warn`; див. [архітектуру](../1-orientation/architecture.md).

## Див. також

[Таблиця хуків для Rust](../hooks/rust.md) · [паритет](../reference/parity.md) ·
[помилки](../reference/errors.md) ·
[політика версіонування та застарівання](../versioning.md)
