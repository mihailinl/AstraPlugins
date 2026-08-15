# Установка CLI

> Перевод. Источник истины — [docs/en](../en/install-cli.md); при расхождении верна английская версия.

Весь путь публикации начинается с команды, и это страница, которая даёт вам
эту команду. Бинарник называется **`astra-plugin`** — не
`astra-plugin-cli`, это только имя крейта.

## Честное состояние этого

**Готовых бинарников пока нет, и `astra-plugin-cli` не на crates.io.**
Проверено сегодня: `https://index.crates.io/as/tr/astra-plugin-cli`
отвечает `404`, тогда как `astra-plugin-sdk` на том же индексе отвечает
`200`, так что это реальное отсутствие, а не проваленный запрос. `gh
release list --repo mihailinl/AstraPlugins` не печатает ничего.

Так что единственный способ получить CLI — собрать её, а для сборки нужен
тулчейн Rust. Поставка готовых бинарников — известная, отдельная,
незакрытая задача: автоматизация релиза для неё пишется прямо сейчас, и на
этой странице появится строка для скачивания в тот день, когда появится
релиз, который можно скачать. До тех пор она описывает всё, что есть, и
ничто здесь не просит вас что-либо скачивать.

Эта цена реальна, и стоит назвать, почему её всё равно стоит платить: CLI —
не обёртка для удобства вокруг какого-то более простого пути. Это
единственное, что пишет правильный workflow релиза, единственное, что не
даёт вашим манифестам разойтись в версии, и единственное, что открывает
заявку на листинг, которую бот реестра реально увидит. Обход её — это то,
как две реальные заявки закончились тишиной — см.
[что такое публикация](publishing.md).

## Предпосылки

| | Зачем | Проверка |
|---|---|---|
| **Rust 1.85 или новее** | каждый крейт здесь `edition = "2024"`, а 1.85 — первый релиз, который его понимает | `cargo --version` |
| **`protoc` в `PATH`** | CLI зависит от `astra-plugin-sdk`, чей `build.rs` компилирует `proto/plugin.proto` через `tonic-build`, который вызывает внешний `protoc` | `protoc --version` |
| **`git`** | `cargo install --git` клонирует через него | `git --version` |

Ни один крейт не объявляет `rust-version`, а CI собирает на `stable`, так
что edition — единственная реально применяемая нижняя граница.

Установка `protoc`, которую чаще всего пропускают:

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

Без него сборка падает в скрипте сборки `astra-plugin-sdk`, и ошибка
называет решение:

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## Установите её

