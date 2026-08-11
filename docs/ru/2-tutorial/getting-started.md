# Быстрый старт

От нуля до плагина, который бросает кости, покрыт тестами и упакован для
релиза. Минут пятнадцать, из которых большая часть — ожидание `cargo`.

Каждый блок кода на этой странице выполняется
[`docs/tools/doctest.py`](../../tools/doctest.py) в CI. Если какой-то из них
неверен, сборка станет красной раньше, чем вы его прочитаете.

## 1 · Установить CLI

SDK публикуются на crates.io, PyPI и npm; сам `astra-plugin` — пока нет:
`cargo install astra-plugin-cli` завершается ошибкой, потому что крейта на
crates.io нет. Ставьте его из исходников. Он собирается на Linux и Windows
стабильным тулчейном Rust (1.85 или новее — дерево на edition 2024) **и с
`protoc` в PATH**. CLI зависит от Rust SDK, чей `build.rs` компилирует
`proto/plugin.proto` через tonic-build, а tonic-build вызывает внешний `protoc`
и своего не несёт. Без него команда ниже останавливается на `error: failed to
run custom build command for astra-plugin-sdk` → `Could not find `protoc``.
Ставится через `apt install protobuf-compiler`, `pacman -S protobuf`,
`brew install protobuf` или `winget install Google.Protobuf`.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

Из клона то же самое делает `cargo install --path astra-plugin-cli --locked`.

**Прочитайте эту версию, прежде чем идти дальше.** Страница написана про
`astra-plugin 0.2.0`, а `--git` собирает то, что лежит в ветке репозитория по
умолчанию. Если напечаталось 0.1.x — у вас CLI старее этой страницы: весь его
набор команд это `create`, `dev`, `build`, `validate`, `keygen`, поэтому уже
следующая команда падает с `unrecognized subcommand 'doctor'`, и так же падает
каждый шаг начиная с §2. Поставьте из клона той ветки, где лежит эта
документация.

Проверьте машину, прежде чем винить код:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Он отвечает на шестнадцать вопросов за один проход — какой CLI вы запустили,
какой каталог конфигурации он вычислил, доступна ли Astra, какие тулчейны у вас
есть (включая `protoc`) и закреплён ли релизный workflow. Это первое, что стоит
запустить, когда что-то непонятно.

## 2 · Сгенерировать проект

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

Пять файлов: `plugin.toml`, `Cargo.toml`, `src/main.rs`, `README.md`,
`.gitignore`. В `Cargo.toml` **одна** зависимость, а `src/main.rs` — пятнадцать
строк плюс модуль тестов.

`--lang` принимает `rust`, `python` или `typescript`; `--template` выбирает
возможности и пример кода, а `--capabilities tools,triggers` перекрывает то,
что подразумевает шаблон.

### SDK, который закрепляет шаблон, ещё не опубликован

Прочитайте это до `cargo build` — иначе прочитаете в виде ошибки. Шаблон
закрепляет ту версию SDK, которую описывает эта документация, а в реестрах
лежит предыдущая, поэтому свежий проект не резолвится — ни на одном из трёх
языков:

| Язык | Что закрепляет шаблон | Что в реестре сегодня | Где падает |
|---|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io: 0.5.0 | `cargo build` |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI: 0.4.0 | `pip install -r requirements.txt` |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm: 0.4.0 | `bun install` |

<!-- doctest: output from="cargo build --release in a freshly scaffolded rust project" -->
```
error: failed to select a version for the requirement `astra-plugin-sdk = "^0.6"`
candidate versions found which didn't match: 0.5.0, 0.2.0, 0.1.5, ...
location searched: crates.io index
required by package `dice_roller v0.1.0`
```

Сами пины не ошибочны: 0.6 — первый релиз Rust SDK, чей `HostClient`
прикладывает `x-session-token`, и на 0.5 демон отвечает `unauthenticated` на
каждый host-вызов, так что ослабление границы меняет ошибку резолвера на
ошибку времени выполнения. Пока релиз не вышел, направьте проект на копию SDK
из этого репозитория. Из клона `AstraPlugins`, лежащего рядом с проектом:

