> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/spec/registry-index.md) maßgeblich.

# Die signierten Registry-Dokumente — normative Spezifikation

**Status:** normativ für die Dokumentformate und die
Verifikationsregeln. **Noch nicht in Kraft:** die hier beschriebene
Signaturkette ist spezifiziert, auf beiden Seiten implementiert und
**nicht verankert** — siehe §0.1, bevor du dich auf irgendeinen Satz in
dieser Datei als Sicherheitsgarantie verlässt.

Vier Dokumente, drei Schemas, eine Signaturkonstruktion:

| Dokument | Schema-String | Signiert von | Kopie dieses Repos |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **nichts** — es ist ein Abzug der in Astra kompilierten Schlüssel | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | ein **Root**-Schlüssel | neben dem Katalog veröffentlicht |
| `index.json` | `astra.registry.index/1` | ein **Index**-Schlüssel, an den `trust.json` delegiert | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | derselbe Index-Schlüssel | `astra-registry/registry/v1/revocations.json` |

Anforderungswörter folgen RFC 2119.

---

## 0. Was diese Kette beantwortet, und was nicht

Sie beantwortet: *ist das der Katalog, den die Astra-Registry
veröffentlicht hat, ist er aktuell, und wurde etwas darin
zurückgezogen?* Es ist das Einzige, was einen gecachten Record sicher
zum Installieren macht, weil der Record einen Artefakt-Digest pinnt und
ein Digest nicht abläuft.

Sie beantwortet **nicht** *wer das Plugin gebaut hat*. Das ist die
GitHub-Build-Attestation, vom Registry-Bot beim Ingest geprüft (§7), nie
vom Daemon. Was der Daemon hält, ist eine Registry-*Behauptung* über den
Autor, beim ersten Install gepinnt (TOFU) und an die Download-URL
gebunden — siehe §7.3. Der UI-Text ist verpflichtet, „gleicher Autor wie
zuvor" zu sagen und nie „verifizierter Build".

### 0.1 Die Kette ist noch nicht verankert — lies das zuerst

* `astra-registry/registry/v1/root.json` trägt
  `"status": "provisioned"` und zwei Ed25519-Schlüssel. Die Zeremonie in
  `astra-registry/SECURITY.md` §4 (`tools/keygen-root.sh`) lief am
  2026-08-11 offline.
* Der Daemon-`PRODUCTION_ROOT_KEYS` listet dieselben zwei. Die
  Registry-Kopie ist öffentlich, damit ein Dritter sie lesen kann, ohne
  eine Binärdatei zu zerlegen, und damit eine Abweichung zwischen
  beiden sichtbar wird; die privaten Hälften waren nie auf einer
  vernetzten Maschine.
* **Ein Root-Schlüssel signiert keinen Katalog.** Er signiert
  `trust.json`, das an einen Index-Signierschlüssel delegiert. **Dieses
  Dokument ist jetzt signiert.** `registry/v1/trust.json` verifiziert
  unter `astra-root-2026a`, delegiert an den Index-Signierschlüssel
  `astra-index-2026a`, und benennt den einen
  Reusable-Workflow-Commit, den der Bot in einer Build-Attestation
  akzeptiert (`e3329df252a46d747676cb540ae4b986af68a3ad`, worauf das
  Tag `plugin-release/v1` zeigt). Die eigene
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` der
  Registry gibt alle drei Tatsachen aus. Also feuert
  `E_TRUST_UNPROVISIONED` beim Ingest nicht mehr.
* Also heute: `trust.json` verifiziert, und ein Index-Schlüssel ist
  delegiert, aber **nichts hat den Katalog damit signiert**. Jeder
  Katalog wird weiterhin als `UNSIGNED` eingestuft, doch die Zeremonie hat
  den Grund geändert — von `NoTrustAnchor` zu **`NoSignatures`**.
  `classify_signature` im Daemon trennt die beiden genau: `NoTrustAnchor`
  heißt, dass kein verifiziertes `trust.json` den Build erreicht hat, es
  also keinen Schlüssel gibt, gegen den irgendeine Signatur geprüft werden
  könnte — der Katalog kann durchaus signiert sein; `NoSignatures` heißt,
  der Anker ist da und der Katalog selbst trägt keine. Was sich verschoben
  hat, ist, welcher Link fehlt: die Lücke liegt jetzt zwischen dem
  delegierten Schlüssel und dem Index, nicht zwischen der Root und der
  Delegation.
* `registry/v1/index.json` und `registry/v1/revocations.json` sind mit
  `"signatures": []` committed — „unsigniert" laut ausgesprochen, wo
  ein fehlendes Member nicht von einem entfernten unterschieden werden
  könnte.
* Konsequenzen, die daraus folgen und nicht wegkaschiert werden dürfen:
  ein unsignierter Katalog kann einen Record nie auf
  installierbar-mit-vollem-Vertrauen hochstufen, und weil
  `verify_revocations_document` strikt ist (§6.4), **wird eine
  unsignierte Widerrufsliste abgelehnt, die Durchsetzung von Widerruf
  ist also ebenfalls nicht aktiv** — `RevocationFreshness::NotEnforced`,
  bis einmal eine signaturgültige Liste geholt wird.

Alles unten beschreibt das Format und den Algorithmus, und nichts davon
ändert sich, wenn der verbleibende Link ankommt. Die Root-Zeremonie ist
bereits gelaufen, und die Delegation ist signiert; was fehlt, ist, dass
eine Signatur im `signatures`-Array eines veröffentlichten
`index.json` erscheint, an dem Punkt fängt die Kette an, auf der
Maschine eines Nutzers Gewicht zu tragen.

## 1. Der Umschlag

Jedes signierte Dokument hat dieselbe äußere Form:

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **Nur `signed` ist authentifiziert.** Nichts außerhalb davon darf als
  Tatsache gelesen werden — nicht `$comment`, nicht die
  `key_id`-Strings, nicht die eigene Form der Signaturliste.
* `sig` ist Base64 der rohen **64-Byte-Ed25519-Signatur**. Das
  Index-Schema pinnt die Schreibweise: `^[A-Za-z0-9+/]{86}==$`.
* `key_id` ist ein **Hinweis** für Logging und Schlüsselauswahl. Ein
  Verifier **MUSS** jeden vertrauten Schlüssel gegen jede angebotene
  Signatur ausprobieren und **MUSS** die `key_id` des Schlüssels
  melden, der tatsächlich verifiziert hat, nie die, die das Dokument
  behauptet hat. Ein Dokument, das darüber lügt, wer es signiert hat,
  verifiziert trotzdem, wenn ein vertrauter Schlüssel es getan hat, und
  verifiziert nie, nur weil es den richtigen Schlüssel benannt hat.
* Ein leeres `signatures`-Array bedeutet unsigniert. Das ist keine
  Fehlerform; es ist der Zustand vor der Zeremonie und der Zustand
  jedes handgeschriebenen lokalen Katalogs.

## 2. Der Signier-Input

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` ist der Schema-String des Dokuments: `astra.registry.trust/1`,
  `astra.registry.index/1`, oder `astra.registry.revocations/1`.
