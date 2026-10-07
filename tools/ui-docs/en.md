<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Plugin UI Kit

Use Astra’s own controls instead of reproducing their CSS. The runtime ships with the installed application; the public package supplies declarations and a build adapter only.

Choose a frontend independently of Rust, Python or TypeScript backend. Vanilla is the default. React projects keep their package and frozen lockfile in frontend/. Install there before astra-plugin build or dev.

## API and components

Wait for loadUi before displaying controls. h accepts a component or tag, props and children. mount supplies the host environment and returns render/unmount. Props and callbacks match Astra. Language, palette and material changes keep the mounted tree and its form state.

{{COMPONENTS}}

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: {{API_VERSION}}});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React and packaging

Use @astra/plugin-ui/build; the adapter resolves UI, React, ReactDOM and JSX imports to fixed host routes. Do not bundle React again. A bootstrap must await loadUi before dynamically importing the React app, so missing resources produce an update message. Release CI installs frontend dependencies with the frozen lockfile for every backend.

## Compatibility and verification

API v1 keeps export names and signatures; appearance follows Astra. Menus, modals and focus handling stay in the iframe. Custom interfaces and existing plugins remain supported. Test Select inside Modal, Escape, focus return, palette changes, narrow frames and glass in the real Tauri/Windows and Electron/Linux windows, including an offline installed bundle.

The minimum version in the snapshot names the prepared Astra build containing the Kit; {{MIN_ASTRA_VERSION}} is unreleased until Astra publishes it. The CLI is 0.5.0, also unreleased. Do not describe either as already shipped.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
