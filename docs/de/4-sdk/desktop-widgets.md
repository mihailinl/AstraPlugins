<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Desktop-Widgets

## Passende Werkzeuge

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

Desktop widgets are user-placed cards on Astra’s Home grid. Use the existing capability `ui_contributions` and slot `desktop.widget`; no new permission or `dom_access` is needed. Astra renders the glass shell, borders, fonts, placement and floating surfaces. The plugin renders transparent content. The overlay remains separate.

This contract is unreleased. Use the development CLI and SDK artifacts supplied for your Astra build; do not assume a registry package with the same version contains it. If building the public authoring checkout, run `cargo build --release --manifest-path astra-plugin-cli/Cargo.toml` (Rust and protoc required), then use that binary. You do not need Astra’s private source.

<!-- doctest: cli -->
```bash
astra-plugin new my-counter --lang python --template desktop-widget --ui vanilla
astra-plugin new my-counter-react --lang rust --template desktop-widget --ui react
```

Backend language (Rust/Python/TypeScript) and frontend (vanilla/React) are independent. The [maintained example](../../../examples/desktop-widget/README.md) and scaffold show both formats, two independent instances, a menu, details and both settings editors. Do not invent an author or accept the scaffold’s license default on the user’s behalf. For an explicitly authorized local test without publication, leave an unknown author empty and omit the license field while undecided. Confirm the author and license with the owner before publication.

Manifest metadata has an English base: write plugin.description in English; listing.name and listing.description in locales/en.json must exactly match plugin.name and plugin.description. Put translated listing text in locales/ru.json (or the appropriate locale), and localize UI labels with keys. After editing name/description, run `astra-plugin locale sync --path .`, then check --strict; this avoids E8 (mismatching keys) and E11 (non-English description). See [localisation](../3-reference/localisation.md).

## Passendes SDK

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

For an unreleased local build, replace the scaffold’s registry dependency with the supplied matching artifact. Rust: set `astra-plugin-sdk = { path = "<relative-sdk-directory>" }` in Cargo.toml, or use the supplied vendored crate. Python: install the supplied SDK wheel or directory into an isolated environment and align requirements with it. TypeScript: use `"astra-plugin-sdk": "file:<relative-sdk-directory-or-tgz>"`, then install; a source SDK directory needs its own `bun run build` first to generate dist. These are build inputs, not installed-plugin paths.

For React, install `frontend/` dependencies with `bun install --frozen-lockfile`, for every backend. The frontend uses `@astra/plugin-ui/build`; do not bundle a second React. A built Rust or bundled TypeScript backend does not require an SDK source checkout on the receiving machine. Python needs the declared interpreter and installed runtime SDK dependencies; do not claim the SDK source directory is bundled automatically.

## Exakte Deskriptoren

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

Replace the scaffold’s backend implementation with the matching module below. Resource paths refer to `ui/`; the shared `index.html` branches on the context, so you need only one HTML entrypoint. The examples cover every descriptor field and the contextual backend hook.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;
use serde_json::json;

#[derive(Default)]
struct Counter;

#[astra::plugin(capabilities = "ui_contributions")]
impl Counter {
    #[hook]
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::widget("counter", "Instance counter",
            DesktopWidget::new(vec![
                WidgetFormat::new("compact", "Compact", "index.html", 2, 2)
                    .with_limits(2, 2, 2, 2).fixed().with_appearance("icon")
                    .with_preview("index.html?sample=1").with_readable_size(120, 90),
                WidgetFormat::new("expanded", "Expanded", "index.html", 4, 3)
                    .with_limits(3, 2, 8, 6).with_appearance("card")
                    .with_readable_size(220, 120),
            ]).repeatable().with_surfaces(vec![
                WidgetSurface::popover("menu", "Menu", "index.html")
                    .with_size(280, 220).with_limits(200, 160, 400, 400),
                WidgetSurface::modal("details", "Details", "index.html")
                    .with_size(480, 320).with_limits(320, 240, 640, 600),
                WidgetSurface::modal("settings", "Settings", "index.html")
                    .with_size(480, 360).with_limits(320, 240, 640, 600),
            ]).with_fields(vec![
                FieldDef::text("title", "Title").with_default("My counter"),
                FieldDef::number("limit", "Count limit").with_default("100")
                    .with_min(1.0).with_max(1000.0).with_step(1.0),
            ]).with_settings_surface("settings"))]
    }

    #[hook]
    async fn handle_widget_ui_call(&self, _ctx: &PluginContext, method: &str,
        _params_json: &str, widget: Option<&WidgetContext>) -> Result<String, ToolError> {
        if method != "ping" { return Err(ToolError::NotFound(method.into())); }
        Ok(json!({"instance": widget.map(|w| &w.instance_id)}).to_string())
    }
}

