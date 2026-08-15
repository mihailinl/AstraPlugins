# Встановлення CLI

> Переклад. Джерело істини — [docs/en](../en/install-cli.md); за розбіжності відповідає англійська версія.

Увесь шлях публікації починається з команди, і це сторінка, яка дає вам цю
команду. Бінарник зветься **`astra-plugin`** — не `astra-plugin-cli`, це
лише ім'я крейта.

## Два шляхи, і який вам потрібен

**Завантажте бінарник.** Реліз [`cli-v0.2.1`][rel] несе готові архіви для
Linux і Windows, файл контрольних сум і пакет Sigstore, який можна
перевірити. Нічого не треба компілювати, тулчейн не задіяний. Це шлях,
який потрібен більшості людей, і він нижче.

**Або зберіть із вихідників** — потрібен Rust 1.85 або новіший і `protoc`.
Беріть цей шлях, якщо ви на платформі без архіву — сьогодні це macOS і ARM
Linux, — або якщо хочете читати чи змінювати CLI, а не лише запускати її.

**`cargo install astra-plugin-cli` — не один із шляхів і працювати не
буде.** Крейт залежить від завендореного `astra-plugin-manifest` за шляхом
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`), cargo
ніколи не пакує вихідники залежності за шляхом, і публікація тому падає з
*all dependencies must have a version requirement specified* — тож крейта
взагалі немає на crates.io (`https://index.crates.io/as/tr/astra-plugin-cli`
відповідає `404` сьогодні, тоді як `astra-plugin-sdk` на тому самому
індексі відповідає `200`). Зняти блокування означає спершу випустити крейт
маніфесту від Astra, і ця сторінка не обіцяє дату для цього.

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## Завантажте бінарник

### Який архів

| Ви на | Беріть |
|---|---|
| **Будь-який Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux, і вам конкретно потрібна збірка glibc | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl — безпечний вибір за замовчуванням, і причина не в смаку.** Збірка
gnu динамічно злінкована, і її таблиця символів вимагає **glibc 2.39 або
новіший**, якого немає в Ubuntu 22.04 (2.35), Debian 12 (2.36) і RHEL 9
(2.34) — на будь-якій з них вона не запуститься, а не буде тонко
барахлити. Архів musl — це виконуваний файл `static-pie` взагалі без
залежності від libc, тож він працює на будь-якій з них. Беріть gnu, лише
якщо точно знаєте, що він вам потрібен.

Повний список артефактів цього релізу, тобто все опубліковане:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### Завантажте і перевірте

Linux, через `curl` — тут не потрібен ні `gh`, ні акаунт GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

Ось реальний запис цих команд:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**Використовуйте `--ignore-missing`.** `SHA256SUMS.txt` перелічує всі три
архіви, тож звичайний `sha256sum -c SHA256SUMS.txt` повідомить про два, які
ви не завантажили, як `FAILED open or read` і **вийде з 1** — що виглядає
точнісінько як пошкоджене завантаження, а насправді ні:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

Архів розпаковується в каталог, що містить бінарник і файли ліцензії:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

Перемістіть `astra-plugin` кудись у свій `PATH` — звична відповідь —
`~/.local/bin`, і `sudo` не потрібен:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

На Windows завантажте `.zip` зі сторінки релізу, розпакуйте його і
покладіть `astra-plugin.exe` у свій `PATH`. `certutil -hashfile <file>
SHA256` — вбудований інструмент контрольних сум, і його вивід порівнюється
з `SHA256SUMS.txt` на око.

### Перевірте, хто його зібрав

Контрольна сума доводить, що байти збігаються з файлом, названим у релізі.
Вона не доводить, хто виробив цей файл — для цього є пакет Sigstore, і `gh`
звіряє його з атестацією збірки GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**Успіх нічого не друкує, коли вивід не в термінал, і виходить з `0`.**
Це збиває з пантелику вперше; перевіряйте `echo $?`, а не шукайте
галочку. Провал — гучний і виходить з `1`:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

Це було вироблено додаванням одного байта до архіву; вказання `--repo` на
репозиторій, що його не збирав, падає точнісінько так само. Один пакет
покриває всі три архіви, і що він засвідчує, можна прочитати через
`--format json`: workflow підпису —
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`,
видавець — `https://token.actions.githubusercontent.com`, а три дайджести
subject — це три рядки `SHA256SUMS.txt`. `gh attestation verify` потрібен
мережевий доступ, щоб отримати корінь довіри, але не логін GitHub.

## Зберіть із вихідників

Беріть цей шлях для macOS чи ARM Linux, де архіву поки немає, або щоб
працювати над самою CLI. Це не запасний варіант на випадок невдалого
завантаження — бінарник вище — та сама програма.

