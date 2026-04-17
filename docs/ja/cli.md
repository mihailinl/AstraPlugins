# `astra-plugin` CLI リファレンス

すべてのサブコマンド、フラグ、動作を網羅します。情報源は `astra-plugin-cli/src/main.rs` と `astra-plugin-cli/src/commands/` です。

## インストール

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

コマンドの全一覧は `astra-plugin --help` で確認できます。各サブコマンドも `--help` を受け付けます。

## `astra-plugin create`

言語別のテンプレートから新しいプラグインプロジェクトの雛形を生成します。

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| 引数 / フラグ | デフォルト | 説明 |
| --- | --- | --- |
| `NAME` | — | プラグイン ID。小文字の英数字とハイフンのみ。マニフェストの `[plugin].id` になります。 |
| `-l, --lang` | `rust` | `rust`、`python`（エイリアス `py`）、`typescript`（エイリアス `ts`）のいずれか。 |
| `-c, --capabilities` | `tools` | カンマ区切りのリスト。有効な値: `tools`、`tts`、`stt`、`ai_provider`、`actions`、`triggers`、`client`、`event_handlers`、`ui_panels`。カンマ周辺の空白は除去されます。 |
| `-o, --output` | `./<NAME>` | 出力先ディレクトリ。 |

### 生成されるもの

すべての雛形に共通して含まれるもの:

- `plugin.toml` — id、name、バージョン `0.1.0`、および指定した `[capabilities]` セクションが有効化された状態で生成されるマニフェスト。
- `proto/plugin.proto` — プラグインプロトコルのローカルコピー。
- `.gitignore`、`README.md`。

言語別に追加されるファイル:

| 言語 | 追加ファイル |
| --- | --- |
| `rust` | `Cargo.toml`（`astra-plugin-sdk`、`tokio`、`serde`、`anyhow`、`async-trait` を含む）、`PluginCapability` 実装のスタブを持つ `src/main.rs`。`entry.command` は `target/release/<name>.exe` に設定されます。 |
| `python` | `pyproject.toml`（`astra-plugin-sdk`、`grpcio`、`protobuf` を含む）、`Plugin` サブクラスのスタブを持つ `src/plugin.py`。`entry.command = "python"`、`args = ["-m", "src.plugin"]`、`runtimes = ["python"]`。 |
| `typescript` | `package.json`、`tsconfig.json`、`Plugin` サブクラスのスタブを持つ `src/index.ts`。`entry.command = "node"`、`args = ["dist/index.js"]`、`runtimes = ["node"]`。 |

## `astra-plugin dev`

ファイル監視と自動再ビルド／再起動付きで、プラグインを開発モードで実行します。

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| 引数 / フラグ | デフォルト | 説明 |
| --- | --- | --- |
| `PATH` | `.` | プラグインディレクトリ（`plugin.toml` を含むディレクトリ）。 |
| `--daemon-addr` | `127.0.0.1:50051` | 稼働中の Astra デーモンの gRPC アドレス。 |

### 動作内容

1. `plugin.toml` を読み込み、言語ごとのビルドコマンドを決定します。
2. プラグインディレクトリのファイル監視を開始します（`target/`、`node_modules/`、`__pycache__/`、`.venv/`、`dist/` は除外）。
3. ビルドを実行します（Rust は `cargo build`、TypeScript は `bun run build` / `tsc`、Python は `uv pip sync` またはビルドなし）。
4. `--daemon-addr`、`--plugin-id`、`--auth-token` を付加して `entry.command` を起動します。
5. ファイル変更時: 子プロセスを終了し、再ビルドして再起動します。

エラーはその場で表示されます。停止するには `Ctrl+C` を押してください。

## `astra-plugin build`

プラグインを配布可能な `.astraplugin` アーカイブにパッケージ化します。

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| 引数 / フラグ | デフォルト | 説明 |
| --- | --- | --- |
| `PATH` | `.` | プラグインディレクトリ。 |
| `-o, --output` | `<id>-<version>.astraplugin` | アーカイブのパス。 |

