> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/publishing.md) maßgeblich.

# Ein Plugin veröffentlichen

**Eine Seite, von einem leeren Verzeichnis bis zu einem Plugin, das
Nutzer installieren können.** Jeder Befehl steht hier in Reihenfolge, mit
der Ausgabe, die er erzeugt. Wenn du nur eine einzige Seite über
Veröffentlichen liest, lies diese; die tieferen Seiten sind verlinkt, wo
sie wichtig sind, und keine davon ist nötig, um fertig zu werden.

---

## Lies diesen Teil, auch wenn du sonst nichts liest

Ein Plugin für Astra zu veröffentlichen bedeutet **eine ganz bestimmte
Sache**: Du taggst ein Release in deinem eigenen GitHub-Repository,
GitHubs CI baut das Bundle und bezeugt es, und du schickst der Registry
eine Listing-Anfrage — ein einziges Mal, für immer.

Diese sind **kein** Veröffentlichen, und jedes davon wurde schon
versucht:

| Kein Veröffentlichen | Warum es nicht funktionieren kann |
|---|---|
| Deinen Quellcode auf GitHub pushen | Die Registry liest nie deinen Quellbaum. Sie liest eine `.astraplugin`-Datei, die an einem Release hängt, und es gibt keine |
| Jemandem ein `.zip` schicken, oder ein auf deinem Laptop gebautes Bundle | Die Bytes tragen keine Build-Attestation, die Registry lehnt sie ab, egal wie gut das Plugin ist |
| Ein Issue öffnen, das einen Maintainer bittet, es für dich zu bauen | Niemand baut dein Plugin außer der eigenen CI deines Repositorys. Es gibt keinen anderen Builder |
| Ein Issue in der Registry öffnen, das dein Plugin beschreibt, aber am Listing-Formular vorbei | Nur das Formular vergibt das `listing`-Label, und nur dieses Label startet einen Ingest. Leere Issues sind dort inzwischen abgeschaltet, und eine unbeschriftete Anfrage bekommt statt Schweigen eine Antwort, die das Label benennt — eine Antwort ist aber kein Listing. Siehe [Einreichen](#8-einreichen-ein-einziges-mal-für-immer) |

**Warum das so sein muss, in zwei Sätzen.** Die Registry pinnt dein
Plugin über den SHA-256 genau der Datei, die ein Nutzer herunterladen
wird, und liest GitHubs Build-Attestation — eine Sigstore-Signatur, aus
der eigenen OIDC-Identität des Workflows geprägt — die aussagt, dass
genau diese Bytes aus diesem Workflow, bei diesem Commit, in diesem
Repository hervorgegangen sind. Eine auf deinem Laptop gebaute und
weitergegebene Datei trägt keines von beidem, es gibt also nichts, das
Astra auf der Maschine des Nutzers prüfen kann, und nichts, das die
Registry pinnen kann.

Nichts davon behauptet, dass dein Code sicher ist. Siehe
[Was Vertrauen begründet](#was-vertrauen-begründet) unten auf dieser
Seite.

---

## Bevor du anfängst

<!-- doctest: cli -->
```bash
astra-plugin --version
```

Gibt das nichts aus, stopp hier und mach zuerst
**[Die CLI installieren](install-cli.md)**. Es ist eine
`cargo install`-Zeile, braucht eine Rust-Toolchain, und es gibt noch
keine vorgebauten Binärdateien — diese Seite sagt das klar und deutlich
und sagt dir, was zu installieren ist.

> **Nimm `0.2.1` oder neuer.** `0.2.0` schreibt einen Release-Workflow,
> den GitHub in dem Moment ablehnt, in dem du dein erstes Tag pushst, ein
> `0.2.0`-Build kann diese Seite also nicht abschließen. Sagt
> `--version` `0.2.0`, führe die `cargo install`-Zeile auf
> [Die CLI installieren](install-cli.md) erneut aus, bevor du
> weitermachst.

Du brauchst auch ein **öffentliches** GitHub-Repository. Attestations
werden in ein öffentliches Transparency-Log veröffentlicht; auf einem
privaten Repository brauchen sie GitHub Enterprise, und der
Release-Workflow sagt dir das, statt still unbezeugte Bundles zu
erzeugen.

---

## 1 · Scaffolding

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

`--lang python` und `--lang typescript` scaffolden die beiden anderen
SDKs; `--template` wählt, wovon du ausgehst (`tool`, `tts`, `stt`,
`stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`,
`blank`). Das Plugin selbst zu schreiben ist
[Erste Schritte](2-tutorial/getting-started.md) und die
[SDK-Seiten](4-sdk/rust.md).

**Fülle zwei Felder in `plugin.toml` aus, bevor du weitermachst.** Das
Scaffold lässt `author` leer und `description` generisch, und beide
landen auf deiner Store-Karte:

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

Das `icon.svg`, das das Scaffold schreibt, ist ein Platzhalter; es zu
ersetzen ist
[Gelistet werden §Wie dein Listing aussehen wird](5-publish/get-listed.md#wie-dein-listing-aussehen-wird).

## 2 · Beweisen, dass es läuft

<!-- doctest: cli -->
```bash
astra-plugin test .
```

Das ist die Conformance-Suite, ausgeführt gegen dein Plugin als **echten
Prozess**, der mit einem Mock-Daemon spricht — nicht gegen einen Typ in
deiner Testdatei. Auf das Urteil gekürzt:

<!-- doctest: output from="astra-plugin test ." -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

Um es stattdessen innerhalb eines laufenden Astra zu treiben,
`astra-plugin dev .` — das ist
[Sideloading](5-publish/sideload.md), die Entwicklungsschleife, und ist
**kein** Weg, das Plugin an jemand anderen weiterzugeben.

## 3 · Den Release-Workflow einrichten

Du schreibst kein YAML. Ein Befehl erledigt das:

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

Diese Commit-SHA ist keine Dekoration. Es ist das, worauf der
veröffentlichte wiederverwendbare Workflow `plugin-release/v1` zeigt,
und eine der SHAs, die die root-signierte `trust.json` der Registry
erlaubt — ein von einem anderen Workflow erzeugter Build wird mit
`E_WORKFLOW_NOT_ALLOWED` abgelehnt. Führe `init-ci` jederzeit erneut aus,
um das Pinning voranzutreiben; es behält die von dir gesetzten Inputs.

**Prüfe die ausgegebene SHA, bevor du weitermachst.** Sie muss
`e3329df252a46d747676cb540ae4b986af68a3ad` sein. Ist es
`dc1a044876926e9cf1170f034e2eab533ec07641`, benutzt du CLI-`0.2.0`: das
ist die SHA des *Tag-Objekts*, und `uses: …@<sha>` braucht einen Commit,
dein erster `git push --tags` scheitert also mit
`invalid value workflow reference`, bevor irgendein Job startet. Führe
die `cargo install`-Zeile auf
[Die CLI installieren](install-cli.md) erneut aus, dann
`astra-plugin init-ci` erneut — es schreibt das Pinning neu und behält
deine Inputs. Nichts wird an Ort und Stelle repariert, eine bestehende
`release.yml` behält die falsche SHA also, bis du sie erneut ausführst.
Das ist der Bug, der das erste Release eines echten Autors kaputtmachte.

Detail, einschließlich was die generierte Datei enthält und warum jede
ihrer drei Permissions erforderlich ist:
[Mit CI veröffentlichen](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` wendet an, was mechanisch behoben werden kann. `--resolve-pin`
fragt GitHub, ob dein Workflow-Pinning noch das aktuelle ist; standardmäßig
aus, damit weder `dev` noch CI das Netzwerk brauchen, um eine Prüfung
auszuführen.

## 4 · Öffentlich pushen

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

An diesem Schritt ist nichts Besonderes — es ist ein gewöhnliches
Repository. Aber beachte, was er *nicht* ist: das zu pushen
veröffentlicht das Plugin nicht, und hier aufzuhören ist, wo die zwei
echten Einreichungen, die diese Seite ausgelöst haben, schiefliefen. Was
es zu einem veröffentlichten Plugin macht, ist das Tag im nächsten
Schritt.

## 5 · Taggen — das ist das Release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

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

`astra-plugin version` schreibt `plugin.toml` **und** jedes andere
Manifest im Projekt in einer Bearbeitung um — `Cargo.toml`,
`package.json`, `pyproject.toml` — sodass sie nicht uneins sein können.
Es lehnt eine Version ab, die unter der aktuellen einsortiert, es sei
denn, du übergibst `--allow-downgrade`, weil Astra sich weigert, ein
Downgrade zu installieren, und ein solches Release unbrauchbar wäre.

**Das Tag ist der ganze Release-Prozess.** Es zu pushen startet deine
`release.yml`, die den gepinnten wiederverwendbaren Workflow aufruft,
der drei Jobs ausführt — einen `plan`-Job, der dein Manifest als Daten
liest und nie deinen Code ausführt, eine `build`-Matrix, die deinen Code
ausführt und kein Schreib-Token hält, und einen `publish`-Job, der jeden
Digest selbst neu ableitet und bezeugt, was er gehasht hat. Diese
Aufteilung ist die Sicherheitseigenschaft und wird in
[Mit CI veröffentlichen §3](5-publish/release-with-ci.md#3-was-ci-tut)
beschrieben.

Wenn es fertig ist, trägt dein GitHub-Release:

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

Das Release wird erst sichtbar, wenn jedes Asset angehängt ist.
Rust-Plugins bekommen eine Datei pro Plattform; TypeScript und Python
bekommen eine einzige `noarch`-Datei.

**Wenn der Workflow überhaupt nicht lief**, ist die übliche Ursache, dass
`on: push: tags:` und `tag-prefix:` nicht übereinstimmen — ein Glob, das
enger als das Prefix ist, feuert nie. Die restlichen Fehlermodi stehen in
[Mit CI veröffentlichen §was schiefgehen kann](5-publish/release-with-ci.md#was-schiefgehen-kann).

## 6 · Das Release selbst prüfen

Jeder kann das, ohne Astra oder der Registry zu vertrauen:

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

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

`astra-plugin verify` beendet sich mit **1**, wenn das Bundle
fehlerhaft ist, und mit **2**, wenn die CLI nicht antworten konnte — zum
Beispiel eine fehlende Datei. Das Archivformat und was ein Verifier
ablehnen muss steht in [`spec/bundle-v2.md`](spec/bundle-v2.md).

## 7 · Das Listing per Preflight prüfen

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Es führt jede Registry-Prüfung aus, die lokal laufen kann, und dann —
die Hälfte, die zählt — benennt es die, die nur die Registry ausführen
kann, sodass du weißt, was noch unbewiesen ist:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that you have admin or maintain on the repository
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

## 8 · Einreichen, ein einziges Mal, für immer

<!-- doctest: cli -->
```bash
astra-plugin publish
```

Es öffnet ein **vorausgefülltes Issue in der Registry** in deinem
Browser. Es lädt nichts hoch und hält keine Zugangsdaten — es gibt kein
`astra-plugin login`, kein Token in deiner Shell-Historie, keinen
Schlüsselbund, mit dem integriert werden müsste. `--print-url` gibt
stattdessen den Link aus, statt einen Browser zu öffnen:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **Benutze diesen Link.** Das `template=plugin-listing.yml` darin ist
> tragend: die Issue-Vorlage deklariert `labels: ["listing",
> "needs-triage"]`, und der Bot der Registry betritt den
> Einreichungspfad nur für ein Issue, das das `listing`-Label trägt.
> Sonst vergibt es niemand — auch der Bot nicht, und zwar absichtlich:
> in jenem Repository ist das Label ein Autoritätstoken und keine
> Kategorie.
>
> Früher schlug das lautlos fehl. Zwei Anfragen eines echten Autors kamen
> ohne Labels an, die Triage gab `mode: "none"` zurück, die Check-,
> Publish- und Kommentar-Schritte wurden alle übersprungen, und **er bekam
> gar keine Antwort, nicht einmal eine Ablehnung** — deshalb existiert
> diese Seite. Beide Hälften sind inzwischen geschlossen: die Registry
> schaltet leere Issues ab, das Formular ist also die einzige Tür, und eine
> Anfrage, die trotzdem ohne Label ankommt, bekommt einen Kommentar, der
> das Label benennt und den einen Klick, der die Verifikation auf genau
> diesem Issue startet. Benutze den Link trotzdem: er ist der Weg, auf dem
> ein Ingest ohne Eingreifen von irgendwem startet.

Die Einreichung trägt **zwei Fakten**: dein Quell-Repository
(`you/dice-roller`) und das Release-Tag (`v0.1.0`), plus zwei
Bestätigungen — dass du das Repository besitzt oder pflegst, und dass du
die Policy gelesen hast. Alles andere wird aus dem bezeugten Bundle
gelesen, weil alles im Bundle von der Attestation abgedeckt ist und
daher strikt mehr wert ist als alles in ein Formular Eingetippte.

## 9 · Was als Nächstes passiert

Detail, einschließlich jedes Grund-Codes:
[Gelistet werden §Was nach der Einreichung passiert](5-publish/get-listed.md#3-was-nach-der-einreichung-passiert).
Die Kurzfassung:

| Ergebnis | Bedeutet | Wer ist beteiligt |
|---|---|---|
| **Published** | Committed, und im Katalog beim nächsten Index-Build | niemand |
| **Delayed** | Alles bestanden; veröffentlicht sich selbst zu einem genannten Zeitpunkt | niemand |
| **Held** | Eine Entscheidung, die die Registry nicht automatisch treffen darf | ein Maintainer, innerhalb von **48 h** |
| **Refused** | Eine Prüfung ist gescheitert | du: beheben und `/recheck` auf dem Issue kommentieren |

**Ein erstes Listing wird immer für eine Person zurückgehalten** — das
ist eines von genau drei Ereignissen, die das brauchen, zusammen mit
einer neu angefragten hochriskanten Permission und einem
Repository-Wechsel. 48 Stunden ist der veröffentlichte SLA für alle
davon.

Ein Hold wird aufgelöst, indem ein Maintainer `/approve` auf deinem
Issue kommentiert, was jede Prüfung von Grund auf erneut ausführt, statt
irgendetwas Gecachtes zu vertrauen. Du tippst diesen Befehl nicht und
musst während des Wartens nichts tun. Siehe
[wie ein Hold aufgelöst wird](5-publish/get-listed.md#wie-ein-hold-aufgelöst-wird).

Der Bot kommentiert dein Issue so oder so mit dem Ergebnis und dem
Grund — und er kommentiert inzwischen auch dann, wenn er *nicht*
loslegt, also genau im Fehlschlag aus Schritt 8. Wenn nach einer Stunde
nichts kommentiert hat, prüfe das `listing`-Label. Fehlt es, bitte einen
Maintainer, es zu setzen: das Labeln löst dasselbe Ereignis aus wie eine
neue Einreichung, die Verifikation startet also auf genau diesem Issue,
ohne dass irgendetwas neu getippt werden muss.

## 10 · Jedes Release danach

Nichts. Taggen, und CI erledigt den Rest; die Registry bemerkt das
Release und generiert den Index neu.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

Falls die Registry es innerhalb weniger Minuten nicht bemerkt hat:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Das ist der manuelle Ping für ein Plugin, das **bereits gelistet** ist.
Ohne `--notify` öffnet `publish` stattdessen eine
Erst-Listing-Anfrage, was nicht das ist, was du bei deinem zweiten
Release willst.

---

## Was Vertrauen begründet

`astra-plugin build` verlinkt hierher, die Antwort lebt also an diesem
Anker, bis dieser Link sich bewegt.

**Nicht irgendein Schlüssel, den du besitzt.** `astra-plugin keygen` und
`astra-plugin sign` erzeugen einen optionalen zweiten Faktor — nützlich
gegen eine Übernahme eines GitHub-Kontos, weil der Schlüssel dort liegt,
wo eine gestohlene GitHub-Sitzung nicht ist. Astra verifiziert nicht
gegen deinen Schlüssel: der Daemon prüft das In-ZIP-Paar
`SIGNATURE`/`PUBKEY` gegen einen *gepinnten Astra-Publisher-Schlüssel*,
ein mit deinem eigenen Schlüssel signiertes Bundle ist also genauso
untrusted wie ein unsigniertes. Sowohl der Befehl als auch die
Format-Einträge, die er schreibt, werden ausgemustert.

**Was Astra tatsächlich zugrunde legt**, ist ein Registry-Eintrag, der
den SHA-256 der gesamten Datei gegensigniert, und — vom Registry-Bot
beim Ingest geprüft, nicht vom Daemon — GitHubs Build-Attestation, die
sagt, welcher Workflow, bei welchem Commit, in welchem Repository diese
Bytes erzeugt hat.

**Wie weit die Kette heute verankert ist.** Die Root-Schlüssel existieren
auf beiden Seiten: `astra-registry/registry/v1/root.json` trägt
`"status": "provisioned"` und zwei Ed25519-Schlüssel, und die
`PRODUCTION_ROOT_KEYS` des Daemons kompiliert dieselben zwei ein.
`registry/v1/trust.json` ist jetzt von `astra-root-2026a` signiert und
delegiert an einen Index-Signierschlüssel, `astra-index-2026a` —
verifiziert mit der eigenen
`node tools/sign-trust.mjs --verify registry/v1/trust.json` der
Registry, die auch die eine Reusable-Workflow-SHA ausgibt, die der Bot
in einer Attestation akzeptiert
(`e3329df252a46d747676cb540ae4b986af68a3ad`, der Commit, auf den
`plugin-release/v1` zeigt). **Der noch fehlende Link ist die Signatur
des Katalogs selbst:** `registry/v1/index.json` und
`revocations.json` tragen `"signatures": []`, ein Standard-Astra-Build
hat also nichts zu prüfen und stuft jeden Katalog als unsigniert ein.
Nichts hier verspricht eine Garantie, die noch nicht vorhanden ist;
siehe [das Sicherheitsmodell](1-orientation/security.md) und
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**Nichts davon sagt, dass der Code sicher ist.** Ein Plugin ist ein
nativer Prozess mit deinen vollen Benutzerrechten; es gibt keine
Sandbox. Ein Listing ist keine Sicherheitsprüfung — niemand liest deinen
Code, und die Registry sagt das in ihrer eigenen Policy.

---

## Die zwei anderen Wege, wie ein Plugin auf eine Maschine kommt

Beide richten sich an Entwickler, beide kosten etwas, und **keines
davon ist Veröffentlichen**:

- [Eine lokale `.astraplugin`-Datei installieren](5-publish/local-install.md)
  — ein Bundle, das außerhalb des Kanals ankam. Vier Permissions werden
  pauschal verweigert, egal was das Manifest verlangt.
- [Ein Quellverzeichnis sideloaden](5-publish/sideload.md) — die
  Entwicklungsschleife. Erfordert den Entwicklermodus, führt unsignierten
  Code mit deinem vollen Benutzerkonto aus, und startet nie automatisch.

## Siehe auch

- [Die CLI installieren](install-cli.md) — woher jeder Befehl auf dieser Seite kommt
- [Mit CI veröffentlichen](5-publish/release-with-ci.md) — der Workflow, vollständig
- [Gelistet werden](5-publish/get-listed.md) — die Einreichung und was ihr folgt
- [Versionierung](versioning.md) — was die Zahlen bedeuten und wie lange eine Deprecation dauert
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)
</content>
