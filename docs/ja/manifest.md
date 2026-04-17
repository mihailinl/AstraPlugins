# `plugin.toml` リファレンス

すべてのプラグインは、プロジェクトのルートに配置した `plugin.toml` マニフェストで自身を宣言します。このファイルは、プラグインの起動方法、実装している機能、受け付ける設定をデーモンに伝えます。

## 完全な例

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` — メタデータ

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `id` | 文字列 | 必須 | 小文字の英数字とハイフン。プラグインを一意に識別します。 |
| `name` | 文字列 | 必須 | Plugins UI に表示される名称。 |
| `version` | 文字列 | 必須 | セマンティックバージョン（`X.Y.Z`）。アップグレード判定に使用されます。 |
| `description` | 文字列 | 推奨 | 短い説明。Plugins UI に表示されます。 |
| `author` | 文字列 | 推奨 | 作者または組織名。 |
| `license` | 文字列 | 推奨 | SPDX ライセンス識別子（`MIT`、`Apache-2.0` など）。 |

## `[entry]` — プラグインの起動方法

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `command` | 文字列 | 必須 | 起動する実行ファイル。Rust ではコンパイル済みバイナリのパス、Python では `"python"`、TypeScript では `"node"` を指定します。 |
| `args` | 文字列配列 | 任意 | `--daemon-addr`、`--plugin-id`、`--auth-token` の前に付加される引数。代表的な値: Python なら `["-m", "src.plugin"]`、Node なら `["dist/index.js"]`。 |
| `runtimes` | 文字列配列 | 任意 | デーモンへのヒント。サポート値: `"python"`、`"node"`、`"rust"`。Python や Node のプラグインは、デーモンがランタイムを準備できる（例: Python 用の `uv` venv 作成）よう、必ず指定してください。 |

デーモンは起動時に `--daemon-addr <addr> --plugin-id <id>` を必ず付加し、クライアントプラグインにはさらに `--auth-token <token>` を付加します。

## `[capabilities]` — プラグインが実装するもの

各フィールドは既定値 `false` のブール値です。実際にコードで扱う機能だけを `true` にしてください。デーモンはこの値に従ってリソースを割り当て、関連する UI（例: TTS のボイスピッカーへの音声追加）にプラグインを出すかを決定します。

| 機能 | 目的 |
| --- | --- |
| `tools` | チャットモデルから呼び出せる AI ツール。 |
| `tts` | テキスト読み上げの音声プロバイダ。 |
| `stt` | 音声認識の言語プロバイダ。 |
| `ai_provider` | 代替の AI 補完バックエンド。 |
| `actions` | Command Graph のカスタムアクション型。 |
| `triggers` | Command Graph のカスタムトリガー型。 |
| `client` | 完全なデーモンクライアント（セッショントークンが必要）。 |
| `ui_contributions` | UI ページ、オーバーレイ、エフェクト、スロット挿入。 |
| `event_handlers` | デーモンのイベントストリームを購読。 |

機能ごとの完全な動作仕様は [機能](capabilities.md) を参照してください。

## `[config]` — ユーザー向け設定

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

ルール:

- `schema` は **JSON Schema の文字列**です。ルートは `"type": "object"` である必要があります。
- デーモンはスキーマをプラグイン設定ページのフォームとしてレンダリングします。
- `title` はフィールドのラベル、`description` はヘルプテキストとして表示されます。
- `default` は初期値を指定します。
- `x-secret: true` を指定すると UI で値がマスクされ、暗号化して保存されます。
- `enum` はドロップダウンとしてレンダリングされます。
- `required` 配列は必須フィールドを示します。
- ユーザーが設定を更新すると、デーモンは新しい JSON ブロブと共に `OnConfigChanged` を呼び出します。

## スキーマ外の TOML フィールド

プラグインはデーモンが無視する任意のトップレベルセクションを追加できます。ツール用途などに便利です。CLI は未知のフィールドについて警告しますが、拒否はしません。

## マニフェストのローカライズ

プラグインバンドル内に `locales/<lang>.json` ファイルを同梱することで、ユーザー向け文字列（`name`、`description`、アクションラベル、フィールドラベルなど）を翻訳できます。各 SDK の `I18n` ヘルパーを使い、コードから読み込んでください。ローカライズ対象はマニフェストの**テキスト**のみで、キーや ID、enum 値は変わりません。

## マニフェストの検証

```bash
astra-plugin validate
```

検査内容:

- 必須フィールドの存在（`plugin.id`、`plugin.name`、`plugin.version`、`entry.command`）。
- `plugin.id` が小文字の英数字とハイフンで構成されていること。
- `plugin.version` が SemVer（`X.Y.Z`）に一致すること。
- 少なくとも 1 つの機能が有効化されていること。
- `[config].schema` が JSON として解析可能で、ルートが `"type": "object"` であること。
- メタデータ（description、author）が揃っていること。

詳細は [CLI リファレンス → validate](cli.md#astra-plugin-validate) を参照してください。
