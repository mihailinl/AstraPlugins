<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Plugin UI Kit

Use Astra’s own controls instead of reproducing their CSS. The runtime ships with the installed application; the public package supplies declarations and a build adapter only.

Choose a frontend independently of Rust, Python or TypeScript backend. Vanilla is the default. React projects keep their package and frozen lockfile in frontend/. Install there before astra-plugin build or dev.

## API and components

Wait for loadUi before displaying controls. h accepts a component or tag, props and children. mount supplies the host environment and returns render/unmount. Props and callbacks match Astra. Language, palette and material changes keep the mounted tree and its form state.

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

## React and packaging

Use @astra/plugin-ui/build; the adapter resolves UI, React, ReactDOM and JSX imports to fixed host routes. Do not bundle React again. A bootstrap must await loadUi before dynamically importing the React app, so missing resources produce an update message. Release CI installs frontend dependencies with the frozen lockfile for every backend.

## Compatibility and verification

API v1 keeps export names and signatures; appearance follows Astra. Ordinary page menus/modals stay in the iframe; desktop widget Select/Tooltip and declared surfaces are rendered by the host outside the card. Custom interfaces and existing plugins remain supported. Test Select inside Modal, Escape, focus return, palette changes, narrow frames and glass in the real Tauri/Windows and Electron/Linux windows, including an offline installed bundle.

The minimum version in the snapshot names the prepared Astra build containing the Kit; {{MIN_ASTRA_VERSION}} is unreleased until Astra publishes it. The CLI is 0.5.0, also unreleased. Do not describe either as already shipped.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)

## Desktop widgets (development contract)

The `desktop-widget` scaffold uses this Kit inside Astra’s glass cards, popovers and modals. Call `astra.widget.getContext()` after initialization; `viewId` selects content. Custom settings edit the host draft, opened only by Astra’s editor; Save applies it and Cancel discards it. Preview is read-only, including instance data writes and backend calls. `openSurface` returns a token, opening parameters are `context.params`, and controls use value callbacks. See the [complete descriptor and content examples](desktop-widgets.md). The widget runtime and matching SDK changes are unreleased; use matching supplied artifacts and pin the runtime floor when Astra ships.

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
