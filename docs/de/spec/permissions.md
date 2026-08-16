> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/spec/permissions.md) maßgeblich.

# Permissions — normative Spezifikation

**Status:** normativ. Das Vokabular, das Gate, die Obergrenzen, die vier
Provenienzpfade und der Hash sind alle implementiert und durchgesetzt;
wo etwas spezifiziert, aber noch nicht durchgesetzt ist, sagt dieses
Dokument das in der jeweiligen Zeile.

Anforderungswörter folgen RFC 2119.

Zwei orthogonale Abschnitte existieren in `plugin.toml`, und sie zu
verwechseln ist genau der Bug, den dieses Vokabular beheben sollte:

|Abschnitt|Richtung|Frage|
|---|---|---|
| `[capabilities]` | Daemon → Plugin | *was implementiere ich, das Astra hineinrufen darf?* |
| `[permissions]` | Plugin → Daemon | *was darf ich hinausrufen, und welche Surfaces darf ich bekommen?* |

Sie waren ein Wort für zwei Dinge, und das Wort bedeutete das erste —
so kam `dom_access` dazu, eine Capability zu sein, die sich ein Plugin
durch bloße Deklaration selbst gewährte.

---

## 1. Das Vokabular

Acht IDs, eine geschlossene Menge (`astra-plugin-manifest/src/permissions.rs`,
`PERMISSION_NAMES`, per Test an das Enum gepinnt). Die Registry
validiert die IDs eines Listings gegen diese Liste, und Astras
lokalisierte Label-Tabelle ist danach indexiert, eine an einer Stelle
hinzugefügte und an den anderen nicht hinzugefügte ID rendert also als
leere Zeile.

| ID | sperrt | was sie gewährt | hohes Risiko |
|---|---|---|---|
| `fire_trigger` | `PluginHostService.FireTrigger` | die gespeicherten Automatisierungen des Nutzers ausführen | |
| `subscribe_events` | `SubscribeEvents` | Daemon-Events empfangen, **beschränkt auf die deklarierten Typen** (§1.1) | |
| `set_variable` | `SetVariable` | in den Variablenkontext des Daemons schreiben, dem aufrufenden Plugin zugeordnet | |
| `send_chat_message` | `SendChatMessage` | einen AI-Turn auslösen — die Tokens des Nutzers ausgeben, mit der Stimme seines Assistenten sprechen | ● |
| `push_to_ui` | `PushToUi` | ein Event ins Astra-Fenster pushen | ● |
| `set_theme_contribution` | `SetThemeContribution` | die gesamte App umgestalten | ● |
| `dom_access` | *kein RPC* — eine **Surface** | das eigene Skript des Plugins im Astra-Fenster ausführen, mit Zugriff auf die Unterhaltungen des Nutzers und die Oberfläche jedes anderen Plugins | ● |
| `client` | *kein RPC* — eine **Surface** | als Client-Frontend agieren: eigene Chat-Oberfläche, eigene Session | ● |

**Die fünf mit ● markierten sind hochriskant** (`HIGH_RISK_PERMISSIONS`)
und bekommen jeweils eine eigene Zustimmungs-Checkbox. §4.3 des Plans
buchstabiert vier Checkboxen aus und lässt `push_to_ui` weg; §5.6
listet fünf. Die Implementierung nimmt die **Vereinigung**, weil die
Uneinigkeit zwischen einem UI-Absatz und dem Sicherheitsabschnitt
besteht, und eine Checkbox zu viel kostet einen Klick, während eine zu
wenig die Eigenschaft kostet.

**`dom_access` und `client` sperren kein RPC**, genau deshalb brauchen
sie einen zweiten Durchsetzungspunkt: sie werden dort durchgesetzt, wo
die *Surface* ausgegeben wird (§4.2), nicht dort, wo ein Aufruf
beantwortet wird.

### 1.1 Permission-Argumente

Ein `[permissions]`-Eintrag ist ein Objekt, kein Bool:

```toml
[permissions]
fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
subscribe_events = { types = ["command_completed"], reason = "Reacts when a command finishes" }
set_variable     = { scopes = ["plugin"] }
```

