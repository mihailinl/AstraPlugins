<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Виджеты рабочего стола

## Начните с совместимых инструментов

Виджеты размещает пользователь в сетке «Главной». Используйте существующую capability `ui_contributions` и слот `desktop.widget`; новое разрешение и `dom_access` не нужны. Astra рисует стеклянную оболочку, края, шрифт и всплывающие поверхности, управляет размещением. Плагин создаёт прозрачное содержимое. Оверлей остаётся отдельной системой.

Контракт пока не выпущен. Используйте предоставленные для вашей сборки Astra артефакты CLI и SDK: пакет из реестра с таким же номером версии может ещё не содержать эти возможности. Чтобы собрать публичный репозиторий инструментов, выполните `cargo build --release --manifest-path astra-plugin-cli/Cargo.toml` (нужны Rust и protoc) и используйте полученный бинарный файл. Исходники самой Astra для этого не нужны.

<!-- doctest: cli -->
```bash
astra-plugin new my-counter --lang python --template desktop-widget --ui vanilla
astra-plugin new my-counter-react --lang rust --template desktop-widget --ui react
```

Язык backend (Rust/Python/TypeScript) и frontend (vanilla/React) выбираются независимо. [Пример](../../../examples/desktop-widget/README.md) и шаблон показывают два формата, независимые экземпляры, меню, детали и два способа настройки. Не выдумывайте автора и не принимайте лицензию по умолчанию от имени пользователя. Для явно разрешённого локального теста без публикации оставьте неизвестного автора пустым и удалите поле license, если лицензия ещё не выбрана. До публикации согласуйте автора и лицензию с владельцем.

Метаданные манифеста имеют английскую основу: plugin.description пишется по-английски; listing.name и listing.description в locales/en.json должны точно совпадать с plugin.name и plugin.description. Русскую подпись/описание добавляйте в locales/ru.json, а UI-подписи — через локализуемые ключи. После изменения имени/описания выполните `astra-plugin locale sync --path .`, затем check --strict; это предотвращает ошибки E8 (несовпадение) и E11 (описание не на английском). [Подробнее о локализации](../3-reference/localisation.md).

## Подключите совместимый SDK

Для локальной невыпущенной сборки замените зависимость из реестра в шаблоне предоставленным артефактом SDK. Rust: укажите `astra-plugin-sdk = { path = "<relative-sdk-directory>" }` в Cargo.toml или подключите предоставленный vendored crate. Python: установите wheel SDK или его каталог в отдельное окружение и согласуйте requirements с этим артефактом. TypeScript: укажите `"astra-plugin-sdk": "file:<relative-sdk-directory-or-tgz>"` и установите зависимости; каталог исходников SDK сначала требует своего `bun run build`, создающего dist. Это входы сборки, а не пути, необходимые установленному плагину.

Для React установите зависимости в `frontend/` командой `bun install --frozen-lockfile`, независимо от языка backend. Используйте `@astra/plugin-ui/build`, не включайте вторую копию React. Готовый Rust backend или собранный в bundle TypeScript backend не требует каталога исходников SDK на машине получателя. Для Python нужны объявленный интерпретатор и установленные runtime-зависимости SDK; его исходники не включаются в bundle автоматически.

## Точные описания виджета

Замените backend шаблона подходящим полным модулем ниже. Пути ресурсов отсчитываются от `ui/`; общий `index.html` выбирает представление по контексту, поэтому достаточно одной HTML-точки входа. Примеры показывают все поля описания и контекстный backend-обработчик.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;
use serde_json::json;

#[derive(Default)]
struct Counter;

