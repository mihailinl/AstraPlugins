# Перехід плагіна на SDK 0.6

> Переклад. Джерело істини — [docs/en](../en/migration-0.6.md); за розбіжності відповідає англійська версія.

Для того, у кого є робочий плагін епохи 0.5. Викладено в тому порядку, в
якому ви зіткнетеся з проблемами: **що ламається під час виконання ще до
того, як ви зміните хоч рядок**, потім що ламається при компіляції, потім
що компілюється, але поводиться інакше, потім що просто попереджає.

Релізний потяг — `sdk-v0.6.0`: крейт Rust іде на 0.6.0, пакети Python і
TypeScript — на 0.5.0. Див. [versioning.md](versioning.md), чому числа
відрізняються.

Кожен фрагмент нижче — реальний код з цього репозиторію — дев'ять
прикладів на Rust були перенесені на 0.6 в коміті `134f6d1`, тож обидві
сторони кожного діфу існують у git і процитовані звідти.

---

## 0. Чому не можна лишитися там, де ви є

Це не реліз «приємного нового API». **Плагін 0.5 вже зламаний проти
поточного демона**, ще до того, як ви щось зміните:

> `HostClient` версії 0.5 не надсилає `x-session-token`, і демон відповідає
> `unauthenticated` на кожен RPC хоста, крім `Register`.

Тож `fire_trigger`, `set_variable`, `log`, `push_to_ui` та інші
провалюються під час виконання, на машині не вашій, з повідомленням, яке
ваш користувач прочитає як «плагін зламаний». Реєстрація все ще проходить
успішно, що і заплутує: плагін виглядає таким, що запустився, а потім
нічого не робить.

Це вся причина, чому існує 0.6, і причина, чому API написання дозволили
змінити в тому самому релізі.

---

## 1. Швидкий шлях (Rust): один рядок, і воно збирається

Якщо вам потрібно, щоб плагін працював сьогодні, а міграція — наступного
тижня, поміняйте імпорт:

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

Це весь дифф. `compat` — це трейт 0.5, типи результатів 0.5 і форми
`HostClient`/`DaemonClient` 0.5, переброшені на трейт 0.6 через загальну
(blanket) реалізацію. Перевірено на реальному 0.5 dice-roller — 255
рядків, незмінених, крім цього рядка:

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
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

(По одному попередженню на кожен застарілий елемент, якого ви торкаєтеся —
тут їх одинадцять, плюс одне `unused_mut`, тому що старому `let mut h =
host.lock().await` він більше не потрібен.)

Воно збирається, інструменти відповідають, і хост, що зберігався в
`set_host`, все ще дістає до демона. Власний набір тестів SDK це
закріплює: сім тестів, написаних *проти трейта 0.5*, прогонюються через
harness 0.6, в `astra-plugin-sdk/src/capability.rs` (`mod compat::tests`).

Три речі, які варто знати перед тим, як на це покладатися:

- **`compat::*` замінює `prelude::*`; це не додавання.** Імпортуйте обидва,
  і у вас в області видимості опиняться два трейти з ім'ям
  `PluginCapability`, і `impl PluginCapability for MyPlugin` стане
  неоднозначним (E0659) замість застарілого.
- **Він зникне в 0.8** — два minor-релізи, згідно з
  [versioning.md](versioning.md).
- **Хуки, яких ніколи не було в 0.5, залишаються відсутніми.**
  `ai_complete`, `tts_activate`, `stt_load` / `stt_unload` /
  `stt_load_state` відповідають `UNIMPLEMENTED` через шим, що протокол
  читає як *хук відсутній*. Щоб їх реалізувати, треба мігрувати трейт.

`compat::*` також реекспортує імена 0.6 — `PluginContext`, `ToolError`,
`Host`, `Daemon`, `Config`, `NoConfig` — тож ви можете переносити хуки на
нові сигнатури по одному, без зміни рядка імпорту. Коли перенесений
останній, поміняйте `compat::*` назад на `prelude::*`, і попередження
зникнуть.

Решта цього документа — саме ця міграція.

---

## 2. Що ламається при компіляції (Rust)

Це реальні помилки від збірки незміненого dice-roller 0.5 проти 0.6 — 15
штук, п'яти видів.