| Member | Typ | Bedeutung |
|---|---|---|
| `reason` | string, ≤ 140 Zeichen | die eigenen Worte des Autors (§6) |
| `types` | Array von String | **nur `subscribe_events`.** Die Event-Typ-Allowlist |
| `scopes` | Array von String | **nur `set_variable`.** `plugin` / `session` / `persistent`. **Reserviert** — der Daemon ordnet heute jeden Plugin-Schreibvorgang nach Plugin-ID zu, das schränkt also noch nichts ein. Es wird geparst, damit ein Manifest, das es deklariert, publizierbar ist und überall identisch hasht |

**`subscribe_events.types` ist eine Allowlist, die der Daemon pro Event
durchsetzt, und eine leere erlaubt nichts.** Drei Zustände, und der
mittlere ist der ganze Punkt:

* Permission abwesend → gar kein Stream;
* Permission gehalten, `types` leer → **erlaubt nichts**; der Daemon
  lehnt die Subscription mit einer Nachricht ab, die den Fix nennt,
  statt einen Stream zurückzugeben, der für immer schweigt;
* `types` aufgelistet → genau diese `AstraEvent::event_type_str()`-Werte.

Die intuitive Lesart — „kein Filter heißt alles" — ist genau das Loch,
das diese Permission schließen soll: ein ungefilterter Abonnent erhält
`speech_recognized`, also jedes Wort, das der Nutzer sagt.

### 1.2 Unbekannte IDs werden behalten, nicht abgelehnt

Ein Manifest, das eine diesem Build unbekannte ID nennt, wird
**akzeptiert**. Zwei Gründe, und beide zeigen in dieselbe Richtung:

1. **Vorwärtskompatibilität.** Neue IDs erscheinen mit neuen Astra-
   Versionen. Ein Daemon, der eine unbekannte ID ablehnte, würde jede
   Erweiterung zu einem Stichtag für jeden älteren Daemon machen.
2. **Der Hash.** `permissions_hash` (§5) wird über diese Bytes von drei
   Implementierungen berechnet. Einen dem Leser unbekannten Schlüssel
   fallenzulassen würde zwei davon uneins darüber machen, was signiert
   wurde.

Eine unbekannte ID ist **wirkungslos** — default-deny bedeutet, sie
gewährt nie etwas — und sie ist nicht still. Das Einwilligungsblatt
rendert sie über ihr `permission.unrecognised`-Label, statt sie
fallenzulassen, ein Nutzer wird also darüber informiert, dass das
Plugin nach etwas fragt, das diese Astra-Version nicht kennt.
`Permissions::unknown()` existiert, damit Tooling sie einzeln auflisten
kann; **`astra-plugin check` tut das heute nicht** — es meldet, dass
ein `[permissions]`-Abschnitt vorhanden ist, und stoppt dort.

(`[capabilities]` ist im Gegensatz dazu `deny_unknown_fields`: es ist
eine geschlossene Menge von Bools, bei der ein Tippfehler genau wie
`false` gelesen wird.)

## 2. Default-deny, und die vier kostenlosen RPCs

**Ein abwesender `[permissions]`-Abschnitt gewährt keine Host-RPCs über
die immer erlaubte Menge hinaus.** Ein fehlender Abschnitt ist nicht
„unspezifiziert"; er ist eine vollständige Antwort, und die Antwort ist
Nein.

Die immer erlaubte Menge umfasst vier, und sie ist als Tabelle
niedergeschrieben (`HOST_RPC_PERMISSIONS` in `host_service.rs`), die
zwei Kanarienvögel gegen jedes RPC prüfen, sodass ein ungesperrtes
neues RPC ein Testfehlschlag ist statt eine stille Auslassung:

| RPC | Permission |
|---|---|
| `Register` | — |
| `PluginLog` | — |
| `GetPluginSelfConfig` | — |
| `GetDaemonInfo` | — |
| `SubscribeEvents` | `subscribe_events` |
| `SendChatMessage` | `send_chat_message` |
| `FireTrigger` | `fire_trigger` |
| `SetVariable` | `set_variable` |
| `SetThemeContribution` | `set_theme_contribution` |
| `PushToUi` | `push_to_ui` |

