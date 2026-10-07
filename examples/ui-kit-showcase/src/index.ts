/**
 * Ui Kit Showcase — an Astra plugin.
 *
 * The plugin is a VALUE, exported from this module, and it starts only when
 * this file is the process entrypoint. That is what lets `test/plugin.test.mjs`
 * drive it in-process, with no daemon and no socket.
 */

import { plugin, s, UiContrib } from "astra-plugin-sdk";

export const app = plugin({
  ui: {
    // The iframes this plugin puts in Astra's window. `url` is served from the
    // plugin's own bundle.
    // Literal English, unlike the labels above, and the reason is the
    // scaffold rather than the daemon: one locales/en.json serves all three
    // language templates and the Python one declares no contribution to hang a
    // `ui.*` key off. Astra resolves this one too — make it
    // `key("ui.main.label")` and add the key when you translate it.
    contributions: [{...UiContrib.page("vanilla", "Vanilla UI Kit", "index.html"), transparent:true}, {...UiContrib.page("react", "React UI Kit", "react.html"), transparent:true}],
    // Reachable from that iframe as `astra.callBackend("ping", {})`. Push data the
    // other way with `ctx.pushToUi(...)`.
    onCall: {
      ping: () => ({ ok: true }),
    },
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as the test does —
// does not start a server.
if (require.main === module) app.run();
