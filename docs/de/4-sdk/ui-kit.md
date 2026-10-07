<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Plugin UI Kit

Verwende Astras echte Bedienelemente statt kopierter CSS-Regeln. Die Runtime gehört zur installierten Anwendung; das öffentliche Paket enthält nur Typdeklarationen und den Build-Adapter.

Das Frontend wird unabhängig vom Rust-, Python- oder TypeScript-Backend gewählt. Vanilla ist der Standard. React besitzt ein eigenes Paket und einen eingefrorenen Lockfile in frontend/. Installiere dort vor astra-plugin build oder dev.

## API und Komponenten

Warte vor der Anzeige auf loadUi. h nimmt Komponente oder Tag, Props und Kinder an. mount stellt die Host-Umgebung bereit und liefert render/unmount. Props und Callbacks entsprechen Astra. Sprach-, Paletten- und Materialänderungen erhalten Baum und Formularzustand.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React und Paketierung

Nutze @astra/plugin-ui/build: Der Adapter leitet UI-, React-, ReactDOM- und JSX-Importe auf feste Host-Pfade um. Bünde keine zweite React-Runtime. Der Bootstrap wartet auf loadUi und importiert die React-App dynamisch, damit Ladefehler einen Update-Hinweis zeigen. Release-CI installiert Frontend-Abhängigkeiten mit eingefrorenem Lockfile für jedes Backend.

## Kompatibilität und Prüfung

API v1 behält Exportnamen und Signaturen; das Aussehen folgt Astra. Menüs, Dialoge und Fokus bleiben im iframe. Eigene Oberflächen und alte Plugins bleiben unterstützt. Prüfe Select in Modal, Escape, Fokusrückgabe, Paletten, schmale Frames und Glas in echten Tauri/Windows- und Electron/Linux-Fenstern, auch im installierten Offline-Bundle.

Die Mindestversion im Snapshot benennt den vorbereiteten Astra-Build mit Kit; 0.2.7 ist noch unveröffentlicht. CLI 0.5.0 ebenfalls. Bezeichne beide nicht als bereits ausgeliefert.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
