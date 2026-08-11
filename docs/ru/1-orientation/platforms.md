# Платформы

Astra выпускает демон для **двух** хостов. Всё остальное на этой странице
следует из этого.

| Ключ платформы | Хост | Astra выпускает демон |
|---|---|---|
| `linux-x64` | Linux, x86_64 | да |
| `windows-x64` | Windows, x86_64 | да |
| `noarch` | любой — интерпретируемый плагин без нативного кода | не применимо, работает на обоих |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **нет** |

Последняя строка — *зарезервировано, но не поддерживается*. Имена существуют в
схеме реестра, чтобы формат индекса не пришлось менять, если Astra однажды
выпустит демон под эти хосты, и чтобы валидатор мог отвергнуть опечатку
(`mac-amd64`), а не записать ключ, который ни один демон никогда не спросит.
Бандл, опубликованный под таким ключом, негде запускать. `astra-plugin build`
отказывается угадывать: на хосте, для которого ключа нет, он просит явно
передать `--target`, а не пакует молча что-то, что окажется `linux-x64`.

## По бандлу на платформу, и от чего зависит их число

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** компилируется в нативный код, поэтому нужен бандл на платформу.
  Релизный workflow собирает их матрицей — `ubuntu-24.04` и `windows-2022`, —
  потому что кросс-сборка это другой набор ошибок.
- **TypeScript и Python** дают один бандл `noarch`. Индекс пишет один и тот же
  URL и дайджест под каждым поддерживаемым ключом платформы, поэтому бандл
  `noarch` находится под `linux-x64` и `windows-x64` как любой другой.

`--all-targets` собирает всё, что нужно плагину, чтобы устанавливаться везде,
где работает Astra: один файл для TypeScript и Python, по одному на платформу
для Rust, каждый своей `cargo build --target`.

## `[platform]`, и почему отсутствие блока — это утверждение

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

Пустой или отсутствующий `[platform]` означает *нет требований*, и демон считает
плагин совместимым везде. Для `noarch`-плагина это верно, для плагина с нативным
бинарником — нет. `astra-plugin doctor` говорит именно это:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` штампует настоящий ответ в `MANIFEST` бандла из
`--target`, поэтому упакованный файл несёт пару `{os, arch}` независимо от того,
что написано в манифесте.

## Что нужно для сборки

| Язык | Нужно | Проверяется |
|---|---|---|
| Rust | Rust **1.85 или новее** — SDK и шаблон на edition 2024 | `astra-plugin doctor` |
| Rust | **`protoc` в PATH.** `astra-plugin-sdk/build.rs` компилирует `proto/plugin.proto` через `tonic_build::configure().compile_protos(…)`, а tonic-build 0.12 вызывает внешний `protoc` и своего не несёт. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ для запуска и `bun` (или бандлер из скрипта `build`) для сборки | `astra-plugin doctor` |
| Python | `python3` плюс `grpcio` и `protobuf` из `requirements.txt` | `astra-plugin doctor` |

`protoc` бьёт первым и выглядит не тем, чем является. CLI зависит от Rust SDK,
поэтому он нужен уже для того, чтобы **поставить сам `astra-plugin`** — до того,
как у вас появится проект, манифест и хоть какая-то причина подозревать
компилятор protobuf. Без него `cargo install` останавливается на
`error: failed to run custom build command for astra-plugin-sdk`, а строкой
ниже — `Could not find `protoc``. CI этого репозитория ставит его в каждой
Rust-джобе (`arduino/setup-protoc@v3`, семь раз в `.github/workflows/ci.yml`) —
самое честное доказательство, что он не опционален.

`astra-plugin doctor` отвечает на всё это одной командой, на той машине, где вы
на самом деле находитесь:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### Порог glibc

Linux-бандл, собранный в CI, проверяется против **GLIBC_2.39**: релизный
workflow дизассемблирует каждый ELF-объект в готовом архиве и валит сборку,
если что-то требует более новую версию символа. Именно это делает плагин,
собранный на `ubuntu-24.04`, работоспособным на дистрибутивах, на которые
рассчитывает Astra, — а иначе такая поломка вылезает только на машине
пользователя.

Если вы собираете Linux-бандл руками на более новом дистрибутиве, это никто не
проверит. Это одна из нескольких причин, по которым релизный путь — это CI.

### В TypeScript-бандлах нет `node_modules`

`.astraplugin` несёт результат сборки, а не дерево зависимостей. Релизный
workflow проверяет, что бандл самодостаточен: случайный `require("chalk")`,
который бандлер не смог отследить, ставится нормально и падает при первом
запуске с `MODULE_NOT_FOUND` на машине, где это никто не починит.

## Где что лежит, по ОС

Astra определяет свои каталоги крейтом `directories`, вызовом
`("com", "astra", "astra")` — CLI делает ровно такой же вызов, поэтому они не
могут разойтись (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Каталог конфигурации | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Файл порта демона | `<config>/daemon.port` | так же |
| Секрет демона | `<config>/daemon.token` | так же |
| Установленные плагины | `<config>/plugins/<id>/` | так же |
| Настройки плагина | `<config>/plugins/<id>/config.json` | так же |
| Логи демона | `<config>/logs/` | так же |

Не гадайте — спросите: `doctor` печатает путь, который вычислила эта машина:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

Демон занимает выданный ОС порт, если 32000 занят, поэтому `127.0.0.1:32000` —
это догадка по умолчанию, а факт — это `daemon.port`.

## macOS

Не поддерживается, и не по забывчивости. Собственный релизный workflow Astra
собирает только `linux-x64` и `windows-x64`, поэтому бандлу `macos-arm64` не на
чем работать; macOS вдобавок означала бы нотаризацию Apple для каждого стороннего
автора. Имена ключей зарезервированы в схеме индекса, никто их не выпускает, а
необработанный хост — жёсткая ошибка, а не тихий откат. Вернуться к вопросу в том
релизе, где Astra выпустит демон под эту цель.
