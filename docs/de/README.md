# Astra-Plugin-Entwicklung

Entwickeln Sie Plugins für [Astra](https://github.com/Stella) — den KI-gestützten digitalen Assistenten — in Rust, Python oder TypeScript.

Plugins sind eigenständige Prozesse, die Astra als Sidecars startet. Sie kommunizieren mit dem Daemon über gRPC und können KI-Tools bereitstellen, TTS/STT-Backends liefern, eigene Aktionen und Trigger zum Command Graph beisteuern, UI-Panels einbetten oder als vollwertige Daemon-Clients agieren.

## Inhaltsverzeichnis

| Dokument | Inhalt |
| --- | --- |
| [Erste Schritte](getting-started.md) | CLI installieren, Ihr erstes Plugin generieren, im Entwicklungsmodus ausführen und ein verteilbares Bundle erstellen |
| [CLI-Referenz](cli.md) | Jeder `astra-plugin`-Unterbefehl mit Flags, Verhalten und Exit-Codes |
| [Rust-SDK](sdk-rust.md) | Trait-basierte API (`PluginCapability`), Field-Builder, `HostClient`, `DaemonClient` |
| [Python-SDK](sdk-python.md) | Decorator-API (`@tool`, `@action`, `@trigger`), automatisches Schema aus Type-Hints, UV-Integration |
| [TypeScript-SDK](sdk-typescript.md) | Klassenbasierte API, automatische Fähigkeitserkennung, `@grpc/grpc-js`-Laufzeit |
| [Manifest](manifest.md) | Referenz zu `plugin.toml` — jeder Abschnitt und jedes Feld |
| [Fähigkeiten](capabilities.md) | Alle 9 Fähigkeiten, API je SDK, Proto-RPCs |
| [Veröffentlichung](publishing.md) | `.astraplugin`-Bundle-Format, Ed25519-Signatur, Sideloading |

## Architektur auf einen Blick

```
┌────────────────────────┐     gRPC     ┌────────────────────────┐
│        Astra           │◀────────────▶│        Plugin          │
│        daemon          │   localhost  │      (sidecar)         │
│                        │              │                        │
│ PluginHostService ─────┼────────────▶│ HostClient             │
│                        │              │                        │
│ plugin-capability ◀────┼──────────────│ PluginCapability       │
│   service client       │              │   service              │
└────────────────────────┘              └────────────────────────┘
```

- Der Daemon startet jedes Plugin als separaten Prozess und übergibt dabei `--daemon-addr`, `--plugin-id` und optional `--auth-token` auf der Kommandozeile.
- Das Plugin startet einen gRPC-Server auf einem zufälligen lokalen Port, verbindet sich zurück mit dem `PluginHostService` des Daemons und **registriert** sich — dabei teilt es mit, welche Fähigkeiten es implementiert.
- Nach der Registrierung ruft der Daemon den `PluginCapabilityService` des Plugins für Tool-Aufrufe, Aktionsausführung, TTS und Lifecycle-Ereignisse auf.
- Das Plugin nutzt den `HostClient`, um zu protokollieren, Trigger auszulösen, seine eigene Konfiguration zu lesen, Variablen zu setzen oder Ereignisse an seine UI-Iframes zu senden. Client-fähige Plugins erhalten zusätzlich einen vollständigen `DaemonClient` mit Zugriff auf die Dienste Chat, Voice, Command, Media, Monitor und Config.

## Auswahl eines SDK

| Faktor | Rust | Python | TypeScript |
| --- | --- | --- | --- |
| Startlatenz | ~10 ms (native Binärdatei) | ~300 ms (Interpreter + grpcio-Import) | ~100 ms (Node-Kaltstart) |
| Speicherverbrauch | Am geringsten | Am höchsten | Mittel |
| Bundle-Größe | ~5–10 MB Binärdatei | ~100 KB Quellcode + vom Daemon verwaltetes venv | ~200 KB Bundle (esbuild) |
| Geeignet für | Leistungskritische Aufgaben, Systemintegration, TTS/STT-Provider | KI-Tooling, Datenverarbeitung, ML-Bibliotheken | Web-APIs, JSON-lastige Arbeit, UI-Integrationen |
| Typsicherheit | Vollständig (Kompilierzeit) | Optional über Hints (Schemagenerierung zur Laufzeit) | Vollständig (Kompilierzeit) |

Alle drei SDKs sind gleichwertig — jede Fähigkeit ist in jedem SDK verfügbar. Wählen Sie dasjenige, dessen Ökosystem zu den von Ihnen benötigten Bibliotheken passt.

## Nächster Schritt

Gehen Sie zu [Erste Schritte](getting-started.md) für die 5-minütige Einführung.
