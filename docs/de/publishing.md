# Plugins veröffentlichen

Alles, was Sie brauchen, um aus Quellcode ein signiertes, verteilbares Bundle zu machen, das Nutzer in Astra sideloaden können.

## Das `.astraplugin`-Bundle

`.astraplugin` ist ein **ZIP-Archiv** mit einem festen Layout. Der Daemon validiert es, verifiziert (optional) die Signatur, extrahiert es in sein Plugin-Verzeichnis und startet `entry.command` mit Anmeldeinformationen.

```
<plugin-id>-<version>.astraplugin
├── plugin.toml                # Manifest
├── bin/                       # Kompilierte Binärdatei (nur Rust)
│   └── my_plugin.exe
├── dist/                      # Gebündeltes JS (nur TypeScript)
│   └── index.js
├── src/                       # Python-Quellen (nur Python)
│   ├── plugin.py
│   └── __init__.py
├── requirements.txt           # Python-Abhängigkeiten (nur Python)
├── requirements.lock          # Python-Abhängigkeiten, von uv aufgelöst (nur Python)
├── ui/                        # Eigene UI-Dateien (optional)
├── locales/                   # i18n-JSON-Dateien (optional)
├── icon.png | icon.svg        # Optionales Branding
├── README.md                  # Optional
├── LICENSE                    # Optional
├── SIGNATURE                  # Ed25519-Signatur (wenn signiert)
└── PUBKEY                     # Ed25519-Public-Key (wenn signiert)
```

Wenn `astra-plugin build` ein Archiv erstellt:

1. Führt es den sprachspezifischen Build-Schritt aus.
2. Kopiert das kompilierte Artefakt in das erwartete Verzeichnis.
3. Schreibt `entry.command` um, sodass es auf den gebündelten Pfad zeigt (nur Rust — Python/TS-Pfade im Archiv sind stabil).
4. Fügt `ui/`, `locales/`, Icon und Dokumente hinzu, falls sie neben `plugin.toml` existieren.
5. Wenn `~/.astra/plugin-keys/private.key` vorhanden ist, signiert es jeden Eintrag mit Ed25519 und fügt `SIGNATURE` und `PUBKEY` hinzu.

## Signieren

### Ein Schlüsselpaar erzeugen

```bash
astra-plugin keygen
```

Ausgabe:

- `~/.astra/plugin-keys/private.key` — base64-kodiertes Ed25519-Seed. **Geheim halten.** Wer diese Datei besitzt, kann neue Versionen Ihres Plugins signieren, und Nutzer werden ihnen vertrauen.
- `~/.astra/plugin-keys/public.key` — kann veröffentlicht werden.

Fügen Sie `--force` hinzu, um ein vorhandenes Schlüsselpaar zu überschreiben (nützlich für Rotation — aber das hebt bereits etablierte Vertrauensbeziehungen auf).

### Signieren während des Builds

Es gibt keinen separaten Signier-Befehl: Sobald ein Schlüsselpaar existiert, signiert `astra-plugin build` automatisch. Das Archiv enthält:

- `SIGNATURE` — ein signiertes Manifest jeder anderen Datei im Archiv.
- `PUBKEY` — der verwendete Public-Key. Nutzer können ihn mit einem bekannten Referenzwert (Ihre Website, Ihre Key-Pinning-Policy) vergleichen, bevor sie installieren.

Um einen **unsignierten** Build zu veröffentlichen, löschen Sie entweder den Private-Key oder bauen Sie auf einer Maschine, die ihn nicht hat.

### Signaturen verifizieren

Die Signaturverifikation erfolgt auf Daemon-Seite beim Sideloading. Der Daemon zeigt den `PUBKEY` des Bundles in der Plugins-UI, damit Nutzer Fingerprints vor dem Klick auf „Installieren" vergleichen können.

## Verteilung

### Direkter Download

Stellen Sie die `.astraplugin`-Datei auf Ihrer Website, in GitHub Releases oder einem beliebigen Filehoster bereit. Nutzer laden herunter und ziehen die Datei auf die Plugins-Seite von Astra.

### Git + Release-Artefakte

Typischer Release-Workflow:

1. `plugin.version` in `plugin.toml` erhöhen.
2. Committen, taggen (`git tag v0.2.0`), pushen.
3. `astra-plugin validate` → `astra-plugin build -o dist/plugin-0.2.0.astraplugin`.
4. `.astraplugin` in das GitHub-Release für diesen Tag hochladen.

CI-freundlich, weil `astra-plugin` eine einzelne Binärdatei ist.

### Registry

Eine zentrale Plugin-Registry ist geplant. Bis sie ausgeliefert wird, teilen Sie Plugins über direkte URLs.

## Sideloading

Der Daemon stellt zwei RPCs zur Installation eines `.astraplugin` bereit:

- `SideloadPlugin(bytes)` — akzeptiert das Bundle über gRPC. Wird vom Dateipicker der Astra-UI verwendet.
- `ImportPluginFile(path)` — weist den Daemon an, die Datei von der Platte zu lesen. Wird verwendet, wenn ein Nutzer die Datei in die UI zieht.

Beide verifizieren die Signatur (falls vorhanden), validieren das Manifest, extrahieren in `~/.astra/plugins/<id>/` und starten den Prozess.

Das Deinstallieren eines Plugins stoppt den Prozess, entfernt das extrahierte Verzeichnis und löscht den Plugin-Zustand.

## Upgrade-Strategie

- Erhöhen Sie `plugin.version` für jeden Release.
- Der Daemon speichert installierte Plugin-Versionen und zeigt ein „Update verfügbar"-Badge, wenn das neue Bundle eine höhere SemVer hat.
- Breaking-Config-Änderungen? Fügen Sie neue Felder mit Defaults hinzu, anstatt bestehende umzubenennen — der Daemon behält die alte Konfiguration beim Upgrade bei.

## Lokalisierung

Liefern Sie ein `locales/`-Verzeichnis innerhalb Ihres Bundles aus:

```
locales/
├── en.json
├── ru.json
├── uk.json
├── de.json
├── es.json
├── zh-CN.json
└── ja.json
```

Jedes SDK hat einen `I18n`-Helper, der diese Dateien liest und bei unbekannten Schlüsseln elegant zurückfällt. Das Manifest übersetzt Feldbezeichnungen (`ActionType.MyAction`, `FieldLabel.X`) — halten Sie die IDs im Code stabil und den Anzeigetext in den JSON-Dateien.

## Checkliste vor einem Release

- [ ] `astra-plugin validate` läuft fehlerfrei durch.
- [ ] `astra-plugin build` ist erfolgreich und produziert ein Archiv in vernünftiger Größe.
- [ ] `plugin.toml` hat `description`, `author` und `license`.
- [ ] Das `[config]`-Schema (falls vorhanden) hat sinnvolle Defaults für jedes Feld.
- [ ] Das Bundle wurde per Sideloading in einer sauberen Daemon-Instanz getestet.
- [ ] Der `PUBKEY`-Fingerprint ist irgendwo dokumentiert, wo Nutzer ihn verifizieren können.
- [ ] `locales/` deckt alle Strings ab, die das Plugin Nutzern zeigt.
- [ ] `README.md` dokumentiert, was das Plugin tut und welche Laufzeit-Anforderungen es hat.
- [ ] Sie haben einen Weg, Nutzer zu erreichen, falls ein kompromittierter Release zurückgerufen werden muss.
