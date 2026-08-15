# Установка CLI

> Перевод. Источник истины — [docs/en](../en/install-cli.md); при расхождении верна английская версия.

Весь путь публикации начинается с команды, и это страница, которая даёт вам
эту команду. Бинарник называется **`astra-plugin`** — не
`astra-plugin-cli`, это только имя крейта.

## Два пути, и какой вам нужен

**Скачайте бинарник.** Релиз [`cli-v0.2.1`][rel] несёт готовые архивы для
Linux и Windows, файл контрольных сумм и пакет Sigstore, который можно
проверить. Ничего не нужно компилировать, тулчейн не задействован. Это путь,
который нужен большинству людей, и он ниже.

**Либо соберите из исходников** — нужен Rust 1.85 или новее и `protoc`.
Берите этот путь, если вы на платформе без архива — сегодня это macOS и ARM
Linux, — либо если хотите читать или менять CLI, а не только запускать её.

**`cargo install astra-plugin-cli` — не один из путей и работать не будет.**
Крейт зависит от завендоренного `astra-plugin-manifest` по пути
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`), cargo
никогда не упаковывает исходники зависимости по пути, и публикация поэтому
падает с *all dependencies must have a version requirement specified* — так
что крейта вообще нет на crates.io (`https://index.crates.io/as/tr/astra-plugin-cli`
отвечает `404` сегодня, тогда как `astra-plugin-sdk` на том же индексе
отвечает `200`). Снять блокировку означает сначала выпустить крейт манифеста
от Astra, и эта страница не обещает дату для этого.

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## Скачайте бинарник

### Какой архив

| Вы на | Берите |
|---|---|
| **Любой Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux, и вам конкретно нужна сборка glibc | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl — безопасный выбор по умолчанию, и причина не во вкусе.** Сборка gnu
динамически слинкована, и её таблица символов требует **glibc 2.39 или
новее**, которого нет в Ubuntu 22.04 (2.35), Debian 12 (2.36) и RHEL 9
(2.34) — на любой из них она не запустится, а не будет тонко барахлить.
Архив musl — это исполняемый файл `static-pie` вообще без зависимости от
libc, так что он работает на любой из них. Берите gnu, только если точно
знаете, что он вам нужен.

Полный список артефактов этого релиза, то есть всё опубликованное:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### Скачайте и проверьте

Linux, через `curl` — здесь не нужен ни `gh`, ни аккаунт GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

Вот реальная запись этих команд:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**Используйте `--ignore-missing`.** `SHA256SUMS.txt` перечисляет все три
архива, так что обычный `sha256sum -c SHA256SUMS.txt` сообщит о двух, что вы
не скачали, как `FAILED open or read` и **выйдет с 1** — что выглядит в
точности как повреждённая загрузка, а на самом деле нет:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

Архив распаковывается в каталог, содержащий бинарник и файлы лицензии:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

Переместите `astra-plugin` куда-нибудь в свой `PATH` — обычный ответ —
`~/.local/bin`, и `sudo` не нужен:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

На Windows скачайте `.zip` со страницы релиза, распакуйте его и поместите
`astra-plugin.exe` в свой `PATH`. `certutil -hashfile <file> SHA256` —
встроенный инструмент контрольных сумм, и его вывод сравнивается с
`SHA256SUMS.txt` на глаз.

### Проверьте, кто его собрал

Контрольная сумма доказывает, что байты совпадают с файлом, названным в
релизе. Она не доказывает, кто произвёл этот файл — для этого есть пакет
Sigstore, и `gh` сверяет его с аттестацией сборки GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**Успех ничего не печатает, когда вывод не в терминал, и выходит с `0`.**
В первый раз это сбивает с толку; проверяйте `echo $?`, а не ищите
галочку. Провал — громкий и выходит с `1`:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

Это было произведено добавлением одного байта к архиву; указание `--repo` на
репозиторий, который его не собирал, падает точно так же. Один пакет
покрывает все три архива, и что он удостоверяет, можно прочитать через
`--format json`: workflow подписи —
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`,
издатель — `https://token.actions.githubusercontent.com`, а три дайджеста
subject — это три строки `SHA256SUMS.txt`. `gh attestation verify` нужен
сетевой доступ, чтобы получить корень доверия, но не логин GitHub.

## Соберите из исходников

Берите этот путь для macOS или ARM Linux, где архива пока нет, либо чтобы
работать над самой CLI. Это не запасной вариант на случай неудачной
загрузки — бинарник выше — та же самая программа.

