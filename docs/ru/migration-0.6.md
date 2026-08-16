# Переход плагина на SDK 0.6

> Перевод. Источник истины — [docs/en](../en/migration-0.6.md); при расхождении верна английская версия.

Для того, у кого есть рабочий плагин эпохи 0.5. Изложено в том порядке, в
котором вы столкнётесь с проблемами: **что ломается во время выполнения
ещё до того, как вы измените хоть строку**, затем что ломается при
компиляции, затем что компилируется, но ведёт себя иначе, затем что просто
предупреждает.

Релизный поезд — `sdk-v0.6.0`: крейт Rust идёт на 0.6.0, пакеты Python и
TypeScript — на 0.5.0. См. [versioning.md](versioning.md), почему числа
различаются.

Каждый фрагмент ниже — реальный код из этого репозитория — девять примеров
на Rust были перенесены на 0.6 в коммите `134f6d1`, так что обе стороны
каждого диффа существуют в git и процитированы оттуда.

---

## 0. Почему нельзя остаться там, где вы есть

Это не релиз «приятного нового API». **Плагин 0.5 уже сломан против
текущего демона**, ещё до того, как вы что-либо измените:

> `HostClient` версии 0.5 не отправляет `x-session-token`, и демон отвечает
> `unauthenticated` на каждый RPC хоста, кроме `Register`.

Так что `fire_trigger`, `set_variable`, `log`, `push_to_ui` и остальные
проваливаются во время выполнения, на машине не вашей, с сообщением,
которое ваш пользователь прочтёт как «плагин сломан». Регистрация всё ещё
проходит успешно, что и запутывает: плагин выглядит запустившимся, а
затем ничего не делает.

Это вся причина, по которой существует 0.6, и причина, по которой API
написания разрешили сменить в том же релизе.

---

## 1. Быстрый путь (Rust): одна строка, и оно собирается

Если вам нужно, чтобы плагин работал сегодня, а миграция — на следующей
неделе, поменяйте импорт:

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

Это весь дифф. `compat` — это трейт 0.5, типы результатов 0.5 и формы
`HostClient`/`DaemonClient` 0.5, переброшенные на трейт 0.6 через общую
(blanket) реализацию. Проверено на реальном 0.5 dice-roller — 255 строк,
неизменённых, кроме этой строки:

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

(По одному предупреждению на каждый устаревший элемент, которого вы
касаетесь — здесь их одиннадцать, плюс одно `unused_mut`, потому что
старому `let mut h = host.lock().await` он больше не нужен.)

Оно собирается, инструменты отвечают, и хост, который хранился в
`set_host`, всё ещё достаёт до демона. Собственный набор тестов SDK это
закрепляет: семь тестов, написанных *против трейта 0.5*, прогоняются через
harness 0.6, в `astra-plugin-sdk/src/capability.rs` (`mod compat::tests`).

Три вещи, которые стоит знать перед тем, как на это полагаться:

- **`compat::*` заменяет `prelude::*`; это не добавление.** Импортируйте
  оба, и у вас в области видимости окажутся два трейта с именем
  `PluginCapability`, и `impl PluginCapability for MyPlugin` станет
  неоднозначным (E0659) вместо устаревшего.
- **Он исчезнет в 0.8** — два minor-релиза, согласно
  [versioning.md](versioning.md).
- **Хуки, которых никогда не было в 0.5, остаются отсутствующими.**
  `ai_complete`, `tts_activate`, `stt_load` / `stt_unload` /
  `stt_load_state` отвечают `UNIMPLEMENTED` через шим, что протокол
  читает как *хук отсутствует*. Чтобы их реализовать, нужно
  мигрировать трейт.

`compat::*` также реэкспортирует имена 0.6 — `PluginContext`,
`ToolError`, `Host`, `Daemon`, `Config`, `NoConfig` — так что вы можете
переносить хуки на новые сигнатуры по одному, без изменения строки
импорта. Когда перенесён последний, поменяйте `compat::*` обратно на
`prelude::*`, и предупреждения исчезнут.

Остальная часть этого документа — как раз эта миграция.

---

## 2. Что ломается при компиляции (Rust)