### 2.1 `Config` — обов'язковий асоційований тип

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

Якщо у вашого плагіна немає налаштувань, це один рядок:

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

Якщо є — оголосіть тип і реалізуйте `on_config` — SDK розбере JSON демона
за вас. bad-apple, до (`examples/bad-apple/src/main.rs` на `134f6d1^`):

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

і після (`examples/bad-apple/src/main.rs`):

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

Двадцять рядків перетворилися на два, а поле неправильного типу тепер
повідомляється замість того, щоб мовчки пропускатися.

> **Використовуйте `#[serde(default)]` (або `#[astra::config]`, який його
> додає).** Перше корисне навантаження налаштувань, яке демон надсилає
> свіжовстановленому плагіну, — `{}`. Тип конфігурації з обов'язковим
> полем його відхиляє, `on_config` тоді не викликається взагалі жодного
> разу, і ваш плагін обслуговує кожен виклик на `Config::default()` —
> порожній API-ключ, ім'я тригера, що є порожнім рядком. SDK голосно
> попереджає саме про цей випадок, але панель логів — не те місце, куди
> ви дивитеся.

`Config<T>` — це безблокувальне сховище для цього: `self.config.load()` —
одне атомарне читання, і перезапис конфіга посеред виклику інструмента не
може його заблокувати.

### 2.2 Обробники приймають `&PluginContext`

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

Додайте `ctx: &PluginContext` (або `_ctx`) після `&self`. Він несе
`plugin_id`, `language`, `active_triggers`, `host` і `daemon`; його дешево
клонувати; він ніколи не `None`. mock-stt, до і після:

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

TTS одночасно згорнув свої чотири аргументи в один `TtsRequest` —
tone-tts перейшов від `(&self, text, voice_id, speed, _pitch)` до
`(&self, _ctx, req: TtsRequest)`, читаючи `req.text`, `req.voice_id`,
`req.speed`.

З місця, куди параметр не може дотягнутися — запущене завдання, `Drop`,
колбек з чужого крейта — `astra_plugin_sdk::ctx()` повертає той самий
контекст.

### 2.3 `set_host` і `set_daemon_client` зникли

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
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

Видаліть хук, видаліть поле, використовуйте `ctx.host()`. Це варто зробити
правильно, а не через шим, тому що форма 0.5 несла в собі дефект.
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

Коли інший виклик інструмента тримав це блокування, `try_lock` повертав
`None`, плагін логував «host client not available yet» і **нічого не
запускав**. Після:

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

У `Arc<dyn Host>` немає блокування, яке можна втратити. Те саме
стосується клієнтських плагінів: `ctx.daemon()` — це `Some` протягом
усього життя плагіна з можливістю `client`, тож кожна гілка «daemon
client not ready» зникає. telegram-client позбувся поля `SharedDaemon` і
цієї перевірки:

