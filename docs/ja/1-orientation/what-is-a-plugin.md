> **これは翻訳です。** 正式な情報源は [docs/en](../../en/1-orientation/what-is-a-plugin.md) です。内容に食い違いがある場合は英語版が優先されます。

# プラグインとは何か

プラグインとは、Astra デーモンが起動する**独立したプログラム**であり、
localhost 上の gRPC でデーモンと対話します。ライブラリではなく、Astra の
アドレス空間にロードされるわけでもなく、Astra が解釈するスクリプトでも
ありません。Astra はシェルがそうするようにコマンドライン引数を渡してこれを
spawn し、シャットダウンを要求し、応じなければプロセスグループを kill する
ことで停止させます。

この 1 つの事実が、残りのほとんどを決めています。

- **gRPC を話せる言語であれば何で書いてもかまいません。** ここには 3 つの
  SDK があります — Rust、Python、TypeScript — これらは
  [完全なパリティ](../reference/parity.md)にあります: 35 個すべてのフックが
  3 つすべてにあります。
- **あなたと同じ権限を持ちます。それ以下ではありません。**
  [セキュリティモデル](security.md) を参照してください。
- **自分自身のバグにはうまく耐えられませんが、Astra には一切影響しません。**
  ハンドラ内の panic は捕捉され、プロセスを kill するのではなくエラーとして
  返されます(`astra-plugin-sdk/src/panics.rs`)。プロセス全体のクラッシュは
  デーモンのヘルスチェックによって 15 秒以内に検出されます。

## 2 つの方向

プラグインが行うことはすべて次の 2 つのどちらかであり、それぞれ
`plugin.toml` 内で別々の名前を持つ別々の系統です。

| | 方向 | マニフェストのセクション | 答えること |
|---|---|---|---|
| **Capabilities** | デーモン → プラグイン | `[capabilities]` | プラグインが何を実装し、Astra が*呼び込める*のは何か |
| **Permissions** | プラグイン → デーモン | `[permissions]` | プラグインが*呼び出せる*ホスト RPC はどれか |

かつてはこの両方に 1 つの単語しかなく、それが `dom_access` — このシステムで
最も危険なもの — が、宣言するだけでプラグインが自分自身に付与できるものに
なってしまっていた経緯です。今では 2 つの単語に分かれています。
`[capabilities] event_handlers = true` を宣言してもイベントを購読できる
ようにはなりません。それをできるようにするのは `[permissions]
subscribe_events` であり、しかもユーザーの同意があって初めてです。

`[permissions]` は**デフォルト拒否**です。セクションがまったくない場合、
プラグインは `Register`、`PluginLog`、`GetPluginSelfConfig`、
`GetDaemonInfo` だけを呼び出せ、それ以外は一切呼び出せません
([`spec/permissions.md` §2](../spec/permissions.md))。

## 10 個のケーパビリティ

すべてのキーは真偽値であり、デフォルトは `false` で、あるものを宣言すると
特定のフックを提供する義務が生じます。右の列は*必須*のもので、任意の
ものは[パリティ表](../reference/parity.md)にあります。

| `[capabilities]` のキー | プラグインが何になるか | 提供が必要なフック |
|---|---|---|
| `tools` | モデルが呼び出せる関数の集合 | `ListTools`、`CallTool` |
| `tts` | Voice 設定内のテキスト読み上げプロバイダ | `TtsSynthesize`、`TtsListVoices` |
| `stt` | 音声認識プロバイダ | `SttProcess`、`SttGetLanguages` |
| `ai_provider` | モデルバックエンド | `AiComplete` |
| `actions` | コマンドエディタ内のステップ | `ExecuteAction`、`GetPluginActionTypes` |
| `triggers` | コマンドがlistenできるトリガー種別 | `GetPluginTriggerTypes`、`FireTrigger` |
| `ui_contributions` | Astra ウィンドウ内のパネル・ページ・オーバーレイ | `GetUiContributions` |
| `event_handlers` | デーモンイベントの購読者 | `SubscribeEvents` |
| `client` | 独自のチャットフロントエンド | `SendChatMessage` |
| `dom_access` | Astra ウィンドウの中で動くコード | なし — これはフックではなく描画上の決定です |

出典: [`reference/manifest.md`](../reference/manifest.md)、デーモンが
あなたのマニフェストをパースするのに使うクレートから生成されています。
`ui_panels` はケーパビリティではなく、これまでもそうだったことはありません
— 出荷済みの 3 つのサンプルがこれを宣言してしまっていましたが、serde は
未知のキーを黙って捨て、唯一の症状は `astra-plugin check` がケーパビリティ
を 1 つも報告しないことでした。`[capabilities]` がまさにこの理由から
未知のキーを拒否するようになっています。

## マニフェストはどんな見た目か

最小の実用例 — ツールを持ち、パーミッションもそれ以外も何もないプラグイン
です。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat."
author = "You"
license = "MIT"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
```

トリガーを発火するものはパーミッションを要求しなければならず、`reason` は
Astra がユーザーに同意を求めるときにユーザーが読む文言です。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice, and fire a trigger when one comes up."
author = "You"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

すべてのセクションとキー: [`reference/manifest.md`](../reference/manifest.md)。

## プラグインにできないこと

- **一度インストールされた後は、自分自身にパーミッションを付与できません。**
  `[permissions]` ブロックはあくまで申請です。レジストリからインストール
  された、あるいはファイルとしてインポートされたプラグインについては、
  許可される集合はデーモンによって、プラグインがどこから来たかに基づいて
  解決され、プラグインが書き込めない場所に保存されます — マニフェストは
  プラグイン自身のディレクトリにあり、プラグインはそこを編集できます。
  **サイドロードされたプラグインは例外です**: この階層ではマニフェスト
  そのものが同意の記録であり、上限は存在しないため、自分のファイルを
  編集することで自分のパーミッションを広げることができます。
  [セキュリティモデル](security.md#プラグインの出所がその上限を決める)
  を参照してください。
- **Astra の `ChatService` に直接到達することはできません。** 登録時に
  プラグインが受け取るセッショントークンは `PluginHostService` にスコープ
  されています。AI のターンを駆動するには `SendChatMessage` を経由する
  必要があり、これは `send_chat_message` パーミッションでゲートされて
  おり、高リスクなものの 1 つです。
- **unrouted なフックに依存することはできません。** フックが proto と
  3 つの SDK すべてに存在していても、デーモン側の呼び出し箇所がない場合が
  あります。今日で言えば `TtsSynthesizeStream` がそれです。実装すること
  自体は無料ですが、呼び出されることに依存することは、
  [パリティ表](../reference/parity.md)が `live` と言うまでサポートされ
  ません。
- **バンドルを持たないプラットフォームにはインストールできません。**
  [プラットフォーム](platforms.md) を参照してください。

## 次に読む

プロセスがどう起動され認証されるかを知りたいなら
[アーキテクチャ](architecture.md)、そうでなければ
[はじめに](../2-tutorial/getting-started.md) へ直接進んでください。