`GetDaemonInfo` ist die eine Ergänzung zur Dreier-Liste des Plans, und
das ist eine Entscheidung statt eine Auslassung: es gibt `version`,
`state`, `grpc_port` und `language` zurück, alles, was
`PluginRegisterResponse` dem Aufrufer bereits übergeben hatte, es
verrät also nichts Neues. Eine Permission-ID dafür zu erfinden würde
dem Nutzer eine Checkbox vorsetzen, die nichts schützt, und Kästchen,
die nichts schützen, sind der Weg, wie Nutzer lernen, Kästchen blind
anzuhaken.

**`client_session_token` wird jedem Plugin ausgestellt.** Das Token ist
*Authentifizierung* (wer ruft an), nicht *Autorisierung* (was darf er
tun). Es Nicht-`client`-Plugins vorzuenthalten würde `PluginLog`,
`GetPluginSelfConfig`, `SubscribeEvents` und `FireTrigger` — die immer
erlaubte Menge — verweigern und jedes Plugin und beide In-Tree-Sidecars
brechen. Das `client`-Gate gehört in die Obergrenze und auf die
spezifischen Surfaces, nicht in das Token.

## 3. Deklarieren ist Fragen; Gewähren ist ein anderes Objekt

**Nichts in einer `plugin.toml` ist eine Gewährung.** Ein
`[permissions]`-Block ist die *Anfrage* des Autors. Die **gewährte
Menge** ist ein separates Objekt, das der Daemon pro Provenienzpfad
auflöst und dort speichert, wo das Plugin es nicht erreichen kann —
`<base_dir>/registry/records/<id>.json`, ein Geschwister des
Plugins-Baums und nie ein Kind davon, mit einem vom Daemon gehaltenen
Schlüssel MACt.

Durchsetzung liest die gewährte Menge und nie das Manifest — die Form
des Aufrufs am Anfang jedes gesperrten RPC (illustrativer Auszug aus
`host_service.rs`, kein lauffähiges Beispiel):

```rust
let (plugin_id, grants) =
    self.require_permission(&request, Permission::FireTrigger, "FireTrigger").await?;
```

Ein Plugin, das seine eigenen Gewährungen durch Bearbeiten seines
eigenen Manifests erweitern könnte, hätte ein Permission-System, das nur
ein Kommentar ist. Das war vor Phase 4 buchstäblich wahr:
`[capabilities] dom_access = true` — eine Zeile in einer Datei im
eigenen Verzeichnis des Plugins — wurde direkt auf die UI-Contribution
kopiert, die der Renderer honoriert, indem er das Skript des Plugins in
das Astra-Fenster selbst lädt.

**Warum der Record nicht im Verzeichnis des Plugins liegt.** Das Plugin
läuft als der Nutzer, mit `current_dir` auf sein Installationsverzeichnis
gesetzt. Modus 0600 schützt gegen andere Nutzer, nicht gegen das Subjekt.
Ein Record, den das Subjekt schreiben kann, lässt ein bösartiges Plugin
sich selbst `dom_access` gewähren, das TOFU-Pinning überschreiben,
`artifact_sha256` umschreiben, um digest-basierten Widerruf zu
umgehen, und die Datei-Hashes umschreiben, sodass die
Start-Zeit-Neuprüfung besteht.

### 3.1 Die Capability-Brücke

`dom_access` und `client` sind sowohl `[capabilities]`-Bools **als
auch** Permission-IDs. Jedes vor der Trennung geschriebene Plugin sagt
am alten Ort, was es will — einschließlich `companion`, `doom` und
`bad-apple`, von denen keines überhaupt einen `[permissions]`-Abschnitt
deklariert.

Also wird ein `[capabilities] dom_access = true`-Bit als **eine Anfrage**
gelesen, genau wie ein `[permissions]`-Eintrag, und bekommt exakt
dieselbe Antwort aus derselben Tabelle (`declared_permissions()`). Die
Brücke ist absichtlich *nicht* „das Capability-Bit gewährt die
Permission": sie legt das Bit dort hin, wo eine Anfrage lebt, sodass es
eine Antwort auf „darf es?" gibt und nicht zwei.

Konsequenz für Autoren: **ein über die Registry veröffentlichtes Plugin
muss `[permissions] dom_access` deklarieren**, weil eine
Registry-Installation aus ihrem Trust-Record gewährt, das aus dem
`[permissions]`-Block der `MANIFEST.json` des Bundles geschrieben wird
— und dieser Eintrag ist das, was das Einwilligungsblatt rendert und
der Nutzer abhakt.

