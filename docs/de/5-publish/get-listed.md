> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/5-publish/get-listed.md) maßgeblich.

# Gelistet werden

**Ein Plugin wird ein einziges Mal gelistet, für immer.** Danach laufen
Releases ohne weiteres Zutun: taggen, CI bauen und bezeugen lassen, und
die Registry nimmt es auf.

Voraussetzung: [ein von CI gebautes Release](release-with-ci.md), auf
einem **öffentlichen** Repository, mit angehängten und bezeugten
`.astraplugin`-Assets. Diese Voraussetzung wird durch das Taggen erfüllt —
der wiederverwendbare Workflow liegt auf dem Default-Branch von
`mihailinl/AstraPlugins` und ist als `plugin-release/v1` veröffentlicht,
sodass ein Tag-Push baut und bezeugt. Alles auf dieser Seite setzt voraus,
dass du das getan hast; falls nicht, mach zuerst
[Mit CI veröffentlichen](release-with-ci.md), oder lies
[Ein Plugin veröffentlichen](../publishing.md), den ganzen Weg auf einer
Seite.

**Was das nicht ersetzt**, weil jedes davon schon versucht wurde: ein
Repository, das deinen Quellcode enthält, ein an jemanden geschicktes
`.zip`, ein auf deinem Laptop gebautes Bundle, oder ein Issue, das einen
Maintainer bittet, es zu bauen. Die Registry listet Release-Assets, die CI
bezeugt hat, und nichts sonst.

Jeder Befehl unten ist `astra-plugin`. Falls du sie nicht hast,
[installiere zuerst die CLI](../install-cli.md).

