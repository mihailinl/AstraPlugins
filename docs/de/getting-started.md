# Erste Schritte

Eine 5-minütige Einführung: CLI installieren, ein Rust-Tools-Plugin generieren, es im Entwicklungsmodus ausführen und ein verteilbares `.astraplugin`-Bundle erstellen.

## Voraussetzungen

- Ein laufender **Astra-Daemon** auf `127.0.0.1:50051` (der standardmäßige gRPC-Port).
- **Rust** 1.75+ (für Rust-Plugins oder um die CLI aus dem Quellcode zu installieren).
- Optional: **Python** 3.10+ oder **Node.js** 20+, falls Sie diese SDKs wählen.

## 1. CLI installieren

Die `astra-plugin`-CLI erstellt, führt aus, baut, validiert und signiert Plugins. Installieren Sie sie aus dem Repository:

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Überprüfung:

```bash
astra-plugin --version
```

## 2. Ein Plugin generieren

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

Die CLI akzeptiert `--lang rust|python|ts` und eine kommagetrennte `--capabilities`-Liste. Alle Optionen finden Sie in der [CLI-Referenz](cli.md).

Das generierte Rust-Projekt enthält:

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

Öffnen Sie `src/main.rs` und geben Sie Ihrem Tool einen sinnvollen Inhalt:

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

## 3. Im Entwicklungsmodus ausführen

```bash
astra-plugin dev
```

Dieser Befehl überwacht das Plugin-Verzeichnis, baut bei Änderungen neu und startet den Prozess neu, während er sich wieder mit dem Daemon unter `127.0.0.1:50051` verbindet. Öffnen Sie den Astra-Chat und bitten Sie ihn, „greet Ada“ auszuführen — der Daemon leitet den Tool-Aufruf an Ihr Plugin weiter und streamt das Ergebnis zurück in den Chat.

Ignorierte Verzeichnisse: `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`.

Mit `--daemon-addr` verweisen Sie auf einen abweichenden Daemon:

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. Manifest validieren

```bash
astra-plugin validate
```

Findet fehlende Pflichtfelder, ungültige SemVer-Angaben und fehlerhafte Konfigurationsschemata. Führen Sie diesen Befehl vor jedem Build aus — der Daemon weigert sich, Plugins zu laden, die die Validierung nicht bestehen.

## 5. Ein verteilbares Bundle erstellen

```bash
astra-plugin build
```

Erzeugt `hello-world-0.1.0.astraplugin` — ein ZIP-Archiv mit der kompilierten Binärdatei, dem Manifest, allen UI-Assets, Sprachdateien und (falls Sie einen Signaturschlüssel besitzen) einem Ed25519-`SIGNATURE`-Eintrag.

Einen bestimmten Pfad geben Sie mit `-o` aus:

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. (Optional) Einen Signaturschlüssel erzeugen

```bash
astra-plugin keygen
```

Erzeugt ein Ed25519-Schlüsselpaar unter `~/.astra/plugin-keys/{private,public}.key`. Jeder nachfolgende `astra-plugin build` signiert das Archiv automatisch. Geben Sie `public.key` an Nutzer weiter, die das Bundle verifizieren möchten.

## 7. Plugin installieren

Ziehen Sie die `.astraplugin`-Datei auf die Plugins-Seite der Astra-UI oder rufen Sie den `SideloadPlugin`-RPC des Daemons auf. Nach der Installation startet der Daemon den Plugin-Prozess mit den korrekten Anmeldedaten neu und das Plugin erscheint in der Plugin-Liste.

## Wie geht es weiter

- [Rust-SDK](sdk-rust.md) — jede Trait-Methode, `FieldDef` / `UiContribution`-Builder, `DaemonClient` für Client-Plugins.
- [Python-SDK](sdk-python.md) — falls Sie `@tool` / `@action`-Dekoratoren und automatische Schemata aus Type-Hints bevorzugen.
- [TypeScript-SDK](sdk-typescript.md) — klassenbasierte API mit `@grpc/grpc-js`.
- [Fähigkeiten](capabilities.md) — vollständige Referenz für tools, TTS, STT, AI-Provider, Aktionen, Trigger, UI-Beiträge, Event-Handler und Client-Modus.
- [Veröffentlichung](publishing.md) — Signieren, Verteilen, Upgrade-Strategie.
