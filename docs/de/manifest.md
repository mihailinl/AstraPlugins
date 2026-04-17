# `plugin.toml`-Referenz

Jedes Plugin deklariert sich selbst in einem `plugin.toml`-Manifest im Wurzelverzeichnis seines Projekts. Diese Datei teilt dem Daemon mit, wie das Plugin zu starten ist, welche Fähigkeiten es implementiert und welche Konfiguration es akzeptiert.

## Vollständiges Beispiel

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` — Metadaten

| Feld | Typ | Pflicht | Beschreibung |
| --- | --- | --- | --- |
| `id` | string | ja | Kleinbuchstaben, Ziffern und Bindestriche. Identifiziert das Plugin eindeutig. |
| `name` | string | ja | Anzeigename in der Plugins-UI. |
| `version` | string | ja | Semantische Version (`X.Y.Z`). Wird zur Upgrade-Erkennung genutzt. |
| `description` | string | empfohlen | Kurze Zusammenfassung. Wird in der Plugins-UI angezeigt. |
| `author` | string | empfohlen | Name des Autors oder der Organisation. |
| `license` | string | empfohlen | SPDX-Lizenzkennung (`MIT`, `Apache-2.0`, …). |

## `[entry]` — Start des Plugins

| Feld | Typ | Pflicht | Beschreibung |
| --- | --- | --- | --- |
| `command` | string | ja | Auszuführende Programmdatei. Bei Rust ist dies der Pfad zur kompilierten Binärdatei; bei Python `"python"`; bei TypeScript `"node"`. |
| `args` | string array | nein | Argumente, die vor `--daemon-addr`, `--plugin-id`, `--auth-token` gesetzt werden. Typische Werte: `["-m", "src.plugin"]` für Python oder `["dist/index.js"]` für Node. |
| `runtimes` | string array | nein | Hinweis an den Daemon. Unterstützt: `"python"`, `"node"`, `"rust"`. Python- und Node-Plugins sollten dies immer setzen, damit der Daemon die Laufzeit vorbereiten kann (z. B. ein `uv`-venv für Python anlegen). |

Der Daemon hängt bei jedem Start `--daemon-addr <addr> --plugin-id <id>` und für Client-Plugins optional `--auth-token <token>` an.

## `[capabilities]` — was das Plugin implementiert

Jedes Feld ist ein boolescher Wert, der standardmäßig `false` ist. Setzen Sie ihn nur für Fähigkeiten auf `true`, die Ihr Code tatsächlich behandelt — der Daemon verwendet dies, um Ressourcen zu reservieren und zu entscheiden, ob das Plugin in relevanten UI-Bereichen angezeigt wird (z. B. um seine Stimmen im TTS-Picker hinzuzufügen).

| Fähigkeit | Zweck |
| --- | --- |
| `tools` | KI-Tools, die vom Chat-Modell aufgerufen werden können. |
| `tts` | Text-to-Speech-Stimmenanbieter. |
| `stt` | Speech-to-Text-Sprachanbieter. |
| `ai_provider` | Alternatives KI-Completion-Backend. |
| `actions` | Eigene Aktionstypen im Command Graph. |
| `triggers` | Eigene Triggertypen im Command Graph. |
| `client` | Vollständiger Daemon-Client (erfordert Sitzungstoken). |
| `ui_contributions` | UI-Seiten, Overlays, Effekte, Slot-Injektionen. |
| `event_handlers` | Abonniert den Ereignisstream des Daemons. |

Siehe [Fähigkeiten](capabilities.md) für das vollständige Verhalten pro Fähigkeit.

## `[config]` — nutzerseitige Einstellungen

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

Regeln:

- `schema` ist ein **JSON-Schema-String**. Die Wurzel muss `"type": "object"` sein.
- Der Daemon rendert das Schema als Formular auf der Plugin-Einstellungsseite.
- `title` liefert die Feldbeschriftung; `description` wird als Hilfetext angezeigt.
- `default` liefert den Anfangswert.
- `x-secret: true` maskiert den Wert in der UI und speichert ihn verschlüsselt.
- `enum` wird als Dropdown gerendert.
- Das Array `required` markiert Pflichtfelder.
- Aktualisiert der Nutzer die Einstellungen, ruft der Daemon `OnConfigChanged` mit dem neuen JSON-Block auf.

## Nicht-Schema-TOML-Felder

Plugins können beliebige zusätzliche Top-Level-Abschnitte hinzufügen, die der Daemon ignoriert — nützlich für Tooling. Die CLI warnt bei unbekannten Feldern, lehnt sie aber nicht ab.

## Manifest lokalisieren

Sie können `locales/<lang>.json`-Dateien innerhalb des Plugin-Bundles ausliefern, um nutzerseitige Zeichenketten zu übersetzen (`name`, `description`, Aktionsbeschriftungen, Feldlabels usw.). Verwenden Sie den `I18n`-Helfer jedes SDK, um sie aus Ihrem Code zu lesen. Lokalisiert werden nur **Textinhalte** des Manifests — Schlüssel, IDs und Enum-Werte bleiben konstant.

## Manifest validieren

```bash
astra-plugin validate
```

Prüfungen:

- Pflichtfelder vorhanden (`plugin.id`, `plugin.name`, `plugin.version`, `entry.command`).
- `plugin.id` besteht aus Kleinbuchstaben, Ziffern und Bindestrichen.
- `plugin.version` entspricht SemVer (`X.Y.Z`).
- Mindestens eine Fähigkeit ist aktiviert.
- `[config].schema` parst als JSON und hat `"type": "object"` als Wurzel.
- Metadaten (`description`, `author`) sind vorhanden.

Siehe [CLI-Referenz → validate](cli.md#astra-plugin-validate).