astra::main!(Counter::default());
```

<!-- doctest: python-plugin -->
```python
from astra_plugin_sdk import (
    Plugin, UiContribution, DesktopWidget, WidgetFormat, WidgetSurface, Field,
)

class Counter(Plugin):
    async def get_ui_contributions(self):
        return [UiContribution.widget("counter", "Instance counter", DesktopWidget(
            repeatable=True,
            formats=[
                WidgetFormat(id="compact", label="Compact", url="index.html",
                    preview_url="index.html?sample=1", appearance="icon",
                    default_w=2, default_h=2, min_w=2, min_h=2, max_w=2, max_h=2,
                    fixed_size=True, min_pixel_width=120, min_pixel_height=90),
                WidgetFormat(id="expanded", label="Expanded", url="index.html",
                    appearance="card", default_w=4, default_h=3, min_w=3, min_h=2,
                    max_w=8, max_h=6, min_pixel_width=220, min_pixel_height=120),
            ],
            surfaces=[
                WidgetSurface.popover("menu", "Menu", "index.html", width=280,
                    height=220, min_width=200, min_height=160, max_width=400, max_height=400),
                WidgetSurface.modal("details", "Details", "index.html", width=480,
                    height=320, min_width=320, min_height=240, max_width=640, max_height=600),
                WidgetSurface.modal("settings", "Settings", "index.html", width=480,
                    height=360, min_width=320, min_height=240, max_width=640, max_height=600),
            ],
            config_fields=[
                Field.text("title", "Title", default="My counter"),
                Field.number("limit", "Count limit", default="100", min=1, max=1000, step=1),
            ], settings_surface="settings"))]

    async def handle_widget_ui_call(self, method, params_json, widget):
        if method == "ping":
            return {"instance": widget.instance_id if widget else None}
        return await self.handle_ui_call(method, params_json)

if __name__ == "__main__":
    Counter().run()
```

<!-- doctest: ts-plugin -->
```ts
import { plugin, UiContrib, Field, type DesktopWidget } from "astra-plugin-sdk";

const widget: DesktopWidget = {
  repeatable: true,
  formats: [
    { id: "compact", label: "Compact", url: "index.html", previewUrl: "index.html?sample=1",
      appearance: "icon", defaultW: 2, defaultH: 2, minW: 2, minH: 2, maxW: 2, maxH: 2,
      fixedSize: true, minPixelWidth: 120, minPixelHeight: 90 },
    { id: "expanded", label: "Expanded", url: "index.html", appearance: "card",
      defaultW: 4, defaultH: 3, minW: 3, minH: 2, maxW: 8, maxH: 6,
      minPixelWidth: 220, minPixelHeight: 120 },
  ],
  surfaces: [
    { id: "menu", label: "Menu", url: "index.html", kind: "popover", width: 280,
      height: 220, minWidth: 200, minHeight: 160, maxWidth: 400, maxHeight: 400 },
    { id: "details", label: "Details", url: "index.html", kind: "modal", width: 480,
      height: 320, minWidth: 320, minHeight: 240, maxWidth: 640, maxHeight: 600 },
    { id: "settings", label: "Settings", url: "index.html", kind: "modal", width: 480,
      height: 360, minWidth: 320, minHeight: 240, maxWidth: 640, maxHeight: 600 },
  ],
  configFields: [
    Field.text("title", "Title", { default: "My counter" }),
    Field.number("limit", "Count limit", { default: "100", min: 1, max: 1000, step: 1 }),
  ],
  settingsSurface: "settings",
};

