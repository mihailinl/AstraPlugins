<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# 插件 UI Kit

使用 Astra 的真实控件，不再模仿其 CSS。Runtime 随已安装的应用提供；公共包只包含类型声明和构建适配器。

Frontend 独立于 Rust、Python 或 TypeScript backend 选择，默认使用 vanilla。React 在 frontend/ 中有独立 package 和冻结的 lockfile。运行 astra-plugin build 或 dev 前先在那里安装依赖。

## API 与组件

显示控件前等待 loadUi。h 接受组件或标签、props 和子元素。mount 提供宿主环境并返回 render/unmount。Props 和 callbacks 与 Astra 相同。语言、调色板和材质变化保持组件树与表单状态。

`Button`, `IconButton`, `Input`, `NumberInput`, `Textarea`, `Select`, `SelectTrigger`, `Combobox`, `Checkbox`, `RadioGroup`, `Toggle`, `SegmentedControl`, `Slider`, `Modal`, `Popover`, `AnchoredMenu`, `Tooltip`, `Card`, `Badge`, `Spinner`, `Icon`, `Section`, `SettingRow`, `FieldLabel`, `EmptyState`

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: 1});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React 与打包

使用 @astra/plugin-ui/build，适配器将 UI、React、ReactDOM、JSX 导向固定宿主路径。不要重复打包 React。Bootstrap 应先等待 loadUi，再动态导入 React 应用，以便加载失败时显示升级提示。Release CI 为所有 backend 使用冻结 lockfile 安装 frontend 依赖。

## 兼容性与验证

API v1 保持导出名和签名，外观随 Astra 更新。菜单、模态框和焦点都留在 iframe 中。自定义界面和旧插件仍受支持。在真实 Tauri/Windows 和 Electron/Linux 窗口中检查 Modal 内的 Select、Escape、焦点恢复、调色板、窄 iframe 与玻璃效果，并在离线安装的 bundle 中重复检查。

Snapshot 的最低版本指向含 Kit 的待发布 Astra 构建。0.2.7 与 CLI 0.5.0 尚未发布，不应描述为已经交付。

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
