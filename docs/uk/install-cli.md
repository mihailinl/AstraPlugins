# Встановлення CLI

> Переклад. Джерело істини — [docs/en](../en/install-cli.md); за розбіжності відповідає англійська версія.

Увесь шлях публікації починається з команди, і це сторінка, яка дає вам цю
команду. Бінарник зветься **`astra-plugin`** — не `astra-plugin-cli`, це
лише ім'я крейта.

## Чесний стан цього

**Готових бінарників поки немає, і `astra-plugin-cli` не на crates.io.**
Перевірено сьогодні: `https://index.crates.io/as/tr/astra-plugin-cli`
відповідає `404`, тоді як `astra-plugin-sdk` на тому самому індексі
відповідає `200`, тож це реальна відсутність, а не провалений запит. `gh
release list --repo mihailinl/AstraPlugins` не друкує нічого.

Тож єдиний спосіб отримати CLI — зібрати її, а для збірки потрібен тулчейн
Rust. Постачання готових бінарників — відома, окрема, незакрита задача:
автоматизація релізу для неї пишеться просто зараз, і на цій сторінці
з'явиться рядок для завантаження того дня, коли з'явиться реліз, який можна
завантажити. До того вона описує все, що є, і ніщо тут не просить вас
щось завантажувати.

Ця ціна реальна, і варто назвати, чому її все одно варто платити: CLI — не
обгортка для зручності навколо якогось простішого шляху. Це єдине, що
пише правильний workflow релізу, єдине, що не дає вашим маніфестам
розійтися у версії, і єдине, що відкриває заявку на лістинг, яку бот
реєстру реально побачить. Обхід її — це те, як дві реальні заявки
закінчилися тишею — див. [що таке публікація](publishing.md).

## Передумови

| | Навіщо | Перевірка |
|---|---|---|
| **Rust 1.85 або новіший** | кожен крейт тут `edition = "2024"`, а 1.85 — перший реліз, що його розуміє | `cargo --version` |
| **`protoc` у `PATH`** | CLI залежить від `astra-plugin-sdk`, чий `build.rs` компілює `proto/plugin.proto` через `tonic-build`, який викликає зовнішній `protoc` | `protoc --version` |
| **`git`** | `cargo install --git` клонує через нього | `git --version` |

Жоден крейт не оголошує `rust-version`, а CI збирає на `stable`, тож
edition — єдина реально застосовувана нижня межа.

Встановлення `protoc`, яке найчастіше пропускають:

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

Без нього збірка падає у скрипті збірки `astra-plugin-sdk`, і помилка
називає рішення:

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## Встановіть її