* **Der Verifier liefert `domain` aus seiner eigenen Konstante, nie aus
  dem `schema`-Member der Datei, die er liest.** Sonst wäre eine
  Signatur über eine `trust.json` durch Bearbeiten eines Strings als
  Signatur über eine `index.json` wiederverwendbar — und jeder, der
  einen Katalog signiert bekommen könnte, könnte dann eine *leere*
  Widerrufsliste veröffentlichen und den Mechanismus abschalten.
* Das `0x00` ist das, was eine Domäne, die ein Präfix einer anderen
  ist, davon abhält, mit ihr zu kollidieren.
* Ed25519-Verifikation **SOLLTE** strikt sein
  (`ed25519_dalek::verify_strict`, oder gleichwertig): schwach-geordnete
  öffentliche Schlüssel und die formbaren Kodierungen ablehnen, die ein
  permissiver Verifier akzeptiert.
* Die Signatur ist über den SHA-256-Digest, an Ed25519 als gewöhnliche
  Nachricht übergeben. Aktiviere keinen „pre-hashed"-Modus; Ed25519
  hasht intern, und diese Konstruktion füttert es mit 32 Bytes.

Beide Seiten davon existieren und stimmen per Test überein:
`astra-registry/bot/lib/sign.mjs` (`signingDigest`, `signEnvelope`,
`verifyEnvelope`) und `astra-daemon/src/plugins/trust.rs`
(`signing_digest`, `verify_envelope`). `astra-registry/bot/fixtures/index/`
hält ein vom JavaScript-Signer erzeugtes Dokument, das der
Rust-Verifier Byte für Byte prüft, sodass keines von beiden ohne roten
Build abdriften kann.

## 3. Kanonisierung (JCS-Profil)

`JCS(signed)` ist RFC 8785 kanonisches JSON, mit einer absichtlichen
Verengung.

* **Objektschlüssel werden nach UTF-16-Code-Unit sortiert** (RFC 8785
  §3.2.3). Das tut JavaScripts Standard-`Array.prototype.sort()`, und
  die Rust-Seite schreibt es explizit aus
  (`a.encode_utf16().cmp(b.encode_utf16())`), statt Byte-Reihenfolge
  anzunehmen. Für rein ASCII-Schlüssel stimmen die beiden Reihenfolgen
  überein; oberhalb der BMP nicht.
