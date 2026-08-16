> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/spec/bundle-v2.md) maßgeblich.

# `.astraplugin`-Bundle-Format, Version 2 — normative Spezifikation

**Status:** normativ. Dieses Dokument definiert die Bytes. Es ist so
geschrieben, dass ein Dritter, der dieses Repository nie gesehen hat,
allein daraus einen Verifier implementieren kann und bei jeder Datei in
[`testdata/bundles/`](../../../testdata/bundles/README.md) zu demselben
Urteil kommt wie wir.

**Schema-String:** `astra.bundle/2`
**Dateierweiterung:** `.astraplugin`
**Medientyp:** keiner registriert; ausgeliefert als
`application/octet-stream`.

Anforderungswörter — **MUST**, **MUST NOT**, **SHOULD**, **MAY** —
folgen RFC 2119. „Reject" bedeutet: das Bundle als Ganzes ablehnen,
nicht extrahieren, nicht auf ein früheres Format zurückfallen. Es gibt
in diesem Format keine Teilakzeptanz.

---

## 0. Was dieses Format ist und nicht ist

Ein v2-Bundle ist ein ZIP-Archiv, dessen **erster Eintrag ein Manifest
ist, das jeden anderen Eintrag benennt und dessen Digest angibt.** Das
ist die ganze Idee. Es erkauft eine Sache, die ein v1-Bundle (ein ZIP
mit einer `plugin.toml` darin) nicht erkaufen konnte: ein Leser erfährt,
was das Archiv *enthalten darf*, bevor er der eigenen Struktur des
Archivs überhaupt vertraut hat, und jede Datei, die auf der Festplatte
landet, wird gegen diese Liste geprüft.

Drei Dinge, die dieses Format absichtlich **nicht** tut, hier genannt,
damit kein Leser sie aus der Anwesenheit von Digests ableitet:

* **Es trägt keine eigene Authentizität.** Nichts in einem v2-Bundle
  beweist, wer es erzeugt hat. Authentizität kommt von außerhalb der
  Datei: eine GitHub-Build-Attestation über `sha256(gesamte Datei)`, und
  ein signierter Registry-Index, der dieselbe Zahl pinnt
  ([`registry-index.md`](registry-index.md)). Das Legacy-In-ZIP-Paar
  `SIGNATURE`/`PUBKEY` (§11) ist *keine* Ausnahme — es läuft aus und ist
  nie ein Vertrauenssignal.
* **Es sagt nichts darüber aus, was das Plugin zur Laufzeit tun darf.**
  Das ist [`permissions.md`](permissions.md).
* **Es ist keine Sandbox-Grenze.** Ein installiertes Plugin ist ein
  nativer Prozess, der mit den vollen Rechten des Nutzers läuft. Ein
  Bundle zu verifizieren sagt dir, dass die Bytes die Bytes sind, die
  der Autor veröffentlicht hat; es schränkt nicht ein, was diese Bytes
  tun, sobald sie laufen.

## 1. Konformität, und welche Implementierung normativ ist

Drei Programme lesen dieses Format:

| | Implementierung | Rolle |
|---|---|---|
| **CLI** | `astra-plugin-cli/src/bundle.rs` (`BundleBuilder`, `Bundle::open`) | schreibt Bundles; `astra-plugin verify` liest sie zurück |
| **Daemon** | `Astra/astra-rs/astra-daemon/src/plugins/bundle.rs` (`inspect`, `BundleManifest::check_structure`) + `ops/install_plugin.rs` (`extract_archive`) | entscheidet, ob die Bytes eines Fremden auf die Festplatte eines Nutzers extrahiert werden |
| **Registry** | `astra-registry/bot/lib/bundle.mjs` (`inspectBundle`) | entscheidet, ob ein Listing veröffentlicht wird |

**Dieses Dokument ist normativ; keine Implementierung ist es.** Wo eine
Implementierung diesem Text widerspricht, hat die Implementierung einen
Bug. Wo zwei Implementierungen einander widersprechen, wird der
Widerspruch als benannte Divergenz in `testdata/bundles/vectors.json`
aufgezeichnet und in §14 wiedergegeben — das `verdict`-Feld dort ist die
richtige Antwort, und das `expect`-Feld ist, was jedes Programm heute
tut.

Konsequenz für eine vierte Implementierung: **implementiere §13, nicht
eines der drei Programme.** Ein Verifier, der den Daemon exakt
nachbildet, würde Divergenz F2 erben; einer, der die Registry
nachbildet, würde F3 erben.

## 2. Der Container

* Ein Bundle **MUSS** ein ZIP-Archiv sein, das von einem konventionellen
  Reader lesbar ist: lokale Dateiheader ab Offset 0, ein zentrales
  Verzeichnis, ein End-of-Central-Directory-Record.
* **ZIP64 DARF NICHT für Eintrag null verwendet werden.** Eine
  `MANIFEST.json`, deren lokaler Header die ZIP64-Größen-Sentinel
  `0xFFFFFFFF` deklariert, wird abgelehnt (§4). Kein anderer Eintrag hat
  eine explizite ZIP64-Einschränkung; ein so großes Manifest ist kein
  Manifest.
* Einträge sind **nur Dateien**. Ein Verzeichniseintrag wird abgelehnt
  (§6.5): Verzeichnisse werden durch die Pfade impliziert und können
  keinen Digest tragen.
* **Eintrag null MUSS `MANIFEST.json` sein, gespeichert
  (Kompressionsmethode 0).** Jeder andere Eintrag **DARF** Methode 0
  (stored) oder Methode 8 (deflate) verwenden. Die CLI packt alles außer
  dem Manifest mit deflate auf Stufe 6; die Vektoren in
  `testdata/bundles/` sind durchgehend stored. Beides ist konform.
* Reihenfolge: `MANIFEST.json` zuerst; das Legacy-`SIGNATURE`/`PUBKEY`-
  Paar, falls vorhanden, zuletzt und in dieser Reihenfolge (§11); alles
  andere dazwischen. Produzenten **SOLLTEN** die Mitte in
  byte-lexikografischer Reihenfolge des Pfads schreiben — die CLI tut
  das, weil ihre Einträge in einer `BTreeMap` leben — aber ein Verifier
  **DARF DAS NICHT VERLANGEN**. Das `files`-Array *des Manifests* ist
  sortiert, und diese Anforderung wird durchgesetzt (§7.4); die eigene
  Reihenfolge des Archivs nicht.