**Одна строка, без клонирования.** Вот та, которую нужно использовать:

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` собирает против зафиксированного в репозитории `Cargo.lock`, а
не переразрешает каждую зависимость до её новейшего релиза, а это разница
между сборкой, которая работает так же, как работала здесь, и той, что
узнаёт о ломающем патч-релизе прямо на вашей машине.

`--git` собирает то, что сейчас несёт `master`, так что версия и коммит,
которые она сообщает, — те, что на `master` в момент запуска. Всё, что в
угловых скобках ниже, различается от машины к машине и от запуска к
запуску: версия и SHA приходят из `master`, пути — из вашего домашнего
каталога, длительность — от вашего процессора.

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

Эта запись снята с `--root <scratch>`, чтобы её получение не перезаписало
ничей установленный бинарник. **Не указывайте `--root`** — как и делает
команда выше — и последние две строки изменятся: `Installing` назовёт
`<home>/.cargo/bin/astra-plugin`, а предупреждение про `PATH` появится
только если `~/.cargo/bin` ещё не в вашем `PATH`. Два SHA — это один и тот
же коммит, напечатанный в двух разных длинах; так делает cargo, это не
расхождение.

**Из клона**, если вы хотите читать или менять CLI, а не только запускать
её:

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

Обычный `git clone` выкачивает `master`, а `master` — это то место, где
живёт текущая CLI, — нет никакой ветки, о которой нужно знать отдельно.

## Проверьте, что сработало

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

Число здесь — заполнитель, потому что ни одна из двух строк установки не
даёт вам выбрать версию: обе собирают коммит, а не релиз, так что вы
получаете версию из `Cargo.toml` этого коммита. `0.2.1` — самая свежая
запись в [changelog CLI](../../astra-plugin-cli/CHANGELOG.md), где также
записано, что у этого крейта нет релизного поезда: ни crates.io, ни тега,
ни бинарников.

Если оболочка её не находит, `cargo install` поместила её в `~/.cargo/bin`
(или `%USERPROFILE%\.cargo\bin` на Windows), а этого каталога нет в вашем
`PATH`. `cargo` печатает предупреждение об этом ровно тогда, когда это
происходит.

### Баг, который ломает первый релиз, и как понять, есть ли в вашей сборке исправление

**`astra-plugin init-ci` раньше закреплял SHA *объекта* аннотированного
тега там, где GitHub требует коммит**, так что первый `git push --tags`
падал с `invalid value workflow reference` ещё до старта любой задачи. Это
был [AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Исправление — это коммит `5b8ab22`, а не номер версии**, и именно на этом
люди спотыкаются. Здесь нет релизного поезда: ничто не опубликовано, так
что никто не устанавливает выбранную версию — все собирают тот коммит,
который склонировали. `5b8ab22` попал в `master` *раньше*, чем бамп,
поднявший число до `0.2.1`, а значит:

- сборка из `master` после `5b8ab22` **содержит исправление и всё равно
  печатает `0.2.0`** — это не сломанная сборка;
- ни одна сборка `0.2.1` не может быть *без* исправления, потому что
  `5b8ab22` — предок коммита с бампом;
- сломанная — это сборка `0.2.0`, сделанная *до* `5b8ab22`, и `--version`
  не отличает её от первого случая.

Так что `0.2.1` стоит иметь — это первое число, которое отвечает на вопрос
само по себе, ровно для этого оно и существует, — но `0.2.0`, который
говорит `0.2.0`, не доказывает ничего. `0.2.1` не добавляет флагов и не
меняет API; единственное изменение поведения — `publish --notify`, чья
ссылка теперь называет форму release-ping реестра вместо пустого issue,
который реестр с тех пор отключил.

Если `--version` печатает `0.2.0`, сначала запустите `which astra-plugin`
(`where` на Windows): самая частая причина — более старый бинарник стоит
раньше в вашем `PATH`, а сама по себе `--version` не отличает это от свежей
сборки более старого коммита. Дальше перестаньте гадать по числу и прочтите
пин: `init-ci` записывает ровно то, из-за чего был баг, и отвечает одной
строкой.

Вот проверка, которая вообще не зависит от версии:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Сборка с исправлением сообщает закрепление
`e3329df252a46d747676cb540ae4b986af68a3ad` — коммит. Сборка без него
сообщает `dc1a044876926e9cf1170f034e2eab533ec07641`, а это *объект тега*
`plugin-release/v1`, и именно его отклоняет GitHub. Если вы видите второе,
переустановите из `master` строкой выше и запустите `init-ci` снова. Её
безопасно перезапускать: она сохраняет ваши входные параметры и переписывает
закрепление. Ничто не чинится на месте, так что существующий `release.yml`
держит плохой SHA, пока вы не перезапустите её.

Полный набор команд:

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

**`astra-plugin login` не существует**, и это намеренно, а не незакончено:
ничто в этом тулчейне никогда не спрашивает у вас учётные данные. См.
[попасть в каталог](5-publish/get-listed.md).

## Как её обновлять

Перезапустите ту же строку `cargo install --git`. Cargo заменяет бинарник
на месте. Самообновления нет, и не будет, пока не появятся подписанные
релизные бинарники, до которых можно обновляться.

## Что идёт не так

| Симптом | Причина |
|---|---|
| `Could not find` protoc` ` | `protoc` нет в `PATH`. См. таблицу выше |
| `feature `edition2024` is required` | Rust старше 1.85 |
| `astra-plugin: command not found` после успешной установки | `~/.cargo/bin` нет в `PATH` |
| `error: could not find `Cargo.toml`` при запуске `cargo install --path .` в корне репозитория | В корне нет workspace-манифеста. Направьте `--path` на `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Более старая `astra-plugin` стоит раньше в вашем `PATH`. `--version` не поможет их различить — запустите `which astra-plugin` (`where` на Windows), чтобы увидеть, какой файл вы реально запускаете |
| `invalid value workflow reference` при первом пуше тега | CLI, писавшая `release.yml`, старше `5b8ab22` и закрепила объект тега. См. [как понять, есть ли в вашей сборке исправление](#баг-который-ломает-первый-релиз-и-как-понять-есть-ли-в-вашей-сборке-исправление) |

## Дальше

- **[Что такое публикация](publishing.md)** — весь путь, от пустого
  каталога до плагина в каталоге, на одной странице.
- [Быстрый старт](2-tutorial/getting-started.md) — написание самого
  плагина.
