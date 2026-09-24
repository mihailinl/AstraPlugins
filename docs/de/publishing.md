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
GitHubs CI baut das Bundle und bezeugt es, und du reichst es einmal im
Panel ein — ein einziges Mal, für immer.

Diese sind **kein** Veröffentlichen, und jedes davon wurde schon
versucht:

| Kein Veröffentlichen | Warum es nicht funktionieren kann |
|---|---|
| Deinen Quellcode auf GitHub pushen | Die Registry liest nie deinen Quellbaum. Sie liest eine `.astraplugin`-Datei, die an einem Release hängt, und es gibt keine |
| Jemandem ein `.zip` schicken, oder ein auf deinem Laptop gebautes Bundle | Die Bytes tragen keine Build-Attestation, die Registry lehnt sie ab, egal wie gut das Plugin ist |
| Einen Maintainer bitten, es für dich zu bauen | Niemand baut dein Plugin außer der eigenen CI deines Repositorys. Es gibt keinen anderen Builder |
| Dein Plugin der Registry irgendwo anders beschreiben als auf der Einreichungsseite des Panels | Die Registry handelt auf eine Einreichung, die im Panel gemacht wird, angemeldet, für ein an dein Konto gebundenes Repository. Eine andere Tür gibt es nicht. Siehe [Einreichen](#8--einreichen-ein-einziges-mal-für-immer) |

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
**[Die CLI installieren](install-cli.md)**. Es gibt jetzt vorgebaute
Binärdateien — lade ein Archiv für Linux oder Windows herunter, prüfe es
gegen `SHA256SUMS.txt`, und keine Toolchain ist beteiligt. Aus dem
Quellcode zu bauen funktioniert weiterhin und ist der Weg auf macOS und
ARM Linux. `cargo install astra-plugin-cli` ist überhaupt kein Weg; diese
Seite sagt, warum.

> **Lies die Gesundheit deines Builds nicht an der Versionsnummer ab.**
> Eine CLI, die vor dem Commit `5b8ab22` gebaut wurde, schreibt einen
> Release-Workflow, den GitHub in dem Moment ablehnt, in dem du dein erstes
> Tag pushst. Dieser Fix landete auf `master` *vor* dem Sprung auf `0.2.1`,
> ein Build kann ihn also tragen und trotzdem `0.2.0` ausgeben, und kein
> `0.2.1` hat ihn nicht. Wer heute von `master` installiert, bekommt den
> Fix, egal was die Zahl sagt. Was es tatsächlich klärt, ist die SHA, die
> `init-ci` ausgibt, und diese Seite führt das in
> [Schritt 3](#3--den-release-workflow-einrichten) aus.

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

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
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

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned c3f342469d186ef48458992930bf1b7c583c78d4 (plugin-release/v1)
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

**Prüfe die ausgegebene SHA, bevor du weitermachst.** Sie muss der
Commit sein, auf den `plugin-release/v1` heute zeigt, und nur das Remote
kann sagen, welcher das ist: `git ls-remote
https://github.com/mihailinl/AstraPlugins.git refs/tags/plugin-release/v1
'refs/tags/plugin-release/v1^{}'` — beide Refspecs, und die gepeelte
`^{}`-Zeile gewinnt, wenn das Remote eine sendet; genau dieses Paar fragt
`init-ci` selbst ab. Weicht dein Pinning ab, führe die
`cargo install`-Zeile auf [Die CLI installieren](install-cli.md) erneut
aus, dann `astra-plugin init-ci` erneut — es schreibt das Pinning neu und
behält deine Inputs. Nichts wird an Ort und Stelle repariert, eine
bestehende `release.yml` behält die veraltete SHA also, bis du sie erneut
ausführst. Der Rest ist Geschichte, und sie ist datiert:
`plugin-release/v1` war von 2026-08-11 bis 2026-08-19 ein annotiertes Tag,
eine CLI älter als Commit `5b8ab22` pinnte dessen Tag-Objekt
`dc1a044876926e9cf1170f034e2eab533ec07641`, wo GitHub einen Commit
braucht, und das ist der Bug, der das erste Release eines echten Autors
mit `invalid value workflow reference` kaputtmachte, bevor irgendein Job
startete; das Tag ist heute leichtgewichtig, also meldet kein Build diese
SHA mehr.

Detail, einschließlich was die generierte Datei enthält und warum jede
ihrer drei Permissions erforderlich ist:
[Mit CI veröffentlichen](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  REGISTRY WARN: B_UNBOUND predicted once this listing needs a binding: there is no .well-known/astra-plugin-owner at the repository root (working tree). From the registry's cutover every first listing needs one, and every listing after the binding deadline; a release without it is refused B_UNBOUND. Mint a token in the panel and run `astra-plugin init-ci --binding <token>` — https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository
  NOT CHECKED: B_BINDING_UNUSABLE, B_OWNER_CHANGED, B_REPOSITORY_RECYCLED, E_WORKFLOW_NOT_ALLOWED — only the registry can answer these, from the plugins service, GitHub and trust.json
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` wendet an, was mechanisch behoben werden kann. `--resolve-pin`
fragt GitHub, ob dein Workflow-Pinning noch das aktuelle ist; standardmäßig
aus, damit weder `dev` noch CI das Netzwerk brauchen, um eine Prüfung
auszuführen.

## 4 · Öffentlich pushen — mit der Owner-Datei

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin init-ci --binding <token>
git add .well-known && git commit -m "Bind this repository to my Minice account" && git push
astra-plugin check --strict
```

An den ersten drei Zeilen ist nichts Besonderes — es ist ein gewöhnliches
Repository. Aber beachte, was es *nicht* ist: Das zu pushen veröffentlicht das
Plugin nicht, und genau hier aufzuhören ist, wo die zwei echten Einreichungen,
die diese Seite ausgelöst haben, schiefgingen. Was es zu einem veröffentlichten
Plugin macht, ist der Tag im nächsten Schritt.

**Die Binding-Zeile ist der Besitznachweis, und sie ist nicht optional.**
Zwischen dem Push und `init-ci` meldest du dich unter
https://astra.minice.ai/plugins mit dem Minice-Konto an, das veröffentlichen
wird, und erzeugst ein Binding-Token für `you/dice-roller` — das Panel schlägt
das Repository auf GitHub nach, deshalb muss es vorher gepusht sein.
`init-ci --binding` schreibt das Token als erste Zeile von
`.well-known/astra-plugin-owner` in die Wurzel deines Repositorys; auf deinem
Default-Branch committet, ist es das, woran die Registry erkennt, welches Konto
für dieses Repository spricht — die eine Sache, die die Build-Bezeugung nicht
sagen kann. Lässt du sie weg, wird deine erste Einreichung mit `B_UNBOUND`
abgelehnt.

Sobald du im nächsten Schritt getaggt hast, liest `astra-plugin check --tag
v0.1.0` die Zeile aus dem Commit des Tags zurück, so wie die Registry es tun
wird. Das Token ist öffentlich und authentifiziert kein Release, merge also nie
eine Binding-Zeile, die du nicht selbst erzeugt hast. Was es festhält, wie lange
es gilt und was ein Umbenennen damit macht, steht in
[Gelistet werden — Das Repository binden](5-publish/get-listed.md#das-repository-binden).

## 5 · Taggen — das ist das Release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
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
[Mit CI veröffentlichen §3](5-publish/release-with-ci.md#3--was-ci-tut)
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

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
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

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

Von dieser Liste ist das Binding-Urteil das eine, das deine eigene Arbeit
entscheidet, und du hast es in
[Schritt 4](#4--öffentlich-pushen--mit-der-owner-datei) erledigt. Der Rest
folgt daraus, dass du ein Release getaggt hast, das der Workflow gebaut
hat.

## 8 · Einreichen, ein einziges Mal, für immer

**Bevor du das ausführst**, lies die Binding-Zeile aus deinem Tag zurück, genau
so, wie die Registry es tun wird. Sie ist die eine Prüfung auf dieser Seite, an
der du scheitern kannst, obwohl du alles andere richtig gemacht hast:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
astra-plugin publish
```

`publish` öffnet die **Einreichungsseite** des Panels in deinem Browser, mit
Repository und Tag schon ausgefüllt. Es lädt nichts hoch und hält keine
Zugangsdaten — es gibt kein `astra-plugin login`, kein Token in deiner
Shell-Historie, keinen Schlüsselbund, mit dem integriert werden müsste. Die
Seite reicht nichts ein, bis du es tust, angemeldet bei dem Minice-Konto, an das
dein Repository gebunden ist. `--print-url` gibt den Link aus, statt einen
Browser zu öffnen:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

Die Einreichung trägt **zwei Fakten**: dein Quell-Repository
(`you/dice-roller`) und den Release-Tag (`v0.1.0`). Alles andere wird aus dem
bezeugten Bundle gelesen, weil alles im Bundle von der Bezeugung gedeckt ist
und damit strikt mehr wert ist als alles, was in ein Formular getippt wird.

## 9 · Was als Nächstes passiert

Details, einschließlich jedes Codes: [Gelistet werden §Was nach der
Einreichung passiert](5-publish/get-listed.md#3--was-nach-der-einreichung-passiert).
Die Kurzfassung: Das Panel zeigt den Zustand der Einreichung, und dieselben
Momente erreichen dich als Benachrichtigungen — an der verifizierten
E-Mail-Adresse deines Minice-Kontos und im Panel, und über Telegram nur, wenn du
es verknüpft hast.

| Ergebnis | Bedeutet | Wer beteiligt ist |
|---|---|---|
| **Veröffentlicht** | Committet, dann im signierten Katalog | niemand |
| **Verzögert** | Alles hat bestanden; es veröffentlicht sich selbst zu der Zeit, die das Panel zeigt | niemand |
| **Angehalten** | Eine Entscheidung, die die Registry nicht automatisch treffen darf | ein Moderator, im Panel |
| **Abgelehnt** | Eine Prüfung ist gescheitert | du: beheb es, dann Recheck im Panel oder erneut taggen, wie der Code sagt |

**Ein erstes Listing wird immer für eine Person angehalten** — eines von genau
drei Ereignissen, die eine brauchen, neben einer neu angeforderten
High-Risk-Berechtigung und einem Wechsel des Repositorys oder der Bindung. Ein
Moderator gibt es im Panel frei oder lehnt es ab; du tust nichts, während du
wartest. Keine Freigabe verkürzt eine Verzögerung, und die `docs/POLICY.md` der
Registry veröffentlicht die Regeln.

## 10 · Jedes Release danach

Nichts. Tagge, und CI erledigt den Rest; die Registry erkennt den neuen Tag
eines gelisteten Plugins von selbst, und das Panel zeigt seinen Zustand.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

Es gibt nichts einzureichen und nichts anzupingen. Ein Release, das nicht
erschienen ist, steht auf der Seite deines Plugins im Panel, mit seinem Zustand
und dem Grund.

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
Registry, die auch die Reusable-Workflow-SHAs ausgibt, die der Bot
in einer Attestation akzeptiert — zwei davon, seit das Tag am 2026-08-19
verschoben wurde: der Commit, auf den `plugin-release/v1` zeigt, und der,
auf den es vorher zeigte. Seit 2026-09-20 ist der Katalog, den Clients
bekommen, mit diesem Schlüssel signiert; die auf `main` der Registry
committeten Kopien, `registry/v1/index.json` und `revocations.json`, tragen
`"signatures": []` mit Absicht, und kein Client liest sie. **Der noch
fehlende Link ist eine signierte Widerrufsliste auf Pages**, Widerruf wird
also noch nicht durchgesetzt.
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