Это реальные ошибки от сборки неизменённого dice-roller 0.5 против
0.6 — 15 штук, пяти видов.

### 2.1 `Config` — обязательный ассоциированный тип

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

Если у вашего плагина нет настроек, это одна строка:

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

Если есть — объявите тип и реализуйте `on_config` — SDK разберёт JSON
демона за вас. bad-apple, до (`examples/bad-apple/src/main.rs` на
`134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

и после (`examples/bad-apple/src/main.rs`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

Двадцать строк превратились в две, а поле неверного типа теперь
сообщается вместо того, чтобы молча пропускаться.

> **Используйте `#[serde(default)]` (или `#[astra::config]`, который его
> добавляет).** Первая полезная нагрузка настроек, которую демон
> отправляет свежеустановленному плагину, — `{}`. Тип конфигурации с
> обязательным полем её отклоняет, `on_config` тогда не вызывается вообще
> ни разу, и ваш плагин обслуживает каждый вызов на `Config::default()` —
> пустой API-ключ, имя триггера, являющееся пустой строкой. SDK громко
> предупреждает именно об этом случае, но панель логов — не то место,
> куда вы смотрите.

`Config<T>` — это безблокировочное хранилище для этого: `self.config.load()`
— одно атомарное чтение, и перезапись конфига посреди вызова инструмента
не может его заблокировать.

### 2.2 Обработчики принимают `&PluginContext`

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

Добавьте `ctx: &PluginContext` (или `_ctx`) после `&self`. Он несёт
`plugin_id`, `language`, `active_triggers`, `host` и `daemon`; его дёшево
клонировать; он никогда не `None`. mock-stt, до и после:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS одновременно свернул свои четыре аргумента в один `TtsRequest` —
tone-tts перешёл от `(&self, text, voice_id, speed, _pitch)` к
`(&self, _ctx, req: TtsRequest)`, читая `req.text`, `req.voice_id`,
`req.speed`.

Из места, куда параметр не может дотянуться — запущенная задача, `Drop`,
коллбэк из чужого крейта — `astra_plugin_sdk::ctx()` возвращает тот же
контекст.

### 2.3 `set_host` и `set_daemon_client` исчезли

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