export const app = plugin({
  ui: {
    contributions: [UiContrib.widget("counter", "Instance counter", widget)],
    onWidgetCall: { ping: (_params, context) => ({ instance: context?.instanceId ?? null }) },
  },
});

if (require.main === module) app.run();
```

## Felder, Ressourcen und Grenzen

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

| Rust/Python and wire | TypeScript descriptor |
|---|---|
| `config_fields` | `configFields` |
| `settings_surface` | `settingsSurface` |
| `preview_url` | `previewUrl` |
| `default_w` / `default_h` | `defaultW` / `defaultH` |
| `min_w` / `min_h` | `minW` / `minH` |
| `max_w` / `max_h` | `maxW` / `maxH` |
| `fixed_size` | `fixedSize` |
| `min_pixel_width` / `min_pixel_height` | `minPixelWidth` / `minPixelHeight` |
| `min_width` / `min_height` | `minWidth` / `minHeight` |
| `max_width` / `max_height` | `maxWidth` / `maxHeight` |

Formats have required stable `id`, localized `label`, `url`, default and minimum grid sizes. `appearance` is `card`, `icon` or `bubble`: card is rectangular, icon has a square shell, and bubble is a capsule spanning its declared placement rectangle. Use equal width/height cell spans for icons; bubbles can be wide and retain the full label. Nonzero maxima constrain resize; zero or omitted maxima select host limits: each card is 1–12 cells wide and 1–10000 cells high. Wider Home layouts provide more placement positions. Minimum ≤ default ≤ nonzero maximum on each axis. `fixedSize` fixes the default cell span, not a pixel viewport. Grid cell size depends only on the viewport, never on widgets or formats. Minimum readable pixel dimensions are preview hints, not live cell-size or resize constraints. Live content receives its actual area and must adapt or scroll without iframe scaling.

Surfaces require `id`, `label`, `url` and `kind` (`popover` or `modal`). Their width/height and limits are pixels; zero selects host defaults/viewport bounds. A `settingsSurface` must name a declared modal. Config fields use the existing [field definitions](../3-reference/config-fields.md); raw text defaults such as `"My counter"` are valid, numeric defaults such as `"100"` are parsed. Labels/descriptions accept existing localization keys such as `$counter.title`.

Keep IDs stable and unique within formats, surfaces and fields. A contribution ID cannot collide with another contribution. IDs use ASCII letters, digits, `-`, `_`, `.`, `:` (1–128 bytes). `index.html` resolves to `ui/index.html`; `views/menu.html` resolves to `ui/views/menu.html`. Query/fragment are allowed. Use forward-slash local paths, without a leading slash, empty segments, dot segments, backslashes, colons or percent-encoded path characters. Every referenced file must exist inside the UI bundle. Invalid widget descriptors are excluded with diagnostics while valid contributions remain.

## Browserkontext und Oberflächen

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

| Method | Result and behavior |
|---|---|
| `getContext()` | Promise of context, including optional opening `params` |
| `onContextChange(callback)` | Context subscription; returns unsubscribe |
| `getConfig()` | Promise of current instance config or settings draft |
| `setConfig(object)` | Promise of success; replaces config; rejects invalid/save failures |
| `getData(key)` | Promise of instance-local string or null; preview returns null |
| `setData(key,string)` | Promise of success; rejects preview, inactive or settings-draft writes |
| `onDataChange(callback)` | Own-instance events `{key,value}`; returns unsubscribe |
| `openSurface(id,options)` | Promise of an opening token string |
| `closeSurface(tokenOrId?)` | Promise of success; token targets one opening, ID the newest match, omitted the topmost owned view |
| `onSurfaceEvent(callback)` | Closed events `{surfaceId,token,type:"closed"}`; returns unsubscribe |

Context has `widgetId`, `instanceId`, `formatId`, `viewId`, `preview`, `active`, `width`, `height`, `config` and optional `params`. `viewId` is empty in the card, or a declared surface ID in a popover, details or settings view. `formatId` remains the selected grid format; width/height are the actual available content area in pixels.

Open arbitrary content with `openSurface('menu', {anchor: element, params: {item: 'counter'}})`. The anchor belongs to the calling iframe. Save the returned token if you later want to close that exact opening; it is different from the declared ID. The new view reads parameters through `(await astra.widget.getContext()).params`; there is no separate getParams method. Parameters must be serializable and are not automatically included in backend context. Pass them explicitly to a backend method when needed.

Astra owns anchoring, viewport limits, nested Select/Tooltip surfaces, Escape, focus and outside dismissal. It closes owned surfaces when their owner disappears, the page changes or editing starts. Do not access Astra’s DOM or move React trees across documents.

## Einstellungen, Daten und Vorschau

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

Standard fields and the optional custom settings view edit the same host draft. Astra’s widget editor opens `settingsSurface`; generic `openSurface('settings')` is rejected. In that view, `context.config` and `getConfig()` expose the draft. Call `setConfig` while editing, then let the host Save commit and Cancel discard. Do not add a second commit mechanism or irreversible backend side effects to draft changes. The draft can read instance data, but data writes are rejected, including surfaces opened from a draft.

`setConfig` replaces the entire JSON object: preserve other keys from the current context/config draft when changing one key. Custom settings input callbacks must send immediately, using the pending-edit merge below rather than awaiting getConfig first. Number/slider values must be numbers, finite and within their field bounds; do not send numeric strings, NaN or Infinity. Await operations and show rejected save/write calls in the UI.

Configuration is per instance and separate from instance-local string data and global plugin configuration. With `repeatable`, each copy has a distinct stable instanceId. Subscribe to `onDataChange` so another view’s writes refresh the count. String data get/set is not an atomic read-modify-write operation: do not concurrently increment the same key from several views. Use one authoritative writer and serialize updates when needed. Disabled/missing plugins retain named placeholders and saved format/config; returning plugins restore them. If an update removes a format, the first declared format is selected and its limits applied.

Preview is inactive and read-only: no input, backend calls, config/data writes or surface opening. Instance data reads return null. Render sample values and disable actions, even for custom settings content. Clean up subscriptions on unmount.

`astra.callBackend` automatically supplies optional `widget_context` to the new contextual hook; Rust/Python use snake_case context fields and `config_json`, TypeScript uses `configJson`, while the browser uses parsed `config`. Default contextual handlers forward to the old UI handler. Existing `home.top`, `home.widgets` and `home.bottom` keep their legacy behavior; new widgets are added by the user.

## Transparenter Inhalt und Kit-Komponenten

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

Save this HTML as `ui/index.html` and the JavaScript as `ui/main.js`. Load the bridge first and await `loadUi` before mounting. The shell is Astra’s; charts and layout may be custom. Input/NumberInput/Select/Combobox callbacks receive values, not DOM change events.

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; props are checked against the public Kit declarations." -->
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<script src="http://astra-plugin.localhost/bridge/astra-bridge.js"></script>
<style>html,body{background:transparent}body{margin:0}</style>
</head><body><div id="app"></div><script type="module" src="main.js"></script></body></html>
```

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; props are checked against the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
let context = await astra.widget.getContext();
let count = context.preview ? 3 : Number(await astra.widget.getData('count') ?? 0);
let error = '';
let menuToken;
let countBusy = false;
const root = ui.mount(document.getElementById('app'), null);

