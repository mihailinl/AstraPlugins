<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit плагінів

Використовуйте справжні контроли Astra замість копіювання CSS. Runtime входить до встановленої програми; публічний пакет містить лише типи й адаптер збирання.

Frontend обирається незалежно від backend на Rust, Python або TypeScript. Типово використовується vanilla. React має власні package і frozen lockfile у frontend/. Встановіть залежності там перед astra-plugin build або dev.

## API та компоненти

Дочекайтеся loadUi перед показом контролів. h приймає компонент або тег, props і дочірні елементи. mount додає оточення хоста й повертає render/unmount. Props і callbacks збігаються з Astra. Зміна мови, палітри й матеріалу зберігає дерево та стан форми.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React та пакування

Використовуйте @astra/plugin-ui/build: адаптер спрямовує UI, React, ReactDOM і JSX на фіксовані маршрути хоста. Не додавайте другу React. Bootstrap має дочекатися loadUi перед динамічним імпортом React-програми, щоб показати повідомлення про оновлення при помилці. Release CI встановлює frontend-залежності з frozen lockfile для кожного backend.

## Сумісність і перевірка

API v1 зберігає назви експортів і сигнатури; оформлення оновлюється з Astra. Меню, модальні вікна й фокус лишаються в iframe. Власні інтерфейси та старі плагіни підтримуються. Перевіряйте Select у Modal, Escape, повернення фокуса, палітри, вузькі iframe та скло у справжніх вікнах Tauri/Windows і Electron/Linux, включно зі встановленим bundle без мережі.

Мінімальна версія snapshot указує підготовлену збірку Astra з Kit; 0.2.7 ще не випущено. CLI 0.5.0 також не випущено. Не називайте їх уже поставленими.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
