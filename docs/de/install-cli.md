> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/install-cli.md) maßgeblich.

# Die CLI installieren

Alles auf dem Veröffentlichungsweg beginnt mit einem Befehl, und das ist
die Seite, die dir diesen Befehl verschafft. Die Binärdatei heißt
**`astra-plugin`** — nicht `astra-plugin-cli`, das ist nur der Name der
Crate.

## Der ehrliche Stand der Dinge

**Es gibt noch keine vorgebauten Binärdateien, und `astra-plugin-cli` ist
nicht auf crates.io.** Heute verifiziert:
`https://index.crates.io/as/tr/astra-plugin-cli` antwortet mit `404`,
während `astra-plugin-sdk` im selben Index mit `200` antwortet, das ist
also eine echte Abwesenheit und kein fehlgeschlagenes Nachschlagen.
`gh release list --repo mihailinl/AstraPlugins` gibt nichts aus.

Der einzige Weg, die CLI zu bekommen, ist also, sie zu bauen, und das
Bauen braucht eine Rust-Toolchain. Vorgebaute `linux-x64`- und
`windows-x64`-Binärdateien auszuliefern ist eine bekannte, separate,
ausstehende Aufgabe; bis sie ankommt, beschreibt diese Seite das
Vollständige dessen, was existiert.

Diese Kosten sind real, und es lohnt sich zu benennen, warum es sich
trotzdem zu zahlen lohnt: die CLI ist kein Bequemlichkeits-Wrapper um
einen anderen, einfacheren Weg. Sie ist das Einzige, was einen korrekten
Release-Workflow schreibt, das Einzige, was deine Manifeste davon
abhält, uneins über die Version zu sein, und das Einzige, was eine
Listing-Anfrage öffnet, die der Bot der Registry tatsächlich sieht. Sie
zu umgehen ist der Grund, warum zwei echte Einreichungen im Schweigen
endeten — siehe [was Veröffentlichen ist](publishing.md).

## Voraussetzungen

| | Warum | Prüfen |
|---|---|---|
| **Rust 1.85 oder neuer** | jede Crate hier ist `edition = "2024"`, und 1.85 ist das erste Release, das das versteht | `cargo --version` |
| **`protoc` im `PATH`** | die CLI hängt von `astra-plugin-sdk` ab, dessen `build.rs` `proto/plugin.proto` mit `tonic-build` kompiliert, das extern ein externes `protoc` aufruft | `protoc --version` |
| **`git`** | `cargo install --git` klont damit | `git --version` |

Keine Crate deklariert eine `rust-version`, und CI baut auf `stable`, die
Edition ist also die einzige tatsächlich durchgesetzte Untergrenze.

`protoc` installieren, was der Punkt ist, den Leute übersehen:

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

Ohne es schlägt der Build im Build-Skript von `astra-plugin-sdk` fehl,
und der Fehler nennt den Fix:

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release -p astra-plugin-sdk" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## Installieren

**Eine Zeile, kein Klon.** Das ist die zu verwendende:

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` baut gegen die eingecheckte `Cargo.lock`, statt jede
Abhängigkeit neu auf ihr neuestes Release aufzulösen, was den Unterschied
ausmacht zwischen einem Build, der so funktioniert wie er hier
funktionierte, und einem, der auf deiner Maschine von einem
Breaking-Patch-Release überrascht wird.

`--git` baut, was `master` gerade trägt, die gemeldete Version und der
gemeldete Commit sind also das, was beim Ausführen auf `master` liegt — die
spitzen Klammern unten sind genau die beiden Teile, die bei dir anders sind:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" -->
```
   Compiling astra-plugin-cli v<version> (/home/you/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in 23.60s
  Installing /home/you/.cargo/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<sha>)` (executable `astra-plugin`)
```

**Aus einem Klon**, wenn du die CLI auch lesen oder ändern willst, nicht
nur ausführen:

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

Ein bloßes `git clone` checkt `master` aus, und `master` ist, wo die
aktuelle CLI ist — es gibt keinen Branch, den du kennen musst.

