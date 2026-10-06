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
`.zip`, ein auf deinem Laptop gebautes Bundle, oder eine Nachricht, die einen
Maintainer bittet, es zu bauen. Die Registry listet Release-Assets, die CI
bezeugt hat, und nichts sonst.

Jeder Schritt unten ist `astra-plugin`, ein Commit in deinem eigenen
Repository oder das Panel unter https://astra.minice.ai/plugins, angemeldet bei
deinem Minice-Konto. Falls du die CLI nicht hast,
[installiere sie zuerst](../install-cli.md) — es gibt vorgebaute Binärdateien.

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
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**Eine davon erledigst du im Voraus, und musst du auch.** Das Binding-Urteil
liest die Zeile, die [Das Repository binden](#das-repository-binden) schreibt.
Committe sie, bevor du taggst, und die Prüfung hat etwas zu finden; lässt du sie
weg, ist die erste Antwort `B_UNBOUND`.

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

**Halte es unter 8 KiB** (8.192 Bytes). Das Icon jedes Eintrags wird in einen
einzigen signierten Katalog eingebettet, den jede Astra-Installation vollständig
herunterlädt, also bezahlt jeder Nutzer jedes Plugins für ein großes Icon. Ein
größeres wird genauso verworfen — dein Release wird gelistet, mit einem
Buchstaben auf der Karte statt deines Bildes —, und `astra-plugin build` warnt
dich, bevor du taggst. Exportiere es in 128×128: als WebP mit Qualität 80 sind
das selbst bei detaillierter Grafik wenige Kilobyte, und ein flaches Design ist
als SVG meist noch kleiner.

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

## Das Repository binden

**Ein Listing gehört einem Minice-Konto.** Jedes erste Listing, und jedes
Release eines Listings, das eine hat, wird gegen eine **Bindung** gelesen: eine
Zeile in `.well-known/astra-plugin-owner` in der Wurzel deines Repositorys, von
der CLI geschrieben aus einem Token, das du im Panel erzeugst, angemeldet bei
dem Minice-Konto, das veröffentlichen wird. Es ist der eine Schritt auf dieser
Seite, der kein Befehl ist, und ihn auszulassen ist der häufigste Weg, auf dem
eine korrekte, ehrliche erste Einreichung abgelehnt wird.

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

**4 · Im Panel einreichen.** `astra-plugin publish` öffnet
die Einreichungsseite des Panels mit Repository und Tag
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

## 2 · Im Panel einreichen

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

Das öffnet die **Einreichungsseite** des Panels in deinem Browser, mit deinem
Repository und Tag schon ausgefüllt. **Es lädt nichts hoch und hält keine
Zugangsdaten** — es gibt kein `astra-plugin login`, kein Token in deiner
Shell-Historie, keinen Schlüsselbund, mit dem integriert werden müsste. Die
Seite füllt sich aus dem Link aus und reicht nichts ein: Das tust du, angemeldet
bei dem Minice-Konto, an das dein Repository gebunden ist. `--print-url` gibt
den Link stattdessen aus:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

Ein Repository ohne Binding-Zeile bekommt das über dem Link gesagt, samt
Verweis, wie man bindet; ein Checkout ohne den Tag bekommt eine Zeile, dass der
Tag gepusht sein muss. Beides sind Erinnerungen, keine Fehler: Die Registry
liest den Commit des Tags und das Release von GitHub, also zählt, was du
gepusht hast.

Die Einreichung trägt **zwei Fakten**:

| Feld | Warum es getippt statt gelesen wird |
|---|---|
| Quell-Repository (`you/dice-roller`) | Das Bundle kann nicht dafür bürgen, von wo es ausgeliefert wird |
| Release-Tag (`v0.1.0`) | Ebenso |

**Alles andere wird aus dem bezeugten Bundle gelesen** — die ID, die Version,
der Anzeigename, die Zusammenfassung, die Lizenz, die Capabilities, die
Berechtigungen, die Plattformen, die Digests, die Größen. Das ist keine
Bequemlichkeit: Alles im Bundle ist von der Bezeugung gedeckt, was es strikt
vertrauenswürdiger macht als alles, was in ein Formular getippt wird. Es
streicht außerdem eine ganze Klasse von Ablehnungen, weil es kein Formular
gibt, dem `plugin.toml` widersprechen könnte.

## 3 · Was nach der Einreichung passiert

Das Panel zeigt den Zustand deiner Einreichung und jeden Grund dazu, und
dieselben Momente erreichen dich als Benachrichtigungen: an der verifizierten
E-Mail-Adresse des Minice-Kontos und im Panel, und über Telegram nur, wenn du es
verknüpft hast — nichts verlangt Telegram. Die Regeln unten sind die der
Registry, veröffentlicht in ihrer `docs/POLICY.md`; die Codes sind die, die das
Panel zeigt, zum Start mit englischen Titeln.

### Die Zustände, die eine Einreichung durchläuft

| Zustand | Bedeutet |
|---|---|
| `received` | Das Panel hat deine Einreichung angenommen, und noch nichts hat sie gelesen |
| `checking` | Der Bot der Registry liest das Release und verifiziert jedes Asset von Grund auf |
| `held` | Alles, was eine Maschine entscheiden kann, hat bestanden, und eine Entscheidung gehört einer Person — siehe unten |
| `approved` | Ein Moderator hat den Hold freigegeben; es wird veröffentlicht, sobald nichts anderes mehr wartet |
| `delayed` | Alles hat bestanden; es veröffentlicht sich selbst zu der Zeit, die das Panel zeigt. Seit dem Registry-Vertrag 3.0.0 wartet kein Release, das du einreichst, hier |
| `published` | In die Registry committet |
| `served` | Im signierten Katalog, aus dem Astra installiert |
| `refused` | Eine Prüfung ist gescheitert. Das Panel nennt den Code, und ob ein Recheck ihn aufheben kann oder er einen neuen Tag braucht |
| `stopped` | Du hast es gestoppt, bevor es veröffentlicht wurde, und es wird nicht veröffentlicht |

*Geändert am 2026-09-26 (Registry-Vertrag 3.0.0).* Vor diesem Datum stand auf
dieser Seite, dass ein erstes Listing immer für eine Person zurückgehalten wird.
Die Regel der Registry selbst steht in `astra-registry/docs/POLICY.md` §2.1 und
§3.

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

Ein erstes Listing, eine neu angeforderte High-Risk-Berechtigung, eine
erweiterte Menge von Berechtigungen und ein Name, den eine Prüfung markiert,
werden wie jedes andere Release sofort veröffentlicht und tragen
`P_REVIEW_PRIORITY`, damit Moderatoren sie zuerst lesen. High-Risk sind hier
vier Namen: `client`, `dom_access`, `send_chat_message`,
`set_theme_contribution` — gleichermaßen in `[capabilities]` und `[permissions]`
erkannt, weil der Abschnitt, in dem du sie deklarierst, nicht der Punkt ist.

### Wenn die Antwort ein Code ist

Eine Ablehnung ist kein Urteil über dein Plugin; sie ist ein benannter,
behebbarer Zustand, und das Panel sagt, auf welchem von zwei Wegen er sich
auflöst. **Recheck**, ein Knopf im Panel, führt jede Prüfung von Grund auf
erneut aus, gegen denselben Tag — für eine Korrektur außerhalb der getaggten
Bytes, etwa ein vergessenes Release-Asset. **Ein neuer Tag** ist der einzige
Weg, etwas innerhalb dieser Bytes zu ändern, weil die Bezeugung genau diese
Bytes deckt. Die Binding-Codes:

| Code | Was er bedeutet | Behebung |
|---|---|---|
| `B_UNBOUND` | Keine Binding-Zeile im getaggten Commit, und dieses Listing braucht eine | Binde das Repository und tagge erneut: [Das Repository binden](#das-repository-binden) |
| `B_BINDING_MALFORMED` | Zwei Binding-Zeilen, oder eine als solche gemeinte Zeile, die keine ist (`Astra-Binding:`, ein zu kurzes Token) | `astra-plugin init-ci --binding <token>` schreibt die Datei mit genau einer Zeile neu; tagge erneut. `astra-plugin check --tag` zeigt das, bevor du pushst |
| `B_BINDING_UNUSABLE` | Das Token in der Zeile bindet nichts, was dieses Release benutzen kann: widerrufen, abgelaufen, für ein anderes Repository erzeugt, oder sein Konto darf nicht veröffentlichen | Erzeuge im Panel ein neues Token für dieses Repository und tagge erneut; das Panel sagt, welcher der zwei Fälle unten auf dich zutrifft |
| `B_BINDING_INVALID` | Nur dir und Moderatoren gezeigt: Das Token selbst ist das Problem — unbekannt, widerrufen, abgelaufen, oder für ein anderes Repository erzeugt | Erzeuge ein neues für dieses Repository |
| `B_ACCOUNT_INELIGIBLE` | Nur dir und Moderatoren gezeigt: Das Konto hinter dem Token darf nicht veröffentlichen, etwa weil es `astraUser` nicht mehr hat | Bring das Konto in Ordnung, dann Recheck |
| `B_OWNER_CHANGED` | Das Repository gehört jetzt einem anderen Besitzer als dem, unter dem dieses Listing erfasst ist | Eine Übertragung ist ein Autorenwechsel. Sie wartet auf einen Moderator; installierte Kopien behalten den alten Namen, bis sie neu installiert werden |
| `B_REPOSITORY_RECYCLED` | Der Repository-Name gehört jetzt einem anderen Repository als dem gelisteten | Dauerhaft: Kein Recheck, Tag oder Freigabe hebt ihn auf. Nur ein Moderator kann die Identität des Listings zurücksetzen |

Und die Release-Codes, auf die Autoren am häufigsten treffen:

| Code | Was er bedeutet | Behebung |
|---|---|---|
| `E_ATTESTATION_MISSING` | Das Bundle hat keine Build-Bezeugung | Du hast ein selbst gebautes Bundle hochgeladen. Lass es CI bauen: [Release mit CI](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | Das Release trägt kein `.astraplugin`-Asset | Der Workflow lief nicht, oder lief und scheiterte. Prüfe den Actions-Tab, hänge die Assets an, dann Recheck |
| `E_RELEASE_NOT_FOUND` | Dieses Repository hat kein Release mit diesem Tag | Ein Release-Entwurf ist für alle außer dir unsichtbar, und ein privates Repository sieht genauso aus wie ein fehlendes. Veröffentliche es, dann Recheck |
| `E_WORKFLOW_NOT_ALLOWED` | Der Build lief mit einem Workflow, den diese Registry nicht erlaubt | Pinne den wiederverwendbaren Astra-Workflow per Commit-SHA — `astra-plugin init-ci` tut das — und tagge erneut |
| `E_ASSET_URL_FOREIGN` | Eine Asset-URL liegt nicht unter den Releases deines eigenen Repositorys | Jede Download-URL muss unter `https://github.com/<owner>/<repo>/releases/download/<tag>/` liegen |
| `E_INPUT_REPO` / `E_INPUT_TAG` | Das Repository oder der Tag hat nicht die erwartete Form | `you/dice-roller`, keine URL; `v0.2.0`, kein Commit-SHA und kein Branch |

Die vollständige Liste, mit Titel und Behebung jedes Codes, ist
`docs/BOT-CHECKS.md` in der Registry.

Zwei Wartezustände sehen aus wie eine hängende Einreichung und sind keine:

| Code | Was er bedeutet |
|---|---|
| `W_ELIGIBILITY_UNREADABLE` | Die Registry liest die Berechtigung deines Kontos aus seiner letzten verifizierten Anmeldung, und die zählt 12 Stunden. Melde dich im Panel an, und das Release geht weiter; eine `notice.sign_in`-Benachrichtigung sagt dasselbe |
| `W_REGISTRY_UNACKNOWLEDGED` | Der Bot der Registry hat sich geändert und wartet auf die Bestätigung eines Operators. Mit deinem Release ist nichts falsch, und von dir wird nichts verlangt |

### Was auf eine Person wartet

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

Eine Ablehnung trägt einen Grund, der dich erreicht. Du tust nichts, während du
wartest; das Panel zeigt den Hold.

Ein Listing, das noch `grandfathered` ist — gelistet vor den Bindungen und noch
nicht gebunden —, hat eine Wartezeit mehr: Ab dem Cutover wartet ein Release
davon, das angehalten und genehmigt wurde, bis das Listing gebunden ist.

### Stoppen, zurückziehen, Einspruch, Meldung

- **Stoppen.** Bis ein Release veröffentlicht ist, kannst du es im Panel
  stoppen, und es wird nicht veröffentlicht.
- **Zurückziehen (Yank).** Nach der Veröffentlichung kannst du eine Version im
  Panel zurückziehen. Ein Yank wird nie rückgängig gemacht — veröffentliche
  stattdessen eine neue Version —, und er wird mit einem Entscheidungsdatensatz
  festgehalten, wie jede andere Entscheidung über ein Listing. Solange dein
  Listing noch nicht gebunden ist, bitte im Panel einen Moderator, es für dich
  zurückzuziehen.
- **Einspruch.** Gegen eine Entscheidung über dein Listing, die du für falsch
  hältst, legst du im Panel Einspruch ein, und die Antwort wird dort
  festgehalten.
- **Bewertungen** sind nur Sterne: kein Text, keine Antworten, keine Namen.
- **Meldungen** über das Plugin eines anderen gehen über
  https://astra.minice.ai/plugins, nicht über GitHub. Ein Sicherheitsproblem in
  Astra, dem Daemon, der Registry oder der Signaturkette geht an
  security@minice.ai — siehe [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#security).

## 4 · Jedes Release danach

Nichts. Tagge, und CI erledigt den Rest: Die Registry erkennt einen neuen Tag
eines gelisteten Plugins von selbst, verifiziert ihn, und das Panel zeigt
seinen Zustand. Es gibt nichts einzureichen und nichts anzupingen. Ein Release,
das nicht erschienen ist, steht auf der Seite deines Plugins im Panel, mit
seinem Zustand und dem Grund.

**Die Bindung wird bei jedem Release geprüft, nicht nur beim ersten.** Jedes wird
gegen die Binding-Zeile in seinem getaggten Commit und den Identitätsdatensatz
des Listings gelesen, also wartet ein Repository, dessen Zeile sich geändert
hat oder das an einen anderen Besitzer gegangen ist, auf eine Person, statt zu
veröffentlichen — und genau das macht ein gestohlenes Token oder ein
übertragenes Repository zu einem Ereignis, das jemand sieht.

## Was ein Listing nicht bedeutet

Ein Listing ist keine Sicherheitsprüfung, und eine als geprüft markierte
Version auch nicht: Das sagt nur, dass ein Moderator diese Version gelesen hat.
Die Registry sagt das in ihrer eigenen Policy: eine Permission entscheidet,
was der Daemon *für* ein Plugin tut, und nichts darüber, was der Prozess
des Plugins mit der Maschine anstellen darf. Es gibt keine Sandbox. Siehe
[das Sicherheitsmodell](../1-orientation/security.md).

## Der heutige Stand

Eine Sache, die ein Leser verdient zu wissen, bevor er dieser Seite folgt.

**Die Signierkette ist durchgehend verankert, durch den Katalog und die
Widerrufsliste.** Genau genommen, und jeder Teil ist überprüfbar:

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
  Widerrufsliste, die Pages ausliefert, ist ebenfalls signiert — seit dem
  astra-registry-Commit `654b942` (2026-10-05) —, Widerrufe werden also
  durchgesetzt.

Siehe [`spec/registry-index.md` §0.1](../spec/registry-index.md) und
[das Sicherheitsmodell](../1-orientation/security.md).

Was das für dich bedeutet: Der Einreichungspfad auf dieser Seite
funktioniert heute Ende-zu-Ende — deine Einreichung wird gelesen, die
Prüfungen laufen, das Panel zeigt die Antwort, ein Listing wird committed, und
die Registry kann eine Version aus bereits installierten Kopien zurückziehen.

## Siehe auch

- [`spec/registry-index.md`](../spec/registry-index.md) — der Index, Widerrufe, und der Verifikationsalgorithmus
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — was der Bot aus deinem Archiv liest
- [Versionierung](../versioning.md) — was die Zahlen bedeuten und wie lange eine Deprecation dauert
</content>