Удалите хук, удалите поле, используйте `ctx.host()`. Это стоит сделать
правильно, а не через шим, потому что форма 0.5 несла в себе дефект.
dice-roller, до (`examples/dice-roller/src/main.rs` на `134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

Когда другой вызов инструмента держал эту блокировку, `try_lock`
возвращал `None`, плагин логировал «host client not available yet» и
**ничего не запускал**. После:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

У `Arc<dyn Host>` нет блокировки, которую можно потерять. То же самое
касается клиентских плагинов: `ctx.daemon()` — это `Some` на протяжении
всей жизни плагина с возможностью `client`, так что каждая ветка «daemon
client not ready» исчезает. telegram-client лишился поля `SharedDaemon` и
этой проверки:

> `Some` — про сам хендл, а не про то, чего он может достичь. Демон
> ограничивает токен сессии каждого плагина `PluginHostService`, так что
> вызовы через `ctx.daemon()` сегодня отвечают `permission_denied` — см.
> [страницу Rust SDK](4-sdk/rust.md#daemon--присутствует-в-sdk-отклоняется-демоном).
> Этот раздел про форму миграции, а не про путь, который сегодня работает
> от начала до конца.

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` удалены

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

Обработчики возвращают `Result<String, ToolError>` (`ActionError` —
псевдоним `ToolError`). Отображение механическое:

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`, или просто `?` при разборе |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

Тип ошибки — не декорация. Именно он говорит циклу ИИ, может ли повтор
хоть чем-то помочь, а `NotConfigured { field }` — именно то, что
превращает «инструмент провалился» в ссылку на конкретное поле настроек.
bad-apple, после:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

Заметьте `?` на `serde_json::to_string`: реализации `From` существуют для
`serde_json::Error`, `std::io::Error`, `tonic::Status` и `anyhow::Error`,
и каждое преобразование — это утверждение о том, какого рода сбой
произошёл — `serde_json::from_str(args)?` внутри `call_tool` означает
`BAD_ARGUMENTS`, единственный сбой, который модель может исправить, попробовав
снова.

Если вместо этого идти через шим, каждый сбой 0.5 становится
`ToolError::Internal`, несущим ту же фразу. Это честное прочтение строки,
чей автор так и не сказал, чем она была, и это хуже, чем то, что вы
можете сказать сами за пять минут.

### 2.5 Более мелкие поломки на этапе компиляции

| Что | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | хук | **удалён.** Демон передаёт `[capabilities]` манифеста в `ASTRA_PLUGIN_CAPABILITIES` |
| `ActiveTriggers::contains` / `update` | `async`, `tokio::RwLock` | синхронно (`ArcSwap`), и `update` теперь `set` |
| `HostClient::new(..)` | конструируем | только `connect_bootstrap` → `register` → аутентифицированный клиент |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | работало | плейсхолдеры, проваливающиеся с фразой: используйте `#[astra::args]`, или добавьте `serde` в собственный `Cargo.toml` |
| `on_shutdown()`, `on_event()`, `on_state_changed()` и другие хуки событий | без `ctx` | `ctx` первым, как и всё остальное |

---

## 3. Что ломается во время выполнения (компилируется, но ведёт себя иначе)

### 3.1 `[permissions]` по умолчанию всё запрещает

То, что укусит первым на машине пользователя, и это вообще не изменение
SDK — это фаза 4. Манифест без раздела `[permissions]` может вызывать
`Register`, `PluginLog` и `GetPluginSelfConfig`, и **больше ничего**.
`fire_trigger`, `set_variable`, `push_to_ui`, `send_chat_message`,
`subscribe_events` и `set_theme_contribution` — каждому нужно объявленное
и выданное разрешение, а отказ приходит как `PERMISSION_DENIED` →
`ToolError::Unauthorized`.

Объявить возможность недостаточно. Из `examples/dice-roller/plugin.toml`:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

`reason` показывается пользователю в момент установки. Пишите его для
него.

### 3.2 Порядок запуска и `on_start`

0.6 исправляет порядок: bind → register → build ctx → `on_config` →
`on_language_changed` → `on_start` → serve. `on_start` — новый, и
возврат `Err` из него **прерывает запуск**: процесс выходит с ненулевым
кодом вместо того, чтобы оставить плагина, которого демон считает
здоровым и который проваливает каждый вызов одинаково.

Здесь место разогреву и фоновым задачам. echo-stt перенёс свой аудиопоток
туда, из `main`; telegram-client перенёс весь запуск бота из
`set_daemon_client`, что и убрало гонку с `on_config_changed`:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 Поведение, которое изменилось молча

- **У `ActiveTriggers` теперь есть писатель.** В 0.5 в него никто никогда
  не писал, так что `contains()` всегда отвечал false. Если вы охраняли
  дорогую полезную нагрузку этим, охрана всегда была закрыта, а теперь
  открыта — полезная нагрузка будет построена.
- **Аудио-канал STT держит 500 чанков, а не 32.** Потоковый распознаватель,
  тихо ронявший аудио под нагрузкой, больше этого не делает. Если вы
  компенсировали потери — перестаньте.
- **`source_id()` больше ни на что не влияет.** Демон перестал фильтровать
  по id источника; каждый клиент видит каждое событие. Устарел в 0.6,
  исчез в 0.8. Передавайте id в `Host::send_chat_message` вместо этого.
- **Возможности приходят от демона**, в `ASTRA_PLUGIN_CAPABILITIES**, а не
  из интроспекции того, какие ваши методы возвращают непустой вектор.
  Плагин, чьи заявленные возможности раньше расходились с манифестом,
  теперь заявляет манифест — именно то, на что согласился пользователь.

---

## 4. Что просто предупреждает

| Предупреждение | Дедлайн | Делайте вместо этого |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | трейт 0.6 — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | удалите переопределение |
| Python `DeprecationWarning: … returned a dict` | 0.7 | возвращайте dataclass |
| `AiGetModels` / `ai_models()` | 0.8 | ничего — демон никогда не спрашивает |

Ничто в этой таблице ещё не является ошибкой, и ничто из этого не станет
ею в пределах одного minor: см. [versioning.md](versioning.md) насчёт
гарантии и того, как она обеспечивается.

---

## 5. Python

Пакет переходит с 0.4.0 на 0.5.0. Класс всё ещё `Plugin`, а декораторы всё
ещё `@tool` / `@action` / `@trigger`, так что большинство файлов меняется
очень мало.

**Сбои теперь кодированы.** `call_tool` и `execute_action` раньше ловили
каждое `Exception` и сплющивали его в `{"success": False, "error":
str(e)}` — именно поэтому каждый сбой выглядел одинаково. Вместо этого
бросьте одну из восьми ошибок, и SDK заполнит и старую строку, и
структурированный `error_detail`:

Из `examples/text-utils/src/plugin.py`:

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` — это та, что становится ссылкой на
конкретное поле настроек.

Что ещё проверить:

- **`stt_transcribe` принимает третий параметр**, `options: SttOptions |
  None`. Переопределение с двумя аргументами продолжает работать —
  сервисёр разбирает вашу сигнатуру один раз и передаёт только то, что вы
  принимаете, — так что это опционально, а добавление `options=None` — это
  как получить подсказку языка от демона и смещение слова активации.
- **Возвращайте dataclass, а не словари**, из хуков возможностей. Словари
  всё ещё работают и выдают `DeprecationWarning`, называя класс, который
  нужно вернуть; они уходят в 0.7.
- **`HostClient` нельзя сконструировать неаутентифицированным.**
  `HostClientBootstrap(addr, plugin_id).register(...)` возвращает
  настоящий.
- **`@ui_call` / `@ui_page` теперь регистрируются.** Раньше это были
  `@staticmethod`, возвращающие словарь, который вызывающая сторона
  отбрасывала.
- Завяжите CI на предупреждениях: `python -W error::DeprecationWarning -m
  pytest`.

## 6. TypeScript

Пакет переходит с 0.4.0 на 0.5.0, и опубликованное имя — `astra-plugin-sdk`
— не `@astra/plugin-sdk`, как раньше говорилось в четырёх местах.

- **Сбои кодированы**, те же восемь, что и везде, и `code` — строковый
  литерал у каждого класса, так что `switch (err.code) { case
  "NOT_CONFIGURED": … }` сужает до подкласса и достаёт `err.configField`
  без приведения типов.
- **Конструктор `HostClient` приватный**; `HostClient.register(...)` —
  единственный способ его получить, и он бросает `RegistrationError`, если
  демон отказывает.
- **Клиенты загружают собственный сгенерированный дескриптор SDK** вместо
  двух вручную поддерживаемых inline-строк proto и проверяют каждый метод,
  который они будут вызывать, в момент подключения — рассогласование
  становится `ProtoContractError` при старте, а не `TypeError` на первом
  вызове.
- **`UiPanel` устарел**; это псевдоним для `UiContribution`.
- Если ваш `package.json` старше 0.5.0, обратите внимание на новую карту
  `exports`, `"type": "commonjs"`, `engines: { node: ">=20" }` и двойной
  вывод CJS+ESM.

---

## 7. Проверка миграции

Astra не нужна установленной, чтобы узнать, сработал ли перенос. SDK 0.6
поставляют тестовый harness, запускающий ваши обработчики в том же
процессе против записывающего хоста:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

Именно этот тест и был тем, как приняли шим: `DiceRoller` там — это
dice-roller версии **0.5**, неизменённый, кроме строки импорта, работающий
на 0.6. Никакого демона, никакого сокета, никакой установленной Astra —
`Harness` строит `PluginContext` вокруг записывающего хоста, так что
`fired_triggers()` — это список, на котором можно делать проверки.

Короткий чек-лист:

1. Собирается без импорта `compat::`.
2. В вашем `plugin.toml` есть раздел `[permissions]` для каждого RPC
   хоста, который вы вызываете, у каждого — `reason`, написанный для
   пользователя.
3. `on_config` видит `{}`, не падая, — это свежая установка.
4. Всё, что вы раньше делали в `set_host` / `set_daemon_client`,
   происходит в `on_start`, и `on_start` возвращает `Err`, когда плагин
   действительно не может работать.
5. Каждый `ToolResult::err` превратился в вариант `ToolError`, называющий
   причину.
