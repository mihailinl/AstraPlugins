# Довідник CLI `astra-plugin`

Кожна підкоманда, прапорець та поведінка — з джерел `astra-plugin-cli/src/main.rs` та `astra-plugin-cli/src/commands/`.

## Встановлення

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Запустіть `astra-plugin --help`, щоб побачити повний список команд. Кожна підкоманда також приймає `--help`.

## `astra-plugin create`

Створює шаблон нового проєкту плагіна з шаблону для відповідної мови.

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| Аргумент / прапорець | Типове значення | Опис |
| --- | --- | --- |
| `NAME` | — | Ідентифікатор плагіна. Має бути у нижньому регістрі, лише літери, цифри та дефіси — це стає значенням `[plugin].id` у маніфесті. |
| `-l, --lang` | `rust` | Один із: `rust`, `python` (псевдонім `py`), `typescript` (псевдонім `ts`). |
| `-c, --capabilities` | `tools` | Список, розділений комами. Допустимі значення: `tools`, `tts`, `stt`, `ai_provider`, `actions`, `triggers`, `client`, `event_handlers`, `ui_panels`. Пробіли навколо ком обрізаються. |
| `-o, --output` | `./<NAME>` | Каталог призначення. |

### Що генерується

Усі шаблони містять:

- `plugin.toml` — маніфест, попередньо заповнений id, name, версією `0.1.0` і розділом `[capabilities]`, увімкненим для запитаних можливостей.
- `proto/plugin.proto` — локальна копія протоколу плагінів.
- `.gitignore`, `README.md`.

Додатки для кожної мови:

| Мова | Додаткові файли |
| --- | --- |
| `rust` | `Cargo.toml` (з `astra-plugin-sdk`, `tokio`, `serde`, `anyhow`, `async-trait`), `src/main.rs` зі скелетом реалізації `PluginCapability`. `entry.command` встановлено у `target/release/<name>.exe`. |
| `python` | `pyproject.toml` (з `astra-plugin-sdk`, `grpcio`, `protobuf`), `src/plugin.py` зі скелетом підкласу `Plugin`. `entry.command = "python"`, `args = ["-m", "src.plugin"]`, `runtimes = ["python"]`. |
| `typescript` | `package.json`, `tsconfig.json`, `src/index.ts` зі скелетом підкласу `Plugin`. `entry.command = "node"`, `args = ["dist/index.js"]`, `runtimes = ["node"]`. |

## `astra-plugin dev`

Запускає плагін у режимі розробки зі спостереженням за файлами та автоматичним перезбиранням/перезапуском.

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| Аргумент / прапорець | Типове значення | Опис |
| --- | --- | --- |
| `PATH` | `.` | Каталог плагіна (той, що містить `plugin.toml`). |
| `--daemon-addr` | `127.0.0.1:50051` | gRPC-адреса запущеного демона Astra. |

### Що вона робить

1. Читає `plugin.toml` і визначає команду збирання для кожної мови.
2. Запускає спостерігач файлів у каталозі плагіна (ігноруючи `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`).
3. Виконує збирання (`cargo build` для Rust, `bun run build` / `tsc` для TypeScript, `uv pip sync` / нічого для Python).
4. Запускає `entry.command`, додаючи `--daemon-addr`, `--plugin-id` та `--auth-token`.
5. При зміні файлу: завершує дочірній процес, пересобирає, перезапускає.

Помилки виводяться на ходу. Натисніть `Ctrl+C`, щоб зупинити.

## `astra-plugin build`

Пакує плагін у архів `.astraplugin` для розповсюдження.

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| Аргумент / прапорець | Типове значення | Опис |
| --- | --- | --- |
| `PATH` | `.` | Каталог плагіна. |
| `-o, --output` | `<id>-<version>.astraplugin` | Шлях до архіву. |

### Кроки збирання для кожної мови

| Мова | Кроки |
| --- | --- |
| `rust` | Запускає `cargo build --release`, копіює бінарник у `bin/` всередині архіву, переписує `entry.command`, щоб він вказував на шлях у бандлі. |
| `typescript` | Запускає `bun build src/index.ts --outdir dist` або повертається до `npx esbuild`. Зібраний JS потрапляє у `dist/` всередині архіву. |
| `python` | Якщо `uv` є у `PATH`, генерує `requirements.lock` через `uv pip compile`. Копіює `src/`, `pyproject.toml`, `requirements.txt` і lock-файл. |

### Структура архіву

```
<plugin-id>-<version>.astraplugin           (ZIP file)
├── plugin.toml              # Manifest (entry.command rewritten for Rust)
├── bin/                     # Compiled binary (Rust only)
├── dist/                    # Bundled JS (TypeScript only)
├── src/                     # Python source
├── requirements.txt         # Python deps (unlocked)
├── requirements.lock        # Python deps (resolved by uv)
├── ui/                      # Custom UI (if present)
├── locales/                 # i18n JSON files (if present)
├── icon.png / icon.svg      # Optional branding
├── README.md / LICENSE      # Optional
├── SIGNATURE                # Ed25519 signature (if keypair exists)
└── PUBKEY                   # Signing public key (if keypair exists)
```

Якщо існує `~/.astra/plugin-keys/private.key`, CLI **автоматично підписує** архів при кожному збиранні — додатковий прапорець не потрібен.

## `astra-plugin validate`

Перевіряє маніфест і схему конфігурації без збирання.

```bash
astra-plugin validate [PATH]
```

Перевіряється:

- Обов'язкові поля маніфесту: `plugin.id`, `plugin.name`, `plugin.version`, `entry.command`.
- `plugin.id` у нижньому регістрі, лише літери, цифри та дефіси.
- `plugin.version` відповідає SemVer `X.Y.Z` (попередження, не помилка, якщо ні).
- Увімкнена принаймні одна можливість (попередження, якщо всі вимкнені).
- `[config].schema`, якщо присутня, парситься як JSON і має `"type": "object"` на кореневому рівні.
- Попередження щодо метаданих: відсутні `description` або `author`.

Виходить з ненульовим кодом лише при серйозних помилках (неможливо розібрати TOML, відсутні обов'язкові поля).

## `astra-plugin keygen`

Генерує пару ключів Ed25519, що використовується `build` для підпису архівів.

```bash
astra-plugin keygen [--force]
```

| Прапорець | Опис |
| --- | --- |
| `--force` | Перезаписує існуючу пару ключів. Без цього прапорця команда відмовляється замінювати наявні ключі. |

Місця виведення (створюються за відсутності):

- `~/.astra/plugin-keys/private.key` — base64-кодований приватний seed Ed25519 (зберігайте в таємниці).
- `~/.astra/plugin-keys/public.key` — base64-кодований публічний ключ Ed25519 (безпечно ділитися).

Коли пара ключів існує, кожне `astra-plugin build` автоматично додає запис `SIGNATURE` (HMAC-подібний дайджест кожного запису ZIP, підписаний Ed25519) і запис `PUBKEY`, щоб споживачі могли перевірити автентичність.

## Оточення

- `RUST_LOG` — керує рівнем деталізації виводу CLI. За замовчуванням — попередження; використовуйте `RUST_LOG=debug` для повного трасування.
- Усі команди CLI враховують поточний `PATH` оболонки при пошуку `cargo`, `node`, `bun`, `npx`, `python` та `uv`.