## 4. Woher die gewährte Menge kommt

### 4.1 Die vier Provenienzpfade

`decide_grants()` ist diese Tabelle als eine reine Funktion.

| Pfad | gewährte Menge |
|---|---|
| **Eingebauter Sidecar** (`builtin_stt`, `builtin_vox`) | eine **code-deklarierte** Menge neben `build_manifest()` dieses Sidecars. Kein Trust-Record, kein Datei-Lesen — ein Sidecar hat *by design* keinen Record, ein Codepfad, der nach einem suchte, wäre also ein Codepfad, der dafür scheitern könnte |
| **Registry-Installation** | der beim Install geschriebene Trust-Record: `MANIFEST.permissions` des Bundles, nach der Zustimmungsprüfung, gekappt von der Obergrenze der Stufe |
| **`ImportPluginFile`** (eine `.astraplugin` von außerhalb des Kanals) | ein Trust-Record bei `tier: "local-unverified"` — die deklarierte Menge des Manifests, **gekappt von der Stufe-2-Obergrenze** |
| **Sideload** (ein Quellverzeichnis, Entwicklermodus) | ein Trust-Record bei `tier: "sideloaded"` — die deklarierte Menge des Manifests, **ungekappt** |

Vier Zweige stehen *nicht* in dieser Tabelle und sind ebenso normativ:

| Zustand | gewährt |
|---|---|
| `Untrusted` — ein Record wurde erwartet und kann nicht geglaubt werden | **nichts** |
| `TamperDetected` — eine Datei stimmt nicht mehr mit dem für sie aufgezeichneten Digest überein | **nichts** |
| `Revoked` — eine signierte Widerrufsliste erfasst es | **nichts** |
| `Unrecorded` — vor Existenz von Trust-Records installiert, überhaupt kein Record | die deklarierte Menge des Manifests, **gekappt von der Stufe-2-Obergrenze** |

`Untrusted` kann trotzdem von Hand gestartet werden, und wenn das
passiert, läuft es ohne Gewährungen: „der Nutzer hat gefragt" ist kein
Beweis über Bytes. `Unrecorded` wird gekappt statt abgelehnt, weil
diesen Plugins nichts zu gewähren funktionierende Installationen bei
einem Upgrade brechen würde, ohne dass der Nutzer es beheben könnte,
und ihnen ihr Manifest ungekappt zu gewähren jedem von ihnen erlauben
würde, sich selbst `dom_access` zu gewähren, indem er eine Datei im
eigenen Verzeichnis bearbeitet. Die Stufe-2-Obergrenze ist genau die
Form von „irgendwoher angekommen, nichts bewiesen".

Ein `Verified`-Plugin ohne glaubwürdigen Record bekommt **nichts**:
`Verified` *bedeutet* einen glaubwürdigen Record, und die Antwort auf
die unmögliche Kombination ist nicht, auf das Manifest zurückzufallen.

Jede Ablehnung benennt ihre Quelle (`GrantSource::describe`) —
„abgelehnt" ohne „und hier ist die Quelle, die nichts dazu zu sagen
hatte" ist der Fehlermodus, der ein Permission-System zurückgerollt
bekommt.

### 4.2 Zwei Tore, nicht eines

Eine Permission wird nur honoriert, wenn **beide** gelten:

1. die **Gewährung** — eine pro Installation gegebene Antwort, die ein
   Einwilligungsblatt erzeugt hat und die ein Trust-Record festhält;
2. die **Obergrenze** — eine pro Provenienz geltende Regel, die kein
   Record überkaufen kann.

`require_permission` fragt das erste für die sechs Host-RPCs, die eine
Permission sperren — `SubscribeEvents`, `SendChatMessage`,
`FireTrigger`, `SetVariable`, `SetThemeContribution`, `PushToUi`. Die
verbleibenden vier (`Register`, `GetPluginSelfConfig`, `PluginLog`,
`GetDaemonInfo`) tragen `None` in `HOST_RPC_PERMISSIONS` und sind
immer erlaubt; §2 hat die Tabelle und die Begründung.
`ceiling_admits` fragt das zweite überall dort, wo eine *Surface*
ausgegeben wird — `PluginStatusMsg`, die UI-Contributions-Antwort, die
Active-Themes-Antwort — sodass der Renderer nie einen Wert erhält, den
er honorieren könnte. Ein Plugin, das in der Grants-Map fehlt, wird
abgelehnt: „darüber nichts aufgelöst" ist kein Grund, ihm die
hochriskanteste Surface im System zu servieren.