<!-- doctest: illustrative reason="каждая строка — фрагмент чужого файла сборки: секция Cargo.toml, вызов pip и поле package.json; одной команды тут нет, каждая была выполнена отдельно до того, как попала на страницу" -->
```bash
# Rust — append to the project's Cargo.toml
#   [patch.crates-io]
#   astra-plugin-sdk = { path = "../AstraPlugins/astra-plugin-sdk" }
#
# Python — install the SDK by path, then the rest of requirements.txt
#   pip install ../AstraPlugins/astra-plugin-sdk-python
#
# TypeScript — pack this tree's SDK and override the specifier
#   (cd ../AstraPlugins/astra-plugin-sdk-ts && bun run build && bun pm pack --destination /tmp/tgz)
#   then set "overrides": { "astra-plugin-sdk": "file:/tmp/tgz/astra-plugin-sdk-0.5.0.tgz" }
```

Ни `astra-plugin doctor`, ни `astra-plugin check` этого не проверяют: оба
читают манифест, а пин лежит в файле сборки конкретного языка. Симптом всегда
приходит от резолвера и всегда на первой сборке.

## 3 · Написать плагин

Замените `src/main.rs` этим. Это плагин целиком — типизированные аргументы,
инструмент, триггер и три теста.

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

Пять вещей стоит назвать:

- **`#[astra::args]`, а не `#[derive(Deserialize, JsonSchema)]`.** Дерайв serde
  разворачивается в `extern crate serde`, который разрешается через extern
  prelude и недостижим через реэкспорт, — поэтому обычный дерайв потребовал бы
  `serde` в *вашем* `Cargo.toml`, а это ровно то, чего шаблон обещает избежать.
  `#[astra::args]` — это те же два дерайва, направленные на копии внутри SDK.
- **Doc-комментарий — это описание, которое читает модель.** И у инструмента, и
  у каждого поля. Пишите, *когда* его использовать, а не как он устроен.
- **Обработчики возвращают `Result<_, ToolError>`.** Ошибка конкретного вызова
  это *данные*: цикл ИИ читает их и решает, что делать, поэтому они едут внутри
  ответа, а не как gRPC-статус. `?` работает с `serde_json::Error`,
  `std::io::Error`, `tonic::Status` и `anyhow::Error`.
- **`ctx.host()` есть всегда.** Контекст несёт клиент хоста, язык интерфейса и
  набор активных триггеров; его дёшево склонировать в фоновую задачу, и он
  никогда не `None`. Ничего не нужно держать в своей структуре под мьютексом.
- **`h.host().deny("fire_trigger")` подставляет отказ.** Так выглядит
  пользователь, который не дал согласия, и это стоит теста — иначе именно эта
  ошибка придёт в ваш баг-трекер.

`cargo test` прогоняет эти три теста против записывающего хоста: без демона, без
сокета, без установленной Astra.

<!-- doctest: illustrative reason="блок выше помечен test=1, так что doctest уже прогнал на нём cargo test" -->
```bash
cargo test
```

## 4 · Объявить, что вам нужно

Инструмент вызывает `fire_trigger`, а `[permissions]` запрещает всё по
умолчанию, значит, нужно попросить. `reason` — это то, что прочитает
пользователь, когда Astra спросит согласия: пишите предложение о *вашем
плагине*, а не о разрешении.

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

