<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit плагінів

Використовуйте справжні контроли Astra замість копіювання CSS. Runtime входить до встановленої програми; публічний пакет містить лише типи й адаптер збирання.

Frontend обирається незалежно від backend на Rust, Python або TypeScript. Типово використовується vanilla. React має власні package і frozen lockfile у frontend/. Встановіть залежності там перед astra-plugin build або dev.

## API та компоненти

Дочекайтеся loadUi перед показом контролів. h приймає компонент або тег, props і дочірні елементи. mount додає оточення хоста й повертає render/unmount. Props і callbacks збігаються з Astra. Зміна мови, палітри й матеріалу зберігає дерево та стан форми.

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`, `ScrollArea`, `Advanced`, `Collapse`, `ProgressBar`, `WidgetHead`, `WidgetMetric`, `AstraLine`, `WidgetPlate`, `WidgetMeter`, `WidgetPlateButton`

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


## Секції на сторінках Settings, AI і Voice

Contribution у `settings.custom`, `ai.custom` або `voice.custom` стає секцією цієї сторінки. Рамку малює Astra: clay-картка, заголовок із `label`, значок з `icon_svg`, бейдж з назвою плагіна, пункт у бічній навігації по секціях (і в пошуку Settings). Малюйте лише вміст — `SettingRow`, `Card` з `variant: 'subtle'`, `Advanced` — і ніколи зовнішній `Section`, інакше на сторінці буде картка в картці з двома заголовками. `Select`, `Combobox` і `Tooltip` з Kit малює поверх сторінки сама Astra, як у віджета; `Modal` і `Popover` лишаються всередині фрейму, тож якщо відкриваєте їх, задайте `height`. При `height = 0` рамка йде за висотою документа, тому не задавайте `html` і `body` висоту `100%`; ненульова `height` лишається фіксованою. `settings.custom` показується й у картці плагіна на сторінці Plugins.

Оформлення — Graphite: clay-поверхні (матові, якщо користувач увімкнув Glass), один акцент, який обирає користувач, підняті плашки для кнопок і заглиблення для полів введення. Kit уже так виглядає. Токени `--glass-*` вилучено й більше не публікуються; якщо малюєте власні блоки, беріть поверхні й текст з `--color-surface`, `--color-surface-raised`, `--color-text` і `--color-text-muted`.

## Desktop widgets (development contract)

Шаблон `desktop-widget` використовує цей Kit у clay-картках і поверхнях host. [Повна інструкція](desktop-widgets.md) описує точні поля SDK, callbacks значень, `context.params`, token, чернетку налаштувань, відкриту редактором, і перегляд лише для читання. Використовуйте надані сумісні артефакти CLI/SDK; можливості ще не випущені. Лицьовий бік картки складайте з `WidgetHead`, `WidgetMetric`, `AstraLine`, `WidgetPlate`, `WidgetMeter` і `WidgetPlateButton` — з них побудовано вбудовані віджети Astra; рамка є для них контейнером розмірів `desktop-widget`.

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
