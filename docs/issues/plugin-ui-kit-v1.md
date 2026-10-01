# Plugin UI Kit v1 — architecture issue draft

Status: local design record, approved for implementation. This draft has not been posted.

Plugin controls currently imitate Astra's CSS and drift as the application changes.
Ship the application's primitives in an iframe-local ESM runtime under the reserved
`/bridge/ui/v1/` route. A generated public authoring package contains declarations,
aliases and a build adapter, never the private component implementation or React runtime.

The canonical contract is `astra-ui/src/plugin-ui/contract.json` together with
`components.ts`. `scripts/build-plugin-ui.ts` builds the runtime, declarations,
resource manifest and token snapshot. Public synchronization requires both checkouts
and explicit refs; the public-only check proves snapshot integrity, not correspondence
to a private checkout.

`astra.loadUi({apiVersion: 1})` waits for environment, CSS and fonts. `h` and `mount`
serve vanilla and JSX consumers. React imports resolve to fixed host modules built
in one splitting graph. One environment subscription per iframe serves all mounted
roots; unmount releases listeners, portals and clear-behind observers. UI updates
replace context values without replacing roots. All overlays stay in the iframe.

The shared read-only context supplies internal labels, language and advanced visibility.
The application remains the settings owner. Shared styles keep fonts, control defaults
and material switching in one implementation. Window backgrounds and scrolling belong
to their respective shells. Compositor differences across the iframe boundary require
manual verification in both installed shells.

No RPC, registry, permission or capability changes. Existing bridge methods remain
available. New scaffolds use the Kit; old plugins are not forced to migrate. Authoring
assets distributed to plugins are MPL-2.0; CLI, tools and documentation are GPL-3.0-or-later.

Release sequencing: ship Astra runtime first; stamp its actual shipping version into
the public snapshot and scaffold minimum; release the CLI separately. Pin the reusable
workflow to the reviewed CLI commit after committing, never to an invented SHA.
No publication or release-tag changes are authorized by this implementation request.

Acceptance: matching exports/declarations/aliases/manifest; isolated dependency graph;
no bundled plugin React; all six backend/frontend combinations; frozen frontend locks
in the read-only build job; deterministic runtime output; adversarial reviews and the
installed-window scenarios in `VERIFICATION.md`.
