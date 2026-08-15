# Быстрый старт

> Перевод. Источник истины — [docs/en](../../en/2-tutorial/getting-started.md); при расхождении верна английская версия.

От нуля до плагина, который бросает кости, имеет тесты и упакован для релиза.
Около пятнадцати минут, большая часть которых — ожидание `cargo`.

Каждый блок кода на этой странице выполняется
[`docs/tools/doctest.py`](../../tools/doctest.py) в CI. Если что-то из этого
неверно, сборка становится красной прежде, чем вы это прочтёте.

## 1 · Установите CLI

Одна строка. Занимает несколько минут и заканчивается печатью версии.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

Число здесь — заполнитель намеренно: `--git` собирает тот коммит, который
`master` несёт в момент запуска, так что печатается версия этого коммита, а
не выбранная вами.

Из клонированного репозитория то же самое делает
`cargo install --path astra-plugin-cli --locked`.

**Нужен Rust 1.85 или новее и `protoc` в PATH.** Без `protoc` сборка
остановится на ``Could not find `protoc` ``. Поставьте его через `apt install
protobuf-compiler`, `pacman -S protobuf`, `brew install protobuf` или `winget
install Google.Protobuf`, затем выполните строку заново.

**Номер версии не может сказать вам, что эта сборка хорошая, а `0.2.0` —
не плохая.** `init-ci` раньше закреплял *объект* тега там, где GitHub
требует коммит, и первый `git push --tags` плагина умирал на этом.
Исправление — коммит `5b8ab22`, который попал в `master` *раньше*, чем
бамп, поднявший число до `0.2.1`; значит, сборка из `master` может нести
исправление и всё равно печатать `0.2.0`, и не существует `0.2.1` без него.
Установка из `master` сегодня даёт исправление, что бы ни говорило число; а
чтобы проверить, а не поверить, запустите `astra-plugin init-ci` и прочтите
напечатанный пин: `e3329df252a46d747676cb540ae4b986af68a3ad` — коммит, это
правильно; `dc1a044876926e9cf1170f034e2eab533ec07641` — объект тега, это баг.
Длинная версия:
[установка CLI](../install-cli.md#баг-который-ломает-первый-релиз-и-как-понять-есть-ли-в-вашей-сборке-исправление).

Одна оговорка, которая вас не заблокирует: CLI не на crates.io и не имеет
готовых бинарников, так что сборка — единственный способ его получить.
Готовые бинарники запланированы. Все подробности, включая что делать, если
не работает: [установка CLI](../install-cli.md).

Проверьте машину, прежде чем винить код:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Она отвечает на шестнадцать вопросов за один проход — какой CLI вы
используете, какой каталог конфигурации она разрешила, доступна ли Astra,
какие у вас есть тулчейны (включая `protoc`), и закреплён ли ваш workflow
релиза. Это первое, что стоит запустить, когда что-то непонятно.

## 2 · Создайте заготовку

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

Шесть файлов:

<!-- doctest: illustrative reason="an annotated tree of what `astra-plugin new` wrote, not a command; the run that produced it is the output block above" -->
```
dice-roller/
├── plugin.toml      манифест — id, версия, возможности, точка входа
├── Cargo.toml       одна зависимость и длинный комментарий, почему только одна
├── src/main.rs      сам плагин: пятнадцать строк плюс тестовый модуль
├── README.md        то, что магазин показывает рядом с вашим плагином
├── icon.svg         иконка-заглушка, которую нужно заменить
└── .gitignore       `target/` и `*.astraplugin`
```

`README.md` и `icon.svg` — не украшение: упаковщик берёт оба по имени, а
реестр вычитывает их обратно из проверенного бандла, чтобы собрать карточку и
страницу вашего листинга. Это то, что человек видит, прежде чем решить вас
установить, так что замените их до публикации —
[как попасть в каталог](../5-publish/get-listed.md) говорит, что нужно
каждому из них.

`--lang` принимает `rust`, `python` или `typescript`; `--template` выбирает
возможности и пример кода, а `--capabilities tools,triggers` переопределяет
то, что подразумевает шаблон.

### Что закрепляет заготовка

| Язык | Заготовка закрепляет | Опубликовано |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

Это разрешается из реестров пакетов, так что `cargo build`, `pip install -r
requirements.txt` и `bun install` работают в свежем проекте без какой-либо
настройки.

**Нижние границы несущие.** Rust 0.6 — первый релиз, чей `HostClient`
прикрепляет `x-session-token`, а Python и TypeScript 0.5.0 — их собственные;
против чего-то более старого демон отвечает `unauthenticated` на каждый вызов
хоста. Ослабление границы меняет ошибку резолвера на ошибку времени
выполнения, а это худший обмен — плагин запускается, обслуживает хуки и
молча не может ответить.

Python: `astra-plugin test` запускает ваш плагин тем `python`, что найдётся в
`PATH`, поэтому сначала активируйте виртуальное окружение, в которое вы
устанавливали. Иначе плагин завершится с `ModuleNotFoundError:
astra_plugin_sdk` ещё до регистрации.

## 3 · Напишите плагин

Замените `src/main.rs` на это. Это весь плагин — типизированные аргументы,
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

Стоит назвать пять вещей:

- **`#[astra::args]`, а не `#[derive(Deserialize, JsonSchema)]`.** Дерайв
  serde испускает `extern crate serde`, которое резолвится через extern
  prelude и недостижимо через ре-экспорт — так что обычный дерайв потребовал
  бы `serde` в *вашем* `Cargo.toml`, а это как раз то, без чего заготовка
  обещает обойтись. `#[astra::args]` — это те же два дерайва, но указывающие
  на копии SDK.
- **Doc-комментарий — это описание, которое читает модель.** И у инструмента,
  и у каждого поля. Пишите о том, когда использовать инструмент, а не о том,
  как он работает.
- **Обработчики возвращают `Result<_, ToolError>`.** Ошибка отдельного вызова
  — это *данные*: цикл ИИ читает её и решает, что делать, поэтому она едет в
  ответе, а не как статус gRPC. `?` работает с `serde_json::Error`,
  `std::io::Error`, `tonic::Status` и `anyhow::Error`.
- **`ctx.host()` доступен всегда.** Контекст несёт клиента хоста, язык
  интерфейса и текущий набор триггеров; его дёшево клонировать в фоновую
  задачу, и он никогда не `None`. Ничего не лежит на вашей структуре за
  блокировкой.
- **`h.host().deny("fire_trigger")` инсценирует отказ.** Так выглядит
  пользователь, который не дал согласия, и это стоит протестировать — именно
  такой сбой иначе получит ваш баг-трекер.

`cargo test` прогоняет эти три теста против записывающего хоста: без демона,
без сокета, без установленной Astra.

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · Объявите, что вам нужно

Инструмент вызывает `fire_trigger`, а `[permissions]` по умолчанию всё
запрещает, так что нужно попросить разрешение. `reason` — это то, что
пользователь прочтёт, когда Astra попросит его дать согласие, — пишите его
как предложение про *ваш плагин*, а не про разрешение вообще.

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

`check` читает манифест тем же парсером, что и демон, — тем же крейтом,
завендоренным и удерживаемым побайтово идентичным, — так что он не может
разойтись с тем, что произойдёт при установке. `--fix` применяет исправления,
которые может доказать, и сообщает об остальных.

## 5 · Запустите набор проверок соответствия

<!-- doctest: cli -->
```bash
astra-plugin test
```

Это на уровень выше, чем `cargo test`: она запускает ваш плагин так же, как
это делает демон, против мок-демона, обслуживающего `PluginHostService`, и
вызывает каждый входящий хук, который подразумевают объявленные вами
возможности.

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
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

`GetPluginTriggerTypes` сообщает **0**, даже несмотря на то, что плагин
запускает триггер. Запустить триггер и *предложить* его — разные вещи:
редактор команд перечисляет то, что плагин объявляет, а это `#[hook] async fn
trigger_types(&self) -> Vec<TriggerTypeDef>`, и у плагина выше его нет.
Заготовка с `--capabilities tools,triggers` пишет этот хук за вас; §3 его
опустил, чтобы уместить файл в один экран. Без объявления триггер всё равно
сработает — но никто не сможет привязать к нему команду.

`required`-хук не может отвечать `UNIMPLEMENTED`; `optional` может, потому
что на проводе `UNIMPLEMENTED` *значит* «этого хука нет».

## 6 · Запустите его внутри Astra

Этот шаг требует запущенной Astra и **режима разработчика**, потому что
сайдлоадит неподписанный каталог:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

Она запускает `check --strict`, собирает, передаёт каталог демону — который
запускает процесс, выпускает его токен и владеет его жизненным циклом, —
затем следит за изменениями, пересобирает, перезапускает и хвостом читает
логи.

Прочтите про [сайдлоадинг](../5-publish/sideload.md), прежде чем включать
режим разработчика. Это инструмент разработчика: он запускает неподписанный
локальный код с вашими полными правами пользователя, и этот переключатель
снижает планку для каждого плагина на машине, а не только для этого. Это не
способ, которым кто-либо устанавливает плагин.

Если `dev` не может достучаться до Astra, `astra-plugin doctor` подскажет,
что из двух не так — демон не запущен, или он разрешил другой каталог
конфигурации, чем CLI.

## 7 · Упакуйте

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" unrun="needs a scaffolded, compiled plugin on disk; re-run it in the project this page builds" -->
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

`verify` перечитывает то, что только что написала `build`, и отвечает на
другой вопрос: что `MANIFEST.json` — это запись 0 и хранится без сжатия, что
список файлов исчерпывающий в обоих направлениях, и что каждый указанный
дайджест, размер и режим соответствуют архиву. Она ничего не говорит о том,
кто это написал, — это дело реестра.

Имя файла не косметика: `<id>-<версия>-<цель>.astraplugin` — это имя, которое
обязан носить опубликованный бандл, а сегмент цели — это ключ платформы
реестра.

**`build` не подписывает, и вам не нужен ключ.** То, что заставляет Astra
устанавливать плагин, — запись реестра, контрподписывающая sha256 всего
файла, а не какой-либо ключ, который у вас есть. См.
[модель безопасности](../1-orientation/security.md).

## 8 · Опубликуйте

Теперь та часть, что важна, и это две команды:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` пишет `.github/workflows/release.yml`, закреплённый по SHA коммита
на переиспользуемый workflow релиза Astra. После этого **тег — это весь
процесс релиза**: CI собирает каждую цель, удостоверяет каждый бандл
происхождением сборки GitHub и прикрепляет их к релизу GitHub.

Затем одна заявка, один раз навсегда, и каждый последующий релиз идёт без
участия человека.

Обратите внимание, чем публикация **не является**: пуш этого репозитория в
GitHub не публикует ваш плагин, и отправка кому-то только что собранного
`.astraplugin` тоже. Реестр закрепляет дайджест файла, который произвёл CI, и
читает прикреплённую к нему аттестацию сборки, а файл, собранный на вашем
ноутбуке, не несёт ни того, ни другого.

**→ [Публикация плагина](../publishing.md)** — весь путь на одной странице,
отсюда до плагина в каталоге, с каждой командой и её ожидаемым выводом.
Страницы по ступеням за ней: [релиз через CI](../5-publish/release-with-ci.md) ·
[попасть в каталог](../5-publish/get-listed.md)

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

| Если вам нужно | Читайте |
|---|---|
| Весь Rust API | [Rust SDK](../4-sdk/rust.md) |
| Каждый ключ `plugin.toml` | [справочник манифеста](../reference/manifest.md) |
| Каждый хук во всех SDK | [паритет](../reference/parity.md) |
| Выпустить релиз | [релиз через CI](../5-publish/release-with-ci.md) |
| Что-то сломалось | [диагностика](../6-operate/troubleshooting.md) |
| Разобранный пример | [примеры](../7-examples/README.md) — одиннадцать штук |
