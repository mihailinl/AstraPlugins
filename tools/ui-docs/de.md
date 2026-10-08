<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Plugin UI Kit

Verwende Astras echte Bedienelemente statt kopierter CSS-Regeln. Die Runtime gehört zur installierten Anwendung; das öffentliche Paket enthält nur Typdeklarationen und den Build-Adapter.

Das Frontend wird unabhängig vom Rust-, Python- oder TypeScript-Backend gewählt. Vanilla ist der Standard. React besitzt ein eigenes Paket und einen eingefrorenen Lockfile in frontend/. Installiere dort vor astra-plugin build oder dev.

## API und Komponenten

Warte vor der Anzeige auf loadUi. h nimmt Komponente oder Tag, Props und Kinder an. mount stellt die Host-Umgebung bereit und liefert render/unmount. Props und Callbacks entsprechen Astra. Sprach-, Paletten- und Materialänderungen erhalten Baum und Formularzustand.

{{COMPONENTS}}

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; controlled values match the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: {{API_VERSION}}});
let title = 'Hello';
let limit = 10;
const root = ui.mount(container, null);
function render() {
  root.render(ui.h('div', null,
    ui.h(ui.SettingRow, {label: 'Title', htmlFor: 'title', control: ui.h(ui.Input, {
      id: 'title', value: title, onChange: value => {title = value; render();},
    })}),
    ui.h(ui.NumberInput, {value: limit, min: 1, max: 100, step: 1,
      onChange: value => {limit = value; render();}}),
    ui.h(ui.Select, {value: title, options: [{value: 'Hello', label: 'Hello'},
      {value: 'Tasks', label: 'Tasks'}], onChange: value => {title = value; render();}}),
    ui.h(ui.Combobox, {value: title, freeSolo: true, options: [{value: 'Tasks', label: 'Tasks'}],
      onChange: value => {title = value; render();}}),
    ui.h(ui.Tooltip, {content: 'Choose or type a title.', placement: 'bottom'},
      ui.h(ui.Button, {'aria-label': 'About the title'}, 'Help'))));
}
render();
// On teardown: root.unmount(). Value callbacks are not DOM change events.
```

## React und Paketierung

Nutze @astra/plugin-ui/build: Der Adapter leitet UI-, React-, ReactDOM- und JSX-Importe auf feste Host-Pfade um. Bünde keine zweite React-Runtime. Der Bootstrap wartet auf loadUi und importiert die React-App dynamisch, damit Ladefehler einen Update-Hinweis zeigen. Release-CI installiert Frontend-Abhängigkeiten mit eingefrorenem Lockfile für jedes Backend.

## Kompatibilität und Prüfung

API v1 behält Exportnamen und Signaturen; das Aussehen folgt Astra. Menüs und Modals normaler Seiten bleiben im iframe; Widget-Select/Tooltip und deklarierte Oberflächen rendert der Host außerhalb der Karte. Eigene Oberflächen und alte Plugins bleiben unterstützt. Prüfe Select in Modal, Escape, Fokusrückgabe, Paletten, schmale Frames und Glas in echten Tauri/Windows- und Electron/Linux-Fenstern, auch im installierten Offline-Bundle.

Die Mindestversion im Snapshot benennt den vorbereiteten Astra-Build mit Kit; {{MIN_ASTRA_VERSION}} ist noch unveröffentlicht. CLI 0.5.0 ebenfalls. Bezeichne beide nicht als bereits ausgeliefert.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Desktop widgets (development contract)

Das `desktop-widget`-Template verwendet dieses Kit in den Glas-Karten und Oberflächen des Hosts. Die [vollständige Anleitung](desktop-widgets.md) beschreibt exakte SDK-Felder, Wert-Callbacks, `context.params`, Rückgabe-Token, den vom Host geöffneten Einstellungsentwurf und schreibgeschützte Vorschauen. Verwenden Sie passende bereitgestellte CLI/SDK-Artefakte; diese Funktionen sind noch nicht veröffentlicht.

## Shared scrollbars

Scrollbar tracks and thumbs are invisible by default in Astra and plugin documents; wheel, touch and keyboard scrolling still work. The bridge applies this policy even to plain HTML plugins that do not call `astra.loadUi()`.

Enable the shared appearance explicitly on the actual scrolling element using `class="ui-scrollbar-visible"`, or set `scrollbar: true` on `ScrollArea`. For document scrolling, apply the class to `document.scrollingElement` (normally html). Visibility is local: nested scrollers stay hidden. `ui-scrollbar-hidden` overrides explicit visibility. Do not recreate scrollbar CSS or set `scrollbar-width/color`.

`ScrollArea` accepts normal HTML div props, a forwarded ref, `tabIndex=0`, `orientation: 'vertical' | 'horizontal' | 'both'` (default both), and `scrollbar?: boolean` (default false). Constrain its height/width and pass a localized accessible label. Explicitly visible bars use the desktop rail's rounded neutral thumb, track and hover colors, without browser arrows. State/data/backend behavior stays with the owner.

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; ScrollArea props match the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
ui.mount(container, ui.h(ui.ScrollArea, {
  scrollbar: true, orientation: 'vertical', 'aria-label': 'History', style: {maxHeight: 240},
}, ui.h('div', null, 'Scrollable content')));
```

React: `<ScrollArea scrollbar orientation="vertical" aria-label={label} style={{maxHeight: 240}}>{rows}</ScrollArea>`. Omit `scrollbar` for invisible scrolling. Switching the prop changes visibility without replacing the viewport. Visible scrollbars follow palettes and forced colors and occupy a 12px native gutter when needed; `scrollbar-gutter: stable` can reserve it. The Desktop and OOBE custom rails are explicitly rendered controls, using the same appearance tokens.