#[astra::plugin(capabilities = "ui_contributions")]
impl Counter {
    #[hook]
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::widget("counter", "Instance counter",
            DesktopWidget::new(vec![
                WidgetFormat::new("compact", "Compact", "index.html", 2, 2)
                    .with_limits(2, 2, 2, 2).fixed().with_appearance("icon")
                    .with_preview("index.html?sample=1").with_readable_size(120, 90),
                WidgetFormat::new("expanded", "Expanded", "index.html", 4, 3)
                    .with_limits(3, 2, 8, 6).with_appearance("card")
                    .with_readable_size(220, 120),
            ]).repeatable().with_surfaces(vec![
                WidgetSurface::popover("menu", "Menu", "index.html")
                    .with_size(280, 220).with_limits(200, 160, 400, 400),
                WidgetSurface::modal("details", "Details", "index.html")
                    .with_size(480, 320).with_limits(320, 240, 640, 600),
                WidgetSurface::modal("settings", "Settings", "index.html")
                    .with_size(480, 360).with_limits(320, 240, 640, 600),
            ]).with_fields(vec![
                FieldDef::text("title", "Title").with_default("My counter"),
                FieldDef::number("limit", "Count limit").with_default("100")
                    .with_min(1.0).with_max(1000.0).with_step(1.0),
            ]).with_settings_surface("settings"))]
    }

    #[hook]
    async fn handle_widget_ui_call(&self, _ctx: &PluginContext, method: &str,
        _params_json: &str, widget: Option<&WidgetContext>) -> Result<String, ToolError> {
        if method != "ping" { return Err(ToolError::NotFound(method.into())); }
        Ok(json!({"instance": widget.map(|w| &w.instance_id)}).to_string())
    }
}

astra::main!(Counter::default());
```

<!-- doctest: python-plugin -->
```python
from astra_plugin_sdk import (
    Plugin, UiContribution, DesktopWidget, WidgetFormat, WidgetSurface, Field,
)

class Counter(Plugin):
    async def get_ui_contributions(self):
        return [UiContribution.widget("counter", "Instance counter", DesktopWidget(
            repeatable=True,
            formats=[
                WidgetFormat(id="compact", label="Compact", url="index.html",
                    preview_url="index.html?sample=1", appearance="icon",
                    default_w=2, default_h=2, min_w=2, min_h=2, max_w=2, max_h=2,
                    fixed_size=True, min_pixel_width=120, min_pixel_height=90),
                WidgetFormat(id="expanded", label="Expanded", url="index.html",
                    appearance="card", default_w=4, default_h=3, min_w=3, min_h=2,
                    max_w=8, max_h=6, min_pixel_width=220, min_pixel_height=120),
            ],
            surfaces=[
                WidgetSurface.popover("menu", "Menu", "index.html", width=280,
                    height=220, min_width=200, min_height=160, max_width=400, max_height=400),
                WidgetSurface.modal("details", "Details", "index.html", width=480,
                    height=320, min_width=320, min_height=240, max_width=640, max_height=600),
                WidgetSurface.modal("settings", "Settings", "index.html", width=480,
                    height=360, min_width=320, min_height=240, max_width=640, max_height=600),
            ],
            config_fields=[
                Field.text("title", "Title", default="My counter"),
                Field.number("limit", "Count limit", default="100", min=1, max=1000, step=1),
            ], settings_surface="settings"))]

    async def handle_widget_ui_call(self, method, params_json, widget):
        if method == "ping":
            return {"instance": widget.instance_id if widget else None}
        return await self.handle_ui_call(method, params_json)

if __name__ == "__main__":
    Counter().run()
```

<!-- doctest: ts-plugin -->
```ts
import { plugin, UiContrib, Field, type DesktopWidget } from "astra-plugin-sdk";

const widget: DesktopWidget = {
  repeatable: true,
  formats: [
    { id: "compact", label: "Compact", url: "index.html", previewUrl: "index.html?sample=1",
      appearance: "icon", defaultW: 2, defaultH: 2, minW: 2, minH: 2, maxW: 2, maxH: 2,
      fixedSize: true, minPixelWidth: 120, minPixelHeight: 90 },
    { id: "expanded", label: "Expanded", url: "index.html", appearance: "card",
      defaultW: 4, defaultH: 3, minW: 3, minH: 2, maxW: 8, maxH: 6,
      minPixelWidth: 220, minPixelHeight: 120 },
  ],
  surfaces: [
    { id: "menu", label: "Menu", url: "index.html", kind: "popover", width: 280,
      height: 220, minWidth: 200, minHeight: 160, maxWidth: 400, maxHeight: 400 },
    { id: "details", label: "Details", url: "index.html", kind: "modal", width: 480,
      height: 320, minWidth: 320, minHeight: 240, maxWidth: 640, maxHeight: 600 },
    { id: "settings", label: "Settings", url: "index.html", kind: "modal", width: 480,
      height: 360, minWidth: 320, minHeight: 240, maxWidth: 640, maxHeight: 600 },
  ],
  configFields: [
    Field.text("title", "Title", { default: "My counter" }),
    Field.number("limit", "Count limit", { default: "100", min: 1, max: 1000, step: 1 }),
  ],
  settingsSurface: "settings",
};

