# はじめに

5 分で完了するチュートリアルです。CLI をインストールし、Rust の tools プラグインの雛形を生成し、開発モードで実行してから、配布可能な `.astraplugin` バンドルをビルドします。

## 前提条件

- `127.0.0.1:50051`（デフォルトの gRPC ポート）で **Astra デーモン**が稼働していること。
- **Rust** 1.75 以上（Rust プラグインの開発、あるいは CLI をソースからインストールする場合）。
- 任意：選択する SDK に応じて **Python** 3.10 以上、または **Node.js** 20 以上。

## 1. CLI のインストール

`astra-plugin` CLI はプラグインの作成、実行、ビルド、検証、署名を行います。リポジトリからインストールしてください。

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

動作確認:

```bash
astra-plugin --version
```

## 2. プラグインの雛形を生成する

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

CLI は `--lang rust|python|ts` とカンマ区切りの `--capabilities` リストを受け付けます。すべてのオプションは [CLI リファレンス](cli.md) を参照してください。

生成される Rust プロジェクトの構成は次のとおりです。

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

`src/main.rs` を開き、ツールに実用的な実装を追加します。

```rust
use astra_plugin_sdk::prelude::*;

struct HelloWorld;

#[async_trait]
impl PluginCapability for HelloWorld {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "greet".into(),
            description: "Return a greeting for the given name".into(),
            parameters_json: r#"{
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }"#.into(),
        }]
    }

    async fn call_tool(&self, _name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value = serde_json::from_str(arguments_json)
            .unwrap_or_default();
        let who = args.get("name").and_then(|v| v.as_str()).unwrap_or("world");
        ToolResult::ok(format!("Hello, {who}!"))
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(HelloWorld).await
}
```

## 3. 開発モードで実行する

```bash
astra-plugin dev
```

このコマンドはプラグインディレクトリを監視し、変更があれば再ビルドしてプロセスを再起動し、`127.0.0.1:50051` のデーモンへ再接続します。Astra のチャットを開き「Ada に挨拶して」と頼むと、デーモンはツール呼び出しをプラグインにルーティングし、結果をチャットへストリーミングで返します。

監視対象外のディレクトリ: `target/`、`node_modules/`、`__pycache__/`、`.venv/`、`dist/`。

デフォルト以外のデーモンを指す場合は `--daemon-addr` を指定します。

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. マニフェストを検証する

```bash
astra-plugin validate
```

必須フィールドの欠落、無効な SemVer、不正な設定スキーマを検出します。ビルド前に必ず実行してください。検証に失敗したプラグインはデーモンがロードを拒否します。

## 5. 配布可能なバンドルをビルドする

```bash
astra-plugin build
```

`hello-world-0.1.0.astraplugin` を生成します。これはコンパイル済みのバイナリ、マニフェスト、UI アセット、ロケール、そして（署名鍵がある場合は）Ed25519 の `SIGNATURE` エントリを含む ZIP アーカイブです。

出力先を指定するには `-o` を使用します。

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. （任意）署名鍵を生成する

```bash
astra-plugin keygen
```

`~/.astra/plugin-keys/{private,public}.key` に Ed25519 の鍵ペアを作成します。それ以降は `astra-plugin build` を実行するたびに自動的にアーカイブへ署名されます。バンドルを検証したいユーザーには `public.key` を共有してください。

## 7. プラグインをインストールする

`.astraplugin` ファイルを Astra UI のプラグインページにドラッグするか、デーモンの `SideloadPlugin` RPC を呼び出します。インストール後、デーモンは正しい資格情報でプラグインプロセスを再起動し、プラグイン一覧に表示されます。

## 次に進むには

- [Rust SDK](sdk-rust.md) — すべてのトレイトメソッド、`FieldDef` / `UiContribution` ビルダー、クライアントプラグイン向けの `DaemonClient`。
- [Python SDK](sdk-python.md) — `@tool` / `@action` デコレータと型ヒントからの自動スキーマ生成を好む場合。
- [TypeScript SDK](sdk-typescript.md) — `@grpc/grpc-js` を利用したクラスベースの API。
- [機能](capabilities.md) — tools、TTS、STT、AI プロバイダ、アクション、トリガー、UI コントリビューション、イベントハンドラ、クライアントモードの完全なリファレンス。
- [公開](publishing.md) — 署名、配布、アップグレード戦略。