## 1 · Preflight

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Es führt jede Prüfung aus, die die Registry ausführt und die lokal
laufen kann, und dann — die Hälfte, die zählt — **benennt es die, die nur
die Registry ausführen kann**, sodass du weißt, was noch unbewiesen ist:

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
```

### Wie dein Listing aussehen wird

Zwei Dateien entscheiden das, und beide hast du bereits neben
`plugin.toml`. Keine wird irgendwo im Manifest benannt — der Packer greift
sie anhand ihres Namens auf, und die Registry liest sie aus dem Bundle,
das sie gerade verifiziert hat, zurück aus. Du tippst nie eine URL, und
niemand kann eine für dich eintippen.

**Das Icon** — das Bild auf der Karte deines Plugins. Eines von:

<!-- doctest: illustrative reason="the accepted filenames, not a command; spec/icon-formats.yaml is the list both the packer and the registry read" -->
```
icon.png    icon.webp    icon.svg    icon.jpg    icon.ico
```

`astra-plugin new` scaffoldet ein Platzhalter-`icon.svg`, damit es etwas
zum Ersetzen gibt. Zeichne es quadratisch; es wird bei etwa 64 Pixeln
angezeigt, will also eine kräftige Silhouette statt feiner Details, und
sollte sowohl auf hellem als auch dunklem Hintergrund lesbar sein, weil
der Store dem Theme des Nutzers folgt. PNG mit transparentem Hintergrund
ist die übliche Antwort.

Wenn du ein SVG ausliefertst, halte es statisch: kein `<script>`, keine
`on*`-Handler, kein `<foreignObject>`, und keine Referenz auf irgendetwas
außerhalb deiner Maschine. Ein Icon, das eines davon trägt, wird
verworfen, und dein Plugin listet ohne Bild. Das lässt dein Release nicht
scheitern — eine dekorative Datei ist kein Gate fürs Ausliefern von
Software — aber du bekommst eine entsprechende Warnung, und niemand sieht
dein Icon.

**`README.md`** — die Seite deines Plugins, gezeigt, wenn jemand auf die
Karte klickt. Das ist, was eine Person liest, während sie entscheidet, ob
sie dich installiert, was es wertvoller macht als die einzeilige
Zusammenfassung.

Es wird als GitHub-flavored Markdown gerendert, Tabellen eingeschlossen.
Screenshots funktionieren, und ein Absatz, der nur aus Bildern besteht,
wird zu einer Galeriezeile:

<!-- doctest: illustrative reason="markdown an author writes in their own README; there is nothing here for a runner to execute" -->
```markdown
![The command editor, mid-roll](docs/editor.png)
![The trigger firing on a natural 20](docs/trigger.png)
```

Drei Regeln, alle davon wendet die Registry an, wenn sie dein Listing
ableitet:

- **Verlinke Bilder mit einem relativen Pfad** und committe sie in dein
  Repository. Sie werden so umgeschrieben, dass sie auf genau den Commit
  zeigen, aus dem dein Release gebaut wurde, sodass sich ein Bild nicht
  ändern kann, nachdem jemand das Listing genehmigt hat.
- **Bilder, die irgendwo außer bei GitHub gehostet sind, werden
  verworfen** und durch ihren Alt-Text ersetzt. Build-Badges
  eingeschlossen. Das ist eine Datenschutzregel und keine
  Sicherheitsregel: jedes entfernte Bild in einer gerenderten README ist
  eine Anfrage von der Maschine eines Nutzers, gestellt bevor er
  irgendetwas installiert hat.
- **Rohes HTML wird entfernt.** Verwende Markdown fürs Layout.

Lange READMEs werden bei 16 KB an einer Zeilengrenze abgeschnitten, mit
einem Link zum Rest auf GitHub.

## 2 · Einreichen

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

Es öffnet ein vorausgefülltes Issue in der Registry in deinem Browser. **Es
lädt nichts hoch und hält keine Zugangsdaten** — es gibt kein
`astra-plugin login`, kein Token in deiner Shell-Historie, keinen
Schlüsselbund, mit dem integriert werden müsste. `--print-url` gibt
stattdessen den Link aus:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **`template=plugin-listing.yml` in dieser URL ist tragend.** Die Vorlage
> deklariert `labels: ["listing", "needs-triage"]`, und der Bot der Registry
> betritt den Einreichungspfad nur für ein Issue, das `listing` trägt.
> Sonst vergibt dieses Label niemand — auch der Bot nicht, mit Absicht:
> dort ist es ein Autoritätstoken und keine Kategorie, und ein Bot, der es
> auf alles Formularförmige stempelt, würde die Ausnahme jedem in die Hand
> geben, der ein Formular kopieren kann.
>
> Zwei echte Listing-Anfragen gingen genau so verloren: sie kamen ohne
> Labels an, die Triage gab `mode: "none"` zurück, die Check-, Publish- und
> Kommentar-Schritte wurden alle übersprungen, und die Autoren bekamen
> **gar keine Antwort, nicht einmal eine Ablehnung**. Das ist jetzt auf
> beiden Seiten behoben. Leere Issues sind in der Registry abgeschaltet,
> die *New issue*-Seite bietet also nur Formulare an; und eine Anfrage, die
> dennoch ohne Label ankommt, bekommt einen Kommentar, der genau sagt, was
> fehlt, plus den einen Klick — ein Maintainer setzt `listing` —, der die
> Verifikation auf genau diesem Issue startet, ohne dass etwas neu getippt
> wird. Über diesen Link zu öffnen überspringt das alles.

Die Einreichung trägt **zwei Fakten**:

| Feld | Warum es eingetippt statt gelesen wird |
|---|---|
| Quell-Repository (`you/dice-roller`) | Das Bundle kann nicht dafür bürgen, von wo es ausgeliefert wird |
| Release-Tag (`v0.2.0`) | Dasselbe |

Plus zwei Bestätigungen: dass du das Repository besitzt oder pflegst, und
dass du die Policy gelesen hast.

**Alles andere wird aus dem bezeugten Bundle gelesen** — die ID, die
Version, der Anzeigename, die Zusammenfassung, die Lizenz, die
Capabilities, die Permissions, die Plattformen, die Digests, die Größen.
Das ist keine Bequemlichkeit: Alles im Bundle wird von der Attestation
abgedeckt, was es strikt vertrauenswürdiger macht als alles in ein
Formular Eingetippte. Es löscht auch eine ganze Klasse von Ablehnungen,
weil es kein Formular gibt, mit dem `plugin.toml` uneins sein könnte.

## 3 · Was nach der Einreichung passiert

Dieser Abschnitt ist der, den zwei echte Autoren brauchten und nicht
hatten. Er beschreibt den Ablauf der Registry, so wie
`astra-registry/docs/POLICY.md` und `docs/BOT-CHECKS.md` ihn definieren;
beide sind aus dem eigenen Code des Bots generiert oder dagegen geprüft
(`bot/lib/policy.mjs`, `bot/lib/codes.mjs`), sodass die Zahlen hier nicht
still vom Code abweichen können, der sie pflegt.

### Die Abfolge

1. **Dein Issue bekommt die Labels `listing` und `needs-triage`** — aus
   der Issue-Vorlage, automatisch. Das ist der Schritt, der entscheidet,
   ob überhaupt etwas passiert; siehe die Warnung in §2.
2. **Der Bot triagiert es**, liest deine zwei Fakten, holt das Release
   unauthentifiziert von GitHub und führt jede Prüfung aus
   `docs/BOT-CHECKS.md` gegen die Bytes aus: die Attestation und welcher
   Workflow sie erzeugt hat, dass die Asset-URLs unter dem eigenen
   Release-Namensraum deines Repositorys liegen, dass du admin oder
   maintain auf dem Repository hast, die Struktur des Archivs, das
   Manifest, die Lizenz, die Versionsordnung, und den
   deklariert-versus-aufgerufen-Host-RPC-Scan.
3. **Der Bot kommentiert dein Issue** mit dem Ergebnis, dem Grund, und —
   wenn es einen gibt — dem genauen Veröffentlichungszeitpunkt. Du wirst
   so oder so informiert.

Wenn nach einer Stunde nichts kommentiert hat, prüfe die Labels des
Issues. Kein `listing`-Label bedeutet, Schritt 1 ist nicht passiert und
nichts Nachgelagertes lief.

### Die vier Ergebnisse

| Ergebnis | Bedeutet | Wer ist beteiligt |
|---|---|---|
| **Published** | Committed, und im Katalog beim nächsten Index-Build | niemand |
| **Delayed** | Alles bestanden; veröffentlicht sich selbst zu einem genannten Zeitpunkt | niemand |
| **Held** | Eine Entscheidung, die die Registry nicht automatisch treffen darf | ein Maintainer, innerhalb von 48 h |
| **Refused** | Eine Prüfung ist gescheitert. Die Policy hatte kein Mitspracherecht | du: beheben und `/recheck` kommentieren |

Ein Release veröffentlicht sich selbst ohne Mensch, wenn alle diese
gelten: es kommt aus dem für dieses Plugin bereits gelisteten Repository,
jede Bot-Prüfung ist grün, die Version ist strikt neuer, es fragt nach
keiner hochriskanten Permission, die es nicht schon hatte, und es fragt
überhaupt nach keiner neuen Permission oder Capability. Lässt nur das
Letzte weg, veröffentlicht es sich immer noch selbst, nach einer
Verzögerung.

**Ein erstes Listing ist nie eines davon.** Es wird per Definition für
eine Person zurückgehalten — siehe unten — die Antwort auf „wie lange bis
mein erstes Plugin gelistet ist" lautet also *bis zu 48 Stunden, nachdem
der Bot kommentiert*, nicht *Minuten*.

### Wie ein Hold aufgelöst wird

Von dir wird nichts verlangt. Ein Maintainer kommentiert **`/approve`**
auf deinem Issue, und der gesamte Ingest läuft dann von Grund auf erneut
gegen die Bytes, so wie sie in diesem Moment sind — eine Genehmigung ist
ein Markierung „eine Person hat zu diesem Zeitpunkt Ja gesagt" und trägt
kein gecachtes Urteil, das Genehmigen überspringt also keine einzige
Prüfung. **`/reject <reason>`** ist die andere Hälfte, und sie muss einen
Grund tragen, der dir mitgeteilt wird. Beide Befehle werden gegen das
Registry-Repository permission-geprüft: Der Kommentierende braucht dort
`admin` oder `maintain`, erneut über die API von GitHub nachgewiesen in
dem Moment, in dem der Befehl gelesen wird, statt aus der Event-Nutzlast
vertraut, und ein Befehl von irgendjemand anderem wird beantwortet statt
ignoriert.

Du tippst keinen der beiden Befehle, und du musst während des Wartens
nichts tun. Sie sind hier nur dokumentiert, damit „für einen Maintainer
zurückgehalten" einen Mechanismus benennt statt ein Schweigen.

*Ein Vorbehalt, genannt, weil die Regel dieser Seite ist, sie zu nennen:*
dieser Maintainer-Befehlspfad landet zur gleichen Zeit in der Registry wie
diese Seite. Wenn dein Hold davor liegt, ist das Ergebnis dasselbe und der
SLA derselbe — ein Maintainer entscheidet immer noch — aber die
Entscheidung wird möglicherweise von Hand statt per Befehl aufgezeichnet.

### Wie eine Ablehnung aussieht

Der Bot kommentiert mit einem festen Code und was dagegen zu tun ist. Eine
Ablehnung ist kein Urteil über dein Plugin; sie ist eine benannte,
behebbare Bedingung. Die, auf die Autoren am häufigsten stoßen:

| Code | Was es bedeutet | Fix |
|---|---|---|
| `E_ATTESTATION_MISSING` | Das Bundle hat keine Build-Attestation | Du hast ein selbst gebautes Bundle hochgeladen. Lass CI es bauen: [Mit CI veröffentlichen](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | Das Release trägt kein `.astraplugin`-Asset | Der Workflow lief nicht, oder lief und schlug fehl. Prüfe den Actions-Tab deines Repositorys |
| `E_RELEASE_NOT_FOUND` | Dieses Repository hat kein Release mit diesem Tag | Ein Entwurfs-Release ist für alle außer dir unsichtbar, und ein privates Repository sieht identisch aus wie ein fehlendes |
| `E_WORKFLOW_NOT_ALLOWED` | Der Build lief über einen Workflow, den diese Registry nicht erlaubt | Pinne den Astra-Reusable-Workflow per Commit-SHA. `astra-plugin init-ci` erledigt das für dich |
| `E_ASSET_URL_FOREIGN` | Eine Asset-URL liegt nicht unter den eigenen Releases deines Repositorys | Jede Download-URL muss unter `https://github.com/<owner>/<repo>/releases/download/<tag>/` liegen |
| `E_OWNERSHIP_UNPROVEN` | Du bist kein Admin oder Maintainer dieses Repositorys | Lass jemanden, der es ist, das Issue öffnen, oder committe `.well-known/astra-plugin-owner` auf dem Default-Branch mit deinem GitHub-Login und kommentiere `/recheck` |
| `E_INPUT_REPO` / `E_INPUT_TAG` | Das Repository oder Tag hat nicht die erwartete Form | `you/dice-roller`, keine URL; `v0.2.0`, keine Commit-SHA oder ein Branch |