* Zeitstempel tragen keine Bedeutung. Die CLI stempelt jeden Eintrag auf
  `1980-01-01T00:00:00` (das früheste, was ein DOS-Zeitstempel
  ausdrücken kann), damit zwei Builds derselben Eingaben dieselben Bytes
  erzeugen. Ein Verifier **DARF KEINEN** Zeitstempel lesen.

## 3. Die zwei Digests

Genau zwei Digest-Konstruktionen existieren in diesem Format. Beide sind
SHA-256, beide werden als **64 Kleinbuchstaben-Hex-Zeichen** gerendert,
und keine wird je case-insensitiv verglichen.

### 3.1 Artefakt-Digest

```
artifact_digest = SHA256(the entire .astraplugin file, byte for byte)
```

Keine Kanonisierung, kein Eintrags-Durchlauf, keine Ausschlüsse. Das ist
die Zahl, die an genau drei Stellen erscheint, und es ist an allen drei
dieselbe Zahl:

1. der Subjekt der GitHub-Build-Attestation,
2. `artifacts.<platform>.sha256` im signierten Registry-Index,
3. was der Daemon streamt und hasht, bevor er das Archiv überhaupt
   öffnet.

Sie wird nackt geschrieben (kein `sha256:`-Präfix), weil jeder Ort, an
dem sie erscheint, bereits typisiert ist.

### 3.2 Manifest-Digest — und warum er domänensepariert ist

```
manifest_digest = SHA256( "astra.bundle/2" ‖ 0x00 ‖ MANIFEST.json bytes )
```

Das Präfix sind die 14 ASCII-Bytes `astra.bundle/2`, gefolgt von einem
Byte `0x00` — 15 Bytes insgesamt — unmittelbar gefolgt von den
*gespeicherten* Bytes von Eintrag null, genau so wie sie im Archiv
liegen, ohne erneute Serialisierung, ohne Whitespace-Normalisierung und
ohne Anpassung des abschließenden Newlines.

**Warum das Präfix existiert.** Ohne es ist die Konstruktion
`SHA256(irgendwelche Bytes)` — genau die Form jedes `files[].sha256` im
selben Dokument. Die beiden wären ununterscheidbare 64-Hex-Strings, die
durch dieselben Records reisen, und ein aus einem Kontext gehobener Wert
würde im anderen verifizieren. Das Präfix macht den Manifest-Digest zu
einer anderen Funktion derselben Bytes.

**Durchgerechnetes Beispiel** (Vektor `ok-minimal`, reproduzierbar mit
`testdata/bundles/handcheck.sh ok-minimal`, das nur `dd`, `od`,
`printf`, `cat` und `sha256sum` verwendet):

```
sha256(manifest bytes)                    2e16024e4557332a2a404a89a94b124807e0b4741046e29fc3f6b94ea1b69682
sha256("astra.bundle/2\0" ‖ manifest)     8e88f82cc6dbb9c253e3a4409a03f763668ca1a46439f994e2a45a6da23ccaf4
sha256(whole file)                        ac3d49a2fc2b7408d5b3c805ec91541510c272547a16e3bc7a30f269ba801aed
```

Eine Implementierung, die den ersten Wert erzeugt, wo der zweite
erwartet wird, hat das Präfix vergessen. `vectors.json` zeichnet beide
Zahlen (`manifest_sha256` und `manifest_digest`) für jeden Vektor auf,
sodass das eine Ein-Zeilen-Prüfung ist, und die beiden sind bei keinem
echten Manifest **je** gleich.

### 3.3 Die ausgemusterte Konstruktion, und die Kollision, die sie ausmusterte

Vor v2 wurde ein Bundle durch eine In-ZIP-`SIGNATURE` über

```
legacy_digest = SHA256( name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ … )
```

in ZIP-Indexreihenfolge authentifiziert, `SIGNATURE` und `PUBKEY` selbst
übersprungen. Keine Trennzeichen, keine Längenpräfixe, keine
Eintragsanzahl, kein Domänenseparator. Diese Konstruktion ist
**mehrdeutig**, und die Mehrdeutigkeit steckt in diesem Repository als
zwei eingefrorene Dateien:

| Vektor | Archiv enthält | trägt bei |
|---|---|---|
| `collision-a-bc` | Eintrag `a`, Inhalt `bc` | `a` ‖ `bc` = `abc` |
| `collision-ab-c` | Eintrag `ab`, Inhalt `c` | `ab` ‖ `c` = `abc` |

Die beiden Archive tragen **bytegleiche `MANIFEST.json`** und damit
identische `manifest_digest`; ihre Artefakt-Digests unterscheiden sich;
und ihre Legacy-Digests sind eine Zahl:

```
legacy_concat_sha256   0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   (both)
```

Eine `SIGNATURE` authentifiziert beide Archive, und ein Verifier, der
dieses Schema benutzt, kann nicht sagen, welches er gerade hält.

Unter v2 sind sie getrennt, und es braucht **beide Richtungen** der
Vollständigkeitsprüfung, um das zu tun (§7.1): in `collision-ab-c` ist
`ab` ein Archiveintrag, den keine Manifest-Zeile abdeckt, *und* `a` ist
eine Manifest-Zeile, die kein Archiveintrag erfüllt. Ein Verifier, der
nur „gelistet ⇒ vorhanden" prüfte, würde es akzeptieren.

`legacy_concat_sha256` ist in `vectors.json` genau zu diesem einen Zweck
aufgezeichnet. Nichts in diesem Projekt sollte ihn je für etwas anderes
berechnen.

## 4. Eintrag null, Byte für Byte

Ein konformer Reader **MUSS** in der Lage sein, `MANIFEST.json` aus
einem Präfix der Datei zu erhalten, ohne irgendetwas zu inflaten und
ohne das zentrale Verzeichnis zu lesen. Das ist die Eigenschaft, die es
einem Reader erlaubt, die erlaubten Inhalte des Archivs zu erfahren,
bevor er angreiferkontrollierter Struktur vertraut hat. Alle drei
Implementierungen tun genau das
(`manifest_from_local_header` in der CLI und im Daemon,
`manifestBytesFromLocalHeader` in der Registry).

Lies den lokalen Dateiheader bei Offset 0. Alle Mehrbyte-Felder sind
Little-Endian.

