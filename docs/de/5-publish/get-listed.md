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

Fast jeder Befehl unten ist `astra-plugin`; die Ausnahme ist
[Schritt 2](#2--beweisen-dass-du-das-repository-kontrollierst), eine einzige
Datei und ein `git commit` in deinem eigenen Repository. Falls du die CLI
nicht hast, [installiere sie zuerst](../install-cli.md) — es gibt jetzt
vorgebaute Binärdateien.

## 1 · Preflight

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Es führt jede Prüfung aus, die die Registry ausführt und die lokal
laufen kann, und dann — die Hälfte, die zählt — **benennt es die, die nur
die Registry ausführen kann**, sodass du weißt, was noch unbewiesen ist:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · for a request through the issue form, until the registry's cutover: that `.well-known/astra-plugin-owner` on your default branch names the account opening it
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**Eine davon kannst du im Voraus erledigen, und solltest du auch.** Die
Ownership-Zeile nennt die Datei, und sie zu committen ist
[Schritt 2](#2--beweisen-dass-du-das-repository-kontrollierst). Tu das,
bevor du einreichst, und die Prüfung besteht beim ersten Versuch; lässt du
es aus, ist die erste Antwort eine Ablehnung.

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

## 2 · Beweisen, dass du das Repository kontrollierst

**Tu das, bevor du das Issue öffnest.** Es ist eine Datei und ein Commit,
und es auszulassen ist der häufigste Weg, wie eine korrekte, ehrliche
erste Einreichung abgelehnt wird.

Die Registry muss eine Frage beantworten, die nichts anderes auf dieser
Seite beantwortet: **Kontrolliert die Person, die dieses Listing anfragt,
das Repository, das gelistet wird?** Die Attestation beweist bereits, dass
das Bundle aus diesem Repository stammt, und das Listing ist daran
gepinnt — aber keiner dieser beiden Fakten sagt, wer *du* bist. Ohne
diesen Schritt könnte ein Fremder das Plugin von jemand anderem listen und
zu der Identität werden, über die dessen Updates die Astra-Nutzer
erreichen.

Committe diese Datei auf den **Default-Branch** deines Repositorys:

<!-- doctest: illustrative reason="the path and content of a file the author writes in their own repository; there is nothing here for a runner to execute" -->
```
path      .well-known/astra-plugin-owner
content   your GitHub login, one per line
```

Der eine Befehl, der sie erstellt, ausgeführt an der Wurzel des
Repositorys deines Plugins:

<!-- doctest: illustrative reason="git commands against the author's own repository — the runner has no such repository, and `cli` blocks must contain an astra-plugin command" -->
```bash
mkdir -p .well-known
echo 'your-github-login' > .well-known/astra-plugin-owner
git add .well-known/astra-plugin-owner
git commit -m "Declare the Astra registry owner for this repository"
git push
```

**Was das beweist:** Jemand, der auf deinen Default-Branch schreiben kann,
bestätigt, dass dieser GitHub-Login für dieses Repository spricht — live
gelesen in dem Moment, in dem der Bot prüft, sodass das Entfernen eines
Logins diese Person daran hindert, eine neue Listing-Anfrage zu öffnen oder
ein `/recheck` zu bestehen. Es erreicht **nicht** ein bereits gelistetes
Plugin: [jedes Release danach](#5--jedes-release-danach) wird gegen das Konto
geprüft, das das Release veröffentlicht hat, und der Eintrag bleibt ohnehin an
dieses Repository gepinnt.
**Was das nicht beweist:** absolut nichts über deinen Code, den niemand
liest; es ist keine Signatur, und es ist keine Sicherheitsprüfung.

### Das Format, genau

Ein Login pro Zeile. Alles nach einem `#` ist ein Kommentar, ein
führendes `@` ist erlaubt, umgebende Leerzeichen werden getrimmt, und der
Abgleich ist groß-/kleinschreibungsunabhängig. Nur die ersten 4 KB werden
gelesen. Diese Datei ist also gültig und listet einen Besitzer:

<!-- doctest: illustrative reason="the contents of a file in the author's repository, not a command" -->
```
# owners of this repository
@Rel0d1x   # primary
```

Liste jede Person auf, die im Namen dieses Repositorys einreichen oder
erneut einreichen darf. Für ein einer Organisation gehörendes Repository
sind das gewöhnlich mehrere Namen.

### Prüfen, dass die Registry sie lesen kann

Der Bot liest die Datei über GitHubs Contents-API, unauthentifiziert, vom
Default-Branch. Du kannst genau die Anfrage stellen, die er stellt:

<!-- doctest: illustrative reason="gh against the author's own repository; `cli` blocks must contain an astra-plugin command, and this one is deliberately shell-only" -->
```bash
gh api repos/you/dice-roller/contents/.well-known/astra-plugin-owner \
  --header 'Accept: application/vnd.github.raw+json'
```

Sie sollte deinen Login zurückgeben. Gibt sie `Not Found (HTTP 404)` aus,
ist die Datei nicht dort, wo der Bot sucht — die üblichen Ursachen sind,
dass sie auf einem anderen Branch als dem Default-Branch liegt, dass sie
noch nicht committed oder gepusht ist, oder dass das Verzeichnis als
`well-known` ohne führenden Punkt geschrieben ist.

### Warum das ein Schritt ist und kein Fallback

Die Registry versucht drei Wege, um Kontrolle festzustellen, und diese
Datei ist der, der für einen gewöhnlichen Autor funktioniert. Das ist
keine Vorliebe, es ist strukturell, und beide anderen wurden dabei
beobachtet, bei echten Einreichungen zu scheitern:

| Weg | Warum er nicht für dich antwortet |
|---|---|
| **Collaborator-Permission** — GitHub fragen, wer `admin` oder `maintain` hat | GitHub beantwortet diesen Endpunkt nur für einen Aufrufer, der bereits Admin-Sichtbarkeit auf das Repository hat. Das Token der Registry gehört der Registry, für *dein* Repository bekommt sie also `403` — was „ich sage es dir nicht" bedeutet, nicht „nein", und als überhaupt keine Antwort behandelt wird |
| **Release-Autor** — das Konto, das das Release veröffentlicht hat | Der Release-Workflow aus [Mit CI veröffentlichen](release-with-ci.md) erstellt das GitHub-Release, dessen Autor also `github-actions[bot]` ist statt eine Person. Genau das Befolgen des dokumentierten Wegs entwertet diesen Weg |
| **`.well-known/astra-plugin-owner`** | Nichts muss für die Registry sichtbar sein, und nichts muss installiert werden. Er antwortet |

Ein `403` beim ersten Weg wird dir nicht angelastet und wird niemals für
sich allein zu einer Ablehnung. Die Ablehnung passiert nur, wenn alle drei
nichts liefern, und das ist genau das, was passiert, wenn diese Datei
nicht existiert.

## Das Repository binden

**Ein Listing wandert von einem GitHub-Login zu einem Minice-Konto.** Die
Owner-Datei oben nennt einen GitHub-Login, und so wird ein erstes Listing über
das Issue-Formular der Registry heute belegt. Ab dem Cutover der Registry braucht
jedes erste Listing stattdessen eine **Bindung**: eine weitere Zeile in derselben
Datei, von der CLI geschrieben aus einem Token, das du im Panel erzeugst,
angemeldet bei dem Minice-Konto, das veröffentlichen wird. Binden kostet jetzt
einen Befehl, und dorthin geht jedes Listing; ein bestehendes Listing hat bis
zur Binding-Frist Zeit (unten).

**1 · Ein Token erzeugen.** Melde dich unter https://astra.minice.ai/plugins mit
dem Minice-Konto an, dem das Listing gehören wird — es braucht `astraUser`, das
mit dem Besitz von Astra kommt — und erzeuge ein Binding-Token für dieses
Repository.

**2 · Die Zeile schreiben.** Irgendwo innerhalb des Repositorys:

<!-- doctest: cli -->
```bash
astra-plugin init-ci --binding <token>
```

Das schreibt `astra-binding: <token>` als **erste Zeile** von
`.well-known/astra-plugin-owner` in der Repository-Wurzel, entfernt jede
frühere Binding-Zeile in jeder Schreibweise, behält deine Login-Zeilen und
nutzt kein Netzwerk:

<!-- doctest: output from="astra-plugin init-ci --binding k3Vq9ZtW2xLr8NfBcY5pHd" unrun="rewrites .well-known/astra-plugin-owner in a git repository; re-run it at the root of your own" -->
```
  Rewrote: .well-known/astra-plugin-owner
    line 1   astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd
    kept     1 other line(s), byte for byte

  This token is public once you push it. It records one Minice account's consent
  to publish from this repository, and it authenticates no release: never merge a
  binding line you did not mint yourself. What that means, and what a rename or a
  transfer does to it:
    https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository

  Next: commit this file on your default branch, then tag. Before you push the tag,
    astra-plugin check --tag <tag>
  reads the line back from the tagged commit, as the registry will.
```

**3 · Auf deinem Default-Branch committen, dann taggen.** Bevor du den Tag
pushst, lies die Zeile genau so zurück, wie die Registry es tun wird — aus dem
Commit des Tags, nicht aus deinem Arbeitsverzeichnis:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
```

Eine fehlerhafte Zeile scheitert hier, mit `B_BINDING_MALFORMED`, solange die
Korrektur noch nichts kostet. Eine fehlende ist eine Warnung, die `B_UNBOUND`
vorhersagt. Vier Antworten, die nur die Registry geben kann, werden jedes Mal
als nicht geprüft genannt.

**4 · Im Panel einreichen.** Aus einem gebundenen Repository öffnet
`astra-plugin publish` die Einreichungsseite des Panels mit Repository und Tag
schon ausgefüllt, zum Beispiel
https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0 — die
Seite reicht nichts ein, bis du es tust, angemeldet.

**Was das Token ist, und was nicht.** Ein Binding-Token ist **öffentlich**: Es
steht in einer Datei in einem öffentlichen Repository. Es hält die **Zustimmung
eines Kontos** fest, aus diesem Repository zu veröffentlichen, und es
**authentifiziert kein Release** — ein Release, das nichts zurückhält, wird
veröffentlicht, bevor das Konto davon erfährt. Merge deshalb **nie eine
Binding-Zeile, die du nicht selbst erzeugt hast**: Ein Pull-Request, der eine
hinzufügt oder ändert, bittet dich, dein Listing dem Konto eines anderen zu
übergeben.

**Wo die Zeile stehen muss.** In der Wurzel des Repositorys, egal in welchem
Verzeichnis dein Plugin liegt; im Commit, auf den dein Release-Tag zeigt; und
innerhalb der ersten 4096 Bytes der Datei. Eine Zeile gilt für jedes Plugin im
Repository. Sie später vom Default-Branch zu löschen, beendet nichts, was schon
gebunden ist.

**Wie lange ein erzeugtes Token gilt.** Ein erzeugtes Token verfällt 30 Tage
nach seiner Erzeugung, es sei denn, eine laufende Einreichung nennt es oder
seine Zeile steht auf dem Default-Branch des Repositorys, wenn die Regel
angewendet wird — die Regel wird vor jeder Verfallsentscheidung neu geprüft.
Ein Autor, der viel später taggt, ohne die Zeile auf dem Default-Branch, erzeugt
also ein neues, und einer, dessen Zeile noch auf diesem Branch steht, wenn die
Regel angewendet wird, nicht. Eine Zeile, die committet und später entfernt
wurde, hält kein Token am Leben.

**Anmelden.** Die Registry liest die Berechtigung des Kontos aus seiner letzten
verifizierten Anmeldung, und die zählt 12 Stunden. Ein Release eines gebundenen
Repositorys wartet, solange sich das Konto in dieser Zeit nicht angemeldet hat;
das Panel sagt es, und eine `notice.sign_in`-Benachrichtigung bittet dich, dich
anzumelden. Nichts wird veröffentlicht, bis du es tust.

**Wohin Benachrichtigungen gehen.** An die verifizierte E-Mail-Adresse des
Minice-Kontos und ins Panel. Telegram ist ein optionaler zusätzlicher Kanal, den
du verknüpfen kannst; nichts verlangt ihn.

**Ein Umbenennen oder eine Übertragung lässt installierte Kopien stranden.**
Astra erkennt ein installiertes Plugin an seinem Repository,
`github:owner/name`. Benenne das Repository um oder übertrage es an einen
anderen Besitzer, und jede installierte Kopie bekommt keine Updates mehr, bis
sie unter dem neuen Namen neu installiert wird. Nichts setzt das außer Kraft.

**Für ein Plugin, das schon gelistet ist.** Ein ungebundenes Listing ist
`grandfathered`: Es veröffentlicht weiter wie heute, bis zum späteren von
Binding-Frist und Cutover der Registry. Die Frist wird festgelegt, bevor
Bindungen durch Dritte öffnen, und von der Registry veröffentlicht. Danach ist
ein ungebundenes Listing `frozen`: Installierte Kopien funktionieren weiter und
es bleibt installierbar, aber kein neues Release davon wird veröffentlicht, bis
eines mit Binding-Zeile veröffentlicht ist — ein gebundenes Release taut es auf,
ohne Strafe. Das erste Release mit Binding-Zeile wird einmal angehalten, bis ein
Moderator es genehmigt, `R_FIRST_BINDING`. Und ab dem Cutover wartet ein
Release eines `grandfathered`-Listings, das angehalten und genehmigt wurde, bis
das Listing gebunden ist.

**Vorabprüfung.** `astra-plugin check` lehnt eine ID ab, die die Registry
ablehnt — eine reservierte ID oder eine außerhalb des ID-Musters der Registry —,
und eine fehlerhafte Binding-Zeile. `astra-plugin dev` und `astra-plugin build`
lehnen keines von beiden ab: Die Regeln der Registry entscheiden, was gelistet
wird, nie, was du ausführen darfst.

## 3 · Einreichen

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

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

Diese Aufnahme stammt aus einem Verzeichnis ohne eigenen Git-Tag. Führst du den
Befehl in deinem Checkout aus, bevor der Tag geholt wurde, erscheint über dem
Absatz eine zusätzliche Zeile — `Note: this checkout has no tag v0.1.0.` Das ist
ein Hinweis, kein Fehler: die Registry liest das Release von GitHub, es zählt
also, dass der Tag gepusht ist und CI die Assets angehängt hat.

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
| Release-Tag (`v0.1.0`) | Dasselbe |

Plus drei Bestätigungen, alle verpflichtend: dass du
`.well-known/astra-plugin-owner` mit deinem Login auf den Default-Branch
committet hast, dass du das Repository besitzt oder pflegst, und dass du die
Policy gelesen hast.

**Alles andere wird aus dem bezeugten Bundle gelesen** — die ID, die
Version, der Anzeigename, die Zusammenfassung, die Lizenz, die
Capabilities, die Permissions, die Plattformen, die Digests, die Größen.
Das ist keine Bequemlichkeit: Alles im Bundle wird von der Attestation
abgedeckt, was es strikt vertrauenswürdiger macht als alles in ein
Formular Eingetippte. Es löscht auch eine ganze Klasse von Ablehnungen,
weil es kein Formular gibt, mit dem `plugin.toml` uneins sein könnte.

## 4 · Was nach der Einreichung passiert

Dieser Abschnitt ist der, den zwei echte Autoren brauchten und nicht
hatten. Er beschreibt den Ablauf der Registry, so wie
`astra-registry/docs/POLICY.md` und `docs/BOT-CHECKS.md` ihn definieren;
beide sind aus dem eigenen Code des Bots generiert oder dagegen geprüft
(`bot/lib/policy.mjs`, `bot/lib/codes.mjs`), sodass die Zahlen hier nicht
still vom Code abweichen können, der sie pflegt.

**Zwei Wege, und sie warten auf Verschiedenes.** Alles unten, bis
[Auf dem Panel-Weg, ab dem Cutover](#auf-dem-panel-weg-ab-dem-cutover), beschreibt eine Anfrage über das
Issue-Formular der Registry, und so entsteht ein erstes Listing heute. Ab dem
Cutover der Registry erreicht ein Release die Registry stattdessen über das
Astra-Plugins-Panel, und **ein Release, das jede automatische Prüfung besteht,
wird sofort veröffentlicht**, markiert als nicht von Astra-Moderatoren geprüft.
Dort wartet nur ein Besitzerwechsel bei einem schon bestehenden Listing auf
einen Moderator.

### Die Abfolge

1. **Dein Issue bekommt die Labels `listing` und `needs-triage`** — aus
   der Issue-Vorlage, automatisch. Das ist der Schritt, der entscheidet,
   ob überhaupt etwas passiert; siehe die Warnung in §3.
2. **Der Bot triagiert es**, liest deine zwei Fakten, holt das Release
   unauthentifiziert von GitHub und führt jede Prüfung aus
   `docs/BOT-CHECKS.md` gegen die Bytes aus: die Attestation und welcher
   Workflow sie erzeugt hat, dass die Asset-URLs unter dem eigenen
   Release-Namensraum deines Repositorys liegen, dass du das Repository
   kontrollierst ([Schritt 2](#2--beweisen-dass-du-das-repository-kontrollierst)),
   die Struktur des Archivs, das Manifest, die Lizenz, die
   Versionsordnung, und den deklariert-versus-aufgerufen-Host-RPC-Scan.
3. **Der Bot kommentiert dein Issue** mit dem Ergebnis, dem Grund, und —
   wenn es einen gibt — dem genauen Veröffentlichungszeitpunkt. Du wirst
   so oder so informiert.

Wenn nach einer Stunde nichts kommentiert hat, prüfe die Labels des
Issues. Kein `listing`-Label bedeutet, Schritt 1 ist nicht passiert und
nichts Nachgelagertes lief.

### Die vier Ergebnisse

Im Issue-Formular:

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

**Im Issue-Formular ist ein erstes Listing nie eines davon.** Es wird per
Definition für eine Person zurückgehalten — siehe unten — die Antwort auf
„wie lange bis mein erstes Plugin gelistet ist" lautet dort also *bis zu 48
Stunden, nachdem der Bot kommentiert*, nicht *Minuten*. Auf dem Panel-Weg, ab
dem Cutover, sind es Minuten: siehe [unten](#auf-dem-panel-weg-ab-dem-cutover).

### Wie ein Hold aufgelöst wird

Von dir wird nichts verlangt. Im Issue-Formular kommentiert ein Maintainer
**`/approve`** auf deinem Issue, und der gesamte Ingest läuft dann von Grund
auf erneut gegen die Bytes, so wie sie in diesem Moment sind — eine Genehmigung ist
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
| `E_OWNERSHIP_UNPROVEN` | Nichts hat bewiesen, dass du dieses Repository kontrollierst | Du hast fast sicher [Schritt 2](#2--beweisen-dass-du-das-repository-kontrollierst) ausgelassen. Committe `.well-known/astra-plugin-owner` auf dem Default-Branch mit deinem GitHub-Login darin, kommentiere dann `/recheck` — kein neues Release und kein neues Tag nötig |
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

### Was im Issue-Formular eine Person braucht

Drei Ereignisse, und die Liste wächst nicht ohne eine Änderung an der
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

Im Issue-Formular bestehen manche Releases alles und veröffentlichen sich
trotzdem nicht sofort:

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

### Auf dem Panel-Weg, ab dem Cutover

*Geändert am 2026-09-26 (Registry-Vertrag 3.0.0).* Vor diesem Datum stand auf
dieser Seite, dass ein erstes Listing immer für eine Person zurückgehalten
wird. Im Issue-Formular gilt das weiter, bis der Cutover das Formular
abschafft. Die Regel der Registry selbst steht in
`astra-registry/docs/POLICY.md` §2.1 und §3.

**Ein Release, das jede automatische Prüfung besteht, wird sofort
veröffentlicht**, ein erstes Listing eingeschlossen. Niemand genehmigt es, und
es gibt keine Veröffentlichungsverzögerung. Die Prüfungen der Registry sind die
ganze Hürde, und eine gescheiterte lehnt das Release weiterhin ab.

**Es wird als nicht von Astra-Moderatoren geprüft markiert.** Jede Version
beginnt so. Ein Moderator kann eine Version später lesen und als geprüft
markieren. Die Markierung gehört zu dieser einen Version, also beginnt dein
nächstes Release wieder als nicht geprüft.

**Nutzer sehen eine Warnung.** Ab dem Astra-Release, das die Markierung
einführt, warnt Astra, bevor es eine nicht geprüfte Version installiert, auch
wenn Astras AI-Werkzeuge die Installation anfordern. Es warnt außerdem überall,
wo ein Nutzer ein Update auf eine solche Version startet, und wendet das Update
erst an, wenn der Nutzer die Warnung bestätigt hat. Das Plugins-Panel zeigt die
Markierung auf der Seite deines Plugins. Astra 0.2.x und jedes Astra-Release
vor dem, das die Markierung einführt, zeigen weder Markierung noch Warnung.

**`reviewed` heißt, dass ein Moderator diese Version gelesen hat, und nichts
weiter.** Es ist keine Sicherheitsprüfung, kein Code-Audit, keine Empfehlung
und keine Sandbox. Ein späteres Advisory, ein Yank oder ein Delist geht immer
vor.

**Nur ein Besitzerwechsel bei einem schon bestehenden Listing wartet auf einen
Moderator:**

| Ereignis | Code |
|---|---|
| Das Repository oder die Identität hat sich geändert | `R_IDENTITY_CHANGED` |
| Das erste Release eines bestehenden Listings mit Binding-Zeile | `R_FIRST_BINDING` |
| Die Binding-Zeile trägt ein anderes Token als das, mit dem das Listing gebunden ist | `R_BINDING_CHANGED` |

Jedes davon liefert den Code einer anderen Partei aus, oder übergibt das
Listing einem anderen Konto, als Update an Menschen, die es schon nutzen. Ein
Moderator genehmigt es im Panel, und danach wartet es die Fenster ab, die die
Registry veröffentlicht. Ein genehmigtes Release wird trotzdem als nicht
geprüft veröffentlicht, denn eine Genehmigung ist keine Prüfung.

## 5 · Jedes Release danach

Nichts. Taggen, und CI erledigt den Rest; die Registry bemerkt das Release
und generiert den Index neu.

Falls sie es nicht bemerkt hat:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Das ist der manuelle Ping für ein Plugin, das **bereits gelistet** ist.
Ohne ihn öffnet `publish` eine Erst-Listing-Anfrage.

**Ownership ist auf diesem Pfad eine andere Frage.** Ein Ping — und der
Cron-Backstop dahinter — prüft das Release gegen das Konto, das es
*veröffentlicht* hat, nicht gegen den Tippenden und nicht gegen
`.well-known/astra-plugin-owner`. Diese Datei zu ändern ändert also nicht,
wer ein Release eines bereits gelisteten Plugins ausliefern kann. Begrenzt
wird das dadurch, dass ein Ping nur ein Repository nennen darf, das die
Registry **bereits gepinnt** hat: ein Repository-Wechsel ist nicht mehr
Routine und geht zurück an einen Menschen.

## Was ein Listing nicht bedeutet

Ein Listing ist keine Sicherheitsprüfung, und eine als geprüft markierte
Version auch nicht: Das sagt nur, dass ein Moderator diese Version gelesen hat.
Die Registry sagt das in ihrer eigenen Policy: eine Permission entscheidet,
was der Daemon *für* ein Plugin tut, und nichts darüber, was der Prozess
des Plugins mit der Maschine anstellen darf. Es gibt keine Sandbox. Siehe
[das Sicherheitsmodell](../1-orientation/security.md).

## Der heutige Stand

Eine Sache, die ein Leser verdient zu wissen, bevor er dieser Seite folgt.

**Die Signierkette ist durch den Katalog hindurch verankert, aber noch nicht
durch die Widerrufsliste.** Genau genommen, und jeder Teil ist überprüfbar:

- die Root-Schlüssel existieren auf beiden Seiten — `registry/v1/root.json`
  trägt `"status": "provisioned"` mit zwei Ed25519-Schlüsseln, und
  `PRODUCTION_ROOT_KEYS` des Daemons kompiliert dieselben zwei ein;
- `registry/v1/trust.json` **ist jetzt signiert** von `astra-root-2026a`
  und delegiert an einen Index-Signierschlüssel, `astra-index-2026a`. Die
  eigene `node tools/sign-trust.mjs --verify registry/v1/trust.json` der
  Registry bestätigt das und gibt die
  Reusable-Workflow-SHAs aus, die der Bot in einer Attestation akzeptiert —
  zwei davon, seit das Tag am 2026-08-19 verschoben wurde: der Commit, auf
  den `plugin-release/v1` zeigt, und der, auf den es vorher zeigte. Also
  feuert `E_TRUST_UNPROVISIONED`, das früher jeden Ingest stoppte, nicht
  mehr;
- **der Katalog, den Clients bekommen, ist signiert.** Seit 2026-09-20
  signiert der Signer der Registry `index.json` mit `astra-index-2026a` und
  deployt es nach Pages. Die auf `main` committeten Kopien,
  `registry/v1/index.json` und `revocations.json`, tragen
  `"signatures": []` mit Absicht, und kein Client liest sie. Die
  Widerrufsliste, die Pages ausliefert, ist weiterhin die unsignierte
  committete, die Durchsetzung von Widerrufen ist also noch nicht aktiv.

Siehe [`spec/registry-index.md` §0.1](../spec/registry-index.md) und
[das Sicherheitsmodell](../1-orientation/security.md).

Was das für dich bedeutet: Der Einreichungspfad auf dieser Seite
funktioniert heute Ende-zu-Ende — dein Issue wird gelesen, die Prüfungen
laufen, der Bot antwortet, und ein Listing wird committed. Was noch
aussteht, ist die signierte Widerrufsliste auf Pages, mit der die Registry
eine Version aus bereits installierten Kopien zurückziehen kann. Nichts auf
dieser Seite ändert sich, wenn sie ankommt.

## Siehe auch

- [`spec/registry-index.md`](../spec/registry-index.md) — der Index, Widerrufe, und der Verifikationsalgorithmus
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — was der Bot aus deinem Archiv liest
- [Versionierung](../versioning.md) — was die Zahlen bedeuten und wie lange eine Deprecation dauert
</content>
