> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/reference/README.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/docgen/gen.py` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# Referenz

Generiert. Jede Seite in diesem Verzeichnis ist eine Funktion des
Quellcodes in diesem Repository, neu gerendert von
`python3 tools/docgen/gen.py` und in CI mit demselben Befehl plus
`--check` auf Abweichung geprüft. Eine von Hand zu bearbeiten lässt den
Build fehlschlagen.

Das ist der Punkt: die Referenzebene ist der Teil der Dokumentation, den
niemand gegen den Quellcode nachliest, also der Teil, der nicht davon
abhängen darf, dass das jemand tut.

| Seite | Was sie beantwortet | Abgeleitet aus |
|---|---|---|
| [`cli.md`](./cli.md) | `astra-plugin`: jeder Befehl, jedes Argument und jedes Flag | den `clap`-Definitionen der CLI-Binärdatei |
| [`manifest.md`](./manifest.md) | `plugin.toml`: jeder Abschnitt und jedes Feld | `astra-plugin-cli/vendor/astra-plugin-manifest` |
| [`protocol.md`](./protocol.md) | die gRPC-Oberfläche: Dienste, RPCs, Streaming, Permissions | `proto/plugin.proto` + `spec/hooks.yaml` |
| [`errors.md`](./errors.md) | die Fehler-Taxonomie, in allen drei SDKs | dem Proto-Enum + dem Fehlermodul jedes SDK |
| [`parity.md`](./parity.md) | welcher Hook in welchem SDK gebunden ist | `spec/hooks.yaml` |

## Was hier nicht ist

**Prosa.** Alles, was *warum* erklärt oder dich durch etwas führt, ist
von Hand geschrieben und lebt außerhalb dieses Verzeichnisses. Ein
Generator hat keine Meinungen.

**Alles Unverifizierte.** Eine Seite hier gibt nur an, was ihr Generator
aus dem Quellcode lesen konnte. Wo eine Tatsache im Astra-Daemon lebt
statt in diesem Repository — die Permission, an die jedes Host-RPC
gebunden ist, zum Beispiel — sagt die Seite, welche eingecheckte Datei
sie trägt und welche Paritätsregel diese Datei an den Daemon pinnt.
</content>
