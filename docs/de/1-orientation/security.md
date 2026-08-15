> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/1-orientation/security.md) maßgeblich.

# Das Sicherheitsmodell

Lies das, bevor du irgendetwas veröffentlichst, und bevor du irgendetwas
installierst.

## Der eine Satz

**Ein Plugin ist ein nativer Prozess, der mit den vollen Rechten deines
Benutzerkontos läuft.** Er kann deine Dateien lesen, Sockets öffnen und
Programme starten. Nichts in Astra sandboxt ihn, isoliert ihn oder schränkt
ihn auf Betriebssystemebene ein.

Das ist keine Lücke, die diese Seite beschönigt — es ist der aktuelle Stand
des Designs. Isolation ist **Phase 7** des Produktionsplans, dort benannt,
damit es eine Entscheidung ist und keine Auslassung, und sie ist **nicht
implementiert**. Kandidatenarbeit, wenn sie kommt: Landlock + seccomp unter
Linux, ein Low-Integrity-Token oder AppContainer unter Windows, rlimits. Bis
dahin sagen „signiert" und „gelistet" nichts darüber aus, was der Prozess mit
deiner Maschine anstellen kann.

Überall dort, wo Astra etwas anderes suggerieren könnte, ist es *verpflichtet*,
das laut zu sagen — sowohl das Installations-Einwilligungsblatt als auch das
Provenance-Panel tragen einen dauerhaften Hinweis, dass eine Attestation nicht
beweist, dass der Code sicher ist. Der Daemon sagt es bereits in der
Nachricht, mit der er eine unverifizierte Installation ablehnt: *„a plugin
runs as a native process with your full privileges, so an unverified one can
take over your machine"* (`astra-daemon/src/plugins/manager.rs`). Wie die
Bildschirme der App selbst aussehen, ist Astras Sache zu dokumentieren, nicht
die dieses Repositorys; diese Seite beschreibt den Daemon, die CLI und die
Formate.

## Was jeder Mechanismus tatsächlich beantwortet

Vier Schichten, vier verschiedene Fragen. Sie zu verwechseln ist, wie aus
„es ist signiert" „es ist sicher" wird.

| Schicht | Mechanismus | Verifiziert von | Beantwortet |
|---|---|---|---|
| 1. Build-Provenienz | GitHub-Artefakt-Attestation (Sigstore keyless, OIDC) | dem Registry-Bot, in der CI | „diese Bytes stammen aus Workflow W bei Commit C in Repository R" |
| 2. Distributionsvertrauen | Ed25519-Gegensignatur über den Artefakt-Digest, in einem signierten Index | dem Daemon, offline | „Astra hat genau diese Bytes gelistet, und sie wurden nicht zurückgezogen" |
| 3. Identitätskontinuität | ein TOFU-Pin auf `github:owner/repo` | dem Daemon, offline | „dieses Update stammt vom selben Autor wie die Installation" |
| 4. Laufzeit-Autorität | `[permissions]` + `require_permission` bei jedem Host-RPC | dem Daemon, bei jedem Aufruf | „was darf dieses Plugin Astra zu tun bitten" |

Keiner davon beantwortet „ist dieser Code sicher". Diese Frage hat keine
mechanische Antwort, und ein System, das das Gegenteil suggeriert, ist
schlimmer als eines, das es offen zugibt.

## Zwei Dinge, die heute wahr sind und nicht abgeschwächt werden

### Die Vertrauenskette ist spezifiziert, implementiert, und einen Link zu kurz verankert

Die Root-Schlüssel existieren, und die Delegation darunter jetzt auch. **Die
Signatur des Katalogs selbst nicht**, sodass auf der Maschine eines Nutzers
nichts verifiziert. Konkret
([`spec/registry-index.md` §0.1](../spec/registry-index.md)):

- die `root.json` der Registry trägt `"status": "provisioned"` und zwei
  Ed25519-Schlüssel, generiert am 2026-08-11 in einer Offline-Zeremonie;