Nachdem du es behoben hast, kommentiere **`/recheck`** auf demselben
Issue. Jede Prüfung läuft von Grund auf erneut gegen die Bytes, so wie sie
in diesem Moment sind; nichts wird fortgesetzt und nichts Wartendes wird
vertraut. Die vollständige Liste, mit dem genauen Wortlaut jedes
Fehlschlags, steht in `docs/BOT-CHECKS.md` in der Registry.

Die eigenen Exit-Codes des Bots sind `0` listed · `1` refused · `3` held
for a maintainer · `2` bot itself failed. Der letzte ist absichtlich
verschieden: „dein Plugin ist schlecht" und „unser Tooling ist schlecht"
dürfen einem Fremden nie als derselbe Kommentar erscheinen.

### Die drei Dinge, die eine Person brauchen

Genau drei, und die Liste wächst nicht ohne eine Änderung an der
veröffentlichten Policy der Registry:

| Ereignis | Warum |
|---|---|
| **Das erste Listing eines Plugins** | Ein einziges Mal, für immer. Noch ist nichts gepinnt, also kann später nichts dagegen geprüft werden |
| **Eine neu angefragte hochriskante Permission** | Der Nutzer wird gebeten, ihr zuzustimmen; jemand sollte zuvor gelesen haben, wofür sie ist |
| **Das Repository oder die Identität hat sich geändert** | Jede installierte Kopie trägt ein Pinning auf das alte Repository. Eine Repository-Änderung ist eine Autorenänderung, bis jemand etwas anderes sagt |