| Offset | Größe | Feld | Anforderung |
|---|---|---|---|
| 0 | 4 | Signatur | **MUSS** `0x04034B50` sein, sonst ablehnen: kein ZIP |
| 6 | 2 | General-Purpose-Flags | Bit 0 (Verschlüsselung) **MUSS** 0 sein; Bit 3 (Data Descriptor) **MUSS** 0 sein |
| 8 | 2 | Kompressionsmethode | **MUSS** 0 sein (stored) |
| 18 | 4 | Komprimierte Größe | **DARF NICHT** `0xFFFFFFFF` sein (ZIP64-Sentinel); **MUSS** ≤ 4 MiB sein |
| 26 | 2 | Länge des Dateinamens `n` | — |
| 28 | 2 | Länge des Extra-Feldes `e` | — |
| 30 | `n` | Dateiname | **MUSS** genau die 13 Bytes `MANIFEST.json` sein |
| 30+`n`+`e` | Größe | die Manifest-Bytes | — |

**Ordne die Beanstandungen so wie die Implementierungen es tun:** prüfe
zuerst den *Namen*. Ein Archiv, dessen Eintrag null eine andere Datei
ist, stolpert über welche der Header-Prüfungen auch immer diese Datei
zufällig verfehlt, und das zu melden schickt den Leser auf die Suche
nach einem Problem mit einem Manifest, das er nicht hat.

Ablehnungen, die das erzeugt, mit ihren Vektoren:

* Eintrag null ist nicht `MANIFEST.json` → `manifest-not-first`.
* Eintrag null ist komprimiert → `manifest-compressed`.
* die Größe läuft über das Ende der Datei hinaus → abgeschnittenes
  Bundle.

**Ein Bundle, das irgendwo eine `MANIFEST.json` enthält, DARF NICHT als
Pre-v2-Bundle gelesen werden.** Ist das Manifest vorhanden, aber nicht
Eintrag null, ist die Antwort eine Ablehnung, nie ein Zurückfallen auf
die schwächeren Regeln. Sonst würde es reichen, einen Eintrag zu
verschieben, um das Pro-Datei-Hashing abzuschalten, das einzige, was v2
hinzufügt. (`manifest-not-first` existiert, um jede Implementierung
daran zu binden.)

### 4.1 Das zentrale Verzeichnis muss übereinstimmen

Eintrag null existiert zweimal: einmal im lokalen Header bei Offset 0,
und einmal als der Central-Directory-Record, den der ZIP-Reader
verwenden wird. Nichts im ZIP-Format zwingt sie, dieselben Bytes zu
beschreiben — das zentrale Verzeichnis wird zuletzt angehängt.

Ein Verifier **MUSS** das Manifest über *beide* Pfade lesen und
vergleichen:

* die CLI und die Registry vergleichen die zwei Byte-Strings / ihre
  Digests;
* der Daemon liest Eintrag 0 über seinen ZIP-Reader und vergleicht die
  Bytes mit denen, die er von Offset 0 gehoben hat.

Vektor: `header-disagree`. Das ist der v2-spezifischste Angriff, den es
gibt. Ungeprüft hasht, zeigt und gegensigniert die Registry ein
Manifest, das kein Daemon je durchsetzen wird.

**Welche Bytes gehasht werden, wenn sie übereinstimmen:** die Bytes bei
Offset 0. Stimmen sie nicht überein, wird das Bundle abgelehnt, die
Frage stellt sich also nicht.

## 5. `MANIFEST.json`

UTF-8-JSON, ein Objekt. Die CLI schreibt es hübsch formatiert mit
abschließendem Newline; der Digest läuft über welche Bytes auch immer
tatsächlich geschrieben werden, Formatierung ist also die Wahl eines
Produzenten, und ein Verifier **DARF NICHT** vor dem Hashen neu
serialisieren.

Vollständiges Beispiel — Vektor `ok-minimal`, die exakten Bytes, die zu
`2e16024e…` hashen:

```json
{
  "schema": "astra.bundle/2",
  "plugin_id": "vector-plugin",
  "version": "1.0.0",
  "platform": {
    "os": "linux",
    "arch": "x86_64"
  },
  "protocol": 1,
  "min_astra_version": "",
  "capabilities": [
    "tools"
  ],
  "permissions": {},
  "permissions_hash": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
  "entry": {
    "command": "./bin/fixture",
    "args": []
  },
  "files": [
    {
      "path": "bin/fixture",
      "sha256": "0f7ceb62618162c2ac6765ac683e65dc81ad19add148ada1e7186d186847caba",
      "size": 33,
      "mode": "0755"
    },
    {
      "path": "plugin.toml",
      "sha256": "da1141bb5c5390f1c8a646a0e0b0be1f26cdc0862ccb850dd86e0cd0238f3117",
      "size": 218,
      "mode": "0644"
    }
  ]
}
```

### 5.1 Felder

| Feld | Typ | Produzent | Verifier |
|---|---|---|---|
| `schema` | string | **MUSS** `"astra.bundle/2"` sein | **MUSS** exakt vergleichen; jeder andere Wert → ablehnen, nie raten |
| `plugin_id` | string | die Plugin-ID, übereinstimmend mit `plugin.toml` | §9 |
| `version` | string | semver | wird von der Registry und dem Daemon gegen das Listing verglichen |
| `platform` | `{os, arch}` | siehe §5.2 | Host-Kompatibilitätsprüfung gehört dem Installer, nicht dem Format |
| `protocol` | integer ≥ 0 | das Wire-Protokoll, das das Plugin spricht | Bereichsprüfung gehört dem Host |
| `min_astra_version` | string | semver, oder `""` für keine Anforderung | — |
| `capabilities` | Array von string | das Capability-Vokabular des Daemons | — |
| `permissions` | object | der `[permissions]`-Abschnitt der `plugin.toml`, wörtlich | §10 |
| `permissions_hash` | string | `"sha256:" ‖ hex` über die kanonischen Bytes aus §10 | §10 |
| `entry` | `{command, args}` | §8 | §8 |
| `files` | array | §7 | §7 |

**Produzenten MÜSSEN jedes Feld oben ausgeben.** Verifier **MÜSSEN**
ein Manifest ablehnen, dem `schema`, `plugin_id`, `version`,
`platform`, `entry` oder `files` fehlt.

*Divergenz, genannt statt versteckt:* der Daemon setzt Defaults für
`protocol`, `min_astra_version`, `capabilities`, `permissions` und
`permissions_hash`, wenn sie fehlen (`#[serde(default)]`); der Reader
der CLI verlangt sie. Ein Bundle, das eines auslässt, ist also
installierbar und nicht durch `astra-plugin verify` verifizierbar.
Produziere keines.

