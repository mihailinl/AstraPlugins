# Быстрый старт

Прохождение за 5 минут: установка CLI, создание шаблона плагина Rust с инструментами, запуск в режиме разработки и сборка распространяемого бандла `.astraplugin`.

## Требования

- Запущенный **демон Astra** на `127.0.0.1:50051` (gRPC-порт по умолчанию).
- **Rust** 1.75+ (для Rust-плагинов или установки CLI из исходников).
- Опционально: **Python** 3.10+ или **Node.js** 20+, если вы выбираете эти SDK.

## 1. Установка CLI

CLI `astra-plugin` создаёт, запускает, собирает, проверяет и подписывает плагины. Установите его из репозитория:

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Проверка:

```bash
astra-plugin --version
```

## 2. Создание шаблона плагина

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

CLI принимает `--lang rust|python|ts` и список `--capabilities`, разделённый запятыми. См. [справочник CLI](cli.md) для всех опций.

Сгенерированный проект Rust содержит:

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

Откройте `src/main.rs` и наполните инструмент полезным содержимым:

```rust
use astra_plugin_sdk::prelude::*;

struct HelloWorld;

#[async_trait]
impl PluginCapability for HelloWorld {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "greet".into(),
            description: "Return a greeting for the given name".into(),
            parameters_json: r#"{
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }"#.into(),
        }]
    }

    async fn call_tool(&self, _name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value = serde_json::from_str(arguments_json)
            .unwrap_or_default();
        let who = args.get("name").and_then(|v| v.as_str()).unwrap_or("world");
        ToolResult::ok(format!("Hello, {who}!"))
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(HelloWorld).await
}
```

## 3. Запуск в режиме разработки

```bash
astra-plugin dev
```

Эта команда следит за директорией плагина, пересобирает при изменениях и перезапускает процесс, переподключаясь к демону по адресу `127.0.0.1:50051`. Откройте чат Astra и попросите её «greet Ada» — демон маршрутизирует вызов инструмента в ваш плагин и передаст результат обратно в чат потоково.

Игнорируемые директории: `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`.

Укажите нестандартный демон через `--daemon-addr`:

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. Валидация манифеста

```bash
astra-plugin validate
```

Обнаруживает отсутствующие обязательные поля, некорректные SemVer-версии, неправильно оформленные схемы конфигурации. Запускайте перед каждой сборкой — демон откажется загружать плагины, не прошедшие валидацию.

## 5. Сборка распространяемого бандла

```bash
astra-plugin build
```

Создаёт `hello-world-0.1.0.astraplugin` — ZIP-архив, содержащий скомпилированный бинарник, манифест, любые UI-ресурсы, локализации и (если у вас есть ключ подписи) запись `SIGNATURE` Ed25519.

Выведите по конкретному пути с `-o`:

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. (Опционально) Генерация ключа подписи

```bash
astra-plugin keygen
```

Создаёт пару ключей Ed25519 в `~/.astra/plugin-keys/{private,public}.key`. Каждая последующая `astra-plugin build` автоматически подписывает архив. Поделитесь `public.key` с пользователями, которые хотят проверить бандл.

## 7. Установка плагина

Перетащите файл `.astraplugin` на страницу «Plugins» в UI Astra или вызовите RPC демона `SideloadPlugin`. После установки демон перезапускает процесс плагина с корректными учётными данными, и он появляется в списке плагинов.

## Куда двигаться дальше

- [Rust SDK](sdk-rust.md) — каждый метод трейта, билдеры `FieldDef` / `UiContribution`, `DaemonClient` для клиентских плагинов.
- [Python SDK](sdk-python.md) — если вы предпочитаете декораторы `@tool` / `@action` и авто-схему из подсказок типов.
- [TypeScript SDK](sdk-typescript.md) — API на основе классов с `@grpc/grpc-js`.
- [Возможности](capabilities.md) — полный справочник по инструментам, TTS, STT, ИИ-провайдерам, действиям, триггерам, UI-контрибуциям, обработчикам событий и клиентскому режиму.
- [Публикация](publishing.md) — подпись, распространение, стратегия обновлений.