> `Some` — про сам хендл, а не про те, чого він може досягти. Демон
> обмежує токен сесії кожного плагіна `PluginHostService`, тож виклики
> через `ctx.daemon()` сьогодні відповідають `permission_denied` — див.
> [сторінку Rust SDK](4-sdk/rust.md#daemon-присутній-у-sdk-відхиляється-демоном).
> Цей розділ про форму міграції, а не про шлях, який сьогодні працює від
> початку до кінця.

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` видалені

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

Обробники повертають `Result<String, ToolError>` (`ActionError` —
псевдонім `ToolError`). Відображення механічне:

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`, або просто `?` при розборі |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

Тип помилки — не декорація. Саме він каже циклу ШІ, чи може повтор
хоч чимось допомогти, а `NotConfigured { field }` — саме те, що
перетворює «інструмент провалився» на посилання на конкретне поле
налаштувань. bad-apple, після:

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

Зверніть увагу на `?` на `serde_json::to_string`: реалізації `From`
існують для `serde_json::Error`, `std::io::Error`, `tonic::Status` і
`anyhow::Error`, і кожне перетворення — це твердження про те, якого роду
збій стався — `serde_json::from_str(args)?` всередині `call_tool` означає
`BAD_ARGUMENTS`, єдиний збій, який модель може виправити, спробувавши
знову.

Якщо натомість йти через шим, кожен збій 0.5 стає `ToolError::Internal`,
що несе ту саму фразу. Це чесне прочитання рядка, чий автор так і не
сказав, чим він був, і це гірше, ніж те, що ви можете сказати самі за
п'ять хвилин.

### 2.5 Менші поломки на етапі компіляції

| Що | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | хук | **видалений.** Демон передає `[capabilities]` маніфесту в `ASTRA_PLUGIN_CAPABILITIES` |
| `ActiveTriggers::contains` / `update` | `async`, `tokio::RwLock` | синхронно (`ArcSwap`), і `update` тепер `set` |
| `HostClient::new(..)` | конструйований | лише `connect_bootstrap` → `register` → автентифікований клієнт |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | працювало | плейсхолдери, що провалюються з фразою: використовуйте `#[astra::args]`, або додайте `serde` до власного `Cargo.toml` |
| `on_shutdown()`, `on_event()`, `on_state_changed()` та інші хуки подій | без `ctx` | `ctx` першим, як і все інше |

---

## 3. Що ламається під час виконання (компілюється, але поводиться інакше)

### 3.1 `[permissions]` за замовчуванням усе забороняє

Те, що вкусить першим на машині користувача, і це взагалі не зміна SDK —
це фаза 4. Маніфест без розділу `[permissions]` може викликати
`Register`, `PluginLog` і `GetPluginSelfConfig`, і **більше нічого**.
`fire_trigger`, `set_variable`, `push_to_ui`, `send_chat_message`,
`subscribe_events` і `set_theme_contribution` — кожному потрібен
оголошений і виданий дозвіл, а відмова приходить як `PERMISSION_DENIED` →
`ToolError::Unauthorized`.

Оголосити можливість недостатньо. Із `examples/dice-roller/plugin.toml`:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

`reason` показується користувачу в момент встановлення. Пишіть його для
нього.

### 3.2 Порядок запуску і `on_start`

0.6 виправляє порядок: bind → register → build ctx → `on_config` →
`on_language_changed` → `on_start` → serve. `on_start` — новий, і
повернення `Err` з нього **перериває запуск**: процес виходить з
ненульовим кодом замість того, щоб залишити плагін, якого демон вважає
здоровим і який провалює кожен виклик однаково.

Тут місце розігріву і фоновим завданням. echo-stt переніс свій
аудіопотік туди, з `main`; telegram-client переніс весь запуск бота з
`set_daemon_client`, що й прибрало гонку з `on_config_changed`:

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

### 3.3 Поведінка, що змінилася мовчки

- **У `ActiveTriggers` тепер є писар.** У 0.5 у нього ніхто ніколи не
  писав, тож `contains()` завжди відповідав false. Якщо ви охороняли
  дороге корисне навантаження цим, охорона завжди була закрита, а тепер
  відкрита — навантаження буде побудоване.
- **Аудіо-канал STT тримає 500 чанків, а не 32.** Потоковий розпізнавач,
  що тихо втрачав аудіо під навантаженням, більше цього не робить. Якщо
  ви компенсували втрати — припиніть.
- **`source_id()` більше ні на що не впливає.** Демон перестав
  фільтрувати за id джерела; кожен клієнт бачить кожну подію. Застарів у
  0.6, зник у 0.8. Передавайте id в `Host::send_chat_message` натомість.
- **Можливості приходять від демона**, у `ASTRA_PLUGIN_CAPABILITIES`, а
  не з інтроспекції того, які ваші методи повертають непорожній вектор.
  Плагін, чиї заявлені можливості раніше розходилися з маніфестом, тепер
  заявляє маніфест — саме те, на що погодився користувач.

---

## 4. Що просто попереджає

| Попередження | Дедлайн | Робіть натомість |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | трейт 0.6 — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | видаліть перевизначення |
| Python `DeprecationWarning: … returned a dict` | 0.7 | повертайте dataclass |
| `AiGetModels` / `ai_models()` | 0.8 | нічого — демон ніколи не питає |

Ніщо в цій таблиці ще не є помилкою, і ніщо з цього не стане нею в межах
одного minor: див. [versioning.md](versioning.md) щодо гарантії і того,
як вона забезпечується.

---

## 5. Python

Пакет переходить з 0.4.0 на 0.5.0. Клас все ще `Plugin`, а декоратори все
ще `@tool` / `@action` / `@trigger`, тож більшість файлів змінюється дуже
мало.

**Збої тепер кодовані.** `call_tool` і `execute_action` раніше ловили
кожне `Exception` і сплющували його в `{"success": False, "error":
str(e)}` — саме тому кожен збій виглядав однаково. Натомість киньте одну
з восьми помилок, і SDK заповнить і старий рядок, і структурований
`error_detail`:

Із `examples/text-utils/src/plugin.py`:

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

`raise NotConfigured("api_key")` — це та, що стає посиланням на конкретне
поле налаштувань.

Що ще перевірити:

- **`stt_transcribe` приймає третій параметр**, `options: SttOptions |
  None`. Перевизначення з двома аргументами продовжує працювати —
  сервісер розбирає вашу сигнатуру один раз і передає лише те, що ви
  приймаєте, — тож це опціонально, а додавання `options=None` — це як
  отримати підказку мови від демона і зміщення слова активації.
- **Повертайте dataclass, а не словники**, з хуків можливостей. Словники
  все ще працюють і видають `DeprecationWarning`, називаючи клас, який
  треба повернути; вони йдуть у 0.7.
- **`HostClient` не можна сконструювати неавтентифікованим.**
  `HostClientBootstrap(addr, plugin_id).register(...)` повертає
  справжній.
- **`@ui_call` / `@ui_page` тепер реєструються.** Раніше це були
  `@staticmethod`, що повертали словник, який викликаюча сторона
  відкидала.
- Зав'яжіть CI на попередженнях: `python -W error::DeprecationWarning -m
  pytest`.

## 6. TypeScript

Пакет переходить з 0.4.0 на 0.5.0, і опубліковане ім'я —
`astra-plugin-sdk` — не `@astra/plugin-sdk`, як раніше говорилося в
чотирьох місцях.

- **Збої кодовані**, ті самі вісім, що й усюди, і `code` — рядковий
  літерал у кожного класу, тож `switch (err.code) { case
  "NOT_CONFIGURED": … }` звужує до підкласу і дістає `err.configField`
  без приведення типів.
- **Конструктор `HostClient` приватний**; `HostClient.register(...)` —
  єдиний спосіб його отримати, і він кидає `RegistrationError`, якщо
  демон відмовляє.
- **Клієнти завантажують власний згенерований дескриптор SDK** замість
  двох вручну підтримуваних inline-рядків proto і перевіряють кожен
  метод, який вони будуть викликати, в момент підключення —
  розбіжність стає `ProtoContractError` при старті, а не `TypeError` на
  першому виклику.
- **`UiPanel` застарілий**; це псевдонім для `UiContribution`.
- Якщо ваш `package.json` старіший за 0.5.0, зверніть увагу на нову
  карту `exports`, `"type": "commonjs"`, `engines: { node: ">=20" }` і
  подвійний вивід CJS+ESM.

---

## 7. Перевірка міграції

Astra не потрібна встановленою, щоб дізнатися, чи спрацювало перенесення.
SDK 0.6 постачають тестовий harness, що запускає ваші обробники в тому
самому процесі проти записувального хоста:

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

Саме цей тест і був тим, як прийняли шим: `DiceRoller` там — це
dice-roller версії **0.5**, незмінений, крім рядка імпорту, що працює на
0.6. Жодного демона, жодного сокета, жодної встановленої Astra —
`Harness` будує `PluginContext` навколо записувального хоста, тож
`fired_triggers()` — це список, на якому можна робити перевірки.

Короткий чек-лист:

1. Збирається без імпорту `compat::`.
2. У вашому `plugin.toml` є розділ `[permissions]` для кожного RPC
   хоста, який ви викликаєте, у кожного — `reason`, написаний для
   користувача.
3. `on_config` бачить `{}`, не падаючи, — це свіже встановлення.
4. Усе, що ви раніше робили в `set_host` / `set_daemon_client`,
   відбувається в `on_start`, і `on_start` повертає `Err`, коли плагін
   справді не може працювати.
5. Кожен `ToolResult::err` перетворився на варіант `ToolError`, що
   називає причину.