Hochriskant heißt hier vier Namen: `client`, `dom_access`,
`send_chat_message`, `set_theme_contribution` — gleichermaßen erkannt in
`[capabilities]` und `[permissions]`, weil der Abschnitt, in dem du sie
deklarierst, nicht der Punkt ist. `push_to_ui` bekommt eine
Zustimmungs-Checkbox, aber keine Prüfung: es zeichnet in ein Panel, das
dein Plugin bereits besitzt.

Eine Prüfung kann eine Entscheidung separat an eine Person übergeben — ein
Name eine Bearbeitung von einem gelisteten Plugin entfernt, ein
Anzeigename, der mit einem kollidiert. Das kommt als `R_CHECK_HELD` an,
ist keines der drei, und trägt denselben SLA.

**Der SLA beträgt 48 Stunden** für diese, ab dem Moment, in dem der Bot
kommentiert. Es gibt einen Maintainer, was genau der Grund ist, warum die
Liste drei Einträge lang ist. Die Registry veröffentlicht, was passiert,
wenn das verrutscht, statt nur das Versprechen: nach 96 Stunden muss der
Maintainer entweder die Warteschlange veröffentlichen oder das auslösende
Ereignis aus der blockierenden Menge nehmen, in einem geprüften Commit,
der auch den Absatz bearbeitet, der das Versprechen macht.

### Wenn ein Release stattdessen wartet

