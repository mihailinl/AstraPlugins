<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit para plugins

Usa los controles reales de Astra en lugar de copiar su CSS. El runtime viene con la aplicación instalada; el paquete público contiene solo declaraciones y el adaptador de compilación.

El frontend se elige independientemente del backend Rust, Python o TypeScript. Vanilla es el valor predeterminado. React tiene su propio paquete y lockfile congelado en frontend/. Instala allí antes de astra-plugin build o dev.

## API y componentes

Espera a loadUi antes de mostrar controles. h recibe un componente o etiqueta, props e hijos. mount aporta el entorno del host y devuelve render/unmount. Props y callbacks coinciden con Astra. Los cambios de idioma, paleta y material conservan el árbol y el estado del formulario.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`, `ScrollArea`

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

## React y empaquetado

Usa @astra/plugin-ui/build: el adaptador redirige UI, React, ReactDOM y JSX a rutas fijas del host. No empaquetes otra copia de React. El bootstrap espera loadUi e importa dinámicamente la aplicación React para mostrar un aviso de actualización si falla la carga. CI instala dependencias frontend con lockfile congelado para cada backend.

## Compatibilidad y verificación

API v1 conserva nombres y firmas; el aspecto evoluciona con Astra. Los menús/modales de páginas normales quedan en el iframe; Select/Tooltip y las superficies declaradas del widget se dibujan en el host fuera de la tarjeta. Se admiten interfaces propias y plugins antiguos. Prueba Select dentro de Modal, Escape, retorno del foco, paletas, frames estrechos y vidrio en ventanas reales de Tauri/Windows y Electron/Linux, incluido el bundle instalado sin red.

La versión mínima del snapshot identifica el build preparado de Astra con Kit; 0.2.7 aún no está publicado. CLI 0.5.0 tampoco. No los describas como ya distribuidos.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Desktop widgets (development contract)

La plantilla `desktop-widget` usa este Kit en las tarjetas y superficies de cristal del host. La [guía completa](desktop-widgets.md) explica los campos exactos, callbacks de valores, `context.params`, tokens, el borrador abierto por el editor y las vistas previas de solo lectura. Use los artefactos CLI/SDK compatibles proporcionados; estas funciones todavía no están publicadas.

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