### 言語別のビルド手順

| 言語 | 手順 |
| --- | --- |
| `rust` | `cargo build --release` を実行し、バイナリをアーカイブ内の `bin/` にコピーして、`entry.command` をバンドル内のパスに書き換えます。 |
| `typescript` | `bun build src/index.ts --outdir dist` を実行し、失敗時は `npx esbuild` にフォールバックします。バンドルされた JS はアーカイブ内の `dist/` に格納されます。 |
| `python` | `uv` が `PATH` にあれば `uv pip compile` を介して `requirements.lock` を生成します。`src/`、`pyproject.toml`、`requirements.txt`、ロックファイルをコピーします。 |

### アーカイブの構成

```
<plugin-id>-<version>.astraplugin           (ZIP file)
├── plugin.toml              # Manifest (entry.command rewritten for Rust)
├── bin/                     # Compiled binary (Rust only)
├── dist/                    # Bundled JS (TypeScript only)
├── src/                     # Python source
├── requirements.txt         # Python deps (unlocked)
├── requirements.lock        # Python deps (resolved by uv)
├── ui/                      # Custom UI (if present)
├── locales/                 # i18n JSON files (if present)
├── icon.png / icon.svg      # Optional branding
├── README.md / LICENSE      # Optional
├── SIGNATURE                # Ed25519 signature (if keypair exists)
└── PUBKEY                   # Signing public key (if keypair exists)
```

`~/.astra/plugin-keys/private.key` が存在する場合、CLI はビルドのたびにアーカイブへ**自動的に署名します** — 追加のフラグは不要です。

## `astra-plugin validate`

ビルドを行わずに、マニフェストと設定スキーマを検査します。

```bash
astra-plugin validate [PATH]
```

検証項目:

- 必須のマニフェストフィールド: `plugin.id`、`plugin.name`、`plugin.version`、`entry.command`。
- `plugin.id` が小文字の英数字とハイフンで構成されていること。
- `plugin.version` が `X.Y.Z` 形式の SemVer に一致していること（一致しない場合は警告扱い、エラーではありません）。
- 少なくとも 1 つの機能が有効化されていること（すべて false の場合は警告）。
- `[config].schema` が存在する場合、JSON として解析可能で、ルートが `"type": "object"` であること。
- メタデータの警告: `description` または `author` が欠落している場合。

終了コードが非ゼロになるのは致命的なエラー（TOML の解析失敗、必須フィールドの欠落）のみです。

## `astra-plugin keygen`

`build` がアーカイブの署名に使用する Ed25519 鍵ペアを生成します。

```bash
astra-plugin keygen [--force]
```

| フラグ | 説明 |
| --- | --- |
| `--force` | 既存の鍵ペアを上書きします。このフラグがない場合、既存の鍵を置き換えることを拒否します。 |

出力場所（必要なら新規作成）:

- `~/.astra/plugin-keys/private.key` — base64 形式の Ed25519 秘密シード（秘匿してください）。
- `~/.astra/plugin-keys/public.key` — base64 形式の Ed25519 公開鍵（共有しても安全）。

鍵ペアが存在すると、`astra-plugin build` は毎回 `SIGNATURE` エントリ（各 ZIP エントリの HMAC 類似のダイジェストを Ed25519 で署名したもの）と `PUBKEY` エントリを自動で追加し、利用者がバンドルの真正性を検証できるようにします。

## 環境変数

- `RUST_LOG` — CLI 出力の詳細度を制御します。既定は警告レベルで、`RUST_LOG=debug` を指定すると完全なトレースが表示されます。
- すべての CLI コマンドは、`cargo`、`node`、`bun`、`npx`、`python`、`uv` を検索する際に現在のシェルの `PATH` を尊重します。
