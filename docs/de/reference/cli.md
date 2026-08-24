> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/reference/cli.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/docgen/cli.py` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# CLI-Referenz

`astra-plugin 0.3.0`. Jedes Flag unten wurde aus der Binärdatei gelesen,
diese Seite kann also keine Option beschreiben, die nicht existiert. Die
Quelle ist
[`astra-plugin-cli/src/main.rs`](../../../astra-plugin-cli/src/main.rs).

Astra Plugin Development CLI

## Überall

| Option | Beschreibung |
|---|---|
| `--json` | Gibt ein einzelnes JSON-Dokument statt menschenlesbarer Ausgabe aus. Fortschrittszeilen werden unterdrückt, sodass die Ausgabe sicher zu pipen ist |
| `-h, --help` | Hilfe ausgeben |
| `-V, --version` | Version ausgeben |

## Befehle

| Befehl | Aliase | Was er tut |
|---|---|---|
| [`new`](#astra-plugin-new) | `create` | Erstellt ein neues Plugin-Projekt aus einer Vorlage |
| [`dev`](#astra-plugin-dev) | — | Startet ein Plugin im Dev-Modus (Sideload in das laufende Astra + Hot-Reload) |
| [`build`](#astra-plugin-build) | — | Baut ein Plugin zu einem verteilbaren .astraplugin-Bundle |
| [`sign`](#astra-plugin-sign) | — | Hängt das auslaufende In-ZIP-SIGNATURE/PUBKEY-Paar an ein gebautes Bundle an |
| [`verify`](#astra-plugin-verify) | — | Verifiziert ein gebautes .astraplugin-Bundle und gibt seine Digests aus |
| [`test`](#astra-plugin-test) | — | Führt die Conformance-Suite gegen einen echten Plugin-Prozess aus |
| [`doctor`](#astra-plugin-doctor) | — | Beantwortet in einem Befehl jede Frage, die gestellt wird, wenn ein Plugin nicht startet: Toolchains, der Daemon, das Manifest, der Einstiegspunkt, Permissions, der Platform-Block, der Release-Workflow |
| [`logs`](#astra-plugin-logs) | — | Liest die Ausgabe eines Plugins vom Daemon, der es gestartet hat |
| [`check`](#astra-plugin-check) | `validate` | Prüft ein Plugin-Manifest, Config-Schema und Release-Workflow |
| [`init-ci`](#astra-plugin-init-ci) | — | Schreibt .github/workflows/release.yml, gepinnt auf einen Commit des wiederverwendbaren Astra-Workflows. Erneut ausführen, um das Pinning zu aktualisieren; es behält deine Inputs |
| [`version`](#astra-plugin-version) | — | Setzt die Version in plugin.toml und jedem anderen Manifest auf einmal |
| [`publish`](#astra-plugin-publish) | — | Bringt ein Release ins Listing: Preflight es, oder öffnet eine vorausgefüllte Einreichung |
| [`keygen`](#astra-plugin-keygen) | — | Erzeugt das OPTIONALE Ed25519-Schlüsselpaar, das `astra-plugin sign` verwendet |

### Es gibt kein `astra-plugin login`

Es gibt **kein `login`**. Ein Plugin listen zu lassen läuft über einen
Browser, in dem der Autor bereits angemeldet ist — die Registry liest
bezeugte Bundles von einem GitHub-Release und verifiziert jedes von
Grund auf, eine Einreichung trägt also nur ein Repository und ein Tag
und sonst nichts. Das bedeutet kein zweites Konto zu erstellen, keinen
Schlüsselbund, mit dem integriert werden müsste, keine Zugangsdaten-Datei,
die durchsickern könnte, und kein Token in einer Shell-Historie. Ein
`login` hier wäre ein Zugangsdaten-Speicher, gebaut, um etwas zu halten,
nach dem nichts fragt.

## astra-plugin new

Auch geschrieben als `astra-plugin create`.

Erstellt ein neues Plugin-Projekt aus einer Vorlage

```
Usage: astra-plugin new [OPTIONS] <NAME>
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `<NAME>` | Plugin-Name (Kleinbuchstaben, Bindestriche erlaubt) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `-l, --lang <LANG>` | Programmiersprache (Default `rust`) |
| `-t, --template <TEMPLATE>` | Was für ein Plugin das ist. Wählt die Capabilities und den Beispielcode; `--capabilities` überschreibt die implizierte Capability-Menge (Default `tool`; eines von `tool`, `tts`, `stt`, `stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`) |
| `-c, --capabilities <CAPABILITIES>` | Capabilities (kommagetrennt: tools, tts, stt, ai_provider, client, actions, triggers, ui_contributions, event_handlers, dom_access). Überschreibt, was auch immer --template impliziert |
| `-o, --output <OUTPUT>` | Ausgabeverzeichnis (Default: ./<name>) |

