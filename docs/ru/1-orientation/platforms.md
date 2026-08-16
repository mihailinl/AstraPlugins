# Платформы

> Перевод. Источник истины — [docs/en](../../en/1-orientation/platforms.md); при расхождении верна английская версия.

Astra поставляет демон для **двух** хостов. Всё ниже следует из этого.

| Ключ платформы | Хост | Astra поставляет демон |
|---|---|---|
| `linux-x64` | Linux, x86_64 | да |
| `windows-x64` | Windows, x86_64 | да |
| `noarch` | любой — интерпретируемый плагин без нативного кода | н/д, работает на обоих |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **нет** |

Последняя строка — *зарезервировано, не поддерживается*. Эти имена существуют
в схеме реестра, чтобы формат индекса не пришлось менять, если Astra позже
поставит демон для этих хостов, и чтобы валидатор мог отклонить опечатку
(`mac-amd64`) вместо того, чтобы записать ключ, который демон никогда не
станет искать. У бандла, опубликованного под одним из них, нет хоста, на
котором он мог бы работать. `astra-plugin build` отказывается угадывать: на
хосте, для которого у неё нет ключа, она говорит передать `--target` явно, а
не молча упаковывать что-то, что сведётся к `linux-x64`.

## Один бандл на платформу, и что определяет, сколько их вам нужно

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** компилируется в нативный код, поэтому нужен один бандл на
  платформу. Workflow релиза собирает их по матрице — `ubuntu-24.04` и
  `windows-2022` — потому что кросс-сборка — это отдельный набор багов.
- **TypeScript и Python** производят единый бандл `noarch`. Индекс
  записывает один и тот же URL и дайджест под каждым поддерживаемым ключом
  платформы, так что `noarch`-бандл находится под `linux-x64` и
  `windows-x64` так же, как любой другой.

`--all-targets` собирает всё, что нужно плагину, чтобы устанавливаться везде,
где работает Astra: один файл для TypeScript и Python, по одному на
платформу для Rust, каждый из своего `cargo build --target`.

## `[platform]`, и почему пропущенный блок — это заявление

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

Пустой или отсутствующий `[platform]` означает *нет требований*, и демон
считает плагин совместимым везде. Это верно для `noarch`-плагина и неверно
для того, что поставляет нативный бинарник. `astra-plugin doctor` говорит об
этом ровно этими словами:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` проставляет настоящий ответ в `MANIFEST` бандла из
`--target`, так что упакованный файл несёт `{os, arch}`, что бы ни говорил
манифест.

## Требования для сборки

| Язык | Нужно | Проверяется |
|---|---|---|
| Rust | Rust **1.85 или новее** — SDK и заготовка используют edition 2024 | `astra-plugin doctor` |
| Rust | **`protoc` в PATH.** `astra-plugin-sdk/build.rs` компилирует `proto/plugin.proto` через `tonic_build::configure().compile_protos(…)`, а tonic-build 0.12 вызывает внешний `protoc`, а не поставляет свой. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ для запуска и `bun` (или бандлер из скрипта `build`) для сборки | `astra-plugin doctor` |
| Python | `python3`, плюс `grpcio` и `protobuf` из `requirements.txt` | `astra-plugin doctor` |

`protoc` — тот, что кусает первым и выглядит как что-то другое. CLI зависит от
Rust SDK, поэтому он нужен, чтобы *установить сам `astra-plugin`* — ещё до
того, как у вас появится проект, манифест или хоть какая-то причина
подозревать компилятор protobuf. Без него `cargo install` останавливается на
`error: failed to run custom build command for astra-plugin-sdk`, с
`Could not find `protoc`` несколькими строками ниже. Собственный CI этого
репозитория устанавливает его в каждой Rust-задаче (`arduino/setup-protoc@v3`,
семь раз в `.github/workflows/ci.yml`), что и есть самое ясное доказательство
того, что он не опционален.

`astra-plugin doctor` отвечает на всё это одной командой, на той машине, на
которой вы действительно находитесь:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
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

### Нижняя граница glibc

Linux-бандл, собранный в CI, проверяется против **GLIBC_2.39** — workflow
релиза разбирает каждый объект ELF в готовом архиве и роняет сборку, если
чему-то нужна более новая версия символа. Именно это делает так, что плагин,
собранный на `ubuntu-24.04`, работает на дистрибутивах, на которые нацелена
Astra, и это тот тип сбоя, который иначе появляется только на машине
пользователя.

Если вы соберёте Linux-бандл вручную на более новом дистрибутиве, это никто
не проверит. Это одна из нескольких причин, почему путь релиза — это CI.

### TypeScript-бандлы не несут `node_modules`

`.astraplugin` поставляет собранный вывод, а не дерево зависимостей. Workflow
релиза проверяет, что бандл самодостаточен: случайный `require("chalk")`,
который бандлер не смог отследить, установится нормально и упадёт при первом
запуске с `MODULE_NOT_FOUND`, на машине, где это некому починить.

## Где что лежит, по ОС

Astra разрешает свои каталоги через крейт `directories`, из
`("com", "astra", "astra")` — CLI использует идентичный вызов, так что эти
два не могут разойтись (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Каталог конфигурации | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Файл порта демона | `<config>/daemon.port` | тот же |
| Секрет самозагрузки демона | `<config>/daemon.token` | тот же |
| Установленные плагины | `<config>/plugins/<id>/` | тот же |
| Настройки плагина | `<config>/plugins/<id>/config.json` | тот же |
| Логи демона | `<config>/logs/` | тот же |

Спрашивайте, а не предполагайте — `doctor` печатает путь, который вычислила
эта машина:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

Демон занимает назначенный ОС порт, когда 32000 занят, так что
`127.0.0.1:32000` — это запасное предположение, а `daemon.port` — это факт.

## macOS

Не поддерживается, и не по недосмотру. Собственный workflow релиза Astra
собирает только `linux-x64` и `windows-x64`, так что у бандла плагина под
`macos-arm64` не было бы хоста для запуска; macOS вдобавок потребовала бы
нотаризацию Apple для каждого стороннего автора. Имена ключей зарезервированы
в схеме индекса, никто их не выдаёт, а необработанный хост — это жёсткая
ошибка, а не тихий откат. Вернуться к этому в релизе, где Astra поставит
демон для этой цели.
