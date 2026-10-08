# UI for an Astra plugin

Use this guide when a plugin adds a page, panel, desktop widget or overlay in Astra.
Technical correctness is necessary, but the finished interface also needs to
work for someone who did not write the plugin.

## Choose the smallest surface that solves the task

Configuration such as an API key, model path, voice choice or threshold belongs
in `[config]` or the TTS/STT config-field hooks. Astra renders those controls;
see [config fields](en/3-reference/config-fields.md). A wake-word plugin normally
needs only its Voice settings, not a separate page; see the
[wake-word contract](en/wakeword-plugins.md).

Use `ui_contributions` when the user needs to view or interact with the
plugin's own content. Pick a slot for the content's role: a page for a workflow,
a panel for a compact view, `desktop.widget` for a user-placed Home card, an overlay for transient content. Request
`dom_access` only if the actual feature needs it; it gives script access to the
Astra window and changes the install consent. Read the
[permissions guide](en/3-reference/permissions.md).

## Implement the surface

Start an ordinary page or panel with `astra-plugin new <id> --template ui`
and read the matching [hooks](en/reference/parity.md). The scaffold names `index.html` as its contribution URL and writes `ui/index.html`. URLs are relative to `ui/`; do not prefix them with another `ui/`. Test that the file actually loads in Astra.
The [companion example](../examples/companion/) uses `dom_access` and runs
inside Astra's own window; use it only for that more privileged mode.

For an iframe contribution, the plugin owns its HTML, CSS and interaction.
Astra supplies a bridge and design tokens. In the current host, load
`<script src="http://astra-plugin.localhost/bridge/astra-bridge.js"></script>`
first in `<head>`; the bridge injects the theme tokens and `window.astra`.
Check the installed build's authoring instructions for its exact URL and
bridge methods if it differs from this guide. Use `astra.callBackend` for
backend calls and the bridge data methods for persistence.

The current iframe slots are `page.custom` (a navigation tab), `home.top`,
`home.widgets`, `home.bottom` (chat widget panels), `statusbar.left`,
`statusbar.right`, `settings.appearance`, `settings.custom`,
`background.behind`, `background.front`, and `overlay.floating` (full-window
layers). A page fills its tab; give in-page panels an explicit height.
The full-window layers are always transparent and do not take clicks.

The current `window.astra` request methods are `getTheme`, `getCssVariables`,
`setCssVariable`, `setAppBackground`, `getPluginId`, `getWindowSize`,
`getData`, `setData`, `navigateTo`, and `callBackend`.
`astra.callBackend(method, params)` calls the plugin's `CallFromUi` hook.
`onBackendMessage` and `on(name, callback)` subscribe to events from
`PushToUi`, which needs the `push_to_ui` permission. Use event names without
colons. `onThemeChange`, `onWindowFocus`, `onWindowBlur`, and
`requestAudioData` are also available. For a different installed Astra
build, use the slot and method list in its offline authoring instruction
from Plugins → Dev instead of guessing.

For a transparent contribution, return `transparent: true` even when using
an SDK page helper, and set `:root { color-scheme: normal; }`,
`body { color-scheme: light dark; }`, and
`html, body { background: transparent; }`. Test the actual result in both
themes; a transparent CSS background alone does not clear the iframe canvas.

The iframe has an opaque origin, so do not depend on
`localStorage` or `sessionStorage`. It cannot create a `Worker`; move
parsing, search, model inference and other heavy work into the plugin process.
Keep bridge calls cancellable or bounded. Await `astra.loadUi({apiVersion: 1})` before mounting Kit controls or dynamically importing the React app; use the scaffold bootstrap and [real component props](en/4-sdk/ui-kit.md). Input and Select callbacks receive values, NumberInput receives a number, rather than DOM change events.

Draw the UI for its actual slot. A transparent panel or overlay must leave
unused space transparent; an opaque full-frame fill hides Astra's wallpaper.
Use Astra's supplied type, surface, edge and accent tokens rather than fixed
colours. Keep text legible on both pale and dark bases. Give every action a
clear label and visible response. Show loading, empty, success and error states
where the workflow can reach them. Support keyboard focus and navigation;
keep motion optional for reduced-motion users. An ordinary page’s custom menu must fit within its frame. A desktop widget opens declared views or Kit Select/Tooltip in host surfaces, which can extend beyond its card.

Examples are technical references, not visual templates. Design the hierarchy,
spacing and controls for this plugin's content. If the user's brief includes
visual preferences, follow them; otherwise keep the surface simple and
consistent with Astra.

## Inspect the running result

After `astra-plugin check . --strict` and `astra-plugin test .`, load the plugin
with `astra-plugin dev .` and examine the real window. Check:

- the normal, empty, loading and error states;
- a narrow window and the slot's actual size;
- pale and dark base colours, and glass enabled and disabled;
- focus order, keyboard operation and readable labels;
- that a panel/overlay leaves the surrounding Astra UI usable;
- that slow backend work does not freeze the window.

Fix observed problems and inspect again. If you cannot run Astra or capture
the screen, report that visual verification is incomplete; a compiler result
does not substitute for it.

## User-placed desktop widgets

Use `--template desktop-widget` and the [desktop widget contract](en/4-sdk/desktop-widgets.md) for several formats, size constraints, per-instance settings and host popovers/modals. Astra supplies their outer material and focus handling. This contract uses `ui_contributions` without `dom_access`; overlay contributions keep their existing separate path. The complete guide supplies matching SDK artifact setup, exact descriptors in all three languages, resource paths and bounds, transparent content, initialization and actual Kit value callbacks.

Custom settings are opened by Astra’s widget editor, edit its draft and use its Save/Cancel. `setConfig` replaces the full object; preserve other fields and enforce finite bounded numeric values. Instance string data is separate; settings draft views cannot write it. Preview cannot call the backend, write config/data or open surfaces. `openSurface` returns a token for a particular opening; its declared view receives `context.params`. Dispose subscriptions on teardown. Use the [complete widget guide](en/4-sdk/desktop-widgets.md) for exact semantics, including nested dismissal.
