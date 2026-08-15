# Платформи

> Переклад. Джерело істини — [docs/en](../../en/1-orientation/platforms.md); за розбіжності відповідає англійська версія.

Astra постачає демон для **двох** хостів. Усе нижче випливає з цього.

| Ключ платформи | Хост | Astra постачає демон |
|---|---|---|
| `linux-x64` | Linux, x86_64 | так |
| `windows-x64` | Windows, x86_64 | так |
| `noarch` | будь-який — інтерпретований плагін без нативного коду | н/д, працює на обох |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **ні** |

Останній рядок — *зарезервовано, не підтримується*. Ці назви існують у схемі
реєстру, щоб формат індексу не довелося змінювати, якщо Astra пізніше
постачить демон для цих хостів, і щоб валідатор міг відхилити одруківку
(`mac-amd64`) замість того, щоб записати ключ, який демон ніколи не буде
шукати. У бандла, опублікованого під одним з них, немає хоста, на якому він
міг би працювати. `astra-plugin build` відмовляється вгадувати: на хості, для
якого в неї немає ключа, вона каже передати `--target` явно, а не мовчки
пакувати щось, що зведеться до `linux-x64`.

## Один бандл на платформу, і що визначає, скільки їх вам потрібно

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** компілюється в нативний код, тому потрібен один бандл на
  платформу. Workflow релізу збирає їх за матрицею — `ubuntu-24.04` і
  `windows-2022` — тому що крос-збірка — це окремий набір багів.
- **TypeScript і Python** виробляють єдиний бандл `noarch`. Індекс записує
  той самий URL і дайджест під кожним підтримуваним ключем платформи, тож
  `noarch`-бандл знаходиться під `linux-x64` і `windows-x64` так само, як
  будь-який інший.

`--all-targets` збирає все, що потрібно плагіну, щоб встановлюватися всюди,
де працює Astra: один файл для TypeScript і Python, по одному на платформу
для Rust, кожен зі свого `cargo build --target`.

## `[platform]`, і чому пропущений блок — це заява

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

Порожній або відсутній `[platform]` означає *немає вимог*, і демон вважає
плагін сумісним всюди. Це правильно для `noarch`-плагіна і неправильно для
того, що постачає нативний бінарник. `astra-plugin doctor` каже про це рівно
цими словами:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` проставляє справжню відповідь у `MANIFEST` бандла з
`--target`, тож упакований файл несе `{os, arch}`, що б не казав маніфест.

## Вимоги для збірки

| Мова | Потрібно | Перевіряється |
|---|---|---|
| Rust | Rust **1.85 або новіший** — SDK і заготовка використовують edition 2024 | `astra-plugin doctor` |
| Rust | **`protoc` у PATH.** `astra-plugin-sdk/build.rs` компілює `proto/plugin.proto` через `tonic_build::configure().compile_protos(…)`, а tonic-build 0.12 викликає зовнішній `protoc`, а не постачає свій. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ для запуску і `bun` (або бандлер зі скрипта `build`) для збірки | `astra-plugin doctor` |
| Python | `python3`, плюс `grpcio` і `protobuf` з `requirements.txt` | `astra-plugin doctor` |

`protoc` — той, що кусає першим і виглядає як щось інше. CLI залежить від
Rust SDK, тому він потрібен, щоб *встановити сам `astra-plugin`* — ще до
того, як у вас з'явиться проєкт, маніфест чи хоч якась причина підозрювати
компілятор protobuf. Без нього `cargo install` зупиняється на
`error: failed to run custom build command for astra-plugin-sdk`, з
`Could not find `protoc`` кількома рядками нижче. Власний CI цього
репозиторію встановлює його в кожному Rust-завданні (`arduino/setup-protoc@v3`,
сім разів у `.github/workflows/ci.yml`), що і є найяснішим доказом того, що
він не опціональний.

`astra-plugin doctor` відповідає на все це однією командою, на тій машині, на
якій ви справді перебуваєте:

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

### Нижня межа glibc

Linux-бандл, зібраний у CI, перевіряється проти **GLIBC_2.39** — workflow
релізу розбирає кожен об'єкт ELF у готовому архіві і провалює збірку, якщо
чомусь потрібна новіша версія символу. Саме це робить так, що плагін,
зібраний на `ubuntu-24.04`, працює на дистрибутивах, на які націлена Astra, і
це той тип збою, який інакше з'являється лише на машині користувача.

Якщо ви зберете Linux-бандл вручну на новішому дистрибутиві, це ніхто не
перевірить. Це одна з кількох причин, чому шлях релізу — це CI.

### TypeScript-бандли не несуть `node_modules`

`.astraplugin` постачає зібраний вивід, а не дерево залежностей. Workflow
релізу перевіряє, що бандл самодостатній: випадковий `require("chalk")`,
який бандлер не зміг відстежити, встановиться нормально і впаде при першому
запуску з `MODULE_NOT_FOUND`, на машині, де це нікому полагодити.

## Де що лежить, за ОС

Astra визначає свої каталоги через крейт `directories`, з
`("com", "astra", "astra")` — CLI використовує ідентичний виклик, тож ці два
не можуть розійтися (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Каталог конфігурації | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Файл порту демона | `<config>/daemon.port` | той самий |
| Секрет самозавантаження демона | `<config>/daemon.token` | той самий |
| Встановлені плагіни | `<config>/plugins/<id>/` | той самий |
| Налаштування плагіна | `<config>/plugins/<id>/config.json` | той самий |
| Логи демона | `<config>/logs/` | той самий |

Питайте, а не припускайте — `doctor` друкує шлях, який визначила ця машина:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

Демон займає призначений ОС порт, коли 32000 зайнятий, тож
`127.0.0.1:32000` — це запасне припущення, а `daemon.port` — це факт.

## macOS

Не підтримується, і не через недогляд. Власний workflow релізу Astra збирає
лише `linux-x64` і `windows-x64`, тож у бандла плагіна під `macos-arm64` не
було б хоста для запуску; macOS додатково вимагала б нотаризацію Apple для
кожного стороннього автора. Назви ключів зарезервовані в схемі індексу, ніхто
їх не видає, а необроблений хост — це жорстка помилка, а не тихий відкат.
Повернутися до цього в релізі, де Astra постачить демон для цієї цілі.
