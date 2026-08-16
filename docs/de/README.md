> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/README.md) maßgeblich.

# Astra-Plugin-Dokumentation

Ein Plugin ist ein eigenständiges Programm, das Astra startet und über gRPC
anspricht. Es kann dem Modell Tools geben, eine Text-zu-Sprache- oder
Sprache-zu-Text-Engine bereitstellen, Schritte und Trigger zum Befehlseditor
hinzufügen, UI beisteuern oder selbst als Chat-Client auftreten.

Es gibt hier zwei Wege, und alles auf dieser Seite gehört zu einem von beiden.

## Ein Plugin schreiben

| | |
|---|---|
| [Was ein Plugin ist](1-orientation/what-is-a-plugin.md) | Die zehn Fähigkeiten (capabilities), und welche du willst |
| [Architektur](1-orientation/architecture.md) | Prozessmodell, die zwei Dienste, der Auth-Handshake |
| [Sicherheitsmodell](1-orientation/security.md) | Was Signaturen beweisen, was nicht, und mit welchen Rechten ein Plugin läuft |
| [Plattformen](1-orientation/platforms.md) | linux-x64 und windows-x64, Pfade je Betriebssystem, Build-Voraussetzungen |
| **[Erste Schritte](2-tutorial/getting-started.md)** | **Von null zu einem laufenden Plugin. Hier anfangen.** |
| [Rust-SDK](4-sdk/rust.md) · [Python-SDK](4-sdk/python.md) · [TypeScript-SDK](4-sdk/typescript.md) | Je eine Seite, inklusive dessen, was das jeweilige SDK noch nicht kann |
| [Beispiele](7-examples/README.md) | Elf Plugins in diesem Repository, jedes mit seiner Plattform |

## Ein Plugin veröffentlichen

**Veröffentlichen ist ein getaggtes Release, das GitHubs CI baut und bezeugt
(attestiert), plus eine einzige Listing-Anfrage, ein einziges Mal.** Den
Quellcode auf GitHub zu pushen ist kein Veröffentlichen; jemandem ein Zip zu
schicken ist kein Veröffentlichen; einen Maintainer zu bitten, dein Plugin zu
bauen, ist kein Veröffentlichen. Die Registry pinnt dein Plugin über den Digest
genau der Datei, die ein Nutzer herunterlädt, und liest GitHubs
Build-Attestation, um zu erfahren, welcher Workflow, welcher Commit und welches
Repository diese Bytes erzeugt haben — und eine auf deinem Laptop gebaute Datei
trägt keines von beidem.

| | |
|---|---|
| **[Ein Plugin veröffentlichen](publishing.md)** | **Der ganze Weg auf einer Seite: leeres Verzeichnis bis gelistetes Plugin, jeder Befehl mit seiner Ausgabe. Hier anfangen.** |
| [Die CLI installieren](install-cli.md) | Lade ein vorgebautes `astra-plugin` herunter und verifiziere es, oder baue aus dem Quellcode. Nicht `cargo install` — das kann nicht funktionieren, und hier steht warum |

Die drei Stufen einzeln, falls gewünscht:

1. [Mit CI veröffentlichen](5-publish/release-with-ci.md) — `astra-plugin init-ci`, dann ein Tag. GitHub baut das Bundle und bezeugt es.
2. [Gelistet werden](5-publish/get-listed.md) — eine Einreichung, einmal, für immer. Danach laufen Releases ohne weiteres Zutun.
3. Nutzer installieren aus Astra heraus, mit dem über den Digest gepinnten Artefakt.

Es gibt zwei weitere Wege, ein Plugin auf eine Maschine zu bringen. **Keiner
davon ist Veröffentlichen.** Beide richten sich an Entwickler, beide kosten
etwas, und beide sagen, was:

- [Eine lokale Datei installieren](5-publish/local-install.md) — eine außerhalb der Registry erhaltene `.astraplugin`-Datei. Vier Berechtigungen werden pauschal verweigert.
- [Ein Quellverzeichnis sideloaden](5-publish/sideload.md) — die Entwicklungsschleife. Erfordert den Entwicklermodus, führt unsignierten Code mit deinem vollen Benutzerkonto aus.

Außerdem: [Versionierungs- und Deprecation-Richtlinie](versioning.md) · [Migration auf 0.6](migration-0.6.md)

## Ein Plugin betreiben

