<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# UI Kit плагинов

Используйте настоящие контролы Astra вместо копирования CSS. Runtime входит в установленное приложение; публичный пакет содержит только типы и адаптер сборки.

Frontend выбирается независимо от backend на Rust, Python или TypeScript. По умолчанию используется vanilla. У React-проекта свой package и frozen lockfile в frontend/. Установите зависимости там перед astra-plugin build или dev.

## API и компоненты

Дождитесь loadUi до показа контролов. h принимает компонент или тег, props и дочерние элементы. mount подключает окружение хоста и возвращает render/unmount. Props и callbacks совпадают с Astra. Смена языка, палитры и материала сохраняет дерево и состояние формы.

{{COMPONENTS}}

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: {{API_VERSION}}});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React и упаковка

Используйте @astra/plugin-ui/build: адаптер перенаправляет UI, React, ReactDOM и JSX на фиксированные маршруты хоста. Не включайте вторую React. Bootstrap должен дождаться loadUi перед динамическим импортом React-приложения, чтобы показать сообщение об обновлении при ошибке загрузки. Release CI устанавливает frontend-зависимости с frozen lockfile для любого backend.

## Совместимость и проверка

API v1 сохраняет имена экспортов и сигнатуры; оформление обновляется вместе с Astra. Меню, модалки и фокус работают внутри iframe. Собственные интерфейсы и старые плагины поддерживаются. Проверяйте Select внутри Modal, Escape, возврат фокуса, палитры, узкий iframe и стекло в настоящих окнах Tauri/Windows и Electron/Linux, включая установленный bundle без сети.

Минимальная версия snapshot указывает подготовленную сборку Astra с Kit; {{MIN_ASTRA_VERSION}} ещё не выпущена. CLI 0.5.0 тоже не выпущен. Не называйте их уже поставленными.

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