export const app = plugin({
  ui: {
    contributions: [UiContrib.widget("counter", "Instance counter", widget)],
    onWidgetCall: { ping: (_params, context) => ({ instance: context?.instanceId ?? null }) },
  },
});

if (require.main === module) app.run();
```

## Поля, ресурсы и ограничения

| Rust/Python and wire | TypeScript descriptor |
|---|---|
| `config_fields` | `configFields` |
| `settings_surface` | `settingsSurface` |
| `preview_url` | `previewUrl` |
| `default_w` / `default_h` | `defaultW` / `defaultH` |
| `min_w` / `min_h` | `minW` / `minH` |
| `max_w` / `max_h` | `maxW` / `maxH` |
| `fixed_size` | `fixedSize` |
| `min_pixel_width` / `min_pixel_height` | `minPixelWidth` / `minPixelHeight` |
| `min_width` / `min_height` | `minWidth` / `minHeight` |
| `max_width` / `max_height` | `maxWidth` / `maxHeight` |

Формат содержит обязательные стабильный `id`, локализуемый `label`, `url`, начальные и минимальные размеры в ячейках сетки. `appearance` принимает `card`, `icon` или `bubble`: card — прямоугольная карточка, icon — квадратная оболочка, bubble — капсула по прямоугольной области размещения. Для icon выбирайте одинаковые ширину и высоту ячеек; bubble может быть широким и сохраняет всю подпись. Ненулевые максимумы ограничивают изменение размеров; нулевые или отсутствующие используют ограничения host: каждая карточка имеет ширину 1–12 и высоту 1–10000 ячеек. Широкая «Главная» предоставляет дополнительные позиции для размещения. На каждой оси минимум ≤ начальный размер ≤ ненулевой максимум. `fixedSize` фиксирует начальный размер в ячейках, а не область в пикселях. Размер ячеек зависит только от области окна, а не от виджетов или их форматов. Минимальные читаемые размеры в пикселях — подсказки для предпросмотра; они не меняют ячейки и ограничения в ячейках. Содержимое получает фактическую область и адаптируется или прокручивается без масштабирования iframe.

Поверхность содержит `id`, `label`, `url` и `kind` (`popover` или `modal`). Её размеры и ограничения задаются в пикселях; ноль выбирает значения host и границы viewport. `settingsSurface` должен ссылаться на объявленный modal. Настройки используют существующие [описания полей](../3-reference/config-fields.md): текстовый default `"My counter"` допустим без JSON-кавычек внутри, числовой `"100"` разбирается. Подписи и описания поддерживают существующий resolver локализации, например `$counter.title`.

Сохраняйте ID стабильными и уникальными внутри форматов, поверхностей и полей. ID contribution не должен совпадать с другим contribution. Допустимы ASCII-буквы, цифры, `-`, `_`, `.`, `:` (1–128 байт). `index.html` разрешается в `ui/index.html`, `views/menu.html` — в `ui/views/menu.html`. Query и fragment допустимы. Используйте локальные пути с прямыми слешами, без начального слеша, пустых сегментов, точек `.`/`..`, обратных слешей, двоеточий или percent-encoded символов пути. Каждый файл должен существовать внутри UI bundle. Некорректный виджет исключается с диагностикой; корректные contributions сохраняются.

## Контекст браузера и поверхности

| Method | Result and behavior |
|---|---|
| `getContext()` | Promise of context, including optional opening `params` |
| `onContextChange(callback)` | Context subscription; returns unsubscribe |
| `getConfig()` | Promise of current instance config or settings draft |
| `setConfig(object)` | Promise of success; replaces config; rejects invalid/save failures |
| `getData(key)` | Promise of instance-local string or null; preview returns null |
| `setData(key,string)` | Promise of success; rejects preview, inactive or settings-draft writes |
| `onDataChange(callback)` | Own-instance events `{key,value}`; returns unsubscribe |
| `openSurface(id,options)` | Promise of an opening token string |
| `closeSurface(tokenOrId?)` | Promise of success; token targets one opening, ID the newest match, omitted the topmost owned view |
| `onSurfaceEvent(callback)` | Closed events `{surfaceId,token,type:"closed"}`; returns unsubscribe |

Контекст содержит `widgetId`, `instanceId`, `formatId`, `viewId`, `preview`, `active`, `width`, `height`, `config` и необязательные `params`. В карточке `viewId` пустой; в поповере, деталях и настройках — ID соответствующей поверхности. `formatId` всегда обозначает выбранный формат сетки. Width/height — фактически доступная содержимому область в пикселях.

Для произвольного содержимого вызовите `openSurface('menu', {anchor: element, params: {item: 'counter'}})`. Якорь принадлежит вызывающему iframe. Сохраните возвращённый token, если хотите закрыть именно это открытие; token отличается от объявленного ID. Представление читает параметры через `(await astra.widget.getContext()).params`; отдельного getParams нет. Параметры должны быть сериализуемыми; в контекст backend они автоматически не включаются — передавайте их аргументами нужного backend-метода.

Метод `closeSurface(tokenOrId?)` закрывает конкретное открытие по token, последнее соответствующее открытие по ID или верхнюю принадлежащую экземпляру поверхность, если аргумент отсутствует. Это не обещание закрыть именно вызывающее представление. Событие закрытия имеет вид `{surfaceId, token, type: 'closed'}`.

Astra управляет якорем, границами viewport, вложенными Select/Tooltip, Escape, фокусом и закрытием снаружи. Поверхности закрываются при исчезновении владельца, уходе со страницы и входе в редактирование. Не обращайтесь к DOM Astra и не переносите React-деревья между документами.

## Настройки, хранение и предпросмотр

Стандартные поля и собственное представление настроек редактируют один черновик host. `settingsSurface` открывает редактор Astra; обычный `openSurface('settings')` отклоняется. Здесь `context.config` и `getConfig()` возвращают черновик. Обновляйте его через `setConfig`; host «Сохранить» применяет его, «Отмена» отбрасывает. Не добавляйте отдельный commit и необратимые backend-действия при изменении черновика. Данные экземпляра читать можно, записывать нельзя, в том числе из поверхностей, открытых из черновика.

`setConfig` заменяет весь JSON-объект: сохраняйте другие поля текущего контекста/черновика при изменении одного ключа. Callback ввода в собственных настройках должен отправлять изменения сразу, с объединением ожидающих изменений как в примере ниже, не ожидая getConfig перед записью. Значения number/slider должны быть числами, конечными и внутри границ поля. Не передавайте строки с числами, NaN или Infinity. Ожидайте завершения вызовов и показывайте ошибки сохранения и записи в интерфейсе.

Конфигурация экземпляра, его локальные строковые данные и глобальная конфигурация плагина разделены. При `repeatable` каждой копии назначается отдельный стабильный instanceId. Подписывайтесь на `onDataChange`, чтобы обновлять счётчик после записи из другого представления. Строковые get/set не являются атомарной операцией чтения-изменения-записи: не увеличивайте один ключ одновременно из нескольких представлений. При необходимости назначьте одного владельца записи и выполняйте изменения последовательно. Отключённый или исчезнувший плагин оставляет подписанные заглушки с форматом и конфигурацией; возвращение восстанавливает их. Если обновление удалило формат, выбирается первый объявленный с его ограничениями.

Предпросмотр неактивен и доступен только для чтения: ввод, backend-вызовы, запись конфигурации/данных и открытие поверхностей запрещены. Чтение данных экземпляра возвращает null. Показывайте демонстрационные значения и отключайте действия, включая собственное содержимое настроек. Отписывайтесь при размонтировании.

`astra.callBackend` автоматически передаёт необязательный `widget_context` новому обработчику. В Rust/Python поля snake_case, конфигурация — строка `config_json`; в TypeScript — `configJson`, в браузере — объект `config`. Контекстные обработчики по умолчанию вызывают прежний UI-обработчик. Слоты `home.top`, `home.widgets`, `home.bottom` сохраняют прежнее поведение; новые виджеты добавляет пользователь.

## Прозрачное содержимое и настоящие компоненты Kit

Сохраните HTML в `ui/index.html`, JavaScript — в `ui/main.js`. Сначала загрузите bridge, затем дождитесь `loadUi` и монтируйте компоненты. Оболочку рисует Astra; графики и разметка могут быть своими. Callback Input/NumberInput/Select/Combobox получает значение, а не DOM-событие change.

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; props are checked against the public Kit declarations." -->
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<script src="http://astra-plugin.localhost/bridge/astra-bridge.js"></script>
<style>html,body{background:transparent}body{margin:0}</style>
</head><body><div id="app"></div><script type="module" src="main.js"></script></body></html>
```

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; props are checked against the public Kit declarations." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
let context = await astra.widget.getContext();
let count = context.preview ? 3 : Number(await astra.widget.getData('count') ?? 0);
let error = '';
let menuToken;
let countBusy = false;
const root = ui.mount(document.getElementById('app'), null);

