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
тулчейн Rust. Поставка готовых бинарников `linux-x64` и `windows-x64` —
известная, отдельная, незакрытая задача; пока она не выполнена, эта
страница описывает всё, что есть.

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

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release -p astra-plugin-sdk" -->
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
которые она сообщает, — те, что на `master` в момент запуска; в угловых
скобках ниже — ровно те две части, которые у вас будут другими:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" -->
```
   Compiling astra-plugin-cli v<version> (/home/you/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in 23.60s
  Installing /home/you/.cargo/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<sha>)` (executable `astra-plugin`)
```

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
astra-plugin 0.2.1
```

Если оболочка её не находит, `cargo install` поместила её в `~/.cargo/bin`
(или `%USERPROFILE%\.cargo\bin` на Windows), а этого каталога нет в вашем
`PATH`. `cargo` печатает предупреждение об этом ровно тогда, когда это
происходит.

### Берите 0.2.1 или новее, и почему это важно

**У `0.2.0` есть баг, который ломает ваш первый релиз.** `astra-plugin
init-ci` закреплял SHA *объекта* аннотированного тега там, где GitHub
требует коммит, так что первый `git push --tags` падал с `invalid value
workflow reference` ещё до старта любой задачи. Это был
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2), и он
исправлен в `0.2.1`.

Неловкая часть, сказанная прямо: `0.2.0` публиковался и до, и после
коммита с исправлением `5b8ab22`, так что какое-то время версия не могла
отличить рабочую сборку от сломанной. `0.2.1` существует, чтобы это
прекратить. Она не добавляет флагов и не меняет API; единственное изменение
поведения — `publish --notify`, чья ссылка теперь называет форму release-ping
реестра вместо пустого issue, который реестр с тех пор отключил.

Если `--version` печатает `0.2.0`, сначала запустите `which astra-plugin`
(`where` на Windows): обычная причина — более старый бинарник стоит раньше
в вашем `PATH`, а сама по себе `--version` их не различает. Если это тот
путь, куда вы только что установили, а число всё ещё `0.2.0`, значит
`master`, из которого вы собирали, ещё не несёт `0.2.1` — коммит с
исправлением `5b8ab22` попал в `master` раньше, чем бамп версии, который
его называет, так что сборка может содержать исправление и всё равно
говорить `0.2.0`. Не гадайте: проверка `init-ci` ниже смотрит на пин,
который CLI действительно записывает, а именно в нём и был баг.

Вы также можете подтвердить это, вообще не доверяя версии, посмотрев на
то, что пишет `init-ci`:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Исправленная сборка сообщает закрепление
`e3329df252a46d747676cb540ae4b986af68a3ad` — коммит. Сборка `0.2.0`
сообщает `dc1a044876926e9cf1170f034e2eab533ec07641`, а это объект тега, и
именно его отклоняет GitHub. `init-ci` безопасно перезапускать: она
сохраняет ваши входные параметры и переписывает закрепление. Ничто не
чинится на месте, так что существующий `release.yml` держит плохой SHA,
пока вы не перезапустите её.

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
| `invalid value workflow reference` при первом пуше тега | CLI, писавшая `release.yml`, была `0.2.0` и закрепила объект тега. См. [берите 0.2.1 или новее](#берите-021-или-новее-и-почему-это-важно) |

## Дальше

- **[Что такое публикация](publishing.md)** — весь путь, от пустого
  каталога до плагина в каталоге, на одной странице.
- [Быстрый старт](2-tutorial/getting-started.md) — написание самого
  плагина.