**Unbekannte Member MÜSSEN akzeptiert und ignoriert werden.** Eine
spätere v2-Ergänzung (etwa eine `changelog_url`) darf nicht jedes
Bundle, das sie trägt, auf einem älteren Host uninstallierbar machen.
Was sich ohne Schema-Sprung nicht ändern darf, ist die *Bedeutung* der
Felder oben — und `schema` wird exakt verglichen, was das begrenzt.

### 5.2 `platform`

```json
{"os": "linux",   "arch": "x86_64"}     → registry platform key  linux-x64
{"os": "windows", "arch": "x86_64"}     → registry platform key  windows-x64
{"os": "any",     "arch": "any"}        → registry platform key  noarch
```

`any` auf einer Achse bedeutet „keine Anforderung": ein Bundle ist
kompatibel mit einem Host, wenn
`(os == "any" || os == host_os) && (arch == "any" || arch == host_arch)`.
`noarch` ist, wie jedes TypeScript- und Python-Plugin ausgeliefert wird
— Quellcode oder Bytecode, von einer Runtime ausgeführt, die der Host
bereits hat — und die Registry schreibt für eines dieselbe URL und
denselben Digest unter jeden unterstützten Plattform-Schlüssel, sodass
kein Client das Wort lernen muss. Vektor: `ok-noarch-runtime`.

Kein anderes `{os, arch}`-Paar benennt heute ein Ziel. `linux-arm64`,
`windows-arm64`, `macos-x64` und `macos-arm64` sind reservierte
Plattform-Schlüssel im Registry-Schema; Astra liefert für sie keinen
Daemon aus.

## 6. Eintragsnamen

Jeder Archiveintragsname wird geprüft. Die Regeln existieren, weil ein
Eintragsname zu einem Pfad auf dem Dateisystem einer anderen Person
wird, und der Extraktor ist nicht das einzige, was ihn liest.

Ein Eintragsname wird **abgelehnt**, wenn eines davon gilt:

1. **leer**.
2. enthält einen **Backslash** `\`. ZIP-Pfade verwenden nur `/`; ein
   Backslash ist unter Windows ein Pfadtrennzeichen und anderswo ein
   wörtliches Dateinamenzeichen.
3. **absolut** — beginnt mit `/`.
4. enthält **`:`**. Auf NTFS schreibt `bin/fixture:stream` *in*
   `bin/fixture` als alternativen Datenstrom, unsichtbar. Vektor:
   `path-ads`.
5. enthält ein **Steuerzeichen** (U+0000–U+001F, U+007F).
6. hat eine **leere Komponente** (`a//b`), oder eine Komponente gleich
   **`.`** oder **`..`**. Vektor: `path-traversal` (`../escape`).
7. hat eine Komponente, die auf einen **Punkt oder ein Leerzeichen**
   endet. Win32 entfernt beides still, `bin/fixture.` und `bin/fixture`
   sind also zwei Einträge und eine Datei. Vektor: `path-trailing-dot`.
8. hat eine Komponente, deren **Stamm** (der Text vor dem ersten `.`,
   case-insensitiv verglichen) ein reservierter MS-DOS-Gerätename ist:
   `con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`. `CON.txt`
   ist auch die Konsole.

Zusätzlich:

9. **Doppelte Namen werden abgelehnt**, sowohl exakt als auch
   **case-insensitiv**: `plugin.toml` und `Plugin.TOML` sind für einen
   ZIP-Reader zwei Einträge und auf NTFS und APFS eine Datei, wo der
   zweite den ersten *nach* dessen Hashing überschreibt. Vektoren:
   `duplicate-entry`, `duplicate-entry-case` (siehe Divergenz F1).
10. **Verzeichniseinträge werden abgelehnt** (§2). Ein Eintrag ist ein
    Verzeichnis, wenn sein Name auf `/` endet, oder wenn seine externen
    Attribute einen Unix-Modus mit `mode & 0o170000 == 0o040000` ergeben.
    Prüfe beides: das erste ist, was ein ZIP-Writer konventionell
    ausgibt, das zweite ist, was ein feindseliger stattdessen ausgeben
    kann.
11. **Symlink-Einträge werden abgelehnt**: ein Eintrag, dessen externe
    Attribute einen Unix-Modus mit `mode & 0o170000 == 0o120000`
    ergeben. Die Umgehung liegt hier im Link-*Ziel*, dem *Inhalt* des
    Eintrags — jede der obigen Pfadregeln untersucht den Namen, und
    keine davon kann ihn sehen. Vektor: `symlink-entry`.

Diese Regeln gelten für **jeden** Eintrag, einschließlich
`MANIFEST.json`, `SIGNATURE` und `PUBKEY`.

## 7. `files` — die Liste, gegen die das Archiv geprüft wird

`files` ist ein Array von Objekten:

| Member | Typ | Regel |
|---|---|---|
| `path` | string | ein Archiveintragsname; gehorcht §6 |
| `sha256` | string | **genau 64 Kleinbuchstaben-Hex-Zeichen**, kein Präfix |
| `size` | integer ≥ 0 | unkomprimierte Byte-Länge |
| `mode` | string | vier Oktalziffern, z. B. `"0755"` — ein *string*, weil JSON kein Oktal-Literal hat und `755` dezimal ein anderer Modus ist |

* `sha256`, das irgendeine Großbuchstaben-Hex-Ziffer enthält, wird
  **abgelehnt**, nicht gefaltet. Digests werden hier als Strings
  verglichen, ein großgeschriebener würde also nie irgendetwas treffen
  und sich als korrupte Datei statt als fehlerhaftes Manifest
  präsentieren. Vektor: `uppercase-digest`.
* `mode` **MUSS** als Oktal parsen. Ein führendes `0o` wird vom Parser
  des Daemons akzeptiert; Produzenten **DÜRFEN** es NICHT ausgeben.
  `"0788"` wird abgelehnt — 8 ist keine Oktalziffer.
* Derselbe `path` **DARF NICHT** zweimal erscheinen.
* Ein reservierter Name (`MANIFEST.json`, `SIGNATURE`, `PUBKEY`)
  **DARF NICHT** erscheinen: das Manifest kann nicht seinen eigenen
  Digest listen, und das Legacy-Paar wird *über* die gelisteten Dateien
  berechnet.