## Prüfen, dass es funktioniert hat

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin 0.2.1
```

Wenn die Shell es nicht findet, hat `cargo install` es in `~/.cargo/bin`
(oder `%USERPROFILE%\.cargo\bin` unter Windows) abgelegt, und dieses
Verzeichnis ist nicht in deinem `PATH`. `cargo` gibt genau dann eine
entsprechende Warnung aus.

### Nimm 0.2.1 oder neuer, und warum das wichtig ist

**`0.2.0` hat einen Bug, der dein erstes Release kaputtmacht.**
`astra-plugin init-ci` pinnte die *Objekt*-SHA eines annotierten Tags, wo
GitHub einen Commit verlangt, sodass der erste `git push --tags` mit
`invalid value workflow reference` fehlschlug, bevor irgendein Job
startete. Das war
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2), und
es ist in `0.2.1` behoben.

Der unangenehme Teil, klar gesagt: `0.2.0` wurde sowohl vor als auch nach
dem Fix-Commit `5b8ab22` veröffentlicht, eine Weile lang konnte die
Version also nicht zwischen einem funktionierenden und einem kaputten
Build unterscheiden. `0.2.1` existiert, um das zu beenden. Es fügt kein Flag hinzu und
ändert keine API; das eine geänderte Verhalten ist `publish --notify`,
dessen Link jetzt das Release-Ping-Formular der Registry benennt statt
auf ein leeres Issue zu setzen, das die Registry inzwischen abgeschaltet
hat.

Wenn `--version` `0.2.0` ausgibt, führe zuerst `which astra-plugin`
(`where` unter Windows) aus: die übliche Ursache ist eine ältere Binärdatei
weiter vorn in deinem `PATH`, und `--version` allein kann die beiden nicht
unterscheiden. Wenn das der Pfad ist, den du gerade installiert hast, und
die Zahl immer noch `0.2.0` lautet, dann trägt der `master`, aus dem du
gebaut hast, `0.2.1` noch nicht — der Fix-Commit `5b8ab22` landete auf
`master`, bevor der Versionssprung es tat, der ihn benennt, ein Build kann
den Fix also enthalten und trotzdem `0.2.0` sagen. Rate nicht: die
`init-ci`-Prüfung unten liest den Pin, den die CLI tatsächlich schreibt,
und genau darum ging es bei dem Bug.

Du kannst es auch bestätigen, ohne der Version überhaupt zu vertrauen,
indem du dir ansiehst, was `init-ci` schreibt:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Ein reparierter Build meldet das Pinning
`e3329df252a46d747676cb540ae4b986af68a3ad` — einen Commit. Ein
`0.2.0`-Build meldet `dc1a044876926e9cf1170f034e2eab533ec07641`, was das
Tag-Objekt ist und das, was GitHub ablehnt. `init-ci` kann gefahrlos
erneut ausgeführt werden: es behält deine Eingaben und schreibt das
Pinning neu. Nichts wird an Ort und Stelle repariert, eine bestehende
`release.yml` behält also die falsche SHA, bis du es erneut ausführst.

Der Befehlssatz, vollständig:

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

Es gibt **kein `astra-plugin login`**, und das ist Absicht statt
Unfertigkeit: nichts in dieser Toolchain fragt dich je nach einer
Zugangsdatei. Siehe [Gelistet werden](5-publish/get-listed.md).

## Aktuell halten

Führe dieselbe `cargo install --git`-Zeile erneut aus. Cargo ersetzt die
Binärdatei an Ort und Stelle. Es gibt kein Self-Update, und es wird auch
keines geben, bevor es signierte Release-Binärdateien gibt, auf die man
aktualisieren könnte.

## Was schiefgehen kann

| Symptom | Ursache |
|---|---|
| `Could not find `protoc`` | `protoc` ist nicht im `PATH`. Siehe die Tabelle oben |
| `feature `edition2024` is required` | Rust älter als 1.85 |
| `astra-plugin: command not found` nach erfolgreicher Installation | `~/.cargo/bin` ist nicht im `PATH` |
| `error: could not find `Cargo.toml`` beim Ausführen von `cargo install --path .` an der Repository-Wurzel | Es gibt an der Wurzel kein Workspace-Manifest. Zeige `--path` auf `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Ein älteres `astra-plugin` liegt vorher in deinem `PATH`. `--version` verrät dir nicht, welches; führe `which astra-plugin` (`where` unter Windows) aus, um zu sehen, welche Datei du tatsächlich ausführst |
| `invalid value workflow reference`, bei deinem ersten Tag-Push | Die CLI, die `release.yml` geschrieben hat, war `0.2.0` und pinnte ein Tag-Objekt. Siehe [nimm 0.2.1 oder neuer](#nimm-021-oder-neuer-und-warum-das-wichtig-ist) |

## Weiter

- **[Was Veröffentlichen ist](publishing.md)** — der ganze Weg, leeres
  Verzeichnis bis gelistetes Plugin, auf einer Seite.
- [Erste Schritte](2-tutorial/getting-started.md) — das Plugin selbst
  schreiben.
</content>
