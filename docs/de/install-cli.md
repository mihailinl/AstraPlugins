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
Bauen braucht eine Rust-Toolchain. Vorgebaute Binärdateien auszuliefern
ist eine bekannte, separate, ausstehende Aufgabe — die Release-Automation
dafür wird gerade geschrieben, und diese Seite bekommt eine Download-Zeile
an dem Tag, an dem es ein Release zum Herunterladen gibt. Bis dahin
beschreibt sie das Vollständige dessen, was existiert, und nichts hier
verlangt von dir, irgendetwas herunterzuladen.

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

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
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
gemeldete Commit sind also das, was beim Ausführen auf `master` liegt. Alles
in spitzen Klammern unten unterscheidet sich je nach Maschine und Lauf — die
Version und die SHA kommen von `master`, die Pfade aus deinem
Home-Verzeichnis, die Dauer von deiner CPU:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

Dieses Transkript entstand mit `--root <scratch>`, damit das Aufzeichnen
niemandes installierte Binärdatei überschreibt. **Lass `--root` weg** — so
wie der Befehl oben — und die letzten beiden Zeilen ändern sich:
`Installing` nennt dann `<home>/.cargo/bin/astra-plugin`, und die
`PATH`-Warnung erscheint nur, wenn `~/.cargo/bin` nicht ohnehin schon in
deinem `PATH` liegt. Die beiden SHAs sind derselbe Commit in zwei
verschiedenen Längen ausgegeben — das macht cargo so, es ist keine
Abweichung.

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
astra-plugin <version>
```

Die Zahl ist ein Platzhalter, weil dich keine der beiden Installationszeilen
eine auswählen lässt: beide bauen einen Commit, kein Release, du bekommst
also die Version aus der `Cargo.toml` dieses Commits. `0.2.1` ist der neueste
Eintrag im [Changelog der CLI](../../astra-plugin-cli/CHANGELOG.md), das
auch festhält, dass diese Crate keinen Release-Zug hat — kein crates.io,
kein Tag, keine Binärdateien.

Wenn die Shell es nicht findet, hat `cargo install` es in `~/.cargo/bin`
(oder `%USERPROFILE%\.cargo\bin` unter Windows) abgelegt, und dieses
Verzeichnis ist nicht in deinem `PATH`. `cargo` gibt genau dann eine
entsprechende Warnung aus.

### Der Bug, der ein erstes Release kaputtmacht, und wie du erkennst, ob dein Build den Fix hat

**`astra-plugin init-ci` pinnte früher die *Objekt*-SHA eines annotierten
Tags, wo GitHub einen Commit verlangt**, sodass der erste `git push --tags`
mit `invalid value workflow reference` fehlschlug, bevor irgendein Job
startete. Das war
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Der Fix ist der Commit `5b8ab22`, keine Versionsnummer**, und das ist der
Teil, über den Leute stolpern. Es gibt hier keinen Release-Zug — nichts ist
veröffentlicht, also installiert niemand eine ausgewählte Version; alle
bauen den Commit, den sie geklont haben. `5b8ab22` landete auf `master`
*vor* dem Versionssprung, der die Zahl auf `0.2.1` hob, was bedeutet:

- ein Build von `master` nach `5b8ab22` **hat den Fix und gibt trotzdem
  `0.2.0` aus** — das ist kein kaputter Build;
- kein `0.2.1`-Build kann den Fix *nicht* haben, denn `5b8ab22` ist ein
  Vorfahre des Versionssprung-Commits;
- ein `0.2.0`-Build von *vor* `5b8ab22` ist der kaputte, und `--version`
  kann ihn nicht vom ersten Fall unterscheiden.

`0.2.1` ist es also wert — es ist die erste Zahl, die die Frage von selbst
beantwortet, und genau dafür existiert sie — aber ein `0.2.0`, das `0.2.0`
sagt, ist kein Beweis für irgendetwas. `0.2.1` fügt kein Flag hinzu und
ändert keine API; das eine geänderte Verhalten ist `publish --notify`,
dessen Link jetzt das Release-Ping-Formular der Registry benennt statt
auf ein leeres Issue zu setzen, das die Registry inzwischen abgeschaltet
hat.

Wenn `--version` `0.2.0` ausgibt, führe zuerst `which astra-plugin`
(`where` unter Windows) aus: die häufigste Ursache ist eine ältere
Binärdatei weiter vorn in deinem `PATH`, und `--version` allein kann das
nicht von einem frischen Build eines älteren Commits unterscheiden. Hör
danach auf, aus der Zahl zu raten, und lies stattdessen den Pin — `init-ci`
schreibt genau das, worum es bei dem Bug ging, und es antwortet in einer
Zeile.

Das ist die Prüfung, die überhaupt nicht von der Version abhängt:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Ein Build mit dem Fix meldet das Pinning
`e3329df252a46d747676cb540ae4b986af68a3ad` — einen Commit. Ein Build ohne
ihn meldet `dc1a044876926e9cf1170f034e2eab533ec07641`, das ist das
*Tag-Objekt* von `plugin-release/v1` und das, was GitHub ablehnt. Wenn du
das zweite siehst, installiere mit der Zeile oben neu aus `master` und führe
`init-ci` erneut aus. Es kann gefahrlos erneut ausgeführt werden: es behält
deine Eingaben und schreibt das Pinning neu. Nichts wird an Ort und Stelle
repariert, eine bestehende `release.yml` behält also die falsche SHA, bis du
es erneut ausführst.

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
| `invalid value workflow reference`, bei deinem ersten Tag-Push | Die CLI, die `release.yml` geschrieben hat, ist älter als `5b8ab22` und pinnte ein Tag-Objekt. Siehe [wie du erkennst, ob dein Build den Fix hat](#der-bug-der-ein-erstes-release-kaputtmacht-und-wie-du-erkennst-ob-dein-build-den-fix-hat) |

## Weiter

- **[Was Veröffentlichen ist](publishing.md)** — der ganze Weg, leeres
  Verzeichnis bis gelistetes Plugin, auf einer Seite.
- [Erste Schritte](2-tutorial/getting-started.md) — das Plugin selbst
  schreiben.
</content>