### 7.1 Vollständigkeit, in beide Richtungen

Sei `Listed` die Menge der `files[].path` und `Present` die Menge der
Archiveintragsnamen minus der drei reservierten Namen oben. Ein
Verifier **MUSS** durchsetzen:

```
Present ⊆ Listed     (no archive entry that the manifest does not list)
Listed ⊆ Present     (no listed file that the archive does not contain)
```

Beides, immer. Eines allein ist ein Loch:

* nur `Listed ⊆ Present` zu prüfen lässt einen Angreifer einen Eintrag
  **hinzufügen**, den der Extraktor schreibt und den nichts hasht —
  Vektor `extra-file` (`bin/backdoor`);
* nur `Present ⊆ Listed` zu prüfen lässt sie einen **fallenlassen** und
  das Bundle intakt nennen — Vektor `missing-file`.

Und es ist die Konjunktion, die das Kollisionspaar trennt (§3.3).

### 7.2 Inhalts-Digests

Für jeden Eintrag in `Present`: der SHA-256 des **unkomprimierten
Inhalts** des Eintrags **MUSS** dem `sha256` seiner `files`-Zeile
entsprechen. Vektor: `content-digest-mismatch` — die richtige
Dateimenge, die richtigen Längen, die falschen Bytes. Das ist die
Prüfung, über die eine ausgetauschte Binärdatei stolpert.

*Wann* das ausgeführt wird, ist eine Implementierungsentscheidung mit
einer harten Randbedingung: die gehashten Bytes **MÜSSEN** die Bytes
sein, die auf der Festplatte landen. Der Daemon hasht daher während der
Extraktion statt in seinem Vor-Extraktions-Durchlauf — siehe Divergenz
F2, die absichtlich so ist und kein Loch.

### 7.3 Größen

Die `size` jedes Eintrags **MUSS** der des Manifests entsprechen. Zwei
unabhängige Prüfungen sind angebracht, und der Daemon macht beide: die
im zentralen Verzeichnis deklarierte Größe, bevor irgendeine Arbeit
getan wird (sie ist angreiferkontrolliert, also ist das ein billiger
Lügendetektor, nicht die echte Prüfung), und eine Byte-Zählung während
des Streamings. Die deklarierte Größe begrenzt die
Streaming-Extraktion. Vektor: `size-mismatch`.

### 7.4 Modi

Wo ein Archiveintrag einen Unix-Modus trägt, **MUSS** `mode & 0o777`
dem `mode & 0o777` des Manifests entsprechen. Wo er keinen trägt — ein
unter Windows geschriebenes Archiv — wird der Vergleich übersprungen;
ein fehlender Modus ist kein Defekt, ein nicht übereinstimmender schon.
Der Modus des Manifests ist das, was ein Extraktor anwendet. Vektor:
`mode-mismatch` (siehe Divergenz F3).

Produzenten normalisieren: die CLI schreibt `0755` für alles
Ausführbare (die aufgelöste Entry-Binärdatei, das On-Disk-Exec-Bit,
oder einen in `[bundle] executables` gelisteten Pfad) und `0644` für
alles andere. Sie kopiert absichtlich keine beliebigen On-Disk-Modi:
ein Checkout unter einer anderen umask würde sonst die Bytes des
Bundles ändern, ohne seinen Inhalt zu ändern.

### 7.5 Sortiert

`files` **MUSS** strikt aufsteigend nach `path` sortiert sein, verglichen
als **rohe Bytes** (nicht nach Unicode-Kollation, nicht
case-insensitiv). Der Daemon setzt strikten Anstieg durch
(`w[0].path >= w[1].path` → ablehnen), was auch den Duplikat-Fall
erfasst. Ein Verifier darf dieses Array binär durchsuchen; ein
unsortiertes würde das still falsch machen. Vektor: `unsorted-files`.

## 8. `entry.command`

`entry.command` ist das eine Feld im Manifest, das zu einem `execve`
wird. Es **MUSS** entweder sein:

* **eine Host-Runtime**, exakt gegen die geschlossene Liste `python`,
  `python3`, `node`, `bun`, `deno` abgeglichen; oder