## 5. Stufen-Obergrenzen

| Stufe | Quelle | Obergrenze |
|---|---|---|
| **1 · Registry** | verifiziert gemäß dem Installationsalgorithmus | **alles**, vorbehaltlich Zustimmung. Kein Override bei einem Fehlschlag |
| **2 · Lokale Datei** (`ImportPluginFile`) | eine von außerhalb des Kanals empfangene `.astraplugin` | `send_chat_message`, `set_theme_contribution`, `dom_access` und `client` werden **pauschal verweigert, nicht nur mit Warnung versehen** |
| **3 · Sideload** | ein Quellverzeichnis, auf das der Nutzer einen Dateidialog gerichtet hat, Entwicklermodus an | **keine** — und es startet **nie automatisch**: der Entwicklermodus ist zur Ladezeit erforderlich, und ein Neustart lässt es gestoppt, bis der Nutzer es erneut startet |

Die Stufe von Sideload wird dem Nutzer als
`provenance.tier.sideloaded` („aus einem Ordner geladen") im
Provenance-Panel angezeigt. Der Plan verlangt außerdem ein dauerhaftes,
nicht wegklickbares „DEVELOPER — unverified code from a local
directory"-Abzeichen auf der Karte und im Fensterrahmen für
`dom_access`; **dieses Abzeichen gibt es heute nicht in der UI**, und
dieses Dokument behauptet das auch nicht.

**Die Höherstufung von Stufe 2 ist nicht implementiert.** Der Plan
beschreibt, eine importierte Datei auf Stufe 1 hochzustufen, wenn ihr
Digest in einem frischen Index auftaucht und die Versionsuntergrenzen
gelten; heute übergibt `import_plugin_file` kein verifiziertes Release
an den Installationspfad, ein importiertes Bundle ist also **immer**
`local-unverified`, egal was der Index über seinen Digest sagt. Sag
einem Autor nicht, dass Veröffentlichen die Obergrenze einer Datei, die
er jemandem geschickt hat, rückwirkend aufheben wird.

Die Stufe-2-Ablehnungsliste ist `TIER2_REFUSED_PERMISSIONS` — absichtlich
**nicht** dieselbe Liste wie `HIGH_RISK_PERMISSIONS`: `push_to_ui` ist
eine Checkbox wert und nicht wert, eine Datei abzulehnen, die der
Nutzer zum Import ausgewählt hat. Die vier sind aus §5.5 zitiert, nicht
abgeleitet.

**Stufe 3 ist nicht Stufe 2 mit einem netteren Abzeichen.** Die
Trennung ist nach *Absicht*, nicht nach Verifikationsstatus. Ein
Nutzer, der einen Dateidialog auf ein Verzeichnis auf seiner eigenen
Festplatte gerichtet hat, hat ein stärkeres Signal gegeben als eine
unverifizierte Datei, die von anderswo ankam — und `companion`, `doom`
und `bad-apple`, die eigenen Vorzeigebeispiele dieses Projekts,
brauchen alle den DOM-Pfad, den Stufe 2 verweigert. Stufe 3 zu deckeln
würde `astra-plugin dev` unmöglich machen.

Unbekannte IDs werden von jeder Obergrenze fallengelassen
(`capped()` filtert auf
`Permission::from_id(id).is_some_and(keep)`): eine Obergrenze, die die
IDs durchließe, die sie nicht klassifizieren konnte, wäre eine
Obergrenze mit einem Loch in Form des nächsten Releases.

**Die überall geltende Design-Regel:** *das Einzige, was ein
Nutzer-Override erkaufen kann, ist das Recht, Code aus einer von Astra
nicht geprüften Quelle auszuführen. Es kann nie eine Permission
erkaufen, um die ein verifiziertes Plugin hätte bitten müssen.*

## 6. Zustimmung

Das Einwilligungsblatt wird **vor jedem Download** gerendert, aus dem
`permissions`-Feld des Katalog-Eintrags — das die Registry beim Ingest
aus dem `[permissions]`-Block der `MANIFEST.json` des Bundles kopiert
hat.

* Jede ID wird über **Astras eigene lokalisierte Label-Tabelle**
  gerendert. Der `reason` des Autors ist untergeordnet: in
  Anführungszeichen, Klartext, ≤ 140 Zeichen, stets mit „The author
  says:" vorangestellt. Er ist nie das Label selbst —
  Formulierungs-Fixes werden mit Astra ausgeliefert und dürfen nicht
  durch ein Listing gestaltet werden können.
* Jede hochriskante Permission bekommt ihre **eigene Checkbox**;
  `dom_access` bekommt einen zweiten Bildschirm.
* Die Antwort reist als **Obergrenze, nicht als Anfrage** in die
  Installation (`InstallOptions::consent`): die Installation wird mit
  `PERMISSIONS_NOT_CONSENTED` abgelehnt, wenn das *Bundle* nach etwas
  fragt, das das Blatt nicht gezeigt hat. Die beiden Listen kommen von
  verschiedenen Orten — das Blatt rendert den Katalog-Eintrag, der
  Trust-Record gewährt aus dem eigenen Manifest des Bundles — und
  nichts sonst lässt sie übereinstimmen. Ein Listing, das nichts
  deklariert, während es ein Bundle ausliefert, das nach `dom_access`
  fragt, ist der „bösartige Registry"-Fall, der direkt auf den
  Einwilligungsbildschirm zielt.
* `consent: None` — die unäre Installation, ein Import, ein Test, eine
  Übernahme — behält das Vor-Zustimmungs-Verhalten: die deklarierte
  Menge des Bundles gewähren, gekappt nach Stufe.

**Updates.** Eine Version, die nach einer Permission fragt, die der
installierten Version nicht gewährt wurde, wird mit
`PERMISSIONS_WIDENED` abgelehnt und wird zu einer Review-Aufforderung;
die explizite Zustimmung des Nutzers ist es, was sie zu einer
Installation macht. Der Vergleich erfolgt **nach Permission-Namen, nie
nach dem gesamten Anfrage-Objekt**: ein Autor, der die Formulierung
eines `reason` verbessert, hat nichts erweitert, und ein Update-Gate,
das das als Erweiterung behandelte, würde Nutzer darauf trainieren,
genau den einen Dialog durchzuklicken, auf den es ankommt.

**Ein Entzug wirkt sofort.** Bei jeder Änderung an
`granted_permissions`, bei einer Ablehnung der Zustimmung und bei
Widerruf lässt der Daemon die serverseitige Subscription fallen und
invalidiert das Session-Token, sodass ein laufender Event-Stream eine
Verengung nicht überleben kann. Dem Plugin wird über den
`x-astra-teardown-reason`-Trailer mitgeteilt, welches davon passiert
ist (`grants_changed`, `consent_declined`, `revoked`, `trust_lost`,
`disabled`, `uninstalled`, `re_registered`) — ein stabiles Token,
sodass ein SDK nie Englisch parsen muss, um zu wissen, ob ein erneuter
Versuch sinnlos ist.

### 6.1 Einen guten `reason` schreiben

Er wird einem Nutzer gezeigt, der gerade entscheidet. Er **MUSS** ≤ 140
Zeichen sein und **SOLLTE**:

* das **Feature nennen, das der Nutzer erkennt**, nicht die API —
  *"Fires the on_dice_roll trigger you configure"*, nicht *"calls
  FireTrigger"*;
* **sagen, wann**, falls nicht immer — *"only while a recording is in
  progress"*;
* es vermeiden, das eigene Label der Permission zu wiederholen; Astra
  rendert das schon;
* Dringlichkeit, Drohungen oder Anweisungen an den Nutzer vermeiden.
  Der Generator lehnt Text mit bidi-Overrides oder
  Zero-Width-Joinern überall dort ab, wo er wörtlich angezeigt wird,
  und ein Einwilligungsblatt ist der letzte Ort, um eine Ausnahme zu
  machen.

Eine Permission ohne plausiblen Reason ist eine Permission, die aus
dem Manifest zu entfernen ist — nichts prüft das automatisch, und eine
das Listing lesende Prüfperson ist die einzige Rückfallebene.

## 7. `permissions_hash`

```
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( JCS(permissions) ) )
```

* `JCS` ist RFC 8785 kanonisches JSON — Schlüssel nach UTF-16-Code-Unit
  sortiert, kompakt. Siehe
  [`registry-index.md` §3](registry-index.md#3-kanonisierung-jcs-profil)
  für das Profil, das beide Repositories implementieren.
* **`null` und `{}` sind derselbe Wert** und hashen gleich, ein
  Produzent, der das Member weglässt, und einer, der ein leeres Objekt
  schreibt, stimmen also überein:
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`.
* **Leere Member werden weggelassen, nicht leer ausgegeben.**
  `set_variable = {}` ist `{}`, nie `{"reason":""}`. Zwei kanonische
  Schreibweisen einer Deklaration sind genau die Drift, die dieser
  Hash verhindern soll.
* Das Präfix `sha256:` ist Teil des Werts, weil er eine
  Repository-Grenze überquert.

Drei Implementierungen berechnen ihn, und alle drei werden verglichen:
der Packer von `astra-plugin` schreibt ihn in `MANIFEST.json`; der
Bot der Registry leitet ihn beim Ingest neu ab und lehnt eine
Diskrepanz ab (`E_PERMISSIONS_HASH_MISMATCH`); der Daemon leitet ihn
neu ab, bevor er dem Manifest glaubt, und blockiert die Installation
(`PERMISSIONS_HASH_MISMATCH`). Goldene Vektoren: `ok-permissions` (eine
korrekte nicht leere Map) und `permissions-hash-mismatch` — siehe
[`bundle-v2.md` §10](bundle-v2.md#10-permissions-und-permissions_hash)
und die F5-Abweichung, die allein den Reader der CLI betrifft.

Der Hash wird auch im Trust-Record aufgezeichnet und beim Discovery
erneut geprüft, sodass eine nach der Installation an Ort und Stelle
bearbeitete `plugin.toml` erkannt statt befolgt wird.

## 8. Was Permissions nicht sind

`[permissions]` beantwortet *was der Daemon für ein Plugin tun wird*.
Es beantwortet nicht *was der Prozess der Maschine antun kann*.

Ein Plugin ist ein nativer Prozess, vom Daemon gestartet, läuft als der
Nutzer mit dessen vollen Rechten. Es kann die Dateien des Nutzers
lesen, Sockets öffnen und — heute — das eigene Token des Daemons von der
Festplatte lesen. **Es gibt keine Sandbox.** Isolation
(Landlock/seccomp, ein AppContainer oder Low-Integrity-Token unter
Windows, rlimits) ist als zukünftige Arbeit eingeplant und ausdrücklich
nicht in diesem Release.

Zwei Konsequenzen, an die dieses Dokument jeden Konsumenten bindet:

* **Astras UI darf nie eine Sandbox suggerieren.** Der
  „does not prove"-Block des Provenance-Panels und der Einzeiler des
  Einwilligungsblatts existieren genau deshalb.
* **Eine Permission-Ablehnung ist eine echte Grenze nur für die eigene
  Autorität des Daemons** — die Automatisierungen, den Chat-Turn, das
  Theme, das Fenster. Für alles andere ist sie ein Stolperdraht, kein
  Gefängnis.

Hier ehrlich zu sein ist kein am Ende angehängter Vorbehalt. Ein
Permission-Modell, das als Sandbox beschrieben wird, ist ein
Permission-Modell, dessen Nutzer schlechtere Entscheidungen treffen,
als sie es mit gar keinem Modell täten.

---

*Beim Schreiben dieses Dokuments geprüfte Quellen:
`Astra/astra-rs/astra-plugin-manifest/src/permissions.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/host_service.rs`
(`HOST_RPC_PERMISSIONS`, `decide_grants`, `ceiling_for`, `declared_permissions`,
`resolve_grants`, `TeardownReason`);
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`InstallOptions::consent`,
`ceiling_admits`, `granted_and_admitted`, `UpdateGate`, `block_codes`);
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`,
`permission_names`, `Tier`, `TrustRecord`);
`astra-plugin-cli/src/bundle.rs` (`canonical_permissions`, `permissions_hash`);
`astra-registry/schema/version-v1.json`; `astra-registry/bot/lib/bundle.mjs`;
`testdata/bundles/vectors.json`.*
</content>