* **Keine unbedeutende Whitespace.** Kompakte Form.
* **Strings** werden escaped, wie von RFC 8785 §3.2.2.2 verlangt: `"`,
  `\` und die C0-Steuerzeichen escapen (Kurzformen, wo sie existieren),
  `/` und alles Nicht-ASCII als wörtliches UTF-8 belassen.
* **Zahlen MÜSSEN Ganzzahlen in ±(2^53 − 1) sein** — JavaScripts
  `Number.MAX_SAFE_INTEGER`. Beide Implementierungen **lehnen** alles
  andere **ab**, statt die Fließkomma-Kanonisierung aus §3.2.2 zu
  implementieren. Die Registry gibt nur Ganzzahlen aus (`serial`,
  `size`, `protocol`), und eine Implementierung, die §3.2.2 *fast*
  richtig hinbekommt, erzeugt Signaturen, die auf einer Seite
  verifizieren und auf der anderen nicht. `1.0` und `1` sind dieselbe
  JSON-Zahl und beide serialisieren als `1`.
* **Doppelte Objektschlüssel MÜSSEN zur Parse-Zeit abgelehnt werden**,
  nicht aufgelöst (RFC 8785 §3.1). `{"a":1,"a":2}` bedeutet zwei
  Dinge, und ein signiertes Dokument muss eines bedeuten. Bytes nach
  dem Dokument werden aus demselben Grund abgelehnt.
* Member, deren Wert `undefined` ist, existieren nicht; so etwas gibt
  es in JSON nicht. (Der Serialisierer der Registry lässt sie weg; ein
  JSON-Parser erzeugt nie einen.)

Die im Repository committede hübsche Datei wird vom *selben*
Serialisierer (`stableStringify`) mit derselben Schlüsselreihenfolge
erzeugt, ein Reviewer, der einen Diff liest, liest also die Bytes, die
signiert werden, modulo Whitespace.

## 4. Schlüssel, Delegation und Rotation

### 4.1 Roots

* Ed25519. Öffentliche Hälften sind **in Astra kompiliert**, Base64 der
  rohen 32 Bytes.
* **Zwei Slots**, in einer Offline-Zeremonie generiert: einer `Active`,
  einer `Reserve`, der nie benutzt wird, bis ein Root ersetzt werden
  muss. Beide werden von Tag eins an ausgeliefert, ein Root zu ersetzen
  ist also eine Signatur statt ein Stichtag.
* Ein Root signiert **`trust.json` und nichts sonst**. Eine
  Root-Signatur erscheint nie auf `index.json`, auf
  `revocations.json`, oder auf einem Bundle.
* `root.json` ist ein Abzug, keine Autorität: es ist absichtlich
  unsigniert — ein selbstsigniertes Root-Dokument beweist nichts, was
  der einkompilierte Schlüssel nicht schon beweist. Es existiert,
  damit die beiden Kopien verglichen werden können. Der
  `fingerprint_sha256` jedes Eintrags ist SHA-256 über den rohen
  32-Byte-öffentlichen Schlüssel, Kleinbuchstaben-Hex; derselbe Wert,
  den `tools/keygen-root.sh` ausgibt und den der Daemon loggt, wenn
  eine Root-Signatur verifiziert.
* Test-Roots existieren (`astra-registry/tools/testkeys/`, private
  Hälften absichtlich committed, `key_id` mit `TEST-ONLY-DO-NOT-TRUST-`
  vorangestellt). Der Daemon kann sie nur hinter dem
  Nicht-Default-Feature `insecure-test-trust-roots` **in einem
  Debug-Profil** einkompilieren; sie in einem Release-Profil zu
  verlangen ist ein `compile_error!`.

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

Verifikationsregeln:

* `serial` **DARF NICHT** 0 sein — 0 ist auf der Seite des Verifiers
  die „noch nichts akzeptiert"-Sentinel, ein veröffentlichtes Dokument
  darf sie also nicht beanspruchen.
* `schema` **MUSS** `astra.registry.trust/1` sein. Prüfe es vor der
  Signatur rein damit ein falsch abgelegtes Dokument „falsches Schema"
  sagt statt „kein Root hat das signiert"; es kann das Ergebnis nicht
  ändern, weil die Digest-Domäne die eigene Konstante des Verifiers
  ist.
* Unbekannte Member werden **behalten und ignoriert**. Eine neuere
  Registry, die ein Feld hinzufügt, darf einen älteren Daemon nicht
  bricken, und das rohe verifizierte `signed` übersteht einen
  Round-Trip, sodass nichts still fallengelassen und neu signiert wird.
* Ein `index_keys`-Eintrag mit einem nicht parsbaren Schlüssel oder
  einem nicht parsbaren Fenster wird **mit einer Warnung
  übersprungen**, nicht fatal: eine schlechte Zeile darf nicht einen
  Katalog kosten, den ein anderer Schlüssel verifizieren könnte. Ein
  nicht parsbares `not_before` wird als *noch nicht gültig* behandelt
  und ein nicht parsbares `not_after` als *abgelaufen* — fail closed
  auf der Zeile, offen auf dem Dokument.
* `reusable_workflow_shas` ist die Allowlist der aufgelösten
  Reusable-Workflow-Commit-SHAs, die der **Registry-Bot** durchsetzt
  (§7). Der Daemon trägt sie mit, benutzt sie aber nicht. Sie zu ändern
  ist eine Root-Schlüssel-Zeremonie, was der ganze Sinn ist, sie hier
  abzulegen.

**Rotation.** Vierteljährlich, und sofort bei Verdacht. Eine geplante
Rotation veröffentlicht eine `trust.json`, in der der ausgehende und
der eingehende Schlüssel **überlappende Fenster für 30 Tage** haben,
sodass `index_keys_valid_at(now)`, das zwei Schlüssel zurückgibt, der
normale Zustand während einer Umstellung ist, keine Anomalie.

### 4.3 Welche Uhr ein Schlüsselfenster beurteilt

Zwei Uhrablesungen existieren: die dieser Maschine, und das
HTTP-`Date` des Fetches, der das Dokument erzeugt hat.

* **Aktualität** (§5) wird bei `now = server_date ?? local` beurteilt —
  glaube der Uhrablesung der Registry für die Dauer eines Fetches. Das
  kostet einen Angreifer nichts, was er nicht schon hatte (er könnte
  einer Maschine, deren Uhr er nicht kontrolliert, ein veraltetes
  Dokument servieren), und rettet den weit häufigeren Fall: ein Laptop
  mit falscher Uhr, dem gesagt wird, sein Katalog sei abgelaufen.
* **Schlüssel-Gültigkeitsfenster** werden bei
  `window_now = max(local, server)` beurteilt — das Netzwerk darf „now"
  *vorwärts* ziehen und **niemals** zurückschieben. `not_after` ist der
  einzige Mechanismus, der einen kompromittierten Index-Schlüssel
  ausmustert; ihn bei einem netzwerkgelieferten Zeitpunkt zu beurteilen
  würde dem Dieb erlauben, auch den Tag zu wählen, für immer, indem er
  mit einem alten `Date` antwortet. Die spätere Ablesung zu nehmen
  macht einen gestohlenen ausgemusterten Schlüssel *stärker*
  abgelaufen, welche Ablesung der Angreifer auch kontrolliert.
* Eine Diskrepanz über **2 Stunden** hinaus
  (`CLOCK_SKEW_TOLERANCE_HOURS`) ist selbst das Signal: das Urteil wird
  `CLOCK_SKEW` statt einer Behauptung über das Dokument. Klein genug,
  dass eine tote CMOS-Batterie es sofort auslöst, groß genug, dass
  gewöhnlicher NTP-loser Drift es nicht tut.
* Alles **Dauerhafte**, das aus einer Uhr geschrieben wird
  (Last-Fetch-Zeitstempel, Untergrenzen), wird zuerst auf die lokale
  Uhr geklammert. Eine Antwort mit `Date: Fri, 01 Jan 2100 …` würde
  sonst die Vorstellung eines Daemons von der Gegenwart dauerhaft auf
  2100 verschieben — ein dauerhafter Denial-of-Service, geschrieben von
  jedem, der einen Fetch beantworten kann.

## 5. `index.json`

### 5.1 Form

`signed` ist:

| Member | Typ | Regel |
|---|---|---|
| `schema` | const `astra.registry.index/1` | erforderlich |
| `serial` | integer ≥ 0 | erforderlich, monoton (§5.4) |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | **beim Signieren** gestempelt, im committeden Baum abwesend |
| `expires_at` | gleich | `issued_at + 30 Tage` |
| `plugins` | array | ein Record pro gelistetem Plugin, nach `id` sortiert |

Zeitstempel sind RFC 3339 UTC, **Sekundenpräzision, keine
Millisekunden, kein Offset**. Zwei Schreibweisen eines Zeitpunkts sind
zwei verschiedene signierte Dokumente.

Ein Plugin-Record trägt `id`, `name`, `version`, `description`,
`license`, `capabilities`, `repository_url`, `source`, `icon_url`,
`downloads`, `stars`, `updated_at`, `download_url`,
`platform_downloads` und `releases[]`. Das vollständige JSON Schema ist
`astra-registry/schema/index-v1.json`; es ist
`additionalProperties: false` und die Autorität für die Feldliste.

Zwei Regeln sind es wert, wiederholt zu werden, weil ein Verifier von
ihnen abhängt:

* **`releases[]` ist die autoritative Hälfte**, neueste zuerst nach
  Semver-Präzedenz. Jedes Release hat `version`, `published_at`,
  `release` (`{kind: "github_release", repo, tag}` oder
  `{kind: "direct", base_url}`) und `artifacts` (Plattform-Schlüssel →
  `{url, filename, sha256, size}`).
* **Die flachen Felder sind eine Projektion** von `releases[0]`,
  berechnet im selben Generator-Durchlauf, sie können also nicht mit
  ihr uneins sein. `version`, `platform_downloads` und `download_url`
  existieren, weil der ausgelieferte Daemon genau diese liest.

Plattform-Schlüssel: `linux-x64`, `windows-x64`, `noarch`, plus die
reservierten `linux-arm64`, `windows-arm64`, `macos-x64`,
`macos-arm64`. Ein `noarch`-Artefakt wird unter **jedem unterstützten
Plattform-Schlüssel** geschrieben, sodass kein Client das Wort kennen
muss (`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`).

`downloads` und `stars` sind immer `0`. Diese Registry zählt nichts.

**Staging-Einträge** — ein Listing, dessen Release auf dem Papier
existiert, aber noch keinen Artefakt-Digest hat — sind mit
`staging: true` markiert, sind **aus `platform_downloads` und
`download_url` ausgelassen**, und sind per Konstruktion
uninstallierbar: kein Digest, keine Installation.

### 5.2 Der Artefakt-Digest, und wohin URLs zeigen dürfen

`artifacts.<key>.sha256` ist `sha256` der gesamten
`.astraplugin`-Datei — dieselbe Zahl wie der Attestations-Subjekt und
was der Daemon hasht
([`bundle-v2.md` §3.1](bundle-v2.md#31-artefakt-digest)). `size` ist
die Länge dieser Datei; das Schema deckelt sie bei 256 MiB.

Jede Artefakt-URL **MUSS** `https://` sein und **MUSS** unter dem
Präfix liegen, das ihr eigenes `release`-Objekt impliziert:

* `github_release` →
  `https://github.com/<repo>/releases/download/<tag>/`,
* `direct` → der `base_url` des Releases,

und **MUSS** auf den deklarierten `filename` enden. Das wird in
`astra-registry/tools/validate.mjs` durchgesetzt, nicht durch ein
Schema-Pattern, weil ein Pattern, das nur GitHub beschreiben konnte,
den selbst gehosteten Fall unaussagbar machte. `direct` existiert für
selbst gehostete und Staging-Kataloge; Policy hält es aus dem
öffentlichen Katalog heraus.

### 5.3 Determinismus — die Eigenschaft, auf die sich ein Auditor stützt

Das `signed`-Member von `index.json` wird von `tools/build-index.mjs`
aus `plugins/**` generiert und **liest keine Uhr**: gleiche Quellen +
gleiche Serial → gleiche Bytes. Schlüssel nach UTF-16-Code-Unit
sortiert, Plugins nach ID, Releases nach Semver. `--check` schlägt
fehl, wenn die committede Datei um ein Byte abweicht, und CI führt es
aus.

`issued_at`/`expires_at` werden von `bot/sign-index.mjs` beim Signieren
hinzugefügt, nicht vom Generator, aus zwei Gründen: sie sind
Eigenschaften der *Veröffentlichung*, und ein Generator, der eine Uhr
läse, könnte nicht reproduziert werden. Das ist es, was das Audit aus
§8 überhaupt möglich macht — ein Dritter kann den Katalog-Inhalt aus
dem Git-Baum neu bauen und ihn mit dem vergleichen, was signiert wurde.

### 5.4 Serial

