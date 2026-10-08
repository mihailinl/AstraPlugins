<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit плагінів

Використовуйте справжні контроли Astra замість копіювання CSS. Runtime входить до встановленої програми; публічний пакет містить лише типи й адаптер збирання.

Frontend обирається незалежно від backend на Rust, Python або TypeScript. Типово використовується vanilla. React має власні package і frozen lockfile у frontend/. Встановіть залежності там перед astra-plugin build або dev.

## API та компоненти

Дочекайтеся loadUi перед показом контролів. h приймає компонент або тег, props і дочірні елементи. mount додає оточення хоста й повертає render/unmount. Props і callbacks збігаються з Astra. Зміна мови, палітри й матеріалу зберігає дерево та стан форми.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`, `ScrollArea`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; controlled values match the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
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

## React та пакування

Використовуйте @astra/plugin-ui/build: адаптер спрямовує UI, React, ReactDOM і JSX на фіксовані маршрути хоста. Не додавайте другу React. Bootstrap має дочекатися loadUi перед динамічним імпортом React-програми, щоб показати повідомлення про оновлення при помилці. Release CI встановлює frontend-залежності з frozen lockfile для кожного backend.

## Сумісність і перевірка

API v1 зберігає назви експортів і сигнатури; оформлення оновлюється з Astra. Меню/модальні вікна звичайних сторінок залишаються в iframe; Select/Tooltip віджета та оголошені поверхні малює host за межами картки. Власні інтерфейси та старі плагіни підтримуються. Перевіряйте Select у Modal, Escape, повернення фокуса, палітри, вузькі iframe та скло у справжніх вікнах Tauri/Windows і Electron/Linux, включно зі встановленим bundle без мережі.

Мінімальна версія snapshot указує підготовлену збірку Astra з Kit; 0.2.7 ще не випущено. CLI 0.5.0 також не випущено. Не називайте їх уже поставленими.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Desktop widgets (development contract)

Шаблон `desktop-widget` використовує цей Kit у скляних картках і поверхнях host. [Повна інструкція](desktop-widgets.md) описує точні поля SDK, callbacks значень, `context.params`, token, чернетку налаштувань, відкриту редактором, і перегляд лише для читання. Використовуйте надані сумісні артефакти CLI/SDK; можливості ще не випущені.

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