Затем проверьте:

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` читает манифест собственным парсером демона — тем же крейтом,
скопированным побайтово, — поэтому он не может разойтись с тем, что произойдёт
при установке. `--fix` применяет исправления, которые может доказать, и
сообщает об остальном.

## 5 · Прогнать набор соответствия

<!-- doctest: cli -->
```bash
astra-plugin test
```

Это уровень выше `cargo test`: он запускает ваш плагин так, как это делает
демон, против mock-демона, обслуживающего `PluginHostService`, и вызывает каждый
входящий хук, который подразумевают объявленные возможности.

<!-- doctest: output from="astra-plugin test . --no-build в том самом проекте dice-roller, который собирает эта страница (собственные tracing-строки плагина уходят в stderr и здесь опущены)" -->
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

`GetPluginTriggerTypes` показывает **0**, хотя плагин триггер выбрасывает.
Выбросить и *предложить* — разные вещи: редактор команд показывает то, что
плагин объявил, а объявляется это хуком `#[hook] async fn trigger_types(&self)
-> Vec<TriggerTypeDef>`, и у плагина выше его нет. Генерация с
`--capabilities tools,triggers` пишет этот хук за вас; в §3 он опущен, чтобы
файл влезал в один экран. Без объявления триггер всё равно выбрасывается — но
привязать к нему команду никто не сможет.

Обязательный хук не имеет права отвечать `UNIMPLEMENTED`; необязательный —
имеет, потому что на проводе `UNIMPLEMENTED` *означает* «этого хука нет».

## 6 · Запустить внутри Astra

Для этого шага нужна работающая Astra и **режим разработчика**, потому что он
сайдлоадит неподписанный каталог:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

Он выполняет `check --strict`, собирает, отдаёт каталог демону — тот запускает
процесс, выпускает токен и владеет жизненным циклом, — затем следит за
изменениями, пересобирает, перезапускает и показывает логи.

Прочитайте [про сайдлоад](../5-publish/sideload.md) до того, как включите режим
разработчика. Это инструмент разработчика: он запускает неподписанный локальный
код с вашими полными правами, и переключатель снижает планку для **каждого**
плагина на машине, а не только для этого. Так плагины не устанавливают.

Если `dev` не достучался до Astra, `astra-plugin doctor` скажет, что именно из
двух не так: демон не запущен, или он вычислил не тот каталог конфигурации, что
CLI.

## 7 · Упаковать

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build . в том самом проекте dice-roller, который собирает эта страница (размер и оба дайджеста — свойства вашей сборки, а не константы)" -->
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

`verify` перечитывает то, что `build` только что записал, и отвечает на другой
вопрос: что `MANIFEST.json` — нулевая запись и она stored, что список файлов
исчерпывающ в обе стороны и что каждый перечисленный дайджест, размер и режим
совпадают с архивом. Про то, кто это написал, он не говорит ничего — это дело
реестра.

Имя файла не косметика: `<id>-<version>-<target>.astraplugin` — это имя, которое
обязан иметь опубликованный бандл, а сегмент target — это ключ платформы в
реестре.

**`build` не подписывает, и ключ вам не нужен.** Astra устанавливает плагин
из-за записи в реестре, подписывающей sha256 всего файла, а не из-за какого-либо
вашего ключа. См. [модель безопасности](../1-orientation/security.md).

## 8 · Опубликовать

Теперь самое важное, и это две команды:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` пишет `.github/workflows/release.yml`, закреплённый по хешу коммита на
переиспользуемый релизный workflow Astra. После этого **тег — это весь процесс
релиза**: CI собирает все цели, выдаёт аттестацию сборки GitHub на каждый бандл
и прикладывает их к GitHub Release.

Затем одна заявка, один раз навсегда, и каждый следующий релиз идёт сам.

→ [Релиз через CI](../5-publish/release-with-ci.md) →
[Попасть в каталог](../5-publish/get-listed.md)

## То же самое на Python

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

Точка входа — `[entry] command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`, а бандл — `noarch`.

## То же самое на TypeScript

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

## Куда дальше

| Если нужно | Читайте |
|---|---|
| Весь API Rust | [Rust SDK](../../en/4-sdk/rust.md) (англ.) |
| Каждый ключ `plugin.toml` | [справочник манифеста](../../en/reference/manifest.md) (англ.) |
| Каждый хук в каждом SDK | [паритет](../../en/reference/parity.md) (англ.) |
| Выпустить релиз | [Релиз через CI](../5-publish/release-with-ci.md) |
| Что-то сломалось | [Диагностика](../6-operate/troubleshooting.md) |
| Рабочий пример | [Примеры](../../en/7-examples/README.md) — их одиннадцать |
