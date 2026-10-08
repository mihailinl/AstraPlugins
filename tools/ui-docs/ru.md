<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit плагинов

Используйте настоящие контролы Astra вместо копирования CSS. Runtime входит в установленное приложение; публичный пакет содержит только типы и адаптер сборки.

Frontend выбирается независимо от backend на Rust, Python или TypeScript. По умолчанию используется vanilla. У React-проекта свой package и frozen lockfile в frontend/. Установите зависимости там перед astra-plugin build или dev.

## API и компоненты

Дождитесь loadUi до показа контролов. h принимает компонент или тег, props и дочерние элементы. mount подключает окружение хоста и возвращает render/unmount. Props и callbacks совпадают с Astra. Смена языка, палитры и материала сохраняет дерево и состояние формы.

{{COMPONENTS}}

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; controlled values match the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: {{API_VERSION}}});
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

## React и упаковка

Используйте @astra/plugin-ui/build: адаптер перенаправляет UI, React, ReactDOM и JSX на фиксированные маршруты хоста. Не включайте вторую React. Bootstrap должен дождаться loadUi перед динамическим импортом React-приложения, чтобы показать сообщение об обновлении при ошибке загрузки. Release CI устанавливает frontend-зависимости с frozen lockfile для любого backend.

## Совместимость и проверка

API v1 сохраняет имена экспортов и сигнатуры; оформление обновляется вместе с Astra. В обычной странице меню/модалки остаются внутри iframe; Select/Tooltip виджета и объявленные поверхности рисует host за границами карточки. Собственные интерфейсы и старые плагины поддерживаются. Проверяйте Select внутри Modal, Escape, возврат фокуса, палитры, узкий iframe и стекло в настоящих окнах Tauri/Windows и Electron/Linux, включая установленный bundle без сети.

Минимальная версия snapshot указывает подготовленную сборку Astra с Kit; {{MIN_ASTRA_VERSION}} ещё не выпущена. CLI 0.5.0 тоже не выпущен. Не называйте их уже поставленными.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)

## Desktop widgets (development contract)

Шаблон `desktop-widget` использует этот Kit в стеклянных карточках, поповерах и модальных окнах Astra. После инициализации вызовите `astra.widget.getContext()`; `viewId` выбирает содержимое. Собственные настройки редактируют черновик, открываемый только редактором Astra; «Сохранить» применяет его, «Отмена» отбрасывает. Предпросмотр доступен только для чтения, включая данные экземпляра и backend-вызовы. `openSurface` возвращает token, параметры открытия доступны в `context.params`; callbacks контролов получают значения. [Полные примеры описания и содержимого](desktop-widgets.md). Runtime и SDK пока не выпущены; используйте предоставленные совместимые артефакты и закрепите минимальную версию после релиза Astra.

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
