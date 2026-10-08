<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# プラグイン UI Kit

CSS を模倣せず、Astra の実際のコントロールを使います。Runtime はインストール済みアプリに含まれ、公開パッケージには型宣言とビルドアダプターだけが含まれます。

Frontend は Rust、Python、TypeScript の backend と独立して選びます。既定は vanilla です。React は frontend/ に専用 package と固定 lockfile を持ちます。astra-plugin build または dev の前にそこで依存関係をインストールします。

## API とコンポーネント

表示前に loadUi を待ちます。h はコンポーネントまたはタグ、props、子を受け取ります。mount はホスト環境を設定し render/unmount を返します。Props と callbacks は Astra と同じです。言語、パレット、マテリアルの変更はツリーとフォーム状態を維持します。

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

## React とパッケージ

@astra/plugin-ui/build を使うと UI、React、ReactDOM、JSX が固定ホストパスへ解決されます。React を重複してバンドルしません。Bootstrap は loadUi の完了後に React アプリを動的 import し、失敗時に更新メッセージを表示します。Release CI はすべての backend で固定 lockfile から frontend 依存関係をインストールします。

## 互換性と検証

API v1 のエクスポート名とシグネチャは維持され、外観は Astra と更新されます。通常ページのメニューとモーダルは iframe 内にあります。ウィジェットの Select/Tooltip と宣言済みサーフェスはカードの外でホストが描画します。独自 UI と既存プラグインも利用できます。Tauri/Windows と Electron/Linux の実際のウィンドウで、Modal 内の Select、Escape、フォーカス復帰、パレット、狭い iframe、ガラスを確認し、ネットワークなしのインストール済み bundle でも繰り返します。

Snapshot の最低バージョンは Kit を含む準備中の Astra ビルドです。0.2.7 と CLI 0.5.0 は未公開です。配布済みと記述しないでください。

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)


## Desktop widgets (development contract)

`desktop-widget` テンプレートはホストのガラスカードとサーフェスでこの Kit を使用します。[完全なガイド](desktop-widgets.md)に正確な SDK フィールド、値のコールバック、`context.params`、トークン、ホストが開く設定ドラフト、読み取り専用プレビューを示します。対応する提供済み CLI/SDK を使用してください。これらは未公開です。

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
