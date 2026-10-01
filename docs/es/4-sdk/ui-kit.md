<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit para plugins

Usa los controles reales de Astra en lugar de copiar su CSS. El runtime viene con la aplicación instalada; el paquete público contiene solo declaraciones y el adaptador de compilación.

El frontend se elige independientemente del backend Rust, Python o TypeScript. Vanilla es el valor predeterminado. React tiene su propio paquete y lockfile congelado en frontend/. Instala allí antes de astra-plugin build o dev.

## API y componentes

Espera a loadUi antes de mostrar controles. h recibe un componente o etiqueta, props e hijos. mount aporta el entorno del host y devuelve render/unmount. Props y callbacks coinciden con Astra. Los cambios de idioma, paleta y material conservan el árbol y el estado del formulario.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React y empaquetado

Usa @astra/plugin-ui/build: el adaptador redirige UI, React, ReactDOM y JSX a rutas fijas del host. No empaquetes otra copia de React. El bootstrap espera loadUi e importa dinámicamente la aplicación React para mostrar un aviso de actualización si falla la carga. CI instala dependencias frontend con lockfile congelado para cada backend.

## Compatibilidad y verificación

API v1 conserva nombres y firmas; el aspecto evoluciona con Astra. Menús, diálogos y foco permanecen dentro del iframe. Se admiten interfaces propias y plugins antiguos. Prueba Select dentro de Modal, Escape, retorno del foco, paletas, frames estrechos y vidrio en ventanas reales de Tauri/Windows y Electron/Linux, incluido el bundle instalado sin red.

La versión mínima del snapshot identifica el build preparado de Astra con Kit; 0.2.7 aún no está publicado. CLI 0.5.0 tampoco. No los describas como ya distribuidos.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