### Предпосылки

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

### Соберите её

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

Чтобы собрать тот самый код, из которого собраны опубликованные бинарники, а
не то, что несёт `master` сегодня, сначала выкачайте тег релиза:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

Скачанный бинарник печатает `astra-plugin 0.2.1`, потому что архив собран из
тега `cli-v0.2.1` и ничего больше. `<version>` — заполнитель только на пути
из исходников: `cargo install --git` собирает то, что несёт `master` в этот
момент, так что вы получаете версию из `Cargo.toml` этого коммита, которая
может опережать самый свежий релиз. `0.2.1` — самая свежая запись в
[changelog CLI](../../astra-plugin-cli/CHANGELOG.md).

Если оболочка её не находит: скачанный бинарник лежит там, куда вы его
скопировали, а `cargo install` кладёт его в `~/.cargo/bin` (или
`%USERPROFILE%\.cargo\bin` на Windows). В любом случае этого каталога нет в
вашем `PATH`. `cargo` печатает предупреждение об этом ровно тогда, когда это
происходит.

### Баг, который ломает первый релиз, и как понять, есть ли в вашей сборке исправление

**`astra-plugin init-ci` раньше закреплял SHA *объекта* аннотированного
тега там, где GitHub требует коммит**, так что первый `git push --tags`
падал с `invalid value workflow reference` ещё до старта любой задачи. Это
был [AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Скачивание бинарника `0.2.1` решает этот вопрос, и это короткий ответ.**
Архив собран из тега `cli-v0.2.1`, `5b8ab22` — предок этого тега, так что у
скачанного бинарника есть исправление. Остальная часть этого раздела — про
сборку из исходников, где номер не решает вопрос.

**Исправление — это коммит `5b8ab22`, а не номер версии**, и именно на этом
люди спотыкаются. Сборка из исходников устанавливает тот коммит, который вы
склонировали, а не выбранный релиз. `5b8ab22` попал в `master` *раньше*, чем
бамп, поднявший число до `0.2.1`, а значит:

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

Если вы скачали бинарник, скачайте архив следующего релиза и замените
файл — сверьте контрольную сумму заново, ведь новый релиз означает новые
байты. Если вы собрали из исходников, перезапустите ту же строку `cargo
install`, и cargo заменит бинарник на месте. **Самообновления нет**, и
ничто в этом тулчейне не звонит домой, чтобы узнать, что вышла новая
версия.

## Что идёт не так

| Симптом | Причина |
|---|---|
| `FAILED open or read` от `sha256sum -c` | Вы скачали один архив, а файл перечисляет три. Добавьте `--ignore-missing` |
| `Error: verifying with issuer "sigstore.dev"` | Архив не совпадает с пакетом, либо `--repo` называет репозиторий, который его не собирал. Скачайте заново, а не рассуждайте об этом |
| `gh attestation verify` вообще ничего не напечатал | Это успех. Она тихая, когда вывод не в терминал; `echo $?` покажет `0` |
| Бинарник не запускается, и загрузчик жалуется, что не найдена версия `GLIBC_2.39` | Вы взяли архив gnu на системе со старым glibc. Возьмите musl — ему не нужен libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` не может сработать, и вот что она об этом говорит. См. начало этой страницы |
| `Could not find` protoc` ` | `protoc` нет в `PATH`. См. таблицу выше |
| `feature `edition2024` is required` | Rust старше 1.85 |
| `astra-plugin: command not found` после успешной установки | Каталог с бинарником нет в `PATH` — для сборки из исходников это `~/.cargo/bin` |
| `error: could not find `Cargo.toml`` при запуске `cargo install --path .` в корне репозитория | В корне нет workspace-манифеста. Направьте `--path` на `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Более старая `astra-plugin` стоит раньше в вашем `PATH`. `--version` не поможет их различить — запустите `which astra-plugin` (`where` на Windows), чтобы увидеть, какой файл вы реально запускаете |
| `invalid value workflow reference` при первом пуше тега | CLI, писавшая `release.yml`, старше `5b8ab22` и закрепила объект тега. См. [как понять, есть ли в вашей сборке исправление](#баг-который-ломает-первый-релиз-и-как-понять-есть-ли-в-вашей-сборке-исправление) |

## Дальше

- **[Что такое публикация](publishing.md)** — весь путь, от пустого
  каталога до плагина в каталоге, на одной странице.
- [Быстрый старт](2-tutorial/getting-started.md) — написание самого
  плагина.
