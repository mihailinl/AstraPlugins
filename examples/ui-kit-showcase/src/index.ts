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
    // Literal English here. Astra resolves a `$key` in these labels too
    // (from 0.2.1, below this plugin's floor): to translate one, make it
    // `key("ui.vanilla.label")` and add that key to locales/en.json.
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
