> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/5-publish/release-with-ci.md) maßgeblich.

# Mit CI veröffentlichen

**Ein Tag ist der ganze Release-Prozess.** Ein Befehl richtet ihn ein, und
danach baust du nie wieder ein Bundle von Hand.

Alles auf dieser Seite startet von der `astra-plugin`-Binärdatei aus. Wenn
du sie nicht hast, [installiere zuerst die CLI](../install-cli.md) — eine
`cargo install`-Zeile, eine Rust-Toolchain erforderlich, noch keine
vorgebauten Binärdateien. Für den ganzen Weg auf einer Seite statt nur
diese eine Stufe davon, siehe
[Ein Plugin veröffentlichen](../publishing.md).

## Warum nicht einfach `astra-plugin build` und hochladen?

Weil nichts für eine auf deinem Laptop gebaute Datei bürgt. Die Registry
liest GitHubs **Build-Attestation** — eine Sigstore-keyless-Signatur, aus
der OIDC-Identität des Workflows geprägt — die sagt *genau diese Bytes
stammen aus diesem Workflow, bei diesem Commit, in diesem Repository*. Ein
handgebautes Bundle trägt so etwas nicht und wird abgelehnt, egal wie gut
es ist — mit `E_ATTESTATION_MISSING`, namentlich.

Aus demselben Grund **ist das Pushen deines Quellcodes auf GitHub kein
Release**, ebenso wenig jemandem die lokal gebaute `.astraplugin` zu
schicken. Die Registry liest nie deinen Quellbaum; sie liest die Assets
auf einem getaggten Release, und sie pinnt sie über den Digest.

Du brauchst keinen Signierschlüssel und wirst auch nicht danach gefragt.
Siehe [das Sicherheitsmodell](../1-orientation/security.md).

## 1 · Den Workflow schreiben

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

**Das funktioniert heute, und jede Hälfte davon ist überprüfbar.**
`.github/workflows/plugin-release.yml` liegt auf dem Default-Branch von
`mihailinl/AstraPlugins` — `git ls-tree -r master --name-only
.github/workflows` listet es auf — und das veröffentlichte Tag existiert:
`git ls-remote --tags origin` löst `plugin-release/v1` zu
`e3329df252a46d747676cb540ae4b986af68a3ad` auf. Weil das Tag existiert,
pinnt `init-ci` diesen Commit statt eines beweglichen Branch-Kopfs, und
gibt nicht mehr den „Not verified"-Hinweis aus, den frühere Versionen
dieser Seite zitierten.

Diese SHA ist dieselbe, die die root-signierte `trust.json` der Registry
in einer Build-Attestation erlaubt —
`node tools/sign-trust.mjs --verify registry/v1/trust.json` in
`astra-registry` gibt sie unter *reusable-workflow SHAs it allows* aus.
Ein von einem anderen Workflow erzeugter Build wird beim Ingest mit
`E_WORKFLOW_NOT_ALLOWED` abgelehnt, das Pinnen ist also keine Nettigkeit;
es ist das, was deine Attestation zu etwas macht, mit dem die Registry
arbeiten kann.

Führe `init-ci` erneut aus, wann immer ein neueres `plugin-release/vN`
veröffentlicht wird; es behält deine Eingaben und verschiebt nur das
Pinning.

Das ist die gesamte autorenseitige CI. Sie ist kurz, weil sie delegiert:

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

Führe `init-ci` erneut aus, um das Pinning voranzutreiben; es behält die
von dir gesetzten Inputs. `--offline` behält das bereits in der Datei
vorhandene Pinning, und `--ref <sha-or-ref>` pinnt etwas Bestimmtes.