Manche Releases bestehen alles und veröffentlichen sich trotzdem nicht
sofort:

| Situation | Code | Verzögerung |
|---|---|---|
| Das Plugin hält **irgendeine** hochriskante Permission, egal ob dieses Release sie geändert hat | `P_DELAY_HIGH_RISK` | 24 h |
| Das Release fragt nach einer Permission oder Capability, die das vorherige nicht hatte, innerhalb der nicht-hochriskanten Menge | `P_DELAY_WIDENED` | 24 h |
| Eines der beiden oben, von einem Autor mit **5 sauberen** Releases in dieser Registry | `P_TRUSTED_AUTHOR` | 6 h |

Der Bot nennt den genauen Veröffentlichungszeitpunkt, und wenn die Uhr
abläuft, läuft der gesamte Ingest von Grund auf erneut gegen die Bytes, so
wie sie dann sind. Die Verzögerung kauft eine Sache, und die Registry
behauptet nicht mehr: ein Fenster, in dem ein Autor, dessen
GitHub-Konto übernommen wurde, ein Release sehen kann, das er nicht selbst
gemacht hat, und das sagen kann.

## 4 · Jedes Release danach

Nichts. Taggen, und CI erledigt den Rest; die Registry bemerkt das Release
und generiert den Index neu.

Falls sie es nicht bemerkt hat:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Das ist der manuelle Ping für ein Plugin, das **bereits gelistet** ist.
Ohne ihn öffnet `publish` eine Erst-Listing-Anfrage.

## Was ein Listing nicht bedeutet

Ein Listing ist keine Sicherheitsprüfung. Niemand liest deinen Code, und
die Registry sagt das in ihrer eigenen Policy: eine Permission entscheidet,
was der Daemon *für* ein Plugin tut, und nichts darüber, was der Prozess
des Plugins mit der Maschine anstellen darf. Es gibt keine Sandbox. Siehe
[das Sicherheitsmodell](../1-orientation/security.md).

## Der heutige Stand

Eine Sache, die ein Leser verdient zu wissen, bevor er dieser Seite folgt.

**Die Signierkette ist bis zur Delegation verankert, aber noch nicht durch
den Katalog hindurch.** Genau genommen, und jeder Teil ist überprüfbar:

- die Root-Schlüssel existieren auf beiden Seiten — `registry/v1/root.json`
  trägt `"status": "provisioned"` mit zwei Ed25519-Schlüsseln, und
  `PRODUCTION_ROOT_KEYS` des Daemons kompiliert dieselben zwei ein;
- `registry/v1/trust.json` **ist jetzt signiert** von `astra-root-2026a`
  und delegiert an einen Index-Signierschlüssel, `astra-index-2026a`. Die
  eigene `node tools/sign-trust.mjs --verify registry/v1/trust.json` der
  Registry bestätigt das und gibt die eine
  Reusable-Workflow-SHA aus, die der Bot in einer Attestation akzeptiert,
  `e3329df252a46d747676cb540ae4b986af68a3ad` — der Commit, auf den
  `plugin-release/v1` zeigt. Also feuert `E_TRUST_UNPROVISIONED`, das
  früher jeden Ingest stoppte, nicht mehr;
- **der Katalog selbst ist weiterhin unsigniert.** `registry/v1/index.json`
  und `revocations.json` tragen `"signatures": []`, sodass ein
  Standard-Astra-Build keine Signatur zu prüfen hat, jeden Katalog als
  unsigniert einstuft und geschlossen ausfällt (fail closed). Die
  Durchsetzung von Widerrufen ist aus demselben Grund ebenfalls nicht
  aktiv.

Siehe [`spec/registry-index.md` §0.1](../spec/registry-index.md) und
[das Sicherheitsmodell](../1-orientation/security.md).

Was das für dich bedeutet: Der Einreichungspfad auf dieser Seite
funktioniert heute Ende-zu-Ende — dein Issue wird gelesen, die Prüfungen
laufen, der Bot antwortet, und ein Listing wird committed. Was noch
aussteht, ist die Signatur, die Astra erlaubt, aus dem zu *installieren*,
was die Registry veröffentlicht. Nichts auf dieser Seite ändert sich, wenn
sie ankommt.

## Siehe auch

- [`spec/registry-index.md`](../spec/registry-index.md) — der Index, Widerrufe, und der Verifikationsalgorithmus
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — was der Bot aus deinem Archiv liest
- [Versionierung](../versioning.md) — was die Zahlen bedeuten und wie lange eine Deprecation dauert
</content>