async function perform(action) {
  if (disposed || context.preview || !context.active) return;
  try { await action(); error = ''; }
  catch (cause) { error = String(cause?.message ?? cause); }
  render();
}

let hostConfig = {...context.config};
let editVersion = 0, acknowledgedVersion = 0;
let disposed = false;
const pending = new Map();
function desiredConfig() {
  const result = {...hostConfig};
  for (const [key, edit] of pending) result[key] = edit.value;
  return result;
}
function changeConfig(key, value) {
  if (disposed || context.preview || !context.active) return;
  if (key === 'limit' && (!Number.isFinite(value) || value < 1 || value > 1000)) {
    throw new Error('Limit must be a finite number from 1 to 1000');
  }
  const version = ++editVersion;
  pending.set(key, {value, version});
  const replacement = desiredConfig(), sent = new Map(pending);
  context = {...context, config: replacement};
  render(); // controlled inputs retain the latest typed value
  function failed(cause) {
    if (disposed) return;
    if (pending.get(key)?.version === version) pending.delete(key);
    context = {...context, config: desiredConfig()};
    throw cause; // perform() displays the error
  }
  let request;
  try {
    // Send in this input turn: the host Save button can close the iframe immediately.
    request = astra.widget.setConfig(replacement);
  } catch (cause) {return failed(cause);}
  return Promise.resolve(request).then(() => {
    if (disposed) return;
    if (version >= acknowledgedVersion) {
      hostConfig = {...replacement}; acknowledgedVersion = version;
    }
    for (const [field, edit] of sent) {
      if (pending.get(field)?.version === edit.version) pending.delete(field);
    }
    context = {...context, config: desiredConfig()};
  }, failed);
}