* **Monoton**, abgeleitet aus `git rev-list --count HEAD -- plugins`
  auf dem Default-Branch. Nie aus einer Datei gelesen-und-erhöht: zwei
  Merges in derselben Minute lesen beide *N* und schreiben beide
  *N+1*, und der zweite hebt den ersten still auf. Ein Commit-Count ist
  eine Eigenschaft der Historie, gleichzeitige Merges bekommen also per
  Konstruktion unterschiedliche Werte. Pfadbegrenzung bedeutet, dass
  ein Docs-Commit die Versionsnummer des Katalogs nicht bewegt.
* Ein Verifier hält eine **Serial-Untergrenze** pro Katalog-URL und
  lehnt alles darunter ab. Die Untergrenze ist
  `max(im Speicher, auf der Festplatte)` und lebt in vom Daemon
  gehaltenem, MACtem Zustand (`astra.registry.state/1`), **nicht** im
  Index-Cache: der Cache ist eine Bequemlichkeit, die jederzeit
  gelöscht werden kann, und die Untergrenze ist eine
  Sicherheitsentscheidung, die genau das Löschen überstehen muss, das
  ein Angreifer durchführen würde. Sie ist *im Code* monoton, sodass
  das Korrumpieren der Zustandsdatei die Datei zurücksetzt und nicht
  den laufenden Prozess.

Drei Dokumente, drei Serial-Regeln, und die Unterschiede sind
absichtlich:

| Dokument | Akzeptiert, wenn | Warum |
|---|---|---|
| `trust.json` | **strikt größer** als das Gehaltene | es ändert sich nur bei einer Schlüsselrotation, „gleiche Serial, andere Bytes" ist also ein Rollback-Versuch und nichts sonst |
| `index.json` | **nicht unter** der Untergrenze | gewöhnliche Neuveröffentlichung |
| `revocations.json` | **größer oder gleich** auf der Festplatte; eine **strikt größere** Serial ersetzt die Menge, eine kleinere-oder-gleiche darf nur **hinzufügen** | die Liste wird nach Zeitplan neu signiert, um innerhalb ihres 7-Tage-Fensters zu bleiben; Gleichheit abzulehnen würde jede ruhige Woche Installationen blockieren machen. „Gleiche Serial, weniger Einträge" ist ein Replay, und Nur-Hinzufügen besiegt das |

Die MAC auf der Zustandsdatei ist ein **Stolperdraht, keine Grenze**:
der Schlüssel lebt im selben 0700-Verzeichnis wie die Datei, die er
authentifiziert, ein Angreifer, der dieses Verzeichnis lesen kann, kann
ihn also fälschen. Es hebt die Hürde von „eine Datei bearbeiten" auf
„den Schlüssel finden und benutzen". Die echte Grenze ist das
Verzeichnis — ein Geschwister von `plugins/`, nie ein Kind, sodass das
Subjekt dieser Entscheidungen nicht auch ihr Autor ist.

### 5.5 Aktualität, und die Asymmetrie, auf die es am meisten ankommt

| Dokument | TTL | Was Veraltung kostet |
|---|---|---|
| `index.json` | **30 Tage** (`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`) | ein **Banner**. Browse sagt, der Katalog sei alt. **Gecachte, digest-gepinnte Records bleiben installierbar.** |
| `revocations.json` | **7 Tage** (`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`) | eine **harte Blockade** neuer Installationen |

Diese Asymmetrie ist die gesamte Aktualitäts-Policy, und sie folgt
daraus, wofür jedes Dokument da ist. Ein Katalog-Record ist ein
*Digest*, und ein Digest läuft nicht ab: ein Angreifer, der die
Registry einfriert, sodass du einen Record behältst, den du bereits
verifiziert hast, gewinnt nichts. Eine Widerrufsliste ist das
Gegenteil — „weitermachen" bedeutet dort „weiter etwas installieren,
das wir vielleicht schon zurückgezogen haben" — also ist das die
Blockade:

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

Beachte den letzten Satz. Veraltung stoppt nie ein bereits laufendes
Plugin.

Urteils-Codes, die ein konformer Client ausgibt, schwerste zuerst
(`IndexVerdict::code`):

| Code | Bedeutung |
|---|---|
| `SIGNATURE_INVALID` | Signaturen wurden angeboten und keine wurde von einem vertrauten Schlüssel gemacht. **Der einzige Code, der Manipulation bedeutet.** Keine Uhr ist beteiligt, um dazu zu kommen, keine Uhr kann es also entschuldigen. |
| `SIGNATURE_KEY_EXPIRED` | ein delegierter Schlüssel hat es signiert, außerhalb seines Fensters, beurteilt mit einem Server-`Date` in der Hand (Skew ist also keine Erklärung) |
| `CLOCK_SKEW` | die Uhr dieser Maschine und die Zeitstempel des Dokuments können nicht beide richtig sein, und die Signatur hat verifiziert — die Uhr ist also verdächtig |
| `CATALOG_STALE` | nach `expires_at` |
| `FRESHNESS_UNKNOWN` | kein `issued_at` und kein `expires_at` — ein handgeschriebener lokaler Katalog |
| `UNSIGNED` | keine Signaturen, oder kein Vertrauensanker, um sie zu prüfen |

`SIGNATURE_INVALID` und `SIGNATURE_KEY_EXPIRED` sind **Ablehnungen**:
das Dokument wird überhaupt nicht gelesen, und es wird kein gecachter
Fallback dafür angeboten. `UNSIGNED` ist keine Ablehnung — es ist der
Zustand der Welt vor der Zeremonie und der jedes lokalen Katalogs —
aber es kann einen Record nie zu voll vertraut hochstufen.

Woher ein Dokument **geholt** wurde, ist nie ein Input. Ein Katalog
wird geglaubt, weil ein delegierter Schlüssel ihn signiert hat;
`plugins.registry_url` ist gewöhnliche Konfiguration, und der Katalog
darf erwartungsgemäß den Host wechseln. Der Verifikationspfad des
Daemons enthält keine Hostname-Prüfung und darf keine bekommen.