### Передумови

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

### Зберіть її

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

Щоб зібрати той самий код, з якого зібрані опубліковані бінарники, а не те,
що несе `master` сьогодні, спершу викачайте тег релізу:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

Завантажений бінарник друкує `astra-plugin 0.2.1`, бо архів зібраний з тега
`cli-v0.2.1` і нічого більше. `<version>` — заповнювач лише на шляху з
вихідників: `cargo install --git` збирає те, що несе `master` у цей
момент, тож ви отримуєте версію з `Cargo.toml` цього коміту, яка може
випереджати найсвіжіший реліз. `0.2.1` — найсвіжіший запис у
[changelog CLI](../../astra-plugin-cli/CHANGELOG.md).

Якщо оболонка її не знаходить: завантажений бінарник лежить там, куди ви
його скопіювали, а `cargo install` кладе його в `~/.cargo/bin` (або
`%USERPROFILE%\.cargo\bin` на Windows). У будь-якому разі цього каталогу
немає у вашому `PATH`. `cargo` друкує попередження про це рівно тоді, коли
це трапляється.

### Баг, який ламає перший реліз, і як зрозуміти, чи є у вашій збірці виправлення

**`astra-plugin init-ci` раніше закріплював SHA *об'єкта* анотованого тега
там, де GitHub вимагає коміт**, тож перший `git push --tags` падав з
`invalid value workflow reference` ще до старту будь-якого завдання. Це був
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Завантаження бінарника `0.2.1` вирішує це питання, і це коротка
відповідь.** Архів зібраний з тега `cli-v0.2.1`, `5b8ab22` — предок цього
тега, тож у завантаженого бінарника є виправлення. Решта цього розділу —
про збірку з вихідників, де номер не вирішує питання.

**Виправлення — це коміт `5b8ab22`, а не номер версії**, і саме на цьому
люди спотикаються. Збірка з вихідників встановлює той коміт, який ви
склонували, а не обраний реліз. `5b8ab22` потрапив до `master` *раніше*,
ніж бамп, що підняв число до `0.2.1`, а отже:

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

Якщо ви завантажили бінарник, завантажте архів наступного релізу і
замініть файл — звірте контрольну суму знову, адже новий реліз означає
нові байти. Якщо ви зібрали з вихідників, перезапустіть той самий рядок
`cargo install`, і cargo замінить бінарник на місці. **Самооновлення
немає**, і ніщо в цьому тулчейні не телефонує додому, щоб дізнатися, що
вийшла нова версія.

## Що йде не так

| Симптом | Причина |
|---|---|
| `FAILED open or read` від `sha256sum -c` | Ви завантажили один архів, а файл перелічує три. Додайте `--ignore-missing` |
| `Error: verifying with issuer "sigstore.dev"` | Архів не збігається з пакетом, або `--repo` називає репозиторій, що його не збирав. Завантажте заново, а не міркуйте про це |
| `gh attestation verify` взагалі нічого не надрукував | Це успіх. Вона тиха, коли вивід не в термінал; `echo $?` покаже `0` |
| Бінарник не запускається, і завантажувач скаржиться, що не знайдено версію `GLIBC_2.39` | Ви взяли архів gnu на системі зі старим glibc. Візьміть musl — йому не потрібен libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` не може спрацювати, і ось що вона про це каже. Див. початок цієї сторінки |
| `Could not find` protoc` ` | `protoc` немає в `PATH`. Див. таблицю вище |
| `feature `edition2024` is required` | Rust старіший за 1.85 |
| `astra-plugin: command not found` після успішного встановлення | Каталог з бінарником немає в `PATH` — для збірки з вихідників це `~/.cargo/bin` |
| `error: could not find `Cargo.toml`` при запуску `cargo install --path .` в корені репозиторію | У корені немає workspace-маніфесту. Спрямуйте `--path` на `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Старіша `astra-plugin` стоїть раніше у вашому `PATH`. `--version` не допоможе їх розрізнити — запустіть `which astra-plugin` (`where` на Windows), щоб побачити, який файл ви реально запускаєте |
| `invalid value workflow reference` при першому пуші тега | CLI, що писала `release.yml`, старша за `5b8ab22` і закріпила об'єкт тега. Див. [як зрозуміти, чи є у вашій збірці виправлення](#баг-який-ламає-перший-реліз-і-як-зрозуміти-чи-є-у-вашій-збірці-виправлення) |

## Далі

- **[Що таке публікація](publishing.md)** — весь шлях, від порожнього
  каталогу до плагіна в каталозі, на одній сторінці.
- [Початок роботи](2-tutorial/getting-started.md) — написання самого
  плагіна.
