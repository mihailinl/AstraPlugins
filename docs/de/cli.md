# `astra-plugin`-CLI-Referenz

Jeder Unterbefehl, jedes Flag und jedes Verhalten — entnommen aus `astra-plugin-cli/src/main.rs` und `astra-plugin-cli/src/commands/`.

## Installation

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Mit `astra-plugin --help` sehen Sie die vollständige Befehlsliste. Jeder Unterbefehl akzeptiert ebenfalls `--help`.

## `astra-plugin create`

Generiert ein neues Plugin-Projekt aus einer sprachspezifischen Vorlage.

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| Argument / Flag | Standard | Beschreibung |
| --- | --- | --- |
| `NAME` | — | Plugin-ID. Muss aus Kleinbuchstaben, Ziffern und Bindestrichen bestehen — dies wird zu `[plugin].id` im Manifest. |
| `-l, --lang` | `rust` | Eines von `rust`, `python` (Alias `py`), `typescript` (Alias `ts`). |
| `-c, --capabilities` | `tools` | Kommagetrennte Liste. Gültige Werte: `tools`, `tts`, `stt`, `ai_provider`, `actions`, `triggers`, `client`, `event_handlers`, `ui_panels`. Leerzeichen um Kommas werden entfernt. |
| `-o, --output` | `./<NAME>` | Zielverzeichnis. |

### Was erzeugt wird

Alle Gerüste enthalten:

- `plugin.toml` — Manifest, vorab ausgefüllt mit ID, Name, Version `0.1.0` und dem `[capabilities]`-Abschnitt aktiviert für die von Ihnen angeforderten Fähigkeiten.
- `proto/plugin.proto` — eine lokale Kopie des Plugin-Protokolls.
- `.gitignore`, `README.md`.

Sprachspezifische Zusätze:

| Sprache | Zusatzdateien |
| --- | --- |
| `rust` | `Cargo.toml` (mit `astra-plugin-sdk`, `tokio`, `serde`, `anyhow`, `async-trait`), `src/main.rs` mit einem Gerüst für `PluginCapability`. `entry.command` auf `target/release/<name>.exe` gesetzt. |
| `python` | `pyproject.toml` (mit `astra-plugin-sdk`, `grpcio`, `protobuf`), `src/plugin.py` mit einem `Plugin`-Subklassengerüst. `entry.command = "python"`, `args = ["-m", "src.plugin"]`, `runtimes = ["python"]`. |
| `typescript` | `package.json`, `tsconfig.json`, `src/index.ts` mit einem `Plugin`-Subklassengerüst. `entry.command = "node"`, `args = ["dist/index.js"]`, `runtimes = ["node"]`. |

## `astra-plugin dev`

Führt das Plugin im Entwicklungsmodus mit Dateiüberwachung und automatischem Rebuild/Neustart aus.

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| Argument / Flag | Standard | Beschreibung |
| --- | --- | --- |
| `PATH` | `.` | Plugin-Verzeichnis (jenes mit der `plugin.toml`). |
| `--daemon-addr` | `127.0.0.1:50051` | gRPC-Adresse des laufenden Astra-Daemons. |

### Ablauf

1. Liest `plugin.toml` und ermittelt pro Sprache den Build-Befehl.
2. Startet einen Datei-Watcher auf dem Plugin-Verzeichnis (ignoriert `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`).
3. Führt den Build aus (`cargo build` für Rust, `bun run build` / `tsc` für TypeScript, `uv pip sync` / nichts für Python).
4. Startet den `entry.command` mit angehängten `--daemon-addr`, `--plugin-id` und `--auth-token`.
5. Bei Dateiänderung: beendet den Kindprozess, baut neu, startet erneut.

Fehler werden inline ausgegeben. Drücken Sie `Ctrl+C` zum Beenden.

## `astra-plugin build`

Paketiert das Plugin in ein verteilbares `.astraplugin`-Archiv.

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| Argument / Flag | Standard | Beschreibung |
| --- | --- | --- |
| `PATH` | `.` | Plugin-Verzeichnis. |
| `-o, --output` | `<id>-<version>.astraplugin` | Archivpfad. |

### Build-Schritte pro Sprache

| Sprache | Schritte |
| --- | --- |
| `rust` | Führt `cargo build --release` aus, kopiert die Binärdatei in `bin/` innerhalb des Archivs und schreibt `entry.command` so um, dass es auf den gebündelten Pfad zeigt. |
| `typescript` | Führt `bun build src/index.ts --outdir dist` aus oder greift auf `npx esbuild` zurück. Das gebündelte JS landet in `dist/` im Archiv. |
| `python` | Ist `uv` im `PATH`, wird `requirements.lock` über `uv pip compile` erzeugt. Kopiert `src/`, `pyproject.toml`, `requirements.txt` und die Lock-Datei. |

### Archivlayout

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

Existiert `~/.astra/plugin-keys/private.key`, **signiert** die CLI das Archiv bei jedem Build **automatisch** — kein zusätzliches Flag erforderlich.

## `astra-plugin validate`

Prüft Manifest und Konfigurationsschema, ohne zu bauen.

```bash
astra-plugin validate [PATH]
```

Geprüfte Punkte:

- Pflichtfelder im Manifest: `plugin.id`, `plugin.name`, `plugin.version`, `entry.command`.
- `plugin.id` besteht aus Kleinbuchstaben, Ziffern und Bindestrichen.
- `plugin.version` entspricht `X.Y.Z` nach SemVer (Warnung, kein Fehler, falls nicht).
- Mindestens eine Fähigkeit ist aktiviert (Warnung, falls alle auf false stehen).
- `[config].schema`, sofern vorhanden, lässt sich als JSON parsen und hat `"type": "object"` als Wurzel.
- Metadaten-Warnungen: fehlende `description` oder `author`.

Der Befehl endet nur bei harten Fehlern mit einem Exit-Code ungleich null (nicht parsbare TOML, fehlende Pflichtfelder).

## `astra-plugin keygen`

Erzeugt ein Ed25519-Schlüsselpaar, das `build` zum Signieren von Archiven verwendet.

```bash
astra-plugin keygen [--force]
```

| Flag | Beschreibung |
| --- | --- |
| `--force` | Überschreibt ein vorhandenes Schlüsselpaar. Ohne dieses Flag verweigert der Befehl das Ersetzen bestehender Schlüssel. |

Ausgabeorte (werden bei Bedarf angelegt):

- `~/.astra/plugin-keys/private.key` — Base64 Ed25519 Private-Seed (geheim halten).
- `~/.astra/plugin-keys/public.key` — Base64 Ed25519 Public Key (bedenkenlos teilbar).

Sobald ein Schlüsselpaar existiert, hängt jeder `astra-plugin build` automatisch einen `SIGNATURE`-Eintrag (HMAC-ähnlicher Hash jedes ZIP-Eintrags, mit Ed25519 signiert) sowie einen `PUBKEY`-Eintrag an, damit Nutzer die Authentizität prüfen können.

## Umgebung

- `RUST_LOG` — steuert die Ausführlichkeit der CLI-Ausgabe. Standard ist Warnstufe; verwenden Sie `RUST_LOG=debug` für eine vollständige Ablaufverfolgung.
- Alle CLI-Befehle respektieren den `PATH` der aktuellen Shell beim Auffinden von `cargo`, `node`, `bun`, `npx`, `python` und `uv`.