## 6. `revocations.json`

### 6.1 Form

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

Generiert aus jeweils einer Datei pro Advisory unter
`astra-registry/tools/revocations/` von `tools/build-revocations.mjs`;
ein Advisory wird zu einem Eintrag pro Schlüssel, den es benennt, und
jeder Eintrag trägt die ID, Severity, Action, Reason und URL des
Advisorys, weil ein Client genau einen davon zeigt — den ersten, der
passt — und jeder muss für sich selbst stehen. Einträge sind nach
`(kind, value)` sortiert, das Dokument ist also deterministisch.

### 6.2 Das Kind-Vokabular

`RevocationKind` in `astra-daemon/src/plugins/trust.rs` ist die
Autorität; die `KINDS`-Tabelle der Registry existiert, damit eine
Registry kein Kind veröffentlichen kann, das der Daemon still ignorieren
würde — ein unbekanntes Kind ist ein Widerruf, der nicht passiert.

| kind | `value` | trifft |
|---|---|---|
| `digest` | 64 Kleinbuchstaben-Hex | `sha256` einer gesamten `.astraplugin`, case-insensitiv verglichen |
| `binary` | 64 Kleinbuchstaben-Hex | `sha256` einer **aufgelösten `entry.command`-Datei** |
| `id` | Plugin-ID | jede Version dieses Plugins |
| `id_version` | `<id>@<semver>` | genau dieses Release |
| `version_range` | Plugin-ID + `versions`-Fenster | siehe §6.3 |
| `identity` | `github:owner/repo` oder `origin:host` | eine gepinnte Publisher-Identität |
| `publisher_key` | eine Schlüssel-ID | die `signer_key_id` eines Trust-Records |

`action` ist `block_install`, `disable` oder `warn`. `warn` blockiert
keine Installation; `disable` stoppt und deaktiviert auch eine bereits
installierte Kopie. `severity` (`critical` / `high` / `moderate` /
`low`) ist nur beratend — kein Verhalten hängt daran.

`reason` wird einem Nutzer **wörtlich** in einer Benachrichtigung
gezeigt, die der Daemon als persistent markiert, der Generator lehnt
also Text mit bidi-Overrides oder Zero-Width-Joinern ab und begrenzt
ihn auf 300 Zeichen.

### 6.3 Versionsfenster

Die Form und Semantik von OSV: `introduced` ist **inklusiv**, `fixed`
ist **exklusiv**, beide optional, und `{}` bedeutet jede Version — was
`version_range` zu einer strikten Verallgemeinerung von `id` macht.
`introduced == fixed` deckt nichts ab und wird beim Build abgelehnt.

Die Reihenfolge ist Standard-Semver-Präzedenz, `1.0.0-rc.1 < 1.0.0`
gilt also: ein Advisory, das „fixed in 1.0.0" sagt, darf `1.0.0-rc.1`
nicht unwiderrufen lassen. Build-Metadaten werden ignoriert
(Semver §10). **Ein Versionsstring, den keine Seite parsen kann, ist
*innerhalb* des Fensters** — die Alternative ist, dass
`version = "totally-fine"` an jeder Grenze vorbeischlüpft, die ein
Advisory ausdrücken könnte, und der Angreifer wählt diesen String.

### 6.4 Verifikation ist strikt, anders als beim Katalog

`verify_index_document` gibt ein abgestuftes Urteil zurück;
`verify_revocations_document` gibt `Err` zurück. Kein Vertrauensanker,
keine Signatur, eine Signatur von einem Fremden, oder eine Signatur von
einem Schlüssel außerhalb seines Fensters sind alle Fehlschläge. Eine
Widerrufsliste wird nur je konsultiert, um etwas zu *verweigern*, ein
Dokument, das niemand zuordnen kann, hat also genau eine sichere
Lesart — „das ist keine Widerrufsliste" — und es als leere Menge
zurückzugeben wäre das vom Angreifer bevorzugte Ergebnis, erreichbar,
indem irgendeine Datei überhaupt serviert wird.

Die Abwesenheit einer brauchbaren Liste wird eine Ebene höher
gehandhabt, durch die 7-Tage-Blockade (§5.5). Das, und kein
permissiver Parser, ist es, was einen Registry-Ausfall davon abhält,
zu einem stillen Verlust der Durchsetzung zu werden.

Eine gecachte Liste wird **bei jedem Laden neu verifiziert**, nie
vertraut, nur weil dieser Daemon sie einmal geschrieben hat — was es
erlaubt, dass die gecachte Kopie ein installations-tauglicher Input
ist, und warum eine Schlüsselrotation die gecachte Liste im selben
Moment ausmustert, in dem sie eine lebende ausmustert.

### 6.5 Die Sideload-Lücke, an der Quelle geschlossen

Ein nur-Digest-Advisory hinterlässt standardmäßig ein Loch: nach
Digest widerrufen, und ein Nutzer kann deinstallieren (wobei er den
Trust-Record fallenlässt, aus dem der Digest gelesen wurde), `plugin.toml`
und die Binärdatei in ein Verzeichnis kopieren, und denselben Code
sideloaden. Ein Verzeichnis hat kein Archiv, hat also keinen
Bundle-Digest und keinen Signer.

Der Generator **lehnt daher ein Advisory ab, dessen jeder Eintrag auf
etwas basiert, das ein Verzeichnis nicht haben kann.** Mindestens ein
Eintrag **MUSS** vom Kind `binary`, `id`, `id_version` oder
`version_range` sein. `identity` und `publisher_key` zählen
ausdrücklich nicht.