function render() {
  if (disposed) return;
  const disabled = context.preview || !context.active;
  const h = ui.h;
  const config = context.config;
  let content;
  if (context.viewId === 'settings') {
    content = h('div', null,
      h(ui.SettingRow, {label: 'Title', htmlFor: 'title', control: h(ui.Input, {
        id: 'title', value: String(config.title ?? ''), disabled,
        onChange: value => perform(() => changeConfig('title', value)),
      })}),
      h(ui.SettingRow, {label: 'Count limit', htmlFor: 'limit', control: h(ui.NumberInput, {
        id: 'limit', value: Number(config.limit ?? 100), min: 1, max: 1000, step: 1, disabled,
        onChange: value => perform(() => changeConfig('limit', value)),
      })}),
      h('p', null, 'Use Astra’s Save or Cancel buttons.'));
  } else if (context.viewId === 'menu') {
    content = h('div', null,
      h(ui.Select, {value: String(config.title ?? 'My counter'), disabled,
        options: [{value: 'My counter', label: 'My counter'}, {value: 'Tasks', label: 'Tasks'}],
        onChange: value => perform(() => changeConfig('title', value)),
      }),
      h(ui.Combobox, {value: String(config.title ?? ''), disabled, freeSolo: true,
        options: [{value: 'Tasks', label: 'Tasks'}],
        onChange: value => perform(() => changeConfig('title', value)),
      }),
      h(ui.Tooltip, {content: 'Changes apply to this instance.', placement: 'bottom'},
        h(ui.Button, {disabled, 'aria-label': 'About settings'}, 'Help')));
  } else if (context.viewId === 'details') {
    content = h('div', null, h('p', null, 'Count: ' + count),
      h('pre', null, JSON.stringify(context.params ?? {}, null, 2)));
  } else {
    content = h('div', null,
      h('strong', null, String(config.title ?? 'My counter')),
      h('output', null, ' ' + count),
      context.formatId === 'expanded' ? h('p', null, 'Each instance keeps its own count.') : null,
      h(ui.Button, {disabled: disabled || countBusy || count >= Number(config.limit ?? 100), onClick: () => perform(async () => {
        if (countBusy) return;
        countBusy = true; render(); // lock this writer before awaiting a read
        try {
          const current = Number(await astra.widget.getData('count') ?? 0);
          const limit = Number(config.limit ?? 100);
          if (!Number.isFinite(current) || current < 0) throw new Error('Stored count is invalid');
          if (current >= limit) {count = current; return;} // lowering a limit does not erase existing data
          const next = Math.min(current + 1, limit);
          await astra.widget.setData('count', String(next)); count = next;
        } finally {countBusy = false;}
      })}, 'Add one'),
      h(ui.Button, {disabled, onClick: event => perform(async () => {
        menuToken = await astra.widget.openSurface('menu', {anchor: event.currentTarget});
      })}, 'Menu'),
      h(ui.Button, {disabled, onClick: () => perform(() => astra.widget.openSurface('details', {
        params: {item: 'counter'},
      }))}, 'Details'),
      h(ui.Button, {disabled: !menuToken, onClick: () => perform(async () => {
        await astra.widget.closeSurface(menuToken);
      })}, 'Close menu'));
  }
  root.render(h('div', null, content, h('p', {role: 'alert'}, error)));
}

