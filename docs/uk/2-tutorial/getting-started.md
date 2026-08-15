# Початок роботи

> Переклад. Джерело істини — [docs/en](../../en/2-tutorial/getting-started.md); за розбіжності відповідає англійська версія.

Від нуля до плагіна, що кидає кості, має тести і упакований для релізу.
Приблизно п'ятнадцять хвилин, більшість з яких — очікування `cargo`.

Кожен блок коду на цій сторінці виконується
[`docs/tools/doctest.py`](../../tools/doctest.py) в CI. Якщо щось із цього
неправильне, збірка стає червоною раніше, ніж ви це прочитаєте.

## 1 · Встановіть CLI

Один рядок. Займає кілька хвилин і закінчується друком версії.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin 0.2.1
```

З клонованого репозиторію те саме робить
`cargo install --path astra-plugin-cli --locked`.

**Потрібен Rust 1.85 або новіший і `protoc` у PATH.** Без `protoc` збірка
зупиниться на ``Could not find `protoc` ``. Встановіть його через `apt install
protobuf-compiler`, `pacman -S protobuf`, `brew install protobuf` або `winget
install Google.Protobuf`, потім виконайте рядок знову.

**Беріть 0.2.1 або новіший.** `0.2.0` пише workflow релізу, який падає на
першому ж пуші тега, тож якщо `--version` друкує `0.2.0`, виконайте рядок
встановлення ще раз.

Одне застереження, яке вас не заблокує: CLI не на crates.io і не має готових
бінарників, тож збірка — єдиний спосіб його отримати. Готові бінарники
заплановані. Усі подробиці, включно з тим, що робити, якщо не працює:
[встановлення CLI](../install-cli.md).

Перевірте машину, перш ніж звинувачувати код:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Вона відповідає на шістнадцять питань за один прохід — який CLI ви
використовуєте, який каталог конфігурації вона визначила, чи доступна Astra,
які у вас є тулчейни (включно з `protoc`), і чи закріплений ваш workflow
релізу. Це перше, що варто запустити, коли щось незрозуміло.

## 2 · Створіть заготовку

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

П'ять файлів: `plugin.toml`, `Cargo.toml`, `src/main.rs`, `README.md`,
`.gitignore`. У `Cargo.toml` **одна** залежність, а `src/main.rs` —
п'ятнадцять рядків плюс тестовий модуль.

`--lang` приймає `rust`, `python` або `typescript`; `--template` обирає
можливості й приклад коду, а `--capabilities tools,triggers` перевизначає те,
що передбачає шаблон.

### Що закріплює заготовка

| Мова | Заготовка закріплює | Опубліковано |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

Це розв'язується з реєстрів пакетів, тож `cargo build`, `pip install -r
requirements.txt` і `bun install` працюють у свіжому проєкті без жодного
налаштування.

**Нижні межі несучі.** Rust 0.6 — перший реліз, чий `HostClient` прикріплює
`x-session-token`, а Python і TypeScript 0.5.0 — їхні власні; проти чогось
старішого демон відповідає `unauthenticated` на кожен виклик хоста.
Послаблення межі міняє помилку резолвера на помилку часу виконання, а це
гірший обмін — плагін запускається, обслуговує хуки і мовчки не може
відповісти.

Python: `astra-plugin test` запускає ваш плагін тим `python`, що знайдеться в
`PATH`, тому спершу активуйте віртуальне середовище, в яке ви встановлювали.
Інакше плагін завершиться з `ModuleNotFoundError: astra_plugin_sdk` ще до
реєстрації.

## 3 · Напишіть плагін

Замініть `src/main.rs` на це. Це весь плагін — типізовані аргументи,
інструмент, тригер і три тести.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

Варто назвати п'ять речей:

- **`#[astra::args]`, а не `#[derive(Deserialize, JsonSchema)]`.** Дерайв
  serde випускає `extern crate serde`, яке розв'язується через extern
  prelude і недосяжне через ре-експорт — тож звичайний дерайв вимагав би
  `serde` у *вашому* `Cargo.toml`, а це саме те, без чого заготовка обіцяє
  обійтися. `#[astra::args]` — це ті самі два дерайви, але вказані на копії
  SDK.
- **Doc-коментар — це опис, який читає модель.** І в інструмента, і в
  кожного поля. Пишіть про те, коли використовувати інструмент, а не про те,
  як він працює.
- **Обробники повертають `Result<_, ToolError>`.** Помилка окремого виклику
  — це *дані*: цикл ШІ читає її і вирішує, що робити, тож вона їде у
  відповіді, а не як статус gRPC. `?` працює з `serde_json::Error`,
  `std::io::Error`, `tonic::Status` і `anyhow::Error`.
- **`ctx.host()` доступний завжди.** Контекст несе клієнта хоста, мову
  інтерфейсу і поточний набір тригерів; його дешево клонувати у фонове
  завдання, і він ніколи не `None`. Нічого не лежить на вашій структурі за
  блокуванням.
- **`h.host().deny("fire_trigger")` інсценує відмову.** Так виглядає
  користувач, що не дав згоди, і це варто протестувати — саме такий збій
  інакше отримає ваш баг-трекер.

`cargo test` прогонить ці три тести проти записувального хоста: без демона,
без сокета, без встановленої Astra.

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · Оголосіть, що вам потрібно

