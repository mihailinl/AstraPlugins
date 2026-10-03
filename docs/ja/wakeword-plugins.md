> **これは翻訳です。** 正式な情報源は [docs/en](../en/wakeword-plugins.md) です。内容に食い違いがある場合は英語版が優先されます。

# ウェイクワードプラグイン

ウェイクワードプラグインは、`plugin.toml` の `[capabilities]` セクションで
`wakeword = true` を宣言します。Astra は、このケーパビリティを持つインストール済み
プラグインを **音声 → Wake Word** に一覧表示します。プラグインをアンインストールすると、
その選択と設定は消えます。プラグインに専用のページや UI コントリビューションは
必要ありません。

## 新しい検出器を作る

現在の CLI と、新しい出力ディレクトリを使います:

<!-- doctest: cli -->
```bash
astra-plugin new my-wakeword --lang rust --template blank --capabilities wakeword --output ./my-wakeword
```

`--lang` には `python` や `typescript` も指定できます。ウェイクワード用のテンプレートは
まだありません。Rust の blank スキャフォールドには、無関係な `hello` ツールとその
テストが含まれています。両方とも置き換えてください。プラグインが実際に他の機能も
提供するのでない限り、ケーパビリティは `wakeword = true` だけにしてください。
マニフェストとコンパイル済みバイナリの食い違いは `astra-plugin check` で検出できます。

デーモンは、`wakeword` だけを宣言したプラグインに対しても、以下の 3 つの呼び出しを
`CallFromUi` 経由で送ります。これはトランスポートの再利用であり、`ui_contributions`、
iframe、`push_to_ui` のいずれも必要としません。汎用のフック表が `CallFromUi` を
UI の下に載せているのは、それが本来の用途だからです。

Rust では、SDK の `handle_ui_call(&self, ctx: &PluginContext,
method: &str, params_json: &str) -> Result<String, ToolError>` フックを実装するか、
`#[ui_call]` メソッドを使います(ハイフンを含む名前には
`#[ui_call(name = "process-audio")]` と `#[ui_call(name = "reset-audio")]` を使います)。
各 `#[ui_call]` メソッドには `///` のドキュメントコメントが必要で、ないとマクロは
コンパイルを拒否します。impl ブロックには
`#[astra::plugin(capabilities = "wakeword")]` を付けてください(上のスキャフォールドは
すでにそうしています)。付けないと、`#[ui_call]` からの自動推論が
`ui_contributions` を宣言し、マニフェストと食い違います。`status`、`reset-audio`、
`process-audio` は、フレームバッファを呼び出し間で保持する 1 つの検出器
インスタンスに振り分けてください。以下の応答の形の JSON 文字列を返します。
Python では SDK の `@ui_call` ハンドラを、TypeScript では 3 つのメソッド名を持つ
`ui: { contributions: [], onCall: { ... } }` を使います。
これらのハンドラが目に見える UI ページを作ることはありません。
エントリポイント、設定へのアクセス、ライフサイクルについては
[Rust](4-sdk/rust.md)、[Python](4-sdk/python.md)、
[TypeScript](4-sdk/typescript.md) の各 SDK ガイドを参照してください。

プラグインは、既存の `[config]` の JSON Schema で設定を提供します。Astra は、
そのプラグインが選択されている間だけ音声ページにフィールドを表示し、
`UpdatePluginConfig` で保存します。文字列、数値、真偽値、列挙のプロパティが
使えます。`"format": "password"` の文字列はパスワード欄になり、`"format": "file"`
(または `"x-astra-field-type": "file_picker"`)はローカルのファイル選択を出します。
`"x-astra-field-type": "slider"` と `"textarea"` は、数値と文字列のプロパティに
それぞれその部品を選びます。設定されたパスを読むのはプラグインで、Astra は
キーワードモデルの形式を定めません。

プロトコル 1 は、3 つのメソッドに認証付きのリクエスト/レスポンスチャネル
`CallFromUi` を使います。これはデーモン内部の呼び出しで、iframe やページは
作られません。

| メソッド | リクエスト JSON | レスポンス JSON |
|---|---|---|
| `status` | `{}` | `{"ready": true}` または `{"ready": false, "message": "…"}` |
| `process-audio` | `{"pcm_base64": "…"}` | `{"detected": false}` または `{"detected": true}` |
| `reset-audio` | `{}` | `{}` |

`pcm_base64` には、16 kHz モノラル、符号付き 16 ビット、リトルエンディアンの PCM が
入ります。Astra は 1 回の呼び出しごとに 100 ms(1600 サンプル)を送ります。
検出器のフレーム長が異なる場合、プラグインは呼び出し間でサンプルを保持しなければ
なりません。Astra がウェイクゲートをリセットすると、`reset-audio` はその保持した
音声とモデルの途中の検出状態を破棄します。Base64 をデコードし、不正な PCM や長さが
奇数の PCM は拒否し、リトルエンディアンのバイト対をそれぞれ `i16` に変換してから、
サンプルを順に検出器へ渡してください。100 ms の各ブロックを完結した発話として
扱ってはいけません。各呼び出しの期限は 2 秒です。音声ループは上限付きのキューを
使い、プラグインを待つことはありません。
`astra-plugin test` は 3 つのメソッドをすべて呼び出し、JSON 応答の形を確認します。
プラグインが未設定かもしれない状態での、すべてゼロの音声ブロックも含みます。
このテストは、選んだキーワードが検出されることまでは確認しません。配布する前に、
有効なモデルを読み込んで `status.ready = true` を確認し、ウェイクフレーズの録音を
いくつか、複数の 100 ms 呼び出しにまたがって再生し、無音、背景雑音、普通の会話を
陰性ケースとして再生してください。`reset-audio` が言いかけのフレーズを消すこと、
リセット後も検出が働くことを確認してください。そのうえでプラグインをインストール
またはサイドロードし、**音声 → Wake Word** で選択して、Astra が聞き取りを始め、
フレーズで起動することを確かめてください。未設定のモデルは、役に立つメッセージを
添えて `ready: false` を返すべきです。

Astra は聞き取りを始める前に `status.ready` を確認します。選択したプラグインが
存在しない、停止している、準備ができていない場合、聞き取りは黙って連続文字起こしに
切り替わるのではなく、安全側に失敗します。実行時の選択には
`voice.wake_word_mode = "plugin__<id>"` を使い、STT や TTS プラグインのプロバイダ ID と
同じく、プラグイン ID のハイフンをアンダースコアに置き換えます。
`ready: true` を返すのは、検出器と設定されたモデルが音声を処理できるようになってから
にしてください。ファイルパスがあるだけでは不十分です。
