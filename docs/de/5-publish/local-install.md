> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/5-publish/local-install.md) maßgeblich.

# Eine lokale `.astraplugin`-Datei installieren

**Fortgeschritten, und es kostet dich vier Permissions.** Diese Seite
beschreibt den Import eines Bundles, das außerhalb des Kanals ankam — ein
Kollege hat es geschickt, du hast es selbst gebaut, ein Release ist noch
nicht gelistet. So werden Plugins nicht installiert;
[das ist der Store](get-listed.md), wo das Artefakt über den Digest
gepinnt wird und Verifikationsfehler harte Blockaden sind.

> **Jemandem diese Datei zu geben ist nicht, dein Plugin zu veröffentlichen.**
> Ein von dir gebautes und verschicktes Bundle trägt keine
> Build-Attestation und keinen Registry-Eintrag, installiert also auf einer
> reduzierten Stufe auf genau der einen Maschine, an die du es geschickt
> hast, und erreicht niemanden sonst. Veröffentlichen ist ein getaggtes
> Release, das die CI baut und bezeugt, plus eine einzige Listing-Anfrage —
> [der ganze Weg ist eine Seite](../publishing.md).

## Was es ist

`PluginService.ImportPluginFile` nimmt einen **Pfad zu einer
`.astraplugin`-Datei** — nicht die Bytes, und kein Verzeichnis. Astras UI
ruft es auf, wenn du eine Datei auswählst.

Das Bundle ist ein ZIP mit `MANIFEST.json` als erstem, gespeichertem
Eintrag. Der Daemon leitet jeden Digest neu ab, prüft, dass die Dateiliste
in beide Richtungen vollständig ist, und lehnt alles ab, das nicht
übereinstimmt. `astra-plugin verify` führt dieselben Prüfungen lokal aus,
und du solltest es ausführen, bevor du eine dir geschickte Datei
importierst ([installiere die CLI](../install-cli.md), falls du sie nicht
hast):

<!-- doctest: cli -->
```bash
astra-plugin verify some-plugin-0.3.0-linux-x64.astraplugin
```

## Die Obergrenze: vier Permissions werden pauschal verweigert

Eine importierte Datei hat keinen Katalog-Eintrag, also hat nichts ihre
Bytes gegensigniert und nichts ihren Autor gepinnt. Sie installiert auf
**Stufe 2**, und die Obergrenze dieser Stufe ist keine Warnung — die
Permissions werden **fallengelassen**:

| Verweigert, egal was das Manifest verlangt | Warum |
|---|---|
| `send_chat_message` | Löst einen AI-Turn aus, als hätte der Nutzer gesprochen |
| `set_theme_contribution` | Gestaltet die gesamte App um |
| `dom_access` | Führt den Code des Plugins im Astra-Fenster aus |
| `client` | Wird ein Chat-Frontend mit eigener Session |

`fire_trigger`, `subscribe_events`, `set_variable` und `push_to_ui`
überstehen die Obergrenze — sie sind das **risikoarme** Ende des
Vokabulars, weshalb es kein Listing braucht, das für sie bürgt, um sie
durchzulassen. Von den vieren bekommt nur `push_to_ui` eine eigene
Zustimmungs-Checkbox.

Die beiden Listen sind absichtlich verschieden, und es lohnt sich, genau
zu sein, welche welche ist:

| Liste | Mitglieder | Was sie entscheidet |
|---|---|---|
| `HIGH_RISK_PERMISSIONS` | `send_chat_message`, `push_to_ui`, `set_theme_contribution`, `dom_access`, `client` | jede bekommt ihre **eigene Zustimmungs-Checkbox**, auf jedem Installationsweg |
| `TIER2_REFUSED_PERMISSIONS` | `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` | **pauschal fallengelassen** bei einer von Hand importierten Datei, Zustimmung hin oder her |

Sie unterscheiden sich um genau eine ID: `push_to_ui` ist eine Checkbox
wert und nicht wert, eine Datei abzulehnen, die der Nutzer absichtlich zum
Import ausgewählt hat — es pusht Events nur in die eigenen Panels des
Plugins und sonst nirgendwohin. Beide Listen stehen in
`astra-plugin-manifest/src/permissions.rs`, von wo aus der Daemon, die CLI
und die Registry sie alle lesen, sodass keine dritte Liste entstehen kann.

Ein Plugin, das eine der vier verweigerten braucht, kann nicht auf diesem
Weg ausgeliefert werden. Es kann
[während der Entwicklung sideloaded](sideload.md) oder gelistet werden.

## Zustimmung, bevor irgendetwas geschrieben wird

`InspectPluginFile` liest das Manifest, **ohne zu installieren**: nichts
wird extrahiert, nichts startet, kein Trust-Record wird geschrieben, keine
Bytes werden aus dem Archiv herauskopiert. Die Datei wird im Speicher
geparst und geschlossen. Es aufzurufen und dann nie zu importieren
hinterlässt die Maschine genau so, wie sie war.

Das ist es, was Astra erlaubt, dir dasselbe Permission-Blatt zu zeigen wie
der Store-Weg, bevor du dich auf irgendetwas festlegst.

## Was du im Vergleich zum Store aufgibst

| | Store | Importierte Datei |
|---|---|---|
| Bytes von der Registry gegensigniert | ja | nein |
| Autor gepinnt, sodass ein Update aus einem anderen Repository verweigert wird | ja | nein |
| Widerruf (Revocation) erreicht dich | ja (sobald die Kette verankert ist) | nein |
| Updates | automatisch, mit Prüfung von Permission-Änderungen | du findest die nächste Datei selbst |
| Hochriskante Permissions | verfügbar, mit Zustimmung | **vier werden verweigert** |
| Verifikationsfehler | harte Blockade, kein Override | die Archivprüfungen gelten weiterhin |

Der Plan beschreibt, eine importierte Datei auf volles Vertrauen
hochzustufen, wenn ihr Digest in einem frischen Index auftaucht. **Diese
Höherstufung ist nicht implementiert** — ein Import bleibt für seine
gesamte Lebensdauer auf Stufe 2.

## Bevor du etwas importierst, das dir jemand geschickt hat

Ein Plugin ist ein nativer Prozess mit deinen vollen Benutzerrechten. Es
gibt keine Sandbox. Eine Datei zu importieren ist eine Entscheidung über
die Person, die sie geschickt hat, nicht über die Datei.
[Das Sicherheitsmodell](../1-orientation/security.md) sagt, was die
Mechanismen beweisen und was nicht.

Wenn es dein eigenes Plugin ist und du es noch schreibst, willst du
[`astra-plugin dev`](sideload.md), nicht das hier.
</content>
