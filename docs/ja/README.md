# Astra プラグイン開発

[Astra](https://github.com/Stella)（AI 搭載のデジタルアシスタント）向けのプラグインを Rust、Python、TypeScript のいずれかで構築できます。

プラグインは Astra がサイドカーとして起動する独立したプロセスです。デーモンとは gRPC 経由で通信し、AI ツールの公開、TTS/STT バックエンドの提供、Command Graph へのカスタムアクション／トリガーの追加、UI パネルの挿入、あるいは完全なデーモンクライアントとしての動作が可能です。

## 目次

| ドキュメント | 内容 |
| --- | --- |
| [はじめに](getting-started.md) | CLI のインストール、最初のプラグインの雛形生成、開発モードでの実行、配布可能なバンドルのビルド |
| [CLI リファレンス](cli.md) | `astra-plugin` の全サブコマンドとフラグ、動作、終了コード |
| [Rust SDK](sdk-rust.md) | トレイトベースの API（`PluginCapability`）、フィールドビルダー、`HostClient`、`DaemonClient` |
| [Python SDK](sdk-python.md) | デコレータ API（`@tool`、`@action`、`@trigger`）、型ヒントからの自動スキーマ生成、UV 統合 |
| [TypeScript SDK](sdk-typescript.md) | クラスベース API、機能の自動検出、`@grpc/grpc-js` ランタイム |
| [マニフェスト](manifest.md) | `plugin.toml` リファレンス — すべてのセクションとフィールド |
| [機能](capabilities.md) | 9 種類すべての機能、SDK ごとの API、proto RPC |
| [公開](publishing.md) | `.astraplugin` バンドル形式、Ed25519 署名、サイドロード |

## アーキテクチャ概観

```
┌────────────────────────┐     gRPC     ┌────────────────────────┐
│        Astra           │◀────────────▶│        Plugin          │
│        daemon          │   localhost  │      (sidecar)         │
│                        │              │                        │
│ PluginHostService ─────┼────────────▶│ HostClient             │
│                        │              │                        │
│ plugin-capability ◀────┼──────────────│ PluginCapability       │
│   service client       │              │   service              │
└────────────────────────┘              └────────────────────────┘
```

- デーモンは各プラグインを独立したプロセスとして起動し、コマンドライン引数として `--daemon-addr`、`--plugin-id`、および必要に応じて `--auth-token` を渡します。
- プラグインはローカルのランダムなポートで gRPC サーバーを起動し、デーモンの `PluginHostService` に接続して**登録**を行い、実装している機能を通知します。
- 登録後、デーモンはプラグインの `PluginCapabilityService` を呼び出してツール呼び出し、アクション実行、TTS、ライフサイクルイベントを処理します。
- プラグインは `HostClient` を用いて、ログ出力、トリガーの発火、自身の設定の読み取り、変数の設定、あるいは UI の iframe へのイベント送信を行います。クライアント機能を持つプラグインには、Chat、Voice、Command、Media、Monitor、Config サービスにアクセスできる完全な `DaemonClient` が追加で提供されます。

## SDK の選び方

| 項目 | Rust | Python | TypeScript |
| --- | --- | --- | --- |
| 起動レイテンシ | 約 10 ms（ネイティブバイナリ） | 約 300 ms（インタプリタ + grpcio のインポート） | 約 100 ms（Node のコールドスタート） |
| メモリフットプリント | 最小 | 最大 | 中程度 |
| バンドルサイズ | 約 5〜10 MB のバイナリ | 約 100 KB のソース + デーモン管理の venv | 約 200 KB のバンドル（esbuild） |
| 向いている用途 | パフォーマンス重視、システム統合、TTS/STT プロバイダ | AI ツール、データ処理、ML ライブラリ | Web API、JSON 中心の処理、UI 統合 |
| 型安全性 | 完全（コンパイル時） | ヒントで任意に指定（実行時にスキーマ生成） | 完全（コンパイル時） |

3 つの SDK はいずれもファーストクラスで、すべての機能がどの SDK でも利用できます。ライブラリを取り込みたいエコシステムに合わせて選択してください。

## 次のステップ

5 分で試せるチュートリアルは [はじめに](getting-started.md) をご覧ください。
