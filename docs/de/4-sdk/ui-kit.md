<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Plugin UI Kit

Verwende Astras echte Bedienelemente statt kopierter CSS-Regeln. Die Runtime gehört zur installierten Anwendung; das öffentliche Paket enthält nur Typdeklarationen und den Build-Adapter.

Das Frontend wird unabhängig vom Rust-, Python- oder TypeScript-Backend gewählt. Vanilla ist der Standard. React besitzt ein eigenes Paket und einen eingefrorenen Lockfile in frontend/. Installiere dort vor astra-plugin build oder dev.

## API und Komponenten

Warte vor der Anzeige auf loadUi. h nimmt Komponente oder Tag, Props und Kinder an. mount stellt die Host-Umgebung bereit und liefert render/unmount. Props und Callbacks entsprechen Astra. Sprach-, Paletten- und Materialänderungen erhalten Baum und Formularzustand.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`, `ScrollArea`, `Advanced`, `Collapse`, `ProgressBar`, `WidgetHead`, `WidgetMetric`, `AstraLine`, `WidgetPlate`, `WidgetMeter`, `WidgetPlateButton`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; controlled values match the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
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

Erfordert Astra 0.2.7 oder neuer und CLI 0.5.1 oder neuer (`cargo install astra-plugin-cli`). In einem älteren Astra zeigt das Template statt der Steuerelemente einen Hinweis zum Aktualisieren.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Abschnitte auf Settings, AI und Voice

Ein Beitrag in `settings.custom`, `ai.custom` oder `voice.custom` wird zu einem Abschnitt dieser Seite. Astra zeichnet den Rahmen: die Clay-Karte, die Überschrift aus `label`, das Zeichen aus `icon_svg`, ein Badge mit dem Pluginnamen, einen Eintrag in der Abschnittsnavigation (und in der Suche von Settings). Rendern Sie nur den Inhalt — `SettingRow`, `Card` mit `variant: 'subtle'`, `Advanced` — nie ein äußeres `Section`, sonst zeigt die Seite eine Karte in einer Karte mit zwei Überschriften. `Select`, `Combobox` und `Tooltip` des Kits zeichnet Astra über der Seite, wie bei einem Widget; ein `Modal` oder `Popover` bleibt im Frame, deklarieren Sie also eine `height`, wenn Sie eines öffnen. Mit `height = 0` folgt der Rahmen der Höhe des Dokuments; setzen Sie `html` und `body` daher nicht auf `100%`. Eine `height` ungleich 0 bleibt fest. `settings.custom` erscheint außerdem auf der Pluginkarte unter Plugins.

Das Aussehen ist Astras Graphite: Clay-Flächen (mattiert, wenn Glass eingeschaltet ist), ein vom Nutzer gewählter Akzent, erhabene Flächen für Buttons und Mulden für Eingabefelder. Das Kit trägt es bereits. Die entfernten `--glass-*`-Tokens werden nicht mehr veröffentlicht; für eigene Flächen lesen Sie `--color-surface`, `--color-surface-raised`, `--color-text` und `--color-text-muted`.

## Desktop widgets (development contract)

Das `desktop-widget`-Template verwendet dieses Kit in den Clay-Karten und Oberflächen des Hosts. Die [vollständige Anleitung](desktop-widgets.md) beschreibt exakte SDK-Felder, Wert-Callbacks, `context.params`, Rückgabe-Token, den vom Host geöffneten Einstellungsentwurf und schreibgeschützte Vorschauen. Widgets sind in Astra 0.2.7 enthalten; die veröffentlichten SDKs (Rust 0.7.4, Python 0.6.4, TypeScript 0.7.3) und CLI 0.5.1 unterstützen sie. Bauen Sie die Kartenfläche aus `WidgetHead`, `WidgetMetric`, `AstraLine`, `WidgetPlate`, `WidgetMeter` und `WidgetPlateButton` — der Anatomie von Astras eigenen Widgets; der Rahmen ist ihr Größencontainer `desktop-widget`.

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