Інструмент викликає `fire_trigger`, а `[permissions]` за замовчуванням усе
забороняє, тож треба попросити дозвіл. `reason` — це те, що користувач
прочитає, коли Astra попросить його дати згоду, — пишіть його як речення про
*ваш плагін*, а не про дозвіл узагалі.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

Потім перевірте:

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` читає маніфест тим самим парсером, що й демон, — тим самим крейтом,
завендореним і утримуваним побайтово ідентичним, — тож він не може розійтися
з тим, що станеться під час встановлення. `--fix` застосовує виправлення, які
може довести, і повідомляє про решту.

## 5 · Запустіть набір перевірок відповідності

<!-- doctest: cli -->
```bash
astra-plugin test
```

Це на рівень вище, ніж `cargo test`: вона запускає ваш плагін так само, як
це робить демон, проти мок-демона, що обслуговує `PluginHostService`, і
викликає кожен вхідний хук, який передбачають оголошені вами можливості.

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

`GetPluginTriggerTypes` повідомляє **0**, хоча плагін і запускає тригер.
Запустити тригер і *запропонувати* його — різні речі: редактор команд
перелічує те, що плагін оголошує, а це `#[hook] async fn trigger_types(&self)
-> Vec<TriggerTypeDef>`, і в плагіна вище його немає. Заготовка з
`--capabilities tools,triggers` пише цей хук за вас; §3 його опустив, щоб
уміститися в один екран. Без оголошення тригер все одно спрацює — але ніхто
не зможе прив'язати до нього команду.

`required`-хук не може відповідати `UNIMPLEMENTED`; `optional` може, тому що
на дроті `UNIMPLEMENTED` *означає* «цього хука немає».

## 6 · Запустіть його всередині Astra

Цей крок потребує запущеної Astra і **режиму розробника**, тому що
сайдлоадить непідписаний каталог:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

Вона запускає `check --strict`, збирає, передає каталог демону — який
запускає процес, видає його токен і володіє його життєвим циклом, — потім
стежить за змінами, пересобирає, перезапускає і хвостом читає логи.

Прочитайте про [сайдлоадинг](../5-publish/sideload.md), перш ніж вмикати
режим розробника. Це інструмент розробника: він запускає непідписаний
локальний код з вашими повними правами користувача, і цей перемикач знижує
планку для кожного плагіна на машині, а не тільки для цього. Це не спосіб,
яким хтось встановлює плагін.

Якщо `dev` не може дістатися до Astra, `astra-plugin doctor` підкаже, що з
двох не так — демон не запущений, або він визначив інший каталог
конфігурації, ніж CLI.

## 7 · Упакуйте

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` перечитує те, що щойно написала `build`, і відповідає на інше
питання: що `MANIFEST.json` — це запис 0 і зберігається без стиснення, що
список файлів вичерпний в обох напрямках, і що кожен зазначений дайджест,
розмір і режим відповідають архіву. Вона нічого не каже про те, хто це
написав, — це справа реєстру.

Ім'я файлу не косметика: `<id>-<версія>-<ціль>.astraplugin` — це ім'я, яке
зобов'язаний носити опублікований бандл, а сегмент цілі — це ключ платформи
реєстру.

**`build` не підписує, і вам не потрібен ключ.** Те, що змушує Astra
встановлювати плагін, — запис реєстру, що контрпідписує sha256 усього файлу,
а не якийсь ключ, який у вас є. Див. [модель безпеки](../1-orientation/security.md).

## 8 · Опублікуйте

Тепер та частина, що важлива, і це дві команди:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` пише `.github/workflows/release.yml`, закріплений за SHA коміту на
багаторазовий workflow релізу Astra. Після цього **тег — це весь процес
релізу**: CI збирає кожну ціль, засвідчує кожен бандл походженням збірки
GitHub і прикріплює їх до релізу GitHub.

Далі одна заявка, один раз назавжди, і кожен наступний реліз йде без участі
людини.

Зверніть увагу, чим публікація **не є**: пуш цього репозиторію в GitHub не
публікує ваш плагін, і надсилання комусь щойно зібраного `.astraplugin`
теж ні. Реєстр закріплює дайджест файлу, який виробив CI, і читає
прикріплену до нього атестацію збірки, а файл, зібраний на вашому ноутбуці,
не несе жодного з цього.

**→ [Публікація плагіна](../publishing.md)** — весь шлях на одній сторінці,
звідси до плагіна в каталозі, з кожною командою та її очікуваним виводом.
Сторінки за щаблями за нею:
[реліз через CI](../5-publish/release-with-ci.md) ·
[потрапити до каталогу](../5-publish/get-listed.md)

## Те саме на Python

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

Точка входу — `[entry] command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`, а бандл — `noarch`.

## Те саме на TypeScript

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## Куди далі

| Якщо вам потрібно | Читайте |
|---|---|
| Весь Rust API | [Rust SDK](../4-sdk/rust.md) |
| Кожен ключ `plugin.toml` | [довідник маніфесту](../reference/manifest.md) |
| Кожен хук у кожному SDK | [паритет](../reference/parity.md) |
| Випустити реліз | [реліз через CI](../5-publish/release-with-ci.md) |
| Щось зламалося | [діагностика](../6-operate/troubleshooting.md) |
| Розібраний приклад | [приклади](../7-examples/README.md) — одинадцять штук |