## 2 · Taggen

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` schreibt `plugin.toml` **und** jedes andere
Manifest im Projekt in einer Bearbeitung um — `Cargo.toml`,
`package.json`, `pyproject.toml` — sodass sie nicht uneins sein können. Es
lehnt eine Version ab, die unter der aktuellen einsortiert, es sei denn,
du übergibst `--allow-downgrade`, weil Astra sich weigert, ein Downgrade
zu installieren, und ein solches Release unbrauchbar wäre.

Das Tag muss `tag-prefix` plus der Manifest-Version entsprechen, und CI
stellt das sicher, bevor sie irgendetwas baut. `astra-plugin version`
gibt das genaue zu verwendende Tag aus:

<!-- doctest: output from="astra-plugin version 0.2.0" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

## 3 · Was CI tut

Dieser Abschnitt beschreibt `.github/workflows/plugin-release.yml`, so
wie es in diesem Repository auf `master` geschrieben steht, bei dem
Commit, auf den `plugin-release/v1` zeigt — dem Commit, den deine
`release.yml` aufruft.

Drei Jobs, und die Aufteilung ist die Sicherheitseigenschaft.

| Job | Führt deinen Code aus | Hält ein Schreib-Token | Was er tut |
|---|---|---|---|
| **plan** | **nein** | ja | Liest `plugin.toml` mit Pythons `tomllib` als *Daten*, prüft tag == version, entscheidet die Build-Matrix, erstellt das Entwurfs-Release |
| **build** (Matrix) | ja | **nein** | `astra-plugin check --strict`, `astra-plugin build`, verify, entpacken, prüft die glibc-Untergrenze und die Eigenständigkeit des TypeScript-Bundles |
| **publish** | nein | ja | Leitet jeden Digest selbst neu ab, schreibt `SHA256SUMS.txt`, bezeugt, lädt hoch, hebt den Entwurfsstatus des Release auf |

`plan` führt nie etwas außerhalb des Repositorys aus — keine
Submodule, keine in `.git/config` persistierten Zugangsdaten. `build`
führt deine `build.rs` und deine Lifecycle-Skripte aus und hat kein Token
zu stehlen. `publish` lädt die Artefakte herunter, hasht sie selbst und
bezeugt, was es gehasht hat.

Die Matrix wird aus der Sprache deines Plugins bestimmt: `linux-x64` +
`windows-x64` für Rust, ein einzelner `noarch`-Zweig für TypeScript und
Python.

### Was auf dem Release landet

| Asset | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | eines pro Plattform-Schlüssel |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | das Attestation-Bundle, sodass ein Nutzer ohne Netzwerkzugriff auf GitHub trotzdem prüfen kann |
| `SHA256SUMS.txt` | dieselben Digests, die die Registry aufzeichnet |

Das Release wird erst sichtbar, wenn jedes Asset angehängt ist.

### Attestation braucht ein öffentliches Repository

Build-Attestations werden in ein öffentliches Transparency-Log
veröffentlicht; auf einem privaten Repository brauchen sie GitHub
Enterprise. Der Workflow löst die Sichtbarkeit deines Repositorys auf
und, wenn sie nicht öffentlich ist, sagt das in der Job-Zusammenfassung
und erzeugt **unbezeugte** Bundles — die die Registry nicht listet. Das
ist eine reale Einschränkung, und sie schlägt laut fehl, statt ein
scheinbar in Ordnung wirkendes Release zu erzeugen.

### Reproduzierbarkeit

`astra-plugin build --reproducible` stellt deterministisches Packen
sicher: sortierte Einträge, ein fester mtime, eine feste
Kompressionsstufe. Zwei Builds aus denselben Eingaben erzeugen denselben
sha256. CI führt bei jedem Release einen Reproduzierbarkeits-Kanarienvogel
aus, was den Nachbau durch Dritte aussagekräftig macht.

## 4 · Selbst prüfen

Jeder kann ein Release verifizieren, ohne Astra oder der Registry zu
vertrauen:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` liest das Bundle selbst und gibt aus, was es
gefunden hat:

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

Exit-Codes sind hier wichtig, und jeder Release-Workflow verzweigt danach:
**1** bedeutet, das Bundle ist fehlerhaft, **2** bedeutet, die CLI konnte
nicht antworten — zum Beispiel eine fehlende Datei. Das Archivformat, und
was ein Verifier ablehnen muss, steht in
[`spec/bundle-v2.md`](../spec/bundle-v2.md).

## 5 · Dann gelistet werden

Einmal. → [Gelistet werden](get-listed.md).

## Was schiefgehen kann

| Symptom | Ursache |
|---|---|
| Der Workflow startet nie | `on: push: tags:` und `tag-prefix:` stimmen nicht überein. Ein Glob, das enger als das Prefix ist, feuert nie |
| „tag does not match the manifest version" | `astra-plugin version <v>` ausführen und committen, bevor du taggst |
| Der Linux-Build scheitert an einem fehlenden Header | `linux-packages: "libasound2-dev pkg-config"` im aufrufenden Workflow setzen |
| Das Bundle ist unbezeugt | Das Repository ist privat |
| `MODULE_NOT_FOUND` beim ersten Start | Eine TypeScript-Abhängigkeit, der der Bundler nicht folgen konnte. CI prüft dagegen; kontrolliere die Externals des Bundlers |
| Ein glibc-Fehler auf der Maschine eines Nutzers | Etwas im Archiv braucht ein Symbol oberhalb von `GLIBC_2.39`. CI prüft auch das |
| `invalid value workflow reference` bevor irgendein Job startet | Das Pinning nennt einen Commit, der `plugin-release.yml` nicht trägt. `astra-plugin init-ci` erneut ausführen, um auf `plugin-release/v1` neu zu pinnen |
| Die Registry lehnt das Release mit `E_WORKFLOW_NOT_ALLOWED` ab | Der Build lief nicht über den gepinnten Astra-Reusable-Workflow. `init-ci` erneut ausführen, neu taggen, und CI neu bauen lassen |

Mehr: [Fehlerbehebung](../6-operate/troubleshooting.md).
</content>
