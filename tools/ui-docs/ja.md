<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# プラグイン UI Kit

CSS を模倣せず、Astra の実際のコントロールを使います。Runtime はインストール済みアプリに含まれ、公開パッケージには型宣言とビルドアダプターだけが含まれます。

Frontend は Rust、Python、TypeScript の backend と独立して選びます。既定は vanilla です。React は frontend/ に専用 package と固定 lockfile を持ちます。astra-plugin build または dev の前にそこで依存関係をインストールします。

## API とコンポーネント

表示前に loadUi を待ちます。h はコンポーネントまたはタグ、props、子を受け取ります。mount はホスト環境を設定し render/unmount を返します。Props と callbacks は Astra と同じです。言語、パレット、マテリアルの変更はツリーとフォーム状態を維持します。

{{COMPONENTS}}

<!-- doctest: illustrative reason="Requires the installed Astra iframe runtime; adapter output is exercised by tools/ui-kit.test.mjs." -->
```js
const ui = await astra.loadUi({apiVersion: {{API_VERSION}}});
const root = ui.mount(container, ui.h(ui.Button, {onClick: () => console.log('clicked')}, 'Astra'));
root.render(ui.h(ui.Input, {value: 'Hello', onChange: console.log}));
root.unmount();
```

## React とパッケージ

@astra/plugin-ui/build を使うと UI、React、ReactDOM、JSX が固定ホストパスへ解決されます。React を重複してバンドルしません。Bootstrap は loadUi の完了後に React アプリを動的 import し、失敗時に更新メッセージを表示します。Release CI はすべての backend で固定 lockfile から frontend 依存関係をインストールします。

## 互換性と検証

API v1 のエクスポート名とシグネチャは維持され、外観は Astra と更新されます。メニュー、モーダル、フォーカスは iframe 内に留まります。独自 UI と既存プラグインも利用できます。Tauri/Windows と Electron/Linux の実際のウィンドウで、Modal 内の Select、Escape、フォーカス復帰、パレット、狭い iframe、ガラスを確認し、ネットワークなしのインストール済み bundle でも繰り返します。

Snapshot の最低バージョンは Kit を含む準備中の Astra ビルドです。{{MIN_ASTRA_VERSION}} と CLI 0.5.0 は未公開です。配布済みと記述しないでください。

[Showcase](../../../examples/ui-kit-showcase/README.md) · [CLI](../reference/cli.md)