async function perform(action) {
  if (disposed || context.preview || !context.active) return;
  try { await action(); error = ''; }
  catch (cause) { error = String(cause?.message ?? cause); }
  render();
}

let hostConfig = {...context.config};
let editVersion = 0, acknowledgedVersion = 0;
let disposed = false;
const pending = new Map();
function desiredConfig() {
  const result = {...hostConfig};
  for (const [key, edit] of pending) result[key] = edit.value;
  return result;
}
function changeConfig(key, value) {
  if (disposed || context.preview || !context.active) return;
  if (key === 'limit' && (!Number.isFinite(value) || value < 1 || value > 1000)) {
    throw new Error('Limit must be a finite number from 1 to 1000');
  }
  const version = ++editVersion;
  pending.set(key, {value, version});
  const replacement = desiredConfig(), sent = new Map(pending);
  context = {...context, config: replacement};
  render(); // controlled inputs retain the latest typed value
  function failed(cause) {
    if (disposed) return;
    if (pending.get(key)?.version === version) pending.delete(key);
    context = {...context, config: desiredConfig()};
    throw cause; // perform() displays the error
  }
  let request;
  try {
    // Send in this input turn: the host Save button can close the iframe immediately.
    request = astra.widget.setConfig(replacement);
  } catch (cause) {return failed(cause);}
  return Promise.resolve(request).then(() => {
    if (disposed) return;
    if (version >= acknowledgedVersion) {
      hostConfig = {...replacement}; acknowledgedVersion = version;
    }
    for (const [field, edit] of sent) {
      if (pending.get(field)?.version === edit.version) pending.delete(field);
    }
    context = {...context, config: desiredConfig()};
  }, failed);
}