* **ein Pfad zu einer im Manifest gelisteten Datei.** Nach Entfernen
  eines führenden `./` und Umwandeln von `\` zu `/` vergleichen. Das
  Ergebnis **MUSS** in `files[].path` erscheinen.

Pauschal abgelehnt:

* leer (nach Trimmen);
* absolut (`/usr/bin/sh`, oder ein Windows-Laufwerksbuchstabe-Präfix
  wie `C:\…`);
* enthält eine `..`-Komponente — Vektor `entry-command-escape`
  (`../../../bin/sh`);
* benennt eine Datei, die das Manifest nicht listet — Vektor
  `entry-command-shell` (`sh`).

**Zu Shells.** Die Registry lehnt eine Shell namentlich ab — `sh`,
`bash`, `zsh`, `fish`, `dash`, `csh`, `ksh`, `cmd`, `cmd.exe`,
`powershell`, `powershell.exe`, `pwsh`, `pwsh.exe` — mit einem eigenen
Fehlercode, weil `entry.command: "sh"` unbeschränkte `args` in
beliebigen Code verwandelt. Die CLI und der Daemon kommen über die
Runtime-oder-gelistet-Datei-Regel zum selben Urteil (eine Shell ist
keines von beidem). Ein konformer Verifier braucht nur die allgemeine
Regel; Shells separat zu benennen erkauft eine bessere Nachricht, kein
anderes Ergebnis.

`entry.args` ist ein Array von Strings, standardmäßig `[]`. Dieses
Format setzt keine Einschränkung auf seinen Inhalt; der Host
interpretiert es nicht.

**„Härte" das nicht zu „muss eine gelistete Datei sein".** Das würde
die gesamte scriptbasierte Hälfte des Katalogs offline nehmen — jedes
TypeScript- und Python-Plugin läuft über eine Host-Runtime. Vektor
`ok-noarch-runtime` (`entry.command: "node"`, `platform: any/any`)
existiert genau, um diesen Fehler abzufangen, und ist ein
*Accept*-Vektor.

## 9. `plugin.toml` und `plugin.id`

Jedes Bundle **MUSS** einen `plugin.toml`-Eintrag enthalten, in
`files` wie jede andere Datei gelistet. Es ist das Plugin-Manifest, das
der Host parst; seine vollständige Feld-Referenz steht in
[der Manifest-Referenz](../reference/manifest.md).

Zwei Regeln gehören in *dieses* Dokument, weil ein Bundle deswegen
abgelehnt werden kann:

* `MANIFEST.plugin_id` und `MANIFEST.version` **MÜSSEN** mit dem
  übereinstimmen, worum der Installer gebeten wurde, und mit dem
  Listing, das das Bundle anbietet. Ohne das könnte ein
  Registry-Eintrag `foo` ein Archiv ausliefern, dessen Manifest `bar`
  sagt, und `bar` würde installieren.
* **`plugin.id` wird zu einer Pfadkomponente** — `<plugins_dir>/<id>/`
  — ein Verzeichnis, das der Host erstellt, in das er schreibt und das
  er rekursiv löscht. Es wird daher validiert:
  * nicht leer, und jedes Zeichen ist `[a-z0-9-]` (Kleinbuchstaben
    ASCII, Ziffern, Bindestrich);
  * **DARF NICHT** auf einen Punkt oder ein Leerzeichen enden (bereits
    durch das Charset ausgeschlossen; als separate Regel gehalten,
    damit eine spätere Lockerung des Charsets das Loch nicht still
    wieder einführen kann);
  * **DARF KEIN** reservierter MS-DOS-Gerätename unter der
    Stamm-Regel von §6.8 sein.

  Vektoren: `plugin-id-traversal`, `plugin-id-con` (siehe Divergenz
  F4). `con` ist unter Linux installierbar, unter Windows unmöglich,
  und für eine Linux-CI, die nur Dinge ausführt, unsichtbar.

## 10. `permissions` und `permissions_hash`

`MANIFEST.permissions` ist der `[permissions]`-Abschnitt des Plugins,
wörtlich kopiert: ein Objekt, das eine Permission-ID auf ein
Anfrage-Objekt abbildet (`{reason?, types?, scopes?}`). Sein Vokabular
und seine Bedeutung stehen in [`permissions.md`](permissions.md); dieser
Abschnitt definiert nur die Bytes und den Hash.

```
canonical_bytes  = RFC 8785 (JCS) serialisation of the permissions object
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( canonical_bytes ) )
```

Regeln:

* **`null` und `{}` sind derselbe Wert** — ein Plugin, das nach nichts
  fragt — und beide kanonisieren zu `{}`. Ein Produzent, der das
  Member weglässt, und einer, der ein leeres Objekt schreibt,
  **MÜSSEN** denselben Hash erzeugen. Dieser Hash ist
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
  = `sha256("{}")`, und er erscheint in den meisten Vektoren.
* Das Präfix `sha256:` ist **Teil des Werts**, anders als
  `files[].sha256`. Es trägt seinen Algorithmus, weil diese Zahl über
  eine Repository-Grenze hinweg verglichen wird — der Packer schreibt
  sie, die Registry leitet sie beim Ingest neu ab, der Host leitet sie
  neu ab, bevor er ihr glaubt.
* Leere Member werden **weggelassen**, nicht leer ausgegeben: eine
  Anfrage ohne reason, ohne types und ohne scopes ist `{}`, nie
  `{"reason":""}`. Zwei kanonische Schreibweisen einer Deklaration sind
  genau die Drift, die dieser Hash verhindern soll.
* JCS in der Praxis: Objektschlüssel nach UTF-16-Code-Unit sortiert,
  keine unbedeutende Whitespace, Strings escaped wie von RFC 8785
  §3.2.2.2 verlangt. Die Werte dieses Dokuments sind nur Strings,
  Arrays von Strings und Objekte — keine Zahlen — die subtile Hälfte
  von JCS (die Zahlenkanonisierung aus §3.2.2) kommt hier also nicht
  vor.

Durchgerechnetes Beispiel (Vektor `ok-permissions`, die Werte, an die
jede Implementierung gebunden ist):

```
{"fire_trigger":{"reason":"Fires the on_dice_roll trigger you configure"},"subscribe_events":{"reason":"Watches for command_completed"}}
→ sha256:63dde3632926bc9fb348e0973dbce01d07476a1569cede023edde451b04a6a85
```

und eines mit Argumenten, kanonisiert:

```
{"set_variable":{"scopes":["plugin"]},"subscribe_events":{"reason":"Watches for command_completed","types":["command_completed","tool_started"]}}
```

Ein Verifier **MUSS** den Hash aus `MANIFEST.permissions` neu
berechnen und ein Manifest ablehnen, das seinem eigenen
`permissions_hash` widerspricht. Vektor:
`permissions-hash-mismatch` — der `permissions`-Block fragt nach
`fire_trigger`, und der `permissions_hash` ist der Hash von `{}`, d. h.
die beiden beschreiben verschiedene Plugins. Siehe Divergenz F5 dafür,
wer das heute prüft.

## 11. Das Legacy-`SIGNATURE`/`PUBKEY`-Paar

Ein Pre-v2-Bundle konnte zwei zusätzliche Einträge tragen:
`SIGNATURE` (Base64 einer 64-Byte-Ed25519-Signatur über den
Verkettungs-Digest aus §3.3) und `PUBKEY` (Base64 des rohen
32-Byte-öffentlichen Schlüssels). Sie **laufen aus**, und solange sie
existieren:

* sie werden **nie** in `files` gelistet (sie werden über die
  gelisteten Dateien berechnet);
* ist einer vorhanden, **MÜSSEN BEIDE** vorhanden sein, und sie
  **MÜSSEN** die letzten zwei Einträge im Archiv sein, `SIGNATURE` dann
  `PUBKEY`. Alles danach läge außerhalb dessen, was die Signatur
  abdeckt. Vektor: `ok-legacy-signed` (ein Accept-Vektor — das Paar
  wird toleriert, nicht verlangt).
* **Sie sind kein Vertrauenssignal.** Ein Schlüssel, der im Archiv
  mitgeliefert wird, das er authentifiziert, beweist nichts darüber,
  wer ihn geschrieben hat, und der Digest, den sie abdecken, ist der
  mehrdeutige. Ein Verifier **DARF NICHT** ihre Anwesenheit, Gültigkeit
  oder Abwesenheit als Beweis für irgendetwas behandeln. Die Registry
  gibt eine Warnung aus (`W_LEGACY_SIGNATURE_ENTRY`) und macht weiter.

Ausmusterung, auf jeder Seite einmal benannt, damit die beiden nicht
auseinanderdriften können: das `LEGACY_PAIR_SUNSET` der CLI
(`astra-plugin 0.5.0 / Astra 0.4.0`) und das
`LEGACY_SIGNATURE_SUNSET` des Daemons
(`Astra 0.4.0 (astra-plugin 0.5.0)`). `astra-plugin build` schreibt sie
bereits nicht mehr; `astra-plugin sign` ist das Einzige, was das tut,
und es geht zusammen mit dem Reader des Daemons in die Ausmusterung.

## 12. Limits

Aus [`spec/limits.yaml`](../../../spec/limits.yaml), dem einen Ort, an
dem diese Zahlen deklariert sind:

| Limit | Wert | Gilt für |
|---|---|---|
| `max_archive_entries` | 10 000 | Anzahl der ZIP-Einträge, `MANIFEST.json` eingeschlossen |
| `max_extract_bytes` | 524 288 000 (500 MiB) | Gesamte unkomprimierte Bytes |
| Manifest-Obergrenze | 4 MiB | `MANIFEST.json` allein |

Ein Bundle, das eines davon überschreitet, **MUSS** abgelehnt werden.
Wende die Eintragsanzahl-Obergrenze **bevor** du einen Record pro
Eintrag zuweist an, und die Byte-Obergrenze sowohl auf die deklarierte
Summe des Manifests als auch auf die Bytes, die während des Streamings
tatsächlich ankommen — die deklarierten Zahlen sind die eigene
Behauptung des Archivs.

Die CLI verweigert das *Bauen* über diese Limits hinaus, sodass ein
Autor es auf der eigenen Maschine erfährt statt aus einer
fehlgeschlagenen Installation bei einem Nutzer.

## 13. Der Verifikationsalgorithmus

Das ist die implementierbare Form. Ein Verifier hält eine Datei und,
optional, eine Erwartung `(plugin_id, version, platform_key)` aus einem
Listing. Jeder Schritt ist bei Fehlschlag ein **Reject**.

**A. Die Datei.**
1. `artifact_digest = SHA256(file)`. Wurde ein erwarteter Digest
   übergeben und stimmt nicht überein, hier stoppen; nichts unten ist
   dann bedeutsam.

**B. Eintrag null, ab Offset 0.** (§4)
2. Den lokalen Dateiheader parsen. Name = `MANIFEST.json`; Flag-Bits 0
   und 3 gelöscht; Methode 0; Größe nicht der ZIP64-Sentinel und ≤
   4 MiB; die Manifest-Bytes herausschneiden.
3. `manifest_digest = SHA256("astra.bundle/2" ‖ 0x00 ‖ manifest_bytes)`.
4. Das Manifest als JSON parsen. `schema == "astra.bundle/2"`, exakt.

**C. Das zentrale Verzeichnis.** (§2, §4.1, §12)
5. Das Archiv normal öffnen. Eintragsanzahl ≤ 10 000.
6. Eintrag 0 im zentralen Verzeichnis ist `MANIFEST.json`, stored, und
   seine Bytes entsprechen denen aus Schritt 2.

**D. Struktur, vor jedem Inhalt.** (§6, §7, §12)
7. Die Einträge in Reihenfolge durchlaufen. Für jeden: §6 anwenden
   (Namensregeln, kein Verzeichnis, kein Symlink, kein exaktes oder
   case-gefaltetes Duplikat).
8. `Present` bilden (Eintragsnamen minus der drei reservierten Namen).
   `Present ⊆ Listed` und `Listed ⊆ Present` prüfen.
9. Für jede `files`-Zeile: 64 Kleinbuchstaben-Hex-`sha256`,
   parsbares vierstelliges Oktal-`mode`, kein doppelter `path`, kein
   reservierter `path`; das Array ist strikt aufsteigend nach `path`
   als Bytes.
10. Für jeden Eintrag in `Present`: deklarierte `size` stimmt überein,
    und — wo das Archiv einen Modus trägt — `mode & 0o777` stimmt
    überein.
11. Summe von `files[].size` ≤ 500 MiB.
12. Ist `SIGNATURE` oder `PUBKEY` vorhanden: beide sind es, und sie
    sind die letzten zwei Einträge in dieser Reihenfolge.
13. `entry.command` ist eine gelistete Datei oder eine Host-Runtime
    (§8).

**E. Inhalt.** (§7.2)
14. Für jeden Eintrag in `Present`, streamend und begrenzt durch die
    deklarierte Größe: SHA-256 des unkomprimierten Inhalts entspricht
    dem des Manifests. Extrahiert der Verifier auch, hash die Bytes,
    die er schreibt, nicht ein zweites Lesen.

**F. Cross-Checks, die das Format verlangt und die ein struktureller
Reader allein nicht machen kann.**
15. `permissions_hash` entspricht der Neuberechnung aus
    `MANIFEST.permissions` (§10).
16. `plugin.toml` parst, und `plugin.id` gehorcht §9. `plugin_id` /
    `version` / `platform` stimmen mit dem Listing überein, das das
    Bundle anbot, falls vorhanden.

Die Schritte A–E brauchen nur die Datei. Schritt F braucht die Datei
und das Listing.

## 14. Goldene Vektoren

`testdata/bundles/` hält 27 eingefrorene `.astraplugin`-Dateien,
`vectors.json` (Urteil, Ebene, beide Digests, und was jede
Implementierung heute tut) und `SHA256SUMS`. Die zwei Konsumenten
halten gevendorte Kopien
(`Astra/astra-rs/astra-daemon/testdata/bundles/`,
`astra-registry/tests/vectors/`), aufgefrischt von
`tools/vendor-testdata.sh`. Jede Suite verifiziert ihre Kopie gegen
`SHA256SUMS`, bevor sie auch nur einen Vektor liest.

**Keine Suite regeneriert ihre Fixtures.** Eine Suite, die ihre
Eingaben aus dem heutigen Code gebaut hätte, würde behaupten, dass der
heutige Code mit sich selbst übereinstimmt.

### Accept (5)

| Vektor | Was er beweist |
|---|---|
| `ok-minimal` | die Kontrolle. Jede Ablehnung muss eine Ablehnung *von* etwas sein |
| `ok-noarch-runtime` | `platform: any/any` + `entry.command: "node"` — wie jedes TypeScript- und Python-Plugin ausgeliefert wird (§5.2, §8) |
| `ok-permissions` | eine nicht leere Permission-Map mit korrektem Hash — drei JCS-Implementierungen gezwungen zuzustimmen (§10) |
| `ok-legacy-signed` | das auslaufende Paar, letzte zwei Einträge, in Reihenfolge (§11) |
| `collision-a-bc` | die ehrliche Hälfte des Kollisionspaars (§3.3) |

### Reject (22)

| Vektor | Regel, die ablehnt |
|---|---|
| `collision-ab-c` | §7.1, **beide** Richtungen |
| `extra-file` | §7.1 `Present ⊆ Listed` |
| `missing-file` | §7.1 `Listed ⊆ Present` |
| `duplicate-entry` | §6.9 exaktes Duplikat |
| `duplicate-entry-case` | §6.9 case-gefaltetes Duplikat (F1) |
| `symlink-entry` | §6.11 |
| `content-digest-mismatch` | §7.2 (F2) |
| `size-mismatch` | §7.3 |
| `mode-mismatch` | §7.4 (F3) |
| `uppercase-digest` | §7 `sha256`-Charset |
| `unsorted-files` | §7.5 |
| `manifest-not-first` | §4 |
| `manifest-compressed` | §4 |
| `header-disagree` | §4.1 |
| `path-traversal` | §6.6 (und §7.1: der Eintrag ist ungelistet) |
| `path-ads` | §6.4 (und §7.1) |
| `path-trailing-dot` | §6.7 (und §7.1) |
| `entry-command-shell` | §8 |
| `entry-command-escape` | §8 |
| `plugin-id-traversal` | §9 (F4) |
| `plugin-id-con` | §9 (F4) |
| `permissions-hash-mismatch` | §10 (F5) |

Anmerkung zu den drei `path-*`-Vektoren: jeder versteckt seinen
feindseligen Eintrag *außerhalb* von `MANIFEST.files`, ein Verifier,
der nur §7.1 implementiert, lehnt also alle drei ab. Er sollte trotzdem
§6 implementieren — an dem Tag, an dem ein Manifest einen solchen Pfad
listet, hat die Vollständigkeit nichts zu sagen, und nur die
Namensregeln haben es.

### 14.1 Selbsttest-Werte

Für jede Implementierung ist die schnellste erste Prüfung, dass beide
Digests jedes Vektors mit `vectors.json`s `artifact_sha256` und
`manifest_digest` übereinstimmen. Diese Zahlen kommen von keinem der
drei Programme:
`testdata/bundles/handcheck.sh` leitet sie erneut aus `dd`, `od`,
`printf`, `cat` und `sha256sum` ab. 27 Artefakt-Digests und 25
Manifest-Digests stimmen überein — die zwei ausgelassenen sind
`manifest-not-first` und `manifest-compressed`, deren Eintrag null per
Konstruktion kein gespeichertes Manifest ist. Ein gemeinsamer Bug kann
drei Programme dazu bringen, einander zuzustimmen; er kann sie nicht
dazu bringen, coreutils zuzustimmen.

## 15. Bekannte Divergenzen

Diese stehen in `vectors.json` unter `divergence`, und jede wird von
allen drei Suiten geprüft — ein fehlerhaftes Verhalten mit einem Test,
der die Farbe wechselt, wenn es behoben ist, statt eines TODO in einem
Kommentar. **In jeder Zeile ist das Urteil dieses Dokuments die
richtige Antwort.**

| | Vektor | wer aus der Reihe tanzt | warum es dort ist, wo es ist |
|---|---|---|---|
| **F1** | `duplicate-entry-case` | nur der Daemon faltet Groß-/Kleinschreibung vor der Duplikatsuche | die CLI und die Registry verwenden exakte Match-Sets. Beide sollten falten. |
| **F2** | `content-digest-mismatch` | der Vor-Extraktions-Durchlauf des Daemons akzeptiert es | **Absicht.** Der Daemon hasht Inhalt *während* der Extraktion, die gehashten Bytes sind also die geschriebenen. Kein Loch; dieselbe Prüfung zu einem anderen Zeitpunkt. |
| **F3** | `mode-mismatch` | der Registry-Bot vergleicht Modi überhaupt nicht (nur Warnung) | Modi werden vom Installer angewendet, nicht von der Registry, sie hat die Prüfung also herabgestuft. §7.4 sagt: vergleichen. |
| **F4** | `plugin-id-*` | die CLI validiert keines davon, weder in `verify` noch in `check` | `PluginManifest::validate` des Daemons und `invalidId` der Registry lehnen beide ab. Die eigene Maschine des Autors sollte das auch. |
| **F5** | `permissions-hash-mismatch` | nur der Bundle-Reader der CLI berechnet den Hash nicht neu | der Daemon blockiert die Installation (`PERMISSIONS_HASH_MISMATCH`), und die Registry lehnt das Listen ab (`E_PERMISSIONS_HASH_MISMATCH`). |

Schließt du eine, lösche den `divergence`-Block und setze das
`expect` dieser Implementierung auf das Urteil — die Suiten sagen es
dir in dem Moment, in dem du es getan hast.

## 16. Was ein verifiziertes Bundle dir sagt und nicht sagt

**Sagt:** diese Bytes sind exakt die Bytes, deren Manifest sie listet,
jede Datei im Archiv ist in beide Richtungen erfasst, nichts extrahiert
außerhalb des Installationsverzeichnisses, und der Digest, den du
hältst, ist der Digest, den jeder andere, der ihn über diese Datei
berechnet, erhält.

**Sagt nicht:** wer es geschrieben hat (das ist die Attestation und der
signierte Index — [`registry-index.md`](registry-index.md)), ob es
gerade zurückgezogen ist (das ist die Widerrufsliste), was es zur
Laufzeit aufrufen darf ([`permissions.md`](permissions.md)), oder was
der Prozess der Maschine antun kann, sobald er startet. Ein Plugin
läuft als der Nutzer, mit den Rechten des Nutzers. Nichts an diesem
Format ändert das, und nichts an Astras UI darf suggerieren, dass es
das tut.

---

*Beim Schreiben dieses Dokuments geprüfte Quellen, alle beim Commit
gelesen, auf dem dies landete: `astra-plugin-cli/src/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`, `jcs`);
`Astra/astra-rs/astra-plugin-manifest/src/manifest.rs` (`validate`,
`is_reserved_device_name`); `astra-registry/bot/lib/bundle.mjs`;
`astra-registry/tools/lib/canonical.mjs`; `spec/limits.yaml`;
`testdata/bundles/{README.md,vectors.json}` und die Vektor-Bytes
selbst.*
</content>