Fünf Durchsetzungspunkte konsumieren die Liste: Installation
(§5.3-A.4 des Plans), Update-Auflösung, der Import-Pfad, der
Sideload-Pfad, und die periodische Schnittmenge der Liste mit
installierten Plugins nach aufgezeichnetem `artifact_sha256`.

## 7. Provenienz — was die Registry prüft, was der Daemon nicht kann

### 7.1 Beim Ingest (Registry-Bot, `bot/lib/attestation.mjs`)

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`. Das beweist, dass ein Workflow in diesem Repository
   diese Bytes gebaut hat und dass Sigstore es aufgezeichnet hat.
2. **Der Subjekt-Digest der Attestation MUSS dem `sha256` des Artefakts
   entsprechen** — der dritte der drei Orte dieser Zahl
   (`E_ATTESTATION_SUBJECT_MISMATCH`).
3. Das Quell-Repository des Zertifikats MUSS
   `https://github.com/<repo>` sein (`E_ATTESTATION_REPO_MISMATCH`).
4. Die **aufgelöste Reusable-Workflow-Commit-SHA** wird aus dem
   Zertifikat zurückgelesen und MUSS in den
   `reusable_workflow_shas` von `trust.json` erscheinen
   (`E_WORKFLOW_NOT_ALLOWED`). Eine fehlende SHA ist ein Fehlschlag,
   kein Default (`E_ATTESTATION_INVALID`).

Schritt 4 ist es, was ein veränderliches `@v1`-Tag als Supply-Chain
unbrauchbar macht: ein Tag kann jederzeit auf einen anderen Commit
umgezeigt werden, und die Attestation würde immer noch das richtige
Repository und die richtige Workflow-Datei benennen. Diese Allowlist
zu ändern ist eine Root-Schlüssel-Zeremonie.

Diese Allowlist existiert jetzt: die signierte `trust.json` benennt
genau einen Commit, `e3329df252a46d747676cb540ae4b986af68a3ad`. Also
stoppt `E_TRUST_UNPROVISIONED` den Ingest nicht mehr, und Schritt 4 ist
aktiv — ein von einem anderen Workflow erzeugter Build wird mit
`E_WORKFLOW_NOT_ALLOWED` abgelehnt. Die Daemon-seitige Hälfte ist aus
einem anderen Grund weiterhin fail-closed: der Katalog selbst trägt
keine Signatur (§0.1).

### 7.2 Nicht implementiert: die Pro-Release-Gegensignatur

`PRODUCTION_PLAN` §5.2 spezifiziert eine Pro-Release-Gegensignatur über

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**Nichts berechnet oder prüft das heute.** Der String erscheint im
Plan und nirgendwo in einem der drei Repositories. Die Authentizität
eines Records kommt derzeit von der Umschlag-Signatur des Index, die
den gesamten Katalog abdeckt. Implementiere keinen Verifier gegen
diesen Abschnitt in der Erwartung, ein solches Feld zu finden.

### 7.3 Was der Daemon stattdessen tut

Der Daemon führt **keine** Sigstore-Verifikation durch: Attestations
werden in der CI des Bots geprüft, wo das Netzwerk, die GitHub-API und
`gh` alle existieren. Lokal tut er zwei Dinge, und deren Kombination
ist es, was eine Kompromittierung des Registry-Schlüssels auf
„neue Plugins veröffentlichen" begrenzt:

* **TOFU-Pinning.** Beim ersten Install zeichnet er die Identität auf,
  die das Listing deklariert hat (`{kind: "github", repo}` oder
  `{kind: "origin", host}`). Ein Update, dessen Identität abweicht, ist
  eine **harte Blockade ohne Override, nie**.
* **URL-vs-Identität-Bindung.** Die Artefakt-URL muss unter dem
  Release-Namensraum des gepinnten Repositorys liegen, nach
  Redirect-Auflösung an Host und Pfad-Präfix verglichen. Die Identität
  ist das Repo, das der Record **deklariert**, nie das Repo, das die
  URL impliziert — es aus der URL abzuleiten würde die Prüfung bei
  einem ersten Install tautologisch machen.

Restrisiko, genannt, weil die UI nicht übertreiben darf: `identity` ist
ein String, den die Registry behauptet. Ein kompromittierter
Index-Schlüssel kann einen Record mit einer wahren Identität und einem
gefälschten Provenance-Block veröffentlichen. Die URL-Prüfung zwingt
die Bytes dazu, aus dem Release-Namensraum des gepinnten Repos zu
kommen; eine Kompromittierung von Repo plus Registry besiegt beides.

## 8. Das Audit-Verfahren

Alles im veröffentlichten Katalog ist von einem Dritten ohne Zugriff
auf irgendeinen privaten Schlüssel verifizierbar. Das ist das
Verfahren. Als **Tooling** markierte Schritte haben ein Skript in
`astra-registry`; als **manuell** markierte Schritte noch nicht, und
das in `PRODUCTION_PLAN` §5.5 genannte
`registry/tools/audit-index.sh` **existiert heute nicht** — es wird
hier als das Verfahren beschrieben, das es automatisieren wird.

**A. Den Katalog-Inhalt reproduzieren.** *(Tooling)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

Vergleiche dann das veröffentlichte `signed`-Member mit dem
regenerierten, nur `issued_at` und `expires_at` ignorierend (§5.3).
Jede andere Differenz ist ein Katalog, der nicht zu seiner eigenen
Git-Historie passt.

*Was das heute ausgibt* (verifiziert beim Schreiben dieses Dokuments):
beide `--check`-Läufe melden „byte-identical to a fresh generation"
bei Serial 1 mit 0 Signaturen, und `validate.mjs` **schlägt fehl** —
alle elf Listings sind Staging-Einträge ohne Artefakt-Digest, was es
ablehnt, es sei denn, `--allow-staging` wird übergeben. Das ist die
richtige Antwort für einen Katalog, dessen Plugins noch nicht
veröffentlicht wurden, und der Grund, warum nichts darin
installierbar ist.