function render() {
  if (disposed) return;
  const disabled = context.preview || !context.active;
  const h = ui.h;
  const config = context.config;
  let content;
  if (context.viewId === 'settings') {
    content = h('div', null,
      h(ui.SettingRow, {label: 'Title', htmlFor: 'title', control: h(ui.Input, {
        id: 'title', value: String(config.title ?? ''), disabled,
        onChange: value => perform(() => changeConfig('title', value)),
      })}),
      h(ui.SettingRow, {label: 'Count limit', htmlFor: 'limit', control: h(ui.NumberInput, {
        id: 'limit', value: Number(config.limit ?? 100), min: 1, max: 1000, step: 1, disabled,
        onChange: value => perform(() => changeConfig('limit', value)),
      })}),
      h('p', null, 'Use Astra’s Save or Cancel buttons.'));
  } else if (context.viewId === 'menu') {
    content = h('div', null,
      h(ui.Select, {value: String(config.title ?? 'My counter'), disabled,
        options: [{value: 'My counter', label: 'My counter'}, {value: 'Tasks', label: 'Tasks'}],
        onChange: value => perform(() => changeConfig('title', value)),
      }),
      h(ui.Combobox, {value: String(config.title ?? ''), disabled, freeSolo: true,
        options: [{value: 'Tasks', label: 'Tasks'}],
        onChange: value => perform(() => changeConfig('title', value)),
      }),
      h(ui.Tooltip, {content: 'Changes apply to this instance.', placement: 'bottom'},
        h(ui.Button, {disabled, 'aria-label': 'About settings'}, 'Help')));
  } else if (context.viewId === 'details') {
    content = h('div', null, h('p', null, 'Count: ' + count),
      h('pre', null, JSON.stringify(context.params ?? {}, null, 2)));
  } else {
    content = h('div', null,
      h('strong', null, String(config.title ?? 'My counter')),
      h('output', null, ' ' + count),
      context.formatId === 'expanded' ? h('p', null, 'Each instance keeps its own count.') : null,
      h(ui.Button, {disabled: disabled || countBusy || count >= Number(config.limit ?? 100), onClick: () => perform(async () => {
        if (countBusy) return;
        countBusy = true; render(); // lock this writer before awaiting a read
        try {
          const current = Number(await astra.widget.getData('count') ?? 0);
          const limit = Number(config.limit ?? 100);
          if (!Number.isFinite(current) || current < 0) throw new Error('Stored count is invalid');
          if (current >= limit) {count = current; return;} // lowering a limit does not erase existing data
          const next = Math.min(current + 1, limit);
          await astra.widget.setData('count', String(next)); count = next;
        } finally {countBusy = false;}
      })}, 'Add one'),
      h(ui.Button, {disabled, onClick: event => perform(async () => {
        menuToken = await astra.widget.openSurface('menu', {anchor: event.currentTarget});
      })}, 'Menu'),
      h(ui.Button, {disabled, onClick: () => perform(() => astra.widget.openSurface('details', {
        params: {item: 'counter'},
      }))}, 'Details'),
      h(ui.Button, {disabled: !menuToken, onClick: () => perform(async () => {
        await astra.widget.closeSurface(menuToken);
      })}, 'Close menu'));
  }
  root.render(h('div', null, content, h('p', {role: 'alert'}, error)));
}

