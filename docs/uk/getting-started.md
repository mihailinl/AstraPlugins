# Початок роботи

5-хвилинний огляд: встановлення CLI, створення шаблону плагіна на Rust з інструментами, запуск його у режимі розробки та збирання бандла `.astraplugin` для розповсюдження.

## Передумови

- Запущений **демон Astra** на `127.0.0.1:50051` (стандартний порт gRPC).
- **Rust** 1.75+ (для плагінів на Rust або щоб встановити CLI з вихідного коду).
- Опціонально: **Python** 3.10+ або **Node.js** 20+, якщо ви обираєте відповідний SDK.

## 1. Встановіть CLI

CLI `astra-plugin` створює, запускає, збирає, валідує та підписує плагіни. Встановіть його з репозиторію:

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Перевірка:

```bash
astra-plugin --version
```

## 2. Створіть шаблон плагіна

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

CLI приймає `--lang rust|python|ts` і список можливостей `--capabilities`, розділених комами. Повний список опцій див. у [CLI reference](cli.md).

Створений проєкт на Rust містить:

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

Відкрийте `src/main.rs` і додайте корисне тіло вашому інструменту:

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

## 3. Запуск у режимі розробки

```bash
astra-plugin dev
```

Ця команда спостерігає за каталогом плагіна, пересобирає при змінах та перезапускає процес, заново підключаючись до демона на `127.0.0.1:50051`. Відкрийте чат Astra і попросіть "greet Ada" — демон спрямує виклик інструменту до вашого плагіна та потоково поверне результат у чат.

Ігноровані каталоги: `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`.

Вказати нестандартну адресу демона можна через `--daemon-addr`:

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. Перевірка маніфесту

```bash
astra-plugin validate
```

Виявляє відсутні обов'язкові поля, некоректну SemVer-версію, пошкоджені схеми конфігурації. Запускайте перед кожним збиранням — демон відмовиться завантажувати плагіни, що не пройшли перевірку.

## 5. Збирання бандла для розповсюдження

```bash
astra-plugin build
```

Створює `hello-world-0.1.0.astraplugin` — ZIP-архів зі скомпільованим бінарником, маніфестом, будь-якими UI-ресурсами, локалями та (якщо у вас є ключ для підпису) записом `SIGNATURE` типу Ed25519.

Вказати конкретний шлях через `-o`:

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. (Опціонально) Згенеруйте ключ для підпису

```bash
astra-plugin keygen
```

Створює пару ключів Ed25519 за адресою `~/.astra/plugin-keys/{private,public}.key`. Кожне наступне `astra-plugin build` автоматично підписує архів. Поділіться `public.key` з користувачами, які хочуть перевірити бандл.

## 7. Встановлення плагіна

Перетягніть файл `.astraplugin` на сторінку Plugins в UI Astra або викличте RPC демона `SideloadPlugin`. Після встановлення демон перезапускає процес плагіна з коректними обліковими даними, і він з'являється у списку плагінів.

## Куди далі

- [Rust SDK](sdk-rust.md) — кожен метод трейту, конструктори `FieldDef` / `UiContribution`, `DaemonClient` для клієнтських плагінів.
- [Python SDK](sdk-python.md) — якщо ви віддаєте перевагу декораторам `@tool` / `@action` та авто-схемі з підказок типів.
- [TypeScript SDK](sdk-typescript.md) — API на основі класів з `@grpc/grpc-js`.
- [Capabilities](capabilities.md) — повний довідник щодо tools, TTS, STT, AI provider, actions, triggers, UI contributions, event handlers та client-режиму.
- [Publishing](publishing.md) — підпис, розповсюдження, стратегія оновлення.
