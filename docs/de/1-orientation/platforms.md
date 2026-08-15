> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/1-orientation/platforms.md) maßgeblich.

# Plattformen

Astra liefert einen Daemon für **zwei** Hosts aus. Alles Folgende ergibt sich
daraus.

| Plattform-Schlüssel | Host | Astra liefert einen Daemon |
|---|---|---|
| `linux-x64` | Linux, x86_64 | ja |
| `windows-x64` | Windows, x86_64 | ja |
| `noarch` | beliebig — ein interpretiertes Plugin ohne nativen Code | entfällt, läuft auf beiden |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **nein** |

Die letzte Zeile ist *reserviert, nicht unterstützt*. Die Namen existieren im
Registry-Schema, damit sich das Index-Format nie ändern muss, falls Astra
diese Hosts später ausliefert, und damit ein Validator einen Tippfehler
(`mac-amd64`) ablehnen kann, statt einen Schlüssel zu schreiben, den kein
Daemon je nachschlägt. Ein unter einem dieser Namen veröffentlichtes Bundle
hat keinen Host, auf dem es läuft. `astra-plugin build` rät nicht: auf einem
Host, für den es keinen Schlüssel kennt, sagt es dir, `--target` explizit
anzugeben, statt stillschweigend etwas zu packen, das zu `linux-x64` auflöst.

## Ein Bundle pro Plattform, und was bestimmt, wie viele du brauchst

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** kompiliert zu nativem Code, braucht also ein Bundle pro Plattform.
  Der Release-Workflow baut sie auf einer Matrix — `ubuntu-24.04` und
  `windows-2022` — weil ein Cross-Build eine andere Klasse von Bugs mit sich
  bringt.
- **TypeScript und Python** erzeugen ein einziges `noarch`-Bundle. Der Index
  schreibt dieselbe URL und denselben Digest unter jedem unterstützten
  Plattform-Schlüssel, sodass ein `noarch`-Bundle wie jedes andere unter
  `linux-x64` und `windows-x64` gefunden wird.

`--all-targets` baut alles, was das Plugin braucht, um überall installierbar
zu sein, wo Astra läuft: eine Datei für TypeScript und Python, eine pro
Plattform für Rust, jeweils aus eigenem `cargo build --target`.

## `[platform]`, und warum ein weggelassener Block eine Behauptung ist

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

Ein leerer oder fehlender `[platform]`-Block bedeutet *keine Anforderung*,
und der Daemon hält das Plugin für überall kompatibel. Das ist richtig für
ein `noarch`-Plugin und falsch für eines, das eine native Binärdatei
ausliefert. `astra-plugin doctor` sagt das genau in diesen Worten:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` prägt die tatsächliche Antwort aus `--target` in das
`MANIFEST` des Bundles, sodass die verpackte Datei `{os, arch}` trägt, egal
was das Manifest sagt.

## Build-Voraussetzungen

| Sprache | Braucht | Geprüft von |
|---|---|---|
| Rust | Rust **1.85 oder neuer** — das SDK und das Scaffold nutzen Edition 2024 | `astra-plugin doctor` |
| Rust | **`protoc` im PATH.** `astra-plugin-sdk/build.rs` kompiliert `proto/plugin.proto` mit `tonic_build::configure().compile_protos(…)`, und tonic-build 0.12 ruft dafür extern `protoc` auf, statt eines mitzuliefern. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ zum Ausführen, und `bun` (oder den Bundler des `build`-Skripts) zum Bündeln | `astra-plugin doctor` |
| Python | `python3`, plus `grpcio` und `protobuf` aus `requirements.txt` | `astra-plugin doctor` |

`protoc` ist der Punkt, der zuerst zubeißt und sich wie etwas anderes liest.
Die CLI hängt vom Rust-SDK ab, wird also gebraucht, um `astra-plugin` *selbst
zu installieren* — bevor du ein Projekt, ein Manifest oder überhaupt einen
Grund hast, einen Protobuf-Compiler zu vermuten. Ohne `protoc` bleibt
`cargo install` bei
`error: failed to run custom build command for astra-plugin-sdk` stehen, mit
`Could not find `protoc`` einige Zeilen weiter unten. Die eigene CI dieses
Repositorys installiert `protoc` in jedem Rust-Job
(`arduino/setup-protoc@v3`, siebenmal in `.github/workflows/ci.yml`), was der
klarste Beweis dafür ist, dass es nicht optional ist.

`astra-plugin doctor` beantwortet all das mit einem einzigen Befehl, auf der
Maschine, auf der du tatsächlich sitzt:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### Die glibc-Untergrenze

Ein in CI gebautes Linux-Bundle wird gegen **GLIBC_2.39** geprüft — der
Release-Workflow zerlegt jedes ELF-Objekt im fertigen Archiv und lässt den
Build fehlschlagen, wenn irgendetwas eine neuere Symbolversion braucht. Das
ist es, was ein auf `ubuntu-24.04` gebautes Plugin auf den Distributionen
laufen lässt, die Astra anvisiert, und es ist genau die Art von Fehler, die
sonst nur auf der Maschine eines Nutzers auftaucht.

Baust du ein Linux-Bundle von Hand auf einer neueren Distribution, prüft das
niemand. Das ist einer von mehreren Gründen, warum der Release-Weg über CI
läuft.

### TypeScript-Bundles enthalten kein `node_modules`

Eine `.astraplugin` liefert die gebündelte Ausgabe aus, keinen
Abhängigkeitsbaum. Der Release-Workflow stellt sicher, dass das Bundle
in sich geschlossen ist: ein verirrtes `require("chalk")`, dem der Bundler
nicht folgen konnte, installiert sich problemlos und stirbt beim ersten
Start mit `MODULE_NOT_FOUND`, auf einer Maschine, auf der niemand das
reparieren kann.

## Wo die Dinge liegen, je Betriebssystem

Astra löst seine Verzeichnisse mit der `directories`-Crate auf, aus
`("com", "astra", "astra")` — die CLI verwendet denselben Aufruf, sodass
sich die beiden nicht widersprechen können (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Config-Verzeichnis | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Daemon-Port-Datei | `<config>/daemon.port` | gleich |
| Daemon-Bootstrap-Secret | `<config>/daemon.token` | gleich |
| Installierte Plugins | `<config>/plugins/<id>/` | gleich |
| Einstellungen eines Plugins | `<config>/plugins/<id>/config.json` | gleich |
| Daemon-Logs | `<config>/logs/` | gleich |

Frag nach, statt anzunehmen — `doctor` gibt den Pfad aus, den diese Maschine
aufgelöst hat:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

Der Daemon nimmt einen vom Betriebssystem zugewiesenen Port, wenn 32000
belegt ist, also ist `127.0.0.1:32000` eine Ausweich-Vermutung und
`daemon.port` die Tatsache.

## macOS

Nicht unterstützt, und nicht aus Versehen. Astras eigener Release-Workflow
baut nur `linux-x64` und `windows-x64`, sodass ein `macos-arm64`-Plugin-Bundle
keinen Host hätte; macOS würde zusätzlich Apple-Notarisierung für jeden
Drittanbieter-Autor aufwerfen. Die Schlüsselnamen sind im Index-Schema
reserviert, nichts gibt sie aus, und ein unbehandelter Host ist ein harter
Fehler statt eines stillen Fallbacks. Bei Gelegenheit wieder aufgreifen, wenn
Astra einen Daemon für dieses Ziel ausliefert.
</content>