**B. Die Signaturkette prüfen.** *(Tooling)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

und, von Hand, dass `trust.json` unter einem Schlüssel in
`registry/v1/root.json` verifiziert, dessen Fingerabdruck mit dem
übereinstimmt, den deine Astra-Binärdatei loggt. Rechne unabhängig
nach, falls du willst: `SHA-256(domain ‖ 0x00 ‖ JCS(signed))`,
Ed25519-Verifikation, gemäß §2–§3.

*Was das heute ausgibt:* `FAIL … no trusted key was supplied (offered: none;
trusted: none)` — es gibt keine `trust.json` zu übergeben und keine
Root, um eine zu verifizieren (§0.1). Ein Verifier, der gegen den
aktuellen Baum etwas anderes meldete, würde lügen.

**C. Serial und Fenster prüfen.** *(manuell)* `serial` muss ≥ der
letzten sein, die du gesehen hast; `expires_at − issued_at` muss 30
Tage für den Katalog und 7 für die Widerrufsliste sein; `key_id` muss
ein Schlüssel sein, den `trust.json` mit einem `issued_at`
enthaltenden Fenster benennt.

**D. Jedes Artefakt gegen das öffentliche Transparency-Log prüfen.**
*(manuell)* Für jedes Release im Index — `<…>` sind Platzhalter, aus
dem Index-Record gelesen, diese zwei Befehle sind also eine Vorlage
statt zum Kopieren-Einfügen:

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` ist das Repository des **Autors**, aus dem `release.repo` des
Index-Records. `--signer-workflow` ist der **gemeinsame
wiederverwendbare** Workflow, der es gebaut hat — der eine, an den
`astra-plugin init-ci` den Aufrufer pinnt, vom Bot als
`DEFAULT_SIGNER_WORKFLOW` in `astra-registry/bot/ingest.mjs` gehalten
und gegen eine Datei geprüft, die in
`AstraPlugins/.github/workflows/` existiert. Nimm den exakten String
aus dieser Konstante, statt ihn zu rekonstruieren; ein vertauschter
Pfad passt zu gar keiner Attestation, und jedes ehrliche Artefakt sieht
dann aus, als hätte es keine.

`gh attestation verify` holt das Sigstore-Bundle für diesen
Artefakt-Digest und prüft es gegen Sigstores Trust-Root,
**einschließlich des Rekor-Transparency-Log-Inklusionsbeweises**. Aus
seiner JSON-Ausgabe, prüfe von Hand, was der Bot beim Ingest prüft
(§7.1): der Subjekt-Digest entspricht dem Digest der Datei, das
Quell-Repository ist das Repo, das der Index benennt, und die
aufgelöste Signer-Workflow-Commit-SHA steht in den
`reusable_workflow_shas` von `trust.json`.

Ein Record, den die Registry für ein Artefakt **ohne** Attestation
veröffentlicht hat, oder eines, dessen Attestation ein anderes
Repository benennt, ist genau die nachträgliche Erkennung, für die
dieses Verfahren existiert: nichts hindert einen kompromittierten
Registry-Schlüssel daran, ein *neues* Plugin zu veröffentlichen, und
Auditierbarkeit ist die gesamte Abwehr.

**E. Das Bundle selbst prüfen.** *(Tooling)* Führe
[`bundle-v2.md` §13](bundle-v2.md#13-der-verifikationsalgorithmus) über
die heruntergeladene Datei aus, und bestätige, dass ihre
`MANIFEST.json` `plugin_id`, `version`, `platform` und
`permissions_hash` mit dem Index-Record übereinstimmen.

## 9. Zusammenfassung dessen, was heute in Kraft ist

| Eigenschaft | Status |
|---|---|
| Dokumentformate, Umschlag, Signierkonstruktion, JCS-Profil | auf beiden Seiten implementiert, per Fixture cross-getestet |
| Root-Schlüssel | **bereitgestellt** am 2026-08-11 — dieselben zwei auf beiden Seiten |
| `trust.json` | **signiert** unter `astra-root-2026a`, delegiert an `astra-index-2026a` und listet einen Workflow-Commit als erlaubt |
| `index.json`/`revocations.json`-Signaturen | leere Arrays im committeden Baum — **das ist jetzt der fehlende Link** |
| Katalog-Urteile, Serial-Untergrenzen, Aktualität, Uhr-Handhabung | im Daemon implementiert und getestet |
| Widerrufs-Vokabular, Matching, fünf Durchsetzungspunkte | implementiert; **wirkungslos, bis einmal eine signaturgültige Liste geholt wird** |
| Build-Attestation-Prüfung beim Ingest | implementiert und aktiv; die Workflow-Allowlist kommt aus der signierten `trust.json` |
| Pro-Release-Gegensignatur | nur im Plan spezifiziert; **keine Implementierung** |
| `audit-index.sh` | existiert nicht; §8 ist das manuelle Verfahren |

---

*Beim Schreiben dieses Dokuments geprüfte Quellen:
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`;
`astra-registry/tools/lib/canonical.mjs`; `astra-registry/tools/lib/revocations.mjs`;
`astra-registry/tools/build-index.mjs`; `astra-registry/bot/lib/sign.mjs`;
`astra-registry/bot/sign-index.mjs`; `astra-registry/bot/lib/attestation.mjs`;
`astra-registry/registry/v1/{root,index,revocations}.json`;
`astra-registry/SECURITY.md`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`refresh_revocations`).*
</content>