- die `PRODUCTION_ROOT_KEYS` des Daemons listet dieselben zwei — diese Datei
  existiert, damit ein Dritter sie lesen kann, ohne eine Binärdatei zu
  zerlegen, und damit eine Abweichung zwischen beiden sichtbar wird;
- ein Root-Schlüssel signiert keinen Katalog: er signiert `trust.json`, das
  an einen Index-Signierschlüssel delegiert. **Dieses Dokument ist jetzt
  signiert.** `registry/v1/trust.json` verifiziert unter `astra-root-2026a`,
  delegiert an `astra-index-2026a` und benennt den einen
  Reusable-Workflow-Commit, den der Bot der Registry in einer
  Build-Attestation akzeptiert. `node tools/sign-trust.mjs --verify
  registry/v1/trust.json` der Registry selbst gibt genau das aus. Also feuert
  die Ingest-seitige Sperre `E_TRUST_UNPROVISIONED` nicht mehr;
- **aber `registry/v1/index.json` trägt weiterhin `"signatures": []`**, und
  `revocations.json` ebenso. Ohne Signatur auf dem Katalog gibt es nichts,
  das der delegierte Schlüssel prüfen könnte, und jeder Katalog wird weiterhin
  als `UNSIGNED` eingestuft — mit Grund **`NoSignatures`**, nicht
  `NoTrustAnchor`: der Anker ist angekommen, die Signaturen nicht.
  `NoTrustAnchor` ist der ältere und schlechtere Fall und heißt, dass gar kein
  verifiziertes `trust.json` den Build erreicht hat;
- und weil Widerrufslisten strikt verifiziert werden, wird eine unsignierte
  abgelehnt, also **ist die Durchsetzung von Widerrufen ebenfalls nicht
  aktiv**.

Ein Standard-Build fällt also weiterhin geschlossen aus (fail closed).
Nichts hier ist ein Versprechen über eine Garantie, die du heute hast; der
Mechanismus trägt erst dann Gewicht für einen Nutzer, wenn ein signierter
Index existiert, und nicht früher.

### Ein lokaler Signierschlüssel verleiht überhaupt kein Vertrauen

`astra-plugin keygen` und `astra-plugin sign` existieren. Sie sind ein
optionaler zweiter Faktor — Verteidigung in der Tiefe gegen eine Übernahme
eines GitHub-Kontos, wobei der Wert darin liegt, dass der Schlüssel dort
liegt, wo eine gestohlene GitHub-Sitzung nicht ist.

Sie sind **nicht** das, was Astra dazu bringt, ein Plugin zu installieren,
und ein mit deinem eigenen Schlüssel signiertes Bundle ist genauso
untrusted wie ein unsigniertes. Der Daemon prüft das In-ZIP-Paar
`SIGNATURE`/`PUBKEY` gegen einen *gepinnten Astra-Publisher-Schlüssel*,
niemals gegen den Schlüssel im Archiv selbst. `astra-plugin build` sagt das
bei jedem Lauf:

<!-- doctest: output from="astra-plugin build ." -->
```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
```

und `astra-plugin sign` sagt das bei Erfolg, absichtlich nicht in `--help`
versteckt:

<!-- doctest: output from="astra-plugin sign <bundle>" -->
```
This signature is an optional second factor, not a trust signal.

Astra does not verify it against your key — the daemon checks the in-ZIP pair against a
pinned Astra publisher key, so a bundle signed with your own key is untrusted by
construction, exactly as an unsigned one is.
```

Das In-ZIP-Paar ist ein auslaufendes Format-Feature; sowohl der Befehl als
auch die Einträge, die er schreibt, stehen zur Entfernung an.

Es gibt kein `astra-plugin login`, und es wird auch keines geben:
Veröffentlichen läuft über ein Repository und ein Tag, also gibt es keine
Zugangsdaten zu speichern und keine, die durchsickern könnten.

## Was das Permission-Gate tut

