> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/install-cli.md) maßgeblich.

# Die CLI installieren

Alles auf dem Veröffentlichungsweg beginnt mit einem Befehl, und das ist
die Seite, die dir diesen Befehl verschafft. Die Binärdatei heißt
**`astra-plugin`** — nicht `astra-plugin-cli`, das ist nur der Name der
Crate.

## Zwei Wege, und welcher für dich

**Lade die Binärdatei herunter.** Release [`cli-v0.2.1`][rel] enthält
vorgebaute Archive für Linux und Windows, eine Prüfsummendatei und ein
Sigstore-Bundle, das du verifizieren kannst. Nichts muss kompiliert
werden, und keine Toolchain ist beteiligt. Das ist der Weg, den die
meisten Leute wollen, und er steht unten.

**Oder baue aus dem Quellcode**, was Rust 1.85 oder neuer und `protoc`
braucht. Nimm diesen Weg, wenn du auf einer Plattform ohne Archiv bist —
heute macOS und ARM Linux — oder wenn du die CLI auch lesen oder ändern
willst, nicht nur ausführen.

**`cargo install astra-plugin-cli` ist keiner der Wege und wird nicht
funktionieren.** Die Crate hängt von einer gevendorten
`astra-plugin-manifest` über einen Pfad ab
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`),
cargo paketiert nie den Quellcode einer Pfad-Abhängigkeit, und das
Veröffentlichen schlägt daher fehl mit *all dependencies must have a
version requirement specified* — die Crate ist also überhaupt nicht auf
crates.io (`https://index.crates.io/as/tr/astra-plugin-cli` antwortet
heute mit `404`, während `astra-plugin-sdk` im selben Index mit `200`
antwortet). Das freizuschalten bedeutet, zuerst die Manifest-Crate von
Astra zu veröffentlichen, und diese Seite verspricht dafür kein Datum.

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## Eine Binärdatei herunterladen

### Welches Archiv

| Du bist auf | Nimm |
|---|---|
| **Jedem Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux, und du willst konkret den glibc-Build | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl ist die sichere Standardwahl, und der Grund ist nicht Geschmack.**
Der gnu-Build ist dynamisch gelinkt, und seine Symboltabelle verlangt
**glibc 2.39 oder neuer**, das Ubuntu 22.04 (2.35), Debian 12 (2.36) und
RHEL 9 (2.34) nicht haben — auf jedem davon startet er nicht, statt
subtil falsch zu funktionieren. Das musl-Archiv ist eine
`static-pie`-ausführbare Datei ganz ohne libc-Abhängigkeit, sie läuft
also auf jedem davon. Nimm gnu nur, wenn du weißt, dass du es willst.

Die vollständige Asset-Liste dieses Releases, also alles Veröffentlichte:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### Holen und prüfen

Linux, über `curl` — hier braucht es weder `gh` noch ein GitHub-Konto:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

Das ist ein reales Transkript dieser Befehle:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**Benutze `--ignore-missing`.** `SHA256SUMS.txt` listet alle drei Archive
auf, ein einfaches `sha256sum -c SHA256SUMS.txt` meldet die zwei, die du
nicht heruntergeladen hast, also als `FAILED open or read` und **beendet
sich mit 1** — was exakt wie ein beschädigter Download aussieht und keiner
ist:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

Das Archiv entpackt sich in ein Verzeichnis, das die Binärdatei und ihre
Lizenzdateien enthält:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

Verschiebe `astra-plugin` irgendwohin in deinen `PATH` — `~/.local/bin`
ist die übliche Antwort, und es braucht kein `sudo`:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

Unter Windows lade das `.zip` von der Release-Seite herunter, entpacke
es, und lege `astra-plugin.exe` in deinen `PATH`. `certutil -hashfile
<file> SHA256` ist das eingebaute Prüfsummenwerkzeug, und dessen Ausgabe
wird per Auge mit `SHA256SUMS.txt` verglichen.

### Prüfen, wer sie gebaut hat

Die Prüfsumme beweist, dass die Bytes zu einer im Release benannten Datei
passen. Sie beweist nicht, wer diese Datei erzeugt hat — dafür gibt es
ein Sigstore-Bundle, und `gh` prüft es gegen GitHubs Build-Attestation:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**Ein Erfolg gibt nichts aus, wenn die Ausgabe kein Terminal ist, und
beendet sich mit `0`.** Das ist beim ersten Mal verwirrend; prüfe `echo
$?`, statt nach einem Häkchen zu suchen. Ein Fehlschlag ist laut und
beendet sich mit `1`:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

Das entstand durch Anhängen eines Bytes an das Archiv; `--repo` auf ein
Repository zu zeigen, das es nicht gebaut hat, scheitert identisch. Ein
Bundle deckt alle drei Archive ab, und was es bezeugt, ist mit
`--format json` lesbar: der signierende Workflow ist
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`,
der Issuer ist `https://token.actions.githubusercontent.com`, und die
drei Subject-Digests sind die drei Zeilen von `SHA256SUMS.txt`. `gh
attestation verify` braucht Netzwerkzugriff, um die Vertrauenswurzel zu
holen, aber keinen GitHub-Login.

## Aus dem Quellcode bauen

Nimm diesen Weg für macOS oder ARM Linux, wo es noch kein Archiv gibt,
oder um an der CLI selbst zu arbeiten. Es ist kein Fallback für einen
fehlgeschlagenen Download — die Binärdatei oben ist dasselbe Programm.

### Voraussetzungen

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

### Bauen

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

