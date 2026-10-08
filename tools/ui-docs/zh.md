<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# 插件 UI Kit

使用 Astra 的真实控件，不再模仿其 CSS。Runtime 随已安装的应用提供；公共包只包含类型声明和构建适配器。

Frontend 独立于 Rust、Python 或 TypeScript backend 选择，默认使用 vanilla。React 在 frontend/ 中有独立 package 和冻结的 lockfile。运行 astra-plugin build 或 dev 前先在那里安装依赖。

## API 与组件

显示控件前等待 loadUi。h 接受组件或标签、props 和子元素。mount 提供宿主环境并返回 render/unmount。Props 和 callbacks 与 Astra 相同。语言、调色板和材质变化保持组件树与表单状态。

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

## React 与打包

使用 @astra/plugin-ui/build，适配器将 UI、React、ReactDOM、JSX 导向固定宿主路径。不要重复打包 React。Bootstrap 应先等待 loadUi，再动态导入 React 应用，以便加载失败时显示升级提示。Release CI 为所有 backend 使用冻结 lockfile 安装 frontend 依赖。

## 兼容性与验证

API v1 保持导出名和签名，外观随 Astra 更新。普通页面的菜单和模态框保留在 iframe 内；小组件的 Select/Tooltip 与声明的浮动界面由主机在卡片外渲染。自定义界面和旧插件仍受支持。在真实 Tauri/Windows 和 Electron/Linux 窗口中检查 Modal 内的 Select、Escape、焦点恢复、调色板、窄 iframe 与玻璃效果，并在离线安装的 bundle 中重复检查。

Snapshot 的最低版本指向含 Kit 的待发布 Astra 构建。{{MIN_ASTRA_VERSION}} 与 CLI 0.5.0 尚未发布，不应描述为已经交付。

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Desktop widgets (development contract)

`desktop-widget` 模板在主机玻璃卡片和浮动界面中使用此 Kit。[完整指南](desktop-widgets.md)说明准确 SDK 字段、值回调、`context.params`、令牌、主机编辑器打开的设置草稿与只读预览。请使用提供的匹配 CLI/SDK 构建产物；这些功能尚未发布。

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