const stopContext = astra.widget.onContextChange(next => {
  hostConfig = {...next.config};
  context = {...next, config: desiredConfig()}; // older acknowledgements cannot erase pending edits
  render();
});
const stopData = astra.widget.onDataChange(({key, value}) => {
  if (key === 'count') {count = Number(value ?? 0); render();}
});
const stopSurface = astra.widget.onSurfaceEvent(event => {
  if (event.type === 'closed' && event.token === menuToken) {menuToken = undefined; render();}
});
addEventListener('pagehide', () => {disposed = true; stopContext(); stopData(); stopSurface(); root.unmount();}, {once: true});
render();
```

## React verwendet dieselben Props

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

The React scaffold bootstrap awaits `astra.loadUi({apiVersion: 1})` before dynamically importing App. Keep it and the supplied build adapter. This typed component fragment uses the same controlled values/callbacks; wire the callbacks to the same immediate per-key merge/setConfig path and display failures. It is not a replacement bootstrap. Send setConfig immediately in the input callback, without deferring behind await or a queue: host Save can close the iframe immediately. Preserve other keys in replacement objects, and merge pending per-key intents with host context so older acknowledgements do not reset typing. The example above versions each field edit and retains newer pending values.

<!-- doctest: illustrative reason="A typed component fragment; bootstrap and bridge state come from the React scaffold. Checked against public Kit declarations." -->
```tsx
import { Input, NumberInput, Select, Combobox, Tooltip, Button, SettingRow } from '@astra/plugin-ui';

export function Settings(props: {
  title: string;
  limit: number;
  saveTitle: (value: string) => void;
  saveLimit: (value: number) => void;
}) {
  return <>
    <SettingRow label="Title" htmlFor="title" control={
      <Input id="title" value={props.title} onChange={props.saveTitle} />
    } />
    <SettingRow label="Limit" htmlFor="limit" control={
      <NumberInput id="limit" value={props.limit} min={1} max={1000} step={1}
        onChange={props.saveLimit} />
    } />
    <Select value={props.title} onChange={props.saveTitle} options={[
      {value: 'My counter', label: 'My counter'}, {value: 'Tasks', label: 'Tasks'},
    ]} />
    <Combobox value={props.title} onChange={props.saveTitle} freeSolo
      options={[{value: 'Tasks', label: 'Tasks'}]} />
    <Tooltip content="Changes apply to this instance." placement="bottom">
      <Button aria-label="About settings">Help</Button>
    </Tooltip>
  </>;
}
```

## Bauen und prüfen

Die vollständigen, überprüfbaren Beispiele stehen auf dieser Seite. Ausführliche Erläuterungen sind in der [englischen](../../en/4-sdk/desktop-widgets.md) und [russischen Anleitung](../../ru/4-sdk/desktop-widgets.md) verfügbar.

<!-- doctest: cli -->
```bash
astra-plugin check . --strict
astra-plugin test .
astra-plugin build .
astra-plugin dev .
```

`test` uses a mock host; `dev` requires running Astra. Check two independent instances, limits and format changes, settings Save/Cancel, missing/returned plugins, preview, popovers beyond the card, nested lists, Escape/focus, viewport edges, theme, text scale and glass settings. Acceptance targets are Windows/Tauri and Linux/Electron. Browser/mock checks do not prove installed native behavior; macOS plugin routing requires separate installed-app verification. Pin the desktop runtime minimum to its first actual release. SDK/CLI publication and deployment are outside this implementation.