Um genau den Code zu bauen, aus dem die veröffentlichten Binärdateien
gebaut wurden, statt dessen, was `master` heute trägt, checke zuerst das
Release-Tag aus:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

Eine heruntergeladene Binärdatei gibt `astra-plugin 0.2.1` aus, weil das
Archiv aus dem Tag `cli-v0.2.1` gebaut ist und aus nichts sonst.
`<version>` ist nur auf dem Quellcode-Weg ein Platzhalter: `cargo install
--git` baut, was `master` in diesem Moment trägt, du bekommst also die
Version aus der `Cargo.toml` dieses Commits, die dem neuesten Release
voraus sein kann. `0.2.1` ist der neueste Eintrag im
[Changelog der CLI](../../astra-plugin-cli/CHANGELOG.md).

Wenn die Shell es nicht findet: eine heruntergeladene Binärdatei liegt
dort, wohin du sie kopiert hast, und `cargo install` legt eine in
`~/.cargo/bin` ab (oder `%USERPROFILE%\.cargo\bin` unter Windows). So
oder so ist dieses Verzeichnis nicht in deinem `PATH`. `cargo` gibt genau
dann eine entsprechende Warnung aus, wenn das passiert.

### Der Bug, der ein erstes Release kaputtmacht, und wie du erkennst, ob dein Build den Fix hat

**`astra-plugin init-ci` pinnte früher die *Objekt*-SHA eines annotierten
Tags, wo GitHub einen Commit verlangt**, sodass der erste `git push --tags`
mit `invalid value workflow reference` fehlschlug, bevor irgendein Job
startete. Das war
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Die `0.2.1`-Binärdatei herunterzuladen klärt das, und das ist die kurze
Antwort.** Das Archiv ist aus dem Tag `cli-v0.2.1` gebaut, `5b8ab22` ist
ein Vorfahre davon, eine heruntergeladene Binärdatei hat den Fix also. Der
Rest dieses Abschnitts gilt für einen Build aus dem Quellcode, wo die Zahl
es nicht klärt.

**Der Fix ist der Commit `5b8ab22`, keine Versionsnummer**, und das ist der
Teil, über den Leute stolpern. Ein Build aus dem Quellcode installiert den
Commit, den du geklont hast, nicht ein ausgewähltes Release. `5b8ab22`
landete auf `master` *vor* dem Versionssprung, der die Zahl auf `0.2.1`
hob, was bedeutet:

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
  locale   Manage `locales/` — the plugin's translations, and its store card's text
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

Hast du eine Binärdatei heruntergeladen, lade das Archiv des nächsten
Releases herunter und ersetze die Datei — prüfe die Prüfsumme erneut, denn
ein neues Release bedeutet neue Bytes. Hast du aus dem Quellcode gebaut,
führe dieselbe `cargo install`-Zeile erneut aus, cargo ersetzt die
Binärdatei an Ort und Stelle. **Es gibt kein Self-Update**, und nichts in
dieser Toolchain telefoniert nach Hause, um herauszufinden, dass eine neue
Version existiert.

## Was schiefgehen kann

| Symptom | Ursache |
|---|---|
| `FAILED open or read` von `sha256sum -c` | Du hast ein Archiv heruntergeladen, und die Datei listet drei auf. Füge `--ignore-missing` hinzu |
| `Error: verifying with issuer "sigstore.dev"` | Das Archiv passt nicht zum Bundle, oder `--repo` nennt ein Repository, das es nicht gebaut hat. Lade neu herunter, statt darüber nachzudenken |
| `gh attestation verify` hat überhaupt nichts ausgegeben | Das ist ein Erfolg. Es ist still, wenn die Ausgabe kein Terminal ist; `echo $?` zeigt `0` |
| Die Binärdatei startet nicht, und der Loader beschwert sich, eine `GLIBC_2.39`-Version wurde nicht gefunden | Du hast das gnu-Archiv auf einem System mit älterem glibc genommen. Nimm das musl-Archiv, es braucht kein libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` kann nicht funktionieren, und das ist, was es dazu sagt. Siehe den Anfang dieser Seite |
| `Could not find `protoc`` | `protoc` ist nicht im `PATH`. Siehe die Tabelle oben |
| `feature `edition2024` is required` | Rust älter als 1.85 |
| `astra-plugin: command not found` nach erfolgreicher Installation | Das Verzeichnis mit der Binärdatei ist nicht im `PATH` — bei einem Build aus dem Quellcode ist das `~/.cargo/bin` |
| `error: could not find `Cargo.toml`` beim Ausführen von `cargo install --path .` an der Repository-Wurzel | Es gibt an der Wurzel kein Workspace-Manifest. Zeige `--path` auf `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Ein älteres `astra-plugin` liegt vorher in deinem `PATH`. `--version` verrät dir nicht, welches; führe `which astra-plugin` (`where` unter Windows) aus, um zu sehen, welche Datei du tatsächlich ausführst |
| `invalid value workflow reference`, bei deinem ersten Tag-Push | Die CLI, die `release.yml` geschrieben hat, ist älter als `5b8ab22` und pinnte ein Tag-Objekt. Siehe [wie du erkennst, ob dein Build den Fix hat](#der-bug-der-ein-erstes-release-kaputtmacht-und-wie-du-erkennst-ob-dein-build-den-fix-hat) |

## Weiter

- **[Was Veröffentlichen ist](publishing.md)** — der ganze Weg, leeres
  Verzeichnis bis gelistetes Plugin, auf einer Seite.
- [Erste Schritte](2-tutorial/getting-started.md) — das Plugin selbst
  schreiben.
</content>