const stopContext = astra.widget.onContextChange(next => {
  hostConfig = {...next.config};
  context = {...next, config: desiredConfig()}; // older acknowledgements cannot erase pending edits
  render();
});
const stopData = astra.widget.onDataChange(({key, value}) => {
  if (key === 'count') {count = Number(value ?? 0); render();}
});
const stopSurface = astra.widget.onSurfaceEvent(event => {
  if (event.type === 'closed' && event.token === menuToken) {menuToken = undefined; render();}
});
addEventListener('pagehide', () => {disposed = true; stopContext(); stopData(); stopSurface(); root.unmount();}, {once: true});
render();
```

## React использует те же props

Bootstrap React-шаблона ожидает `astra.loadUi({apiVersion: 1})` перед динамическим импортом App. Сохраните его и адаптер сборки. Этот типизированный фрагмент использует реальные value/callback props; свяжите callbacks с тем же немедленным объединением изменений каждого ключа/setConfig и показывайте ошибки. Фрагмент не заменяет bootstrap. Отправляйте setConfig сразу в callback, не откладывая за await/очередью: host «Сохранить» может немедленно закрыть iframe. Полные replacement-объекты должны сохранять другие ключи, а ожидающие изменения каждого ключа — переживать старые подтверждения контекста. Пример выше хранит version для каждого изменения и объединяет ожидаемые значения с последним контекстом host.

<!-- doctest: illustrative reason="A typed component fragment; bootstrap and bridge state come from the React scaffold. Checked against public Kit declarations." -->
```tsx
import { Input, NumberInput, Select, Combobox, Tooltip, Button, SettingRow } from '@astra/plugin-ui';

export function Settings(props: {
  title: string;
  limit: number;
  saveTitle: (value: string) => void;
  saveLimit: (value: number) => void;
}) {
  return <>
    <SettingRow label="Title" htmlFor="title" control={
      <Input id="title" value={props.title} onChange={props.saveTitle} />
    } />
    <SettingRow label="Limit" htmlFor="limit" control={
      <NumberInput id="limit" value={props.limit} min={1} max={1000} step={1}
        onChange={props.saveLimit} />
    } />
    <Select value={props.title} onChange={props.saveTitle} options={[
      {value: 'My counter', label: 'My counter'}, {value: 'Tasks', label: 'Tasks'},
    ]} />
    <Combobox value={props.title} onChange={props.saveTitle} freeSolo
      options={[{value: 'Tasks', label: 'Tasks'}]} />
    <Tooltip content="Changes apply to this instance." placement="bottom">
      <Button aria-label="About settings">Help</Button>
    </Tooltip>
  </>;
}
```

## Сборка и проверка

<!-- doctest: cli -->
```bash
astra-plugin check . --strict
astra-plugin test .
astra-plugin build .
astra-plugin dev .
```

`test` использует mock host, `dev` требует запущенную Astra. Проверьте независимость двух экземпляров, размеры и смену формата, сохранение/отмену настроек, исчезновение/возвращение плагина, предпросмотр, выход поповера за карточку, вложенные списки, Escape/фокус, края viewport, тему, масштаб текста и стекло. Целевые платформы приёмки — Windows/Tauri и Linux/Electron. Браузерные/mock-проверки не доказывают работу установленного приложения; маршрутизация плагинов macOS требует отдельной проверки установленной Astra. Минимальную версию runtime закрепляют по первому фактическому релизу. Публикация SDK/CLI и развёртывание сюда не входят.
