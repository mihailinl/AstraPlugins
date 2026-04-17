# Справочник CLI `astra-plugin`

Каждая подкоманда, флаг и поведение — взято из `astra-plugin-cli/src/main.rs` и `astra-plugin-cli/src/commands/`.

## Установка

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Выполните `astra-plugin --help`, чтобы увидеть полный список команд. Каждая подкоманда также принимает `--help`.

## `astra-plugin create`

Сгенерировать скелет нового проекта плагина из шаблона для выбранного языка.

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| Аргумент / флаг | По умолчанию | Описание |
| --- | --- | --- |
| `NAME` | — | Идентификатор плагина. Должен содержать строчные буквы, цифры и дефисы — становится значением `[plugin].id` в манифесте. |
| `-l, --lang` | `rust` | Один из `rust`, `python` (алиас `py`), `typescript` (алиас `ts`). |
| `-c, --capabilities` | `tools` | Список, разделённый запятыми. Допустимые токены: `tools`, `tts`, `stt`, `ai_provider`, `actions`, `triggers`, `client`, `event_handlers`, `ui_panels`. Пробелы вокруг запятых обрезаются. |
| `-o, --output` | `./<NAME>` | Целевая директория. |

### Что генерируется

Все шаблоны включают:

- `plugin.toml` — манифест, предзаполненный с id, name, версией `0.1.0` и секцией `[capabilities]`, в которой включены запрошенные вами возможности.
- `proto/plugin.proto` — локальная копия протокола плагинов.
- `.gitignore`, `README.md`.

Дополнительные файлы по языкам:

| Язык | Дополнительные файлы |
| --- | --- |
| `rust` | `Cargo.toml` (с `astra-plugin-sdk`, `tokio`, `serde`, `anyhow`, `async-trait`), `src/main.rs` с заготовкой реализации `PluginCapability`. `entry.command` установлен в `target/release/<name>.exe`. |
| `python` | `pyproject.toml` (с `astra-plugin-sdk`, `grpcio`, `protobuf`), `src/plugin.py` с заготовкой подкласса `Plugin`. `entry.command = "python"`, `args = ["-m", "src.plugin"]`, `runtimes = ["python"]`. |
| `typescript` | `package.json`, `tsconfig.json`, `src/index.ts` с заготовкой подкласса `Plugin`. `entry.command = "node"`, `args = ["dist/index.js"]`, `runtimes = ["node"]`. |

## `astra-plugin dev`

Запустить плагин в режиме разработки с отслеживанием файлов и автоматической пересборкой/перезапуском.

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| Аргумент / флаг | По умолчанию | Описание |
| --- | --- | --- |
| `PATH` | `.` | Директория плагина (та, в которой лежит `plugin.toml`). |
| `--daemon-addr` | `127.0.0.1:50051` | gRPC-адрес работающего демона Astra. |

### Что она делает

1. Читает `plugin.toml` и определяет команду сборки для каждого языка.
2. Запускает наблюдателя за файлами в директории плагина (игнорируя `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`).
3. Выполняет сборку (`cargo build` для Rust, `bun run build` / `tsc` для TypeScript, `uv pip sync` / ничего для Python).
4. Запускает `entry.command` с добавленными параметрами `--daemon-addr`, `--plugin-id` и `--auth-token`.
5. При изменении файлов: завершает дочерний процесс, пересобирает, перезапускает.

Ошибки выводятся прямо в консоль. Нажмите `Ctrl+C`, чтобы остановить.

## `astra-plugin build`

Упаковать плагин в распространяемый архив `.astraplugin`.

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| Аргумент / флаг | По умолчанию | Описание |
| --- | --- | --- |
| `PATH` | `.` | Директория плагина. |
| `-o, --output` | `<id>-<version>.astraplugin` | Путь к архиву. |

### Шаги сборки по языкам

| Язык | Шаги |
| --- | --- |
| `rust` | Выполняет `cargo build --release`, копирует бинарник в `bin/` внутри архива, переписывает `entry.command` так, чтобы он указывал на путь внутри бандла. |
| `typescript` | Выполняет `bun build src/index.ts --outdir dist` либо использует `npx esbuild` как запасной вариант. Собранный JS попадает в `dist/` внутри архива. |
| `python` | Если `uv` есть в `PATH`, генерирует `requirements.lock` через `uv pip compile`. Копирует `src/`, `pyproject.toml`, `requirements.txt` и lock-файл. |

### Структура архива

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

Если существует `~/.astra/plugin-keys/private.key`, CLI **автоматически подписывает** архив при каждой сборке — дополнительный флаг не нужен.

## `astra-plugin validate`

Проверить манифест и схему конфигурации без сборки.

```bash
astra-plugin validate [PATH]
```

Проверяемые элементы:

- Обязательные поля манифеста: `plugin.id`, `plugin.name`, `plugin.version`, `entry.command`.
- `plugin.id` содержит строчные буквы, цифры и дефисы.
- `plugin.version` соответствует SemVer `X.Y.Z` (предупреждение, не ошибка, если нет).
- Включена хотя бы одна возможность (предупреждение, если все выключены).
- `[config].schema`, если присутствует, парсится как JSON и имеет `"type": "object"` в корне.
- Предупреждения о метаданных: отсутствует `description` или `author`.

Завершается с ненулевым кодом только при серьёзных ошибках (непарсящийся TOML, отсутствующие обязательные поля).

## `astra-plugin keygen`

Сгенерировать пару ключей Ed25519, используемую `build` для подписи архивов.

```bash
astra-plugin keygen [--force]
```

| Флаг | Описание |
| --- | --- |
| `--force` | Перезаписать существующую пару ключей. Без этого флага команда откажется заменять уже имеющиеся ключи. |

Расположение выходных файлов (создаются, если отсутствуют):

- `~/.astra/plugin-keys/private.key` — приватное зерно Ed25519 в base64 (храните в секрете).
- `~/.astra/plugin-keys/public.key` — публичный ключ Ed25519 в base64 (можно делиться).

Как только пара ключей существует, каждая `astra-plugin build` автоматически добавляет запись `SIGNATURE` (HMAC-подобный дайджест каждой ZIP-записи, подписанный Ed25519) и запись `PUBKEY`, чтобы потребители могли проверить подлинность.

## Окружение

- `RUST_LOG` — управляет уровнем детализации вывода CLI. По умолчанию — уровень warning; используйте `RUST_LOG=debug` для полной трассировки.
- Все команды CLI используют текущий `PATH` оболочки при поиске `cargo`, `node`, `bun`, `npx`, `python` и `uv`.
