> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/3-reference/README.md) maßgeblich.

# Referenz

Zwei Ebenen, und der Unterschied ist wichtig.

## Generiert — kann nicht abweichen

Diese werden von [`tools/docgen`](../../../tools/docgen/) aus dem Code
erzeugt, den sie beschreiben, und die CI führt
`python3 tools/docgen/gen.py --check` aus: eine eingecheckte Seite, die von
einem frischen Lauf abweicht, lässt den Build mit einem Diff fehlschlagen.
Die CLI-Seite wird erzeugt, indem `astra-plugin --help` *ausgeführt* wird,
statt `main.rs` zu parsen, weil ein zweiter Parser für clap's Derive-Makros
eine weitere Sache ist, die still mit dem Tool uneins sein kann.

Sie liegen ein Verzeichnis höher, in [`../reference/`](../reference/), wo
der Generator sie hinschreibt.

| Seite | Generiert aus |
|---|---|
| [`plugin.toml`](../reference/manifest.md) | `astra-plugin-manifest` — die Crate, mit der der Daemon Manifeste parst |
| [CLI](../reference/cli.md) | den `clap`-Definitionen, durch Ausführen der Binärdatei |
| [Protokoll](../reference/protocol.md) | [`proto/plugin.proto`](../../../proto/plugin.proto) |
| [Fehler](../reference/errors.md) | die Fehler-Taxonomie in allen drei SDKs |
| [Hook-Parität](../reference/parity.md) | [`spec/hooks.yaml`](../../../spec/hooks.yaml) — 35 Hooks, 3 SDKs |

Hook-Tabellen je SDK, aus derselben Spezifikation gerendert:
[Rust](../hooks/rust.md) · [Python](../hooks/python.md) ·
[TypeScript](../hooks/typescript.md).

## Handgeschrieben — von einem Menschen geprüft

Zwei Seiten beschreiben Dinge, die kein Generator von einem Typ ablesen
kann: was eine Permission dem Nutzer, der um ihre Gewährung gebeten wird,
*bedeutet*, und wie die drei verschiedenen Dinge, die „Config" heißen,
zusammenpassen.

| Seite | |
|---|---|
| [Permissions](permissions.md) | Jede ID, was sie gewährt, und wie man einen `reason` schreibt |
| [Config- und Settings-Felder](config-fields.md) | `[config]`, typisierte Einstellungen, und die TTS/STT-Feld-Hooks |
| [Lokalisierung](localisation.md) | `locales/<code>.json`, der `$key`-Marker, und wo das Englisch-Gate greift — **nur auf Englisch** |

Jedes Codebeispiel auf beiden Seiten wird in der CI von
[`docs/tools/doctest.py`](../../tools/doctest.py) ausgeführt.

## Normative Spezifikationen

Für alle, die einen Verifier, einen Packer oder eine Registry implementieren
statt eines Plugins. Das sind RFC-2119-Dokumente mit goldenen Vektoren,
keine Anleitungen.

[Bundle v2](../spec/bundle-v2.md) · [Registry-Index](../spec/registry-index.md) ·
[Permissions](../spec/permissions.md)
</content>