| | |
|---|---|
| [Fehlerbehebung](6-operate/troubleshooting.md) | Sortiert nach den Fehlern, die der Daemon und die CLI tatsächlich ausgeben |
| [Logs](6-operate/logs.md) | Wo sie liegen, je Betriebssystem, und wie man ihnen folgt |
| [Performance](6-operate/performance.md) | Timeouts, Start-Budget, Shutdown-Frist, Archivgrenzen |

## Referenz

Der größte Teil der Referenzebene ist **generiert** aus dem Code, den sie
beschreibt, und die CI schlägt fehl, wenn eine eingecheckte Seite von einem
frischen Lauf abweicht. Das ist Absicht: eine von Hand geschriebene
Referenzseite ist eine zweite Definition der Schnittstelle — und immer die,
die falsch ist.

| Seite | Generiert aus |
|---|---|
| [`plugin.toml`](reference/manifest.md) | `astra-plugin-manifest` — die Crate, mit der der Daemon dein Manifest parst |
| [CLI](reference/cli.md) | den `clap`-Definitionen, durch Ausführen von `astra-plugin --help` |
| [Protokoll](reference/protocol.md) | `proto/plugin.proto` |
| [Fehler](reference/errors.md) | die Fehler-Taxonomie in allen drei SDKs |
| [Hook-Parität](reference/parity.md) | `spec/hooks.yaml` — alle 35 Hooks in allen drei SDKs |
| [Berechtigungen](3-reference/permissions.md) | handgeschrieben: jede Berechtigung, was sie gewährt, wie man eine Begründung schreibt |
| [Config-Felder](3-reference/config-fields.md) | handgeschrieben: Settings-UI, `[config]`, und die TTS/STT-Feld-Hooks |

Normative Spezifikationen, für alle, die einen Verifier oder eine Registry
implementieren statt eines Plugins: [Bundle v2](spec/bundle-v2.md) ·
[Registry-Index](spec/registry-index.md) · [Berechtigungen](spec/permissions.md).

## Sprachen

Englisch ist maßgeblich. Sechs Übersetzungen liegen daneben, jede eine
Datei-für-Datei-Spiegelung dieser Seiten — dieselben Dateien, dieselben
Überschriften, dieselbe Reihenfolge:

[Deutsch](README.md) · [Español](../es/README.md) · [日本語](../ja/README.md) · [Русский](../ru/README.md) · [Українська](../uk/README.md) · [简体中文](../zh-CN/README.md)

Die CI prüft die Form einer Übersetzung: dass sie genau die Seiten hat, die
`docs/en` hat, dass jeder Link darin auflöst und dass jedes Codebeispiel darin noch läuft —
identische Beispiele werden einmal ausgeführt und als `identical to` das
englische Original gemeldet, sodass ein in der Übersetzung abgedriftetes
Beispiel erneut auf eigene Rechnung läuft. Die CI kann nicht prüfen, ob ein Satz
noch dasselbe bedeutet wie der englische. Deshalb gilt bei jeder Abweichung
Englisch, jede übersetzte Seite sagt das oben, und eine Korrektur an einer von
ihnen ist willkommen.

## Zwei Dinge, bei denen die gesamte Dokumentation sorgfältig ist

**Plugins laufen nicht in einer Sandbox.** Ein Plugin ist ein nativer Prozess,
der als du läuft, mit deinen Dateien und deinem Netzwerk. Signaturen
beantworten *wer diese Bytes veröffentlicht hat*; Berechtigungen beantworten
*was der Daemon tut, wenn das Plugin danach fragt*. Keines von beidem
beantwortet, was der Prozess mit deiner Maschine anstellen kann. Siehe
[das Sicherheitsmodell](1-orientation/security.md).

**Die Vertrauenskette ist bis zur Delegation verankert, aber noch nicht durch
den Katalog hindurch.** Die Root-Schlüssel existieren und stimmen auf beiden
Seiten überein, und auch die root-signierte `trust.json`, die an einen
Index-Signierschlüssel delegiert, existiert jetzt — sie verifiziert unter
`astra-root-2026a` und benennt den einen Reusable-Workflow-Commit, den die
Registry in einer Build-Attestation akzeptiert. Was noch fehlt, ist die
Signatur des Katalogs selbst: `registry/v1/index.json` und
`revocations.json` tragen `"signatures": []`, sodass ein Standard-Build nichts
zu prüfen hat, geschlossen ausfällt (fail closed) und jeden Katalog als
unsigniert einstuft. Das ist in
[`spec/registry-index.md` §0.1](spec/registry-index.md) niedergeschrieben und
wird überall wiederholt, wo es wichtig ist, statt stillschweigend wegimpliziert
zu werden.
</content>