Der Daemon setzt `[permissions]` an genau einer Stelle durch:
`require_permission`, bei sechs der zehn `PluginHostService`-RPCs. Die
anderen vier — `Register`, `GetPluginSelfConfig`, `PluginLog` und
`GetDaemonInfo` — sind **immer erlaubt** und laufen ohne jede
Berechtigungsprüfung; sie sind `(…, None)` in der Tabelle
`HOST_RPC_PERMISSIONS` des Daemons, und in ihrem Rumpf gibt es keinen
`require_permission`-Aufruf. Ein registriertes Plugin mit leerem
`[permissions]`-Block erreicht genau diese vier und sonst nichts. Warum sie
frei sind, steht
[in der Permissions-Referenz](../3-reference/permissions.md#die-vier-kostenlosen-aufrufe).
Die Tabelle, die `require_permission` liest — `HOST_RPC_PERMISSIONS` im
Daemon — ist über Paritätsregel R6 an
[`spec/hooks.yaml`](../../../spec/hooks.yaml) gepinnt, sodass die generierte
[Permission-Spalte](../reference/parity.md) nicht vom durchsetzenden Code
abweichen kann.

Zwei unabhängige Tore, und beide müssen passieren
([`spec/permissions.md` §4.2](../spec/permissions.md)):

1. **die Gewährung (grant)** — eine pro Installation gegebene Antwort, die
   ein Einwilligungsblatt erzeugt hat und die ein Trust-Record festhält;
2. **die Obergrenze (ceiling)** — eine pro Herkunft geltende Regel, die kein
   Record überkaufen kann.

Das Manifest ist eine *Anfrage*. Für die Stufen 1 und 2 liegt die gewährte
Menge dort, wo das Plugin sie nicht schreiben kann, denn ein Plugin, das
seine eigenen Gewährungen durch Bearbeiten seines eigenen Manifests erweitern
könnte, hätte ein Permission-System, das nur ein Kommentar ist.

**Stufe 3 ist die Ausnahme, und das mit Absicht.** Für ein sideload­etes
Quellverzeichnis liefert `decide_grants` des Daemons
`declared.capped(|_| true)` — das Manifest *ist* der Zustimmungs-Nachweis, bei
jedem Laden aus dem eigenen Verzeichnis des Plugins gelesen, ohne Obergrenze
darüber. Ein sideload­etes Plugin kann daher seine eigenen Permissions durch
Bearbeiten seiner eigenen `plugin.toml` zwischen Neustarts erweitern, bis hin
zum gesamten Vokabular. Das ist ein weiterer Grund, warum der Entwicklermodus
ein Entwicklerwerkzeug ist und kein Installationsweg.

Fünf Permissions sind hochriskant und bekommen jeweils eine eigene
Zustimmungs-Checkbox: `send_chat_message`, `push_to_ui`,
`set_theme_contribution`, `dom_access`, `client`. `dom_access` bekommt einen
zweiten Bildschirm. Details, einschließlich wie man einen `reason` schreibt,
der sich zu lesen lohnt: [Permissions](../3-reference/permissions.md).

## Die Herkunft eines Plugins bestimmt seine Obergrenze

| Stufe | Quelle | Obergrenze |
|---|---|---|
| **1 · Registry** | aus dem Store installiert, verifiziert | alles, was angefragt wurde, vorbehaltlich Zustimmung. Kein Override bei einem Verifikationsfehler |
| **2 · Lokale Datei** | eine von Hand importierte `.astraplugin` | `send_chat_message`, `set_theme_contribution`, `dom_access` und `client` werden **pauschal verweigert, nicht nur mit Warnung versehen** |
| **3 · Sideload** | ein Quellverzeichnis, Entwicklermodus an | **keine Obergrenze** — und es startet nie automatisch |

Stufe 3 ist absichtlich unbegrenzt: es ist die Entwicklungsschleife für
UI-Plugins, und eine Begrenzung würde `dom_access` unentwickelbar machen. Sie
ist außerdem hinter eine explizite Einstellung gesperrt, startet nach einem
Neustart nie von selbst und ist
[als Entwicklerwerkzeug dokumentiert](../5-publish/sideload.md), nicht als
Installationsweg.

Vier Zustände bekommen **nichts**, egal was das Manifest sagt: `Untrusted`,
`TamperDetected`, `Revoked`, und ein `Verified`-Plugin, dessen Record nicht
geglaubt werden kann. Ein vor der Existenz von Trust-Records installiertes
Plugin (`Unrecorded`) bekommt sein Manifest auf die Obergrenze von Stufe 2
gekappt — „irgendwoher angekommen, nichts bewiesen" ist genau diese Form.

## Wogegen nicht verteidigt wird

Benannt, statt einer Leserin zum Entdecken überlassen:

| Bedrohung | Status |
|---|---|
| Ein Plugin liest deine Dateien, deine Schlüssel, dein Netzwerk | **Nicht verteidigt.** Es existiert keine Isolation — Phase 7 |
| Ein Plugin liest `daemon.token` und registriert sich als Client | **Nicht verteidigt.** Gleicher Grund |
| Eine bösartige oder kompromittierte Registry liefert andere Bytes | Verteidigt *per Design* — der Index gegensigniert einen Digest, und der Daemon hasht neu — **aber nicht in Kraft**: die Roots sind bereitgestellt (`registry/v1/root.json`, dieselben zwei in den Daemon kompilierten Schlüssel), und der Katalog-Index, den sie signieren, ist weiterhin unsigniert |
| Eine bereits installierte, zurückgezogene Version | Spezifiziert; heute nicht durchgesetzt, weil eine unsignierte Widerrufsliste abgelehnt wird |
| Ein anderer lokaler Prozess ruft den Capability-Server deines Plugins auf | **Verteidigt.** Der Daemon legt bei jedem Aufruf das Spawn-Token vor und setzt `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, sodass das SDK einen Aufruf ohne dieses Token ablehnt. Unter einem Daemon, der zu alt ist, um den Header zu senden, bleibt das SDK bei `warn` — ein falsches Token wird abgelehnt, ein fehlendes akzeptiert — weil es sonst nichts tun könnte |
| Ein Plugin bearbeitet sein eigenes Manifest, um seine Permissions zu erweitern | **Verteidigt auf den Stufen 1 und 2** — Gewährungen stammen aus einem vom Daemon verwalteten Trust-Record, nicht aus dem Manifest. **Nicht verteidigt auf Stufe 3**: bei einem sideload­eten Verzeichnis *ist* das Manifest die Gewährung und hat keine Obergrenze, sodass es jede Permission im Vokabular durch Bearbeiten seiner eigenen Datei erwerben kann |
| Ein von Hand platzierter Sideload-Marker | Verteidigt. Der Daemon lehnt einen Marker ab, den er nicht selbst geschrieben hat |

## Für Nutzer, in einem Absatz

Installiere aus Astra heraus. Der Store-Pfad pinnt das Artefakt über den
Digest, und Verifikationsfehler sind harte Blockaden ohne Override. Wenn dir
jemand eine `.astraplugin`-Datei schickt, ist der Import eine Entscheidung,
die du über diese Person triffst, und vier Permissions werden verweigert,
egal was die Datei verlangt. Wenn dir jemand sagt, du sollst den
Entwicklermodus einschalten und Astra auf einen Ordner zeigen lassen, bittet
dich diese Person, unsignierten Code als du selbst auszuführen.

## Siehe auch

- [`spec/registry-index.md`](../spec/registry-index.md) — die Dokumentformate und der Verifikationsalgorithmus, normativ
- [`spec/permissions.md`](../spec/permissions.md) — Gewährungen, Obergrenzen, Zustimmung, `permissions_hash`
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — was in einer `.astraplugin` steckt und was ein Verifier ablehnen muss
- [Fehlerbehebung](../6-operate/troubleshooting.md) — was jeder Verifikationsfehler bedeutet, wenn du auf ihn stößt
</content>