**Один рядок, без клонування.** Ось той, який треба використовувати:

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` збирає проти зафіксованого в репозиторії `Cargo.lock`, а не
перерозв'язує кожну залежність до її найновішого релізу, а це різниця між
збіркою, що працює так само, як працювала тут, і тією, що дізнається про
ламаючий патч-реліз прямо на вашій машині.

`--git` збирає те, що зараз несе `master`, тож версія й коміт, які вона
повідомляє, — ті, що на `master` у момент запуску. Усе, що в кутових дужках
нижче, різниться від машини до машини і від запуску до запуску: версія і SHA
приходять з `master`, шляхи — з вашого домашнього каталогу, тривалість — від
вашого процесора.

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

Цей запис знято з `--root <scratch>`, щоб його отримання не перезаписало
чийсь встановлений бінарник. **Не вказуйте `--root`** — як і робить команда
вище — і останні два рядки зміняться: `Installing` назве
`<home>/.cargo/bin/astra-plugin`, а попередження про `PATH` з'явиться лише
якщо `~/.cargo/bin` ще не у вашому `PATH`. Два SHA — це один і той самий
коміт, надрукований у двох різних довжинах; так робить cargo, це не
розбіжність.

**З клону**, якщо ви хочете читати або міняти CLI, а не лише запускати її:

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

Звичайний `git clone` викачує `master`, а `master` — це те місце, де живе
поточна CLI, — немає жодної гілки, про яку треба знати окремо.

## Перевірте, що спрацювало

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

Число тут — заповнювач, бо жоден із двох рядків встановлення не дає вам
обрати версію: обидва збирають коміт, а не реліз, тож ви отримуєте версію з
`Cargo.toml` цього коміту. `0.2.1` — найсвіжіший запис у
[changelog CLI](../../astra-plugin-cli/CHANGELOG.md), де також записано, що
в цього крейта немає релізного потяга: ні crates.io, ні тега, ні бінарників.

Якщо оболонка її не знаходить, `cargo install` помістила її в
`~/.cargo/bin` (або `%USERPROFILE%\.cargo\bin` на Windows), а цього
каталогу немає у вашому `PATH`. `cargo` друкує попередження про це рівно
тоді, коли це трапляється.

### Баг, який ламає перший реліз, і як зрозуміти, чи є у вашій збірці виправлення

**`astra-plugin init-ci` раніше закріплював SHA *об'єкта* анотованого тега
там, де GitHub вимагає коміт**, тож перший `git push --tags` падав з
`invalid value workflow reference` ще до старту будь-якого завдання. Це був
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Виправлення — це коміт `5b8ab22`, а не номер версії**, і саме на цьому
люди спотикаються. Тут немає релізного потяга: ніщо не опубліковано, тож
ніхто не встановлює обрану версію — усі збирають той коміт, який
склонували. `5b8ab22` потрапив до `master` *раніше*, ніж бамп, що підняв
число до `0.2.1`, а отже:

- збірка з `master` після `5b8ab22` **містить виправлення і все одно друкує
  `0.2.0`** — це не зламана збірка;
- жодна збірка `0.2.1` не може бути *без* виправлення, бо `5b8ab22` —
  предок коміту з бампом;
- зламана — це збірка `0.2.0`, зроблена *до* `5b8ab22`, і `--version` не
  відрізняє її від першого випадку.

Тож `0.2.1` варто мати — це перше число, яке відповідає на питання само по
собі, саме для цього воно й існує, — але `0.2.0`, що каже `0.2.0`, не
доводить нічого. `0.2.1` не додає прапорців і не змінює API; єдина зміна
поведінки — `publish --notify`, чиє посилання тепер називає форму
release-ping реєстру замість порожнього issue, який реєстр відтоді вимкнув.

Якщо `--version` друкує `0.2.0`, спершу запустіть `which astra-plugin`
(`where` на Windows): найчастіша причина — старіший бінарник стоїть раніше
у вашому `PATH`, а сама лише `--version` не відрізняє це від свіжої збірки
старішого коміту. Далі перестаньте вгадувати за числом і прочитайте пін:
`init-ci` записує саме те, через що був баг, і відповідає одним рядком.

Ось перевірка, яка взагалі не залежить від версії:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Збірка з виправленням повідомляє закріплення
`e3329df252a46d747676cb540ae4b986af68a3ad` — коміт. Збірка без нього
повідомляє `dc1a044876926e9cf1170f034e2eab533ec07641`, а це *об'єкт тега*
`plugin-release/v1`, і саме його відхиляє GitHub. Якщо ви бачите друге,
перевстановіть з `master` рядком вище і запустіть `init-ci` знову. Її
безпечно перезапускати: вона зберігає ваші вхідні параметри і переписує
закріплення. Ніщо не лагодиться на місці, тож наявний `release.yml` тримає
поганий SHA, поки ви його не перезапустите.

Повний набір команд:

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

**`astra-plugin login` не існує**, і це навмисно, а не незакінчено: ніщо в
цьому тулчейні ніколи не питає у вас облікові дані. Див.
[потрапити до каталогу](5-publish/get-listed.md).

## Як її оновлювати

Перезапустіть той самий рядок `cargo install --git`. Cargo замінює
бінарник на місці. Самооновлення немає, і не буде, поки не з'являться
підписані релізні бінарники, до яких можна оновлюватися.

## Що йде не так

| Симптом | Причина |
|---|---|
| `Could not find` protoc` ` | `protoc` немає в `PATH`. Див. таблицю вище |
| `feature `edition2024` is required` | Rust старіший за 1.85 |
| `astra-plugin: command not found` після успішного встановлення | `~/.cargo/bin` немає в `PATH` |
| `error: could not find `Cargo.toml`` при запуску `cargo install --path .` в корені репозиторію | У корені немає workspace-маніфесту. Спрямуйте `--path` на `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Старіша `astra-plugin` стоїть раніше у вашому `PATH`. `--version` не допоможе їх розрізнити — запустіть `which astra-plugin` (`where` на Windows), щоб побачити, який файл ви реально запускаєте |
| `invalid value workflow reference` при першому пуші тега | CLI, що писала `release.yml`, старша за `5b8ab22` і закріпила об'єкт тега. Див. [як зрозуміти, чи є у вашій збірці виправлення](#баг-який-ламає-перший-реліз-і-як-зрозуміти-чи-є-у-вашій-збірці-виправлення) |

## Далі

- **[Що таке публікація](publishing.md)** — весь шлях, від порожнього
  каталогу до плагіна в каталозі, на одній сторінці.
- [Початок роботи](2-tutorial/getting-started.md) — написання самого
  плагіна.
