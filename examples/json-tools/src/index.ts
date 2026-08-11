/**
 * The entrypoint. `plugin.toml` runs `node dist/index.js`, and this is all it
 * takes: the plugin itself is a value in `plugin.ts`, which is what lets the
 * test suite drive it without starting a process.
 */

import { app } from "./plugin";

app.run();