## astra-plugin dev

Startet ein Plugin im Dev-Modus (Sideload in das laufende Astra + Hot-Reload)

```
Usage: astra-plugin dev [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Daemon-gRPC-Adresse. Standardmäßig der Port, den der laufende Daemon in <config>/daemon.port geschrieben hat, sonst 127.0.0.1:32000 |
| `--standalone` | Startet den Plugin-Prozess direkt, statt den Daemon zu bitten. Das Plugin kann sich so nicht bei Astra registrieren — siehe den ausgegebenen Hinweis |

## astra-plugin build

Baut ein Plugin zu einem verteilbaren .astraplugin-Bundle

```
Usage: astra-plugin build [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `-o, --output <OUTPUT>` | Ausgabedatei-Pfad. Standardmäßig <id>-<version>-<target>.astraplugin, der Name, den ein veröffentlichtes Bundle haben muss — das Target-Segment ist der Plattform-Schlüssel der Registry |
| `--target <TARGET>` | Plattform, für die dieses Bundle ist: linux-x64, windows-x64, oder noarch. Standardmäßig der Host für native Plugins und noarch für TypeScript/Python |
| `--reproducible` | Stellt deterministisches Packen sicher: sortierte Einträge, mtime 1980-01-01, feste Kompressionsstufe. Zwei Builds derselben Eingaben erzeugen denselben sha256 |
| `--all-targets` | Baut jedes Bundle, das dieses Plugin braucht, um überall installierbar zu sein, wo Astra läuft. Eine Datei für TypeScript und Python (noarch); eine pro Plattform für Rust, jeweils aus eigenem `cargo build --target` |

**Versteckt: `--no-sign`.** Wird akzeptiert und fehlt in `--help`
(`#[arg(hide = true)]`). Veraltetes No-op: `build` signiert nie.
Beibehalten, weil der gepinnte Release-Workflow es übergibt, und das
Flag zu entfernen würde jeden bereits veröffentlichten Autoren-Workflow
brechen. Wird mit dem Legacy-Paar des Formats entfernt.

## astra-plugin sign

Hängt das auslaufende In-ZIP-SIGNATURE/PUBKEY-Paar an ein gebautes
Bundle an.

Ein optionaler zweiter Faktor, kein Vertrauenssignal: Astra prüft das
In-ZIP-Paar gegen einen gepinnten Astra-Publisher-Schlüssel, ein mit
deinem eigenen Schlüssel signiertes Bundle ist also genauso untrusted
wie ein unsigniertes. Was Astra dazu bringt, ein Plugin zu installieren,
ist der Registry-Eintrag, der sha256(gesamte Datei) gegensigniert, nicht
irgendein Schlüssel, den du besitzt. Sowohl dieser Befehl als auch die
Format-Einträge, die er schreibt, werden in einem zukünftigen Release
entfernt.

```
Usage: astra-plugin sign [OPTIONS] <FILE>
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `<FILE>` | Die .astraplugin, die an Ort und Stelle signiert wird |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--key <KEY>` | Liest den Ed25519-Seed von diesem Pfad statt von ~/.astra/plugin-keys/private.key. Ein Pfad, nie der Schlüssel selbst |

## astra-plugin verify

Verifiziert ein gebautes .astraplugin-Bundle und gibt seine Digests aus

```
Usage: astra-plugin verify [OPTIONS] <FILE>
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `<FILE>` | Pfad zur .astraplugin-Datei |

## astra-plugin test

Führt die Conformance-Suite gegen einen echten Plugin-Prozess aus.

Startet das Plugin so, wie der Daemon es startet, gegen einen
Mock-Daemon, der PluginHostService bedient, und ruft jeden eingehenden
Hook auf, den die Capabilities des Manifests implizieren. Ein Hook, den
`spec/hooks.yaml` als `required` markiert, darf nicht mit UNIMPLEMENTED
antworten; ein `optional`er darf das, weil UNIMPLEMENTED die Art des
Protokolls ist zu sagen „dieser Hook fehlt".

```
Usage: astra-plugin test [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--no-build` | Verwendet, was auch immer schon gebaut ist, statt zuerst zu bauen |
| `--report <REPORT>` | Schreibt den maschinenlesbaren Conformance-Report hierhin |

## astra-plugin doctor

Beantwortet in einem Befehl jede Frage, die gestellt wird, wenn ein
Plugin nicht startet: Toolchains, der Daemon, das Manifest, der
Einstiegspunkt, Permissions, der Platform-Block, der Release-Workflow

```
Usage: astra-plugin doctor [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis). Projektprüfungen werden übersprungen, wenn dort keine plugin.toml liegt (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Zu prüfende Daemon-gRPC-Adresse |

## astra-plugin logs

Liest die Ausgabe eines Plugins vom Daemon, der es gestartet hat

```
Usage: astra-plugin logs [OPTIONS] [PLUGIN_ID]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PLUGIN_ID]` | Plugin-ID. Default: die plugin.id des Manifests in --path |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--path <PATH>` | Wo nach einer plugin.toml gesucht werden soll, wenn keine ID angegeben ist (Default `.`) |
| `--daemon-addr <DAEMON_ADDR>` | Daemon-gRPC-Adresse |
| `-n, --lines <LINES>` | Wie viele Tail-Zeilen angefragt werden (Default `200`) |
| `-f, --follow` | Bis Strg+C weiter pollen |

## astra-plugin check

Auch geschrieben als `astra-plugin validate`.

Prüft ein Plugin-Manifest, Config-Schema und Release-Workflow

```
Usage: astra-plugin check [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--strict` | Behandelt Warnungen als Fehler |
| `--fix` | Wendet die Fixes an, die mechanisch angewendet werden können, prüft dann erneut. Schreibt nur um, was es beweisen kann; alles andere wird weiterhin gemeldet |
| `--resolve-pin` | Fragt GitHub, ob das Release-Workflow-Pinning aktuell ist. Standardmäßig aus: `astra-plugin dev` führt bei jedem Start `check --strict` aus, und der Release-Workflow teilt der Prüfung über ASTRA_PLUGIN_WORKFLOW_SHA mit, wovon aus er läuft, sodass keines von beiden das Netzwerk braucht |

## astra-plugin init-ci

Schreibt .github/workflows/release.yml, gepinnt auf einen Commit des
wiederverwendbaren Astra-Workflows. Erneut ausführen, um das Pinning zu
aktualisieren; es behält deine Inputs

```
Usage: astra-plugin init-ci [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--ref <WORKFLOW_REF>` | Ein 40-Hex-Commit zum Pinnen (wörtlich verwendet, kein Netzwerk), oder ein Ref-Name zum Auflösen. Default: das veröffentlichte Workflow-Tag, sonst der Kopf des Default-Branch |
| `--linux-packages <LINUX_PACKAGES>` | Setzt den linux-packages-Input, z. B. "libasound2-dev pkg-config". Weggelassen, wird der Wert einer bestehenden Datei behalten |
| `--offline` | Rührt nie das Netzwerk an: behält das bereits in der Datei vorhandene Pinning |

## astra-plugin version

Setzt die Version in plugin.toml und jedem anderen Manifest auf einmal

```
Usage: astra-plugin version [OPTIONS] <VERSION> [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `<VERSION>` | Die neue Version, striktes Semver und ohne führendes 'v' |
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--allow-downgrade` | Erlaubt eine Version, die unter der aktuellen einsortiert. Astra verweigert die Installation eines Downgrades, ein solches Release ist also unbrauchbar |

## astra-plugin publish

Bringt ein Release ins Listing: Preflight es, oder öffnet eine
vorausgefüllte Einreichung.

Lädt nichts hoch und hält keine Zugangsdaten — die Registry liest die
bezeugten Bundles vom GitHub-Release und verifiziert jedes von Grund
auf, eine Einreichung trägt also nur dein Repository und ein Tag.

```
Usage: astra-plugin publish [OPTIONS] [PATH]
```

**Argumente**

| Argument | Beschreibung |
|---|---|
| `[PATH]` | Pfad zum Plugin-Verzeichnis (Default: aktuelles Verzeichnis) (Default `.`) |

**Optionen**

| Option | Beschreibung |
|---|---|
| `--dry-run` | Führt jede Prüfung aus, die die Registry ausführt und die lokal laufen kann, benennt die, die nur die Registry ausführen kann, und stoppt |
| `--notify` | Ein Release-Ping für ein Plugin, das BEREITS gelistet ist — die manuelle Notfalllösung aus Aufgabe 3.4, für den Fall, dass die Registry ein Release nicht von selbst bemerkt hat. Ohne es öffnet dies eine Erst-Listing-Anfrage |
| `--repo <REPO>` | Quell-Repository als `owner/name`. Default: das `origin`-Remote |
| `--tag <TAG>` | Release-Tag. Default: das Tag-Prefix des Plugins plus seine Version |
| `--print-url` | Gibt die URL aus und öffnet keinen Browser |

## astra-plugin keygen

Erzeugt das OPTIONALE Ed25519-Schlüsselpaar, das `astra-plugin sign`
verwendet.

Du brauchst keinen zum Veröffentlichen: `build` liest ihn nicht, und
Astras Vertrauen kommt vom Registry-Eintrag über sha256(gesamte Datei),
nicht von irgendeinem Schlüssel, den du besitzt.

```
Usage: astra-plugin keygen [OPTIONS]
```

**Optionen**

| Option | Beschreibung |
|---|---|
| `--force` | Überschreibt ein bestehendes Schlüsselpaar |
</content>
