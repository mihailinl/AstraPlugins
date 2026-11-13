> **これは翻訳です。** 正式な情報源は [docs/en](../../en/3-reference/permissions.md) です。内容に食い違いがある場合は英語版が優先されます。

# パーミッション

各 `[permissions]` id が何を許可するか、それがユーザーに何を要求するか、
そして読む価値のある `reason` の書き方について。

これは作者向けのページです。規範的なルール — 付与、上限、
`permissions_hash`、正確な拒否のセマンティクス — は
[`spec/permissions.md`](../spec/permissions.md) にあります。各 id が
どの RPC をゲートするかの生成された表は
[`reference/manifest.md`](../reference/manifest.md) と
[`reference/parity.md`](../reference/parity.md) にあり、どちらも
`spec/hooks.yaml` から導出され、パリティルール R6 によってデーモン自身の
テーブルと照合されています。

## その形

`[capabilities]` は、デーモンがあなたのプラグインに**呼び込める**ことを
述べます。`[permissions]` は、あなたのプラグインが**呼び出せる**ホスト
RPC を述べます。2 つの問い、2 つのセクション; ケーパビリティがパーミッション
を含意することは決してありません。

3 つの性質があり、いずれもいつか誰かを驚かせます。

1. **デフォルト拒否。** `[permissions]` セクションがなければ、ブートストラップ
   の 4 つを超えるホスト RPC はありません。
2. **宣言することは求めることであり、受け取ることではありません。** あなたの
   マニフェストは申請です。許可される集合は、プラグインがどこから来たかに
   基づいてデーモンによって解決され、インストールまたはインポートされた
   プラグインについては、プラグインが書き込めない場所に保存されます —
   マニフェストはあなたのプラグイン自身のディレクトリにあり、あなたの
   プラグインはそれを編集できます。**サイドロードはこれを逆転させます**:
   開発者モードでのソースディレクトリについては、マニフェストそのものが
   付与であり、読み込みのたびに再読み込みされ、上限はありません。これが
   作成用ループを機能させているものであり、また、サイドロードがインストール
   経路ではなく開発者向けツールである理由でもあります。
3. **未知の id は保持され、無効化されます。** 新しい id は新しい Astra と
   ともに出荷されるため、古いデーモンは、認識できないキーをあなたの
   マニフェストを拒否する代わりに保持します。それは何も付与しません。
   `astra-plugin check` は警告します — タイポはパース時には前方互換の
   id と見分けがつかないため、エラーではなく警告になり、`--strict` は
   それを失敗する終了コードに変えます。

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client, read_ai_settings, speak, read_user_identity, receive_attachments, request_settings_change, propose_commands
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Astra のインストール同意シートも、同じ id をその
   `permission.unrecognised` ラベルの下に表示します。そのため、入り口
   でも静かに落とされることはありません。

## 何も必要としない 4 つの呼び出し

| RPC | なぜ無償か |
|---|---|
| `Register` | ハンドシェイクです。まだパーミッションを持つプラグインは存在しません |
| `PluginLog` | 自分自身のログへの書き込みです |
| `GetPluginSelfConfig` | 自分自身の設定を読むことです |
| `GetDaemonInfo` | `version`、`state`、`grpc_port`、`language` — これらはすべて register のレスポンスがすでに渡しているものです |

`GetDaemonInfo` が無償であることは意思決定であり、見落としではありません:
何も守らないチェックボックスは、ユーザーがチェックボックスにチェックを
入れることを学習してしまう原因です。

## 14 個の id

| Id | ゲートする対象 | 専用チェックボックス | ローカルインポートで拒否される | 何ができるようになるか |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | なし | なし | ユーザーが保存した自動化を実行する |
| `subscribe_events` | `SubscribeEvents` | なし | なし | デーモンイベントを受信する — **`types` の許可リストを取ります** |
| `set_variable` | `SetVariable` | なし | なし | デーモンの変数コンテキストに、あなた専用の名前空間で書き込む |
| `send_chat_message` | `SendChatMessage` | **あり** | **あり** | ユーザーが話したかのように AI のターンを駆動する |
| `push_to_ui` | `PushToUi` | **あり** | なし | 自分自身のパネルにイベントを push する |
| `set_theme_contribution` | `SetThemeContribution` | **あり** | **あり** | アプリ全体のスタイルを変更する |
| `dom_access` | — (サーフェス) | **あり** | **あり** | 会話やすべての他プラグインのインターフェースへのアクセスを伴い、Astra ウィンドウ内であなたのコードを実行する |
| `client` | — (サーフェス) | **あり** | **あり** | 独自のセッションを持つチャットフロントエンドになる |
| `read_ai_settings` | `GetAiSettings` | なし | なし | ユーザーのチャットのプロバイダー、モデル、エンドポイントを読む(キーは含まない) |
| `speak` | `Speak`, `StopSpeaking` | **あり** | なし | 自分の言葉を Astra の声で読み上げ、それを止める |
| `read_user_identity` | `GetUserIdentity` | なし | なし | このインストールとサインイン中のアカウントの、自分のプラグイン専用に作られた仮名 ID を読む |
| `receive_attachments` | — (配送) | **あり** | なし | 求めるツールの中で、人が添付した画像を受け取る |
| `request_settings_change` | `RequestSettingsChange` | なし | なし | 本人が応答するカードで、アシスタントが変更できる設定の変更を頼む |
| `propose_commands` | `ProposeCommand` | **あり** | なし | 残してもらうコマンドを本人に提案する。本人はそれを Astra の Workshop のシートから残す |

`dom_access` と `client` はどの RPC もゲートしません。それがまさに
ポイントです: これらは**サーフェス**です。`dom_access` は、UI コントリビュー
ションが Astra ウィンドウ内のスクリプトとして描画されるか、サンドボックス
化された iframe として描画されるかを決めます; `client` は、プラグインが
何になれるかの上限です。これらは呼び出しのゲートではなく、そのサーフェス
が渡される場所で拒否されます。`receive_attachments` も RPC をゲートし
ませんが、向きが逆です: あなたが呼ぶものは何もありません。Astra があなたの
ツールに何を*送るか*を決めます — [後述](#人が添付した画像を受け取る)。

`dom_access` にはさらに 2 つ目の同意画面があります。これを使おうとして
いるなら、まず[セキュリティモデル](../1-orientation/security.md) を読み、
自分のパネルへの `push_to_ui` では足りないことを確認してください。

## 引数

2 つの id は引数を取り、どちらも得られるものを絞り込みます。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` は許可リストであり、デーモンによって強制
  されます** — あなたのプラグインが送るフィルタによってではありません。
  これがないと、`speech_recognized` を含む、すべてのイベントをすべての
  購読者が受信していました。`speech_recognized` はユーザーの書き起こし
  を運びます。空のリストは何も許可しません。
- **`set_variable.scopes`** は `"plugin"`、`"session"`、`"persistent"`
  のいずれかです。

## ユーザーの AI 設定を読む

ユーザーのモデルを自分で呼ぶプラグイン — 独自のアシスタントや要約ツール — は、ユーザーがどのプロバイダー、モデル、エンドポイントを選んだかを知る必要があります。**Astra に尋ねてください。Astra のファイルは決して読まないでください。** `read_ai_settings` を宣言し、`GetAiSettings`(Rust と Python では `get_ai_settings()`、TypeScript では `getAiSettings()`)を呼びます:

| フィールド | 内容 |
|---|---|
| `provider` | チャットのプロバイダー id。ユーザーが保存したエンドポイントは `openai_compatible`、Astra 自身のサービスは `astra` |
| `model` | チャットのモデル id |
| `api_base_url` | エンドポイント。userinfo、query、fragment は取り除かれ、パスは本人が設定したまま送られます(トークンをパスに入れるリレーなら、それがそのまま渡ります)。`astra` では空です。そのエンドポイントはあなたが呼ぶものではありません |
| `is_loopback` | エンドポイントがこのマシン上にある(`127.0.0.0/8`、`::1`、`localhost`) — ローカルモデル |

API キー、ユーザーが保存した他のエンドポイント、システムプロンプト、チャット以外のロールは決して含まれません。キーが必要なプラグインは、自分の `[config]` でユーザーに尋ねてください(シークレットとして印を付けます)。これは高リスクでもなく、ローカルインポートに対して拒否されることもありません: この情報への誠実な道であり、`settings.json` を読むより高く値付けすればプラグインを誤った方向へ押しやります。Astra 自身のファイルを読むことは、公開時の人間によるレビューが探すものです。この呼び出しより古い Astra は `UNIMPLEMENTED` を返します。

## Astra の声で話す

知らせたいことがあるプラグイン — タイマー、終わったビルド、届いたメッセージ — は、それを Astra に言わせることができます。`speak` を宣言し、`Speak`(Rust と Python では `speak(text)`、TypeScript では `ctx.speak(text)`)を呼びます。

`speak` は**高リスク**です: あなたの言葉は Astra の声で、まるで Astra が言ったかのように聞こえるため、専用の同意チェックボックスを持ちます。ローカルインポートに対して拒否されることはありません — アナウンスはプラグインが望むごく普通のことであり、チェックボックスがその判断です。許可に加えて、`Speak` には **Astra を利用できるアカウント**と、**本人の応答音声がオンであること**が必要です。Astra がロックされている間は拒否されます。

呼び出しは発話が続く間だけ続き、それがどうなったかを返します:

| 結果 | 意味 | どうするか |
|---|---|---|
| `SPOKEN` | 聞き届けられた | 何もしない |
| `STOPPED` | 終わる前に静かにするよう求められた: ウェイクワード、応答音声のオフ、停止、あなた自身の `StopSpeaking` | 何もしない — **エラーではありません**。頼まれていないのにもう一度言わないでください |
| `NOT_SPOKEN` | 言われなかった。`error`(チャットのチャンクが運ぶのと同じ `PluginError`)が理由を示す | 下のコードを読んでください。拒否されたものはキューに入りません |

| `error.code` | いつ |
|---|---|
| `PLUGIN_ERROR_BAD_ARGUMENTS` | 不可視文字を取り除くとテキストが空になる、または **300 文字**(`spec/limits.yaml` の `speak_text_max_chars`)より長い。長いテキストは拒否され、切り詰められることはありません |
| `PLUGIN_ERROR_RATE_LIMITED` | 発話時間を使い切った。文字数で割り当てられます — **一度に 450、その後は毎秒 3**、1 回の呼び出しは最低 20 — そして `retry_after_ms` が、いつまた余裕ができるかを示します |
| `PLUGIN_ERROR_UNAVAILABLE` | 本人が Astra の音声をオフにした、Astra がロックされている、音声がない、または発話キューが受け付けられなかった。代わりにテキストを表示してください。本人に設定を変えるよう求めないでください |

あなたの言葉は、あなた自身の以前の言葉の後ろに、専用のレーンで並ぶので、Astra の応答を遮ることはありません。`StopSpeaking` は、あなたが言わせようとしたもの — 鳴っているものもキューにあるものも — をすべて止め、それ以外は何も止めません。`speak` パーミッションを共有し、誰かがサインインしているかどうかに関係なく動作します。上限はデーモンのものです: SDK はカウンターを表示できるよう `SPEAK_TEXT_MAX_CHARS` をエクスポートしますが、自分では何もチェックしません。この呼び出しより古い Astra は `UNIMPLEMENTED` を返します。

## 誰が Astra を使っているかを知る

人やマシンごとに利用を制限するプラグイン — 試用期間、クォータ、ライセンス — には、それぞれの安定した id が必要です。**Astra に尋ねてください。ハードウェアのシリアル番号や Astra のファイルは決して読まないでください。** `read_user_identity` を宣言し、`GetUserIdentity`(Rust と Python では `get_user_identity()`、TypeScript では `ctx.getUserIdentity()`)を呼びます:

| フィールド | 内容 |
|---|---|
| `install_id` | この Astra のインストール。Astra とあなたのプラグインの再起動やアップデートをまたいで同じで、別のインストールでは異なる。Astra にまだインストールキーがない間は空 |
| `signed_in` | 誰かが Astra にサインインしている |
| `authorized` | …そしてそのアカウントで Astra を利用できる |
| `account_id` | サインイン中のアカウント。本人がサインインするどのデバイスでも同じ。`authorized` でなければ空 |

どちらの id も**あなたのプラグイン専用に作られた仮名**です: 別のプラグインは同じ人、同じマシンに対して異なる id を読むので、2 つのプラグインがそれを使って記録を突き合わせることはできません。これはこの API を誠実に使うプラグインに対して成り立つことです: プラグインのネイティブコードは Astra のファイルを読めます。どちらも秘密ではなく、アカウント自身の id、本人の名前やメールアドレス、ハードウェアのシリアル番号であることも決してありません。高リスクではなく、ローカルインポートに対して拒否されることもありません: マシンのシリアル番号に代わる誠実な手段であり、高く値付けすればプラグインをそこへ押し戻してしまいます。この呼び出しより古い Astra は `UNIMPLEMENTED` を返します。

**`auth_changed` もそれに合わせて絞られました**(Astra、2026-11-12)。`auth_changed` イベントを許可されたプラグインは、以前はアカウント自身の id、本人の表示名、そのプランを受け取っていました。今は `authenticated`、`authorized`、`timestamp`、`account_id` を受け取ります — `GetUserIdentity` が返すのと同じ仮名で、あなたが `read_user_identity` を持ち、かつアカウントで Astra を利用できる場合を除いて `""` です。`user_id` と `user_name` は引き続き `null` として、`subscription_tier` は `""` として届くので、古い形式向けに書かれたパーサーはそのまま解析できます。どれももう値を運びません。

## 人が添付した画像を受け取る

画像を扱うツール — レシートを読む、植物の名前を調べる、写真を説明する — は、Astra が応答しているメッセージに人が添付した画像を求めることができます。**これを行う Astra のリリースはまだありません:** デーモンは `plugin-provider-slots` ビルドフィーチャー付きでビルドされたときにだけ画像を送ります。それ以外の Astra はこの要求を無視し、ツールは画像を受け取りません。

必要なことは 2 つです。`[permissions]` で `receive_attachments` を宣言し、画像を必要とする各ツールに印を付けます。そのうえで、ハンドラーの中で画像を読みます:

| SDK | ツールに印を付ける | 画像を読む |
|---|---|---|
| Rust | `#[tool(wants_attachments)]`、または `ToolDef::new(…).with_attachments(true)` | `ctx.attachments()` |
| Python | `@tool("…", wants_attachments=True)`、または `ToolDef(…, wants_attachments=True)` | `current_attachments()` |
| TypeScript | `tool({…})` または `ToolDef` に `wantsAttachments: true` | `ctx.attachments`、または `currentAttachments()` |

各画像は `mime_type` (TypeScript では `mimeType`)、`data` (バイト列)、`filename` (添付されたときの名前だけで、フォルダーは決して含みません) を持ちます。求めていないツールは空のリストを読み、画像を運ばない呼び出しも同じです。

Astra が呼び出しに画像を渡すのは、次のすべてが成り立つときだけです:

- ツールが `ListTools` の応答で `wants_attachments` を宣言している;
- あなたのプラグインが `receive_attachments` を持っている;
- 呼び出しが、人が会話の中で送ったメッセージに応答する途中で行われた — 呼び出しの invocation がその会話を示します。レポートのウェイク、コマンドの AI ステップ、サブエージェントのターンでは決して渡されず、人が承認していない Workshop のコマンドのために Astra がターンを保留している間も渡されません。

届くのは**その 1 つのメッセージ**に添付されたものだけです: 会話の前のほうの画像も、ツールが生成した画像も、モデルが名指しした画像も決して届きません。最大 **4** 枚 (`spec/limits.yaml` の `image_input_max_images`)、合計 20 MiB まで、新しいものが残り、添付された順に並びます; 読めない画像は決して送られません。送られなかったものがあるとき — 収まりきらなかった、またはプラグインに許可がない — は、あなたの結果のあとで**モデル**にそのことが伝えられます; ツールは単に少なく受け取るか、まったく受け取らないだけです。

現在、Astra のチャット入力欄は添付された画像をすべて最大 768 ピクセルに縮小し、元のファイル名を保ったまま JPEG として再エンコードするので、ツールが受け取るのはそれです。`filename` の拡張子ではなく `mime_type` に従ってください。

1 回の呼び出しは最大 20 MiB の画像を運ぶことがあり、これは gRPC の既定の受信上限 4 MiB を超えます。3 つの SDK の capability サーバーは最大 64 MiB (`plugin_max_message_bytes`) まで受信します; SDK を使わずにプロトコルを実装するプラグインは、自分のサーバーの受信上限を 4 MiB より大きくする必要があります。

`receive_attachments` は**高リスク**です: 人の写真が Astra のものではないコードに届くため、独自の同意チェックボックスを持ちます。ローカルインポートでは拒否されません — `speak` と同じく、チェックボックスが判断です。

## 設定の変更を本人に頼む

Astra の設定のどれかを変えてほしい本当の理由がある — ツールの調整先のモデル、そのプラグインに合う声 — プラグインは、それを**頼み**、本人がカードで決めます。Astra の `settings.json` を自分で書き換えてはいけませんし、そのために Astra 自身のセッションを借りてもいけません: 本人の知らないところで本人の Astra を変えることになり、公開時の人によるレビューはまさにそれを探します。`request_settings_change` を宣言し、`RequestSettingsChange` を呼び出します(Rust と Python では `request_settings_change(changes, reason)`、TypeScript では `ctx.requestSettingsChange(changes, reason)`)。**まだどの Astra リリースもこれに応えません。** `plugin-requests` ビルド機能付きでビルドされた Astra はリクエストを受け付けます。それなしでビルドされた新しい Astra はコード `not_compiled` の `REFUSED` を返し、古い Astra — 今日のすべてのリリース — では呼び出しが `UNIMPLEMENTED` で失敗します。これはエラーであり、結果ではありません。

各変更は、ドット区切りの設定パスと、望む値を JSON にしたものです — 値は SDK が JSON にしてくれます。頼めるのはアシスタント自身が変更できる設定だけ — 声、AI モデル、言語。パーミッションモード、キー、Tool Search は決して頼めません — で、各値はアシスタント自身の変更とまったく同じように検査されます。カードはあなたのプラグインの名前、各設定の今の値と変更後の値、そしてあなたの言葉での `reason` を見せます。すべて変わるか、何も変わらないかのどちらかで、変わるのはカードが見せたものそのものです。

**呼び出しは、本人が応答するかカードが期限切れになるまで続きます** — Astra の確認タイムアウトで、最短 30 秒、本人が変えていなければ 120 秒。SDK は独自の期限を付けません。モデルが待っているツール呼び出しのような、すぐに応答しなければならない経路では決して await しないでください。

| 結果 | 意味 | どうするか |
|---|---|---|
| `APPLIED` | 本人が許可した。設定は今、頼んだ値になっている | 何もしない |
| `UNCHANGED` | すでにその値だった。誰にも尋ねていない | 何もしない |
| `DECLINED` | 本人が断った — 今、または以前に、あなたのプラグインがこれらの設定のどれかを変えることを。Astra がそうした設定について再び尋ねるのは、それが別の方法で変わった後か、再起動の後だけ | 本人の今の設定のまま続ける。**頼まれもしないのに再び尋ねない** |
| `TIMED_OUT` | カードが期限切れになる前に誰も応答しなかった(ウィンドウが 1 つも開いていなかった場合も含む) | 本人がいるときに、後で尋ねる |
| `REFUSED` | 尋ねなかった、または適用しなかった: `code` が理由を、`refused_path` が関係する設定(あれば)を示し、`error` は `PluginError` | 下のコードを読む |

| `code` | いつ |
|---|---|
| `not_compiled` | この Astra はリクエストを受け付けない: `plugin-requests` 機能なしでビルドされた |
| `locked` | Astra がパスコードでロックされている |
| `invalid` | 変更がない、同じパスが 2 回、JSON でない値、またはカードに全体を表示できないほど多い |
| `too_many` | **8** 件を超える変更(`spec/limits.yaml` の `settings_change_max_changes`) |
| `reason_too_long` | **140 文字**を超える理由(`settings_change_reason_max_chars`)。全体が表示されるので、切り詰められずに拒否される |
| `busy` | あなたのリクエストの 1 つがすでに本人を待っている: カードはプラグインごとに同時に 1 枚 |
| `rate_limited` | **まとめて 2 件まで、その後は 2 分に 1 件**。`error.retry_after_ms` が次に空く時を示す |
| `not_assistant_editable` | アシスタントが変更できないパス |
| `invalid_value`, `unknown_choice` | その設定が持てない値、または設定が提供していない選択肢 |
| `needs_api_key`, `needs_stt_provider`, `provider_unreachable` | 変更すると Astra に必要なものがなくなる: その AI プロバイダーのキー、音声認識、応答するプロバイダー |
| `stale` | カードが出ている間に設定が変わったので、本人が許可したものと書き込まれるものが一致しない。何も書き込まれていない |
| `stopped` | あなたのプラグインの権限が先に終わった — 停止された、無効にされた、取り下げられた、またはアカウントが Astra を利用できなくなった |
| `write_refused` | 設定を書き込めなかった |

現在の値は決して返されません: プラグインが知るのは結果だけです。上限はデーモンのものです: SDK は `SETTINGS_CHANGE_MAX_CHANGES` と `SETTINGS_CHANGE_REASON_MAX_CHARS` をエクスポートしますが、自分ではどちらも検査しません。許可に加えて、呼び出しには **Astra を利用できるアカウント** が必要です。許可がない、またはアカウントが Astra を利用できない場合は、他のホスト呼び出しと同じく失敗した呼び出しになり、結果ではありません。高リスクではなく、ローカルインポートでも拒否されません: リクエストのたびに本人が応答するカードが出るので、同意は毎回求められます。この呼び出しより古い Astra は `UNIMPLEMENTED` を返します。

## コマンドを本人に提案する

役に立つ自動化を渡せるプラグイン — 自分のアクションで組んだ「おはようと言ったらニュースを読み上げて」のようなもの — は、それを**提案し**、本人が決めます。プラグインが本人のコマンドライブラリを自分で書き込むことはできません: `CommandService` はプラグインのセッションには閉じられており、この呼び出しができる前は、プラグインはチャットでコマンドを説明し、本人が組み直してくれることを願うしかありませんでした。`propose_commands` を宣言し、`ProposeCommand` を呼び出します(Rust と Python では `propose_command(key, command, reason)`、TypeScript では `ctx.proposeCommand(key, command, reason)`)。**まだどの Astra リリースもこれに応えません。** `plugin-requests` ビルド機能付きでビルドされた Astra は提案を受け付けます。それなしでビルドされた新しい Astra はコード `not_compiled` の `REFUSED` を返し、古い Astra — 今日のすべてのリリース — では呼び出しが `UNIMPLEMENTED` で失敗します。これはエラーであり、結果ではありません。

コマンドは **1 つのポータブルなコマンド** — `.astra` ファイルの `commands[]` に入っているもの — です。いちばん簡単な作り方は、Astra で組み立て、コマンドのページからエクスポートし、そのファイルをプラグインと一緒に配ることです。どの SDK にも、そうしたファイルをコマンドごとに分けるヘルパーがあります(Rust と Python では `commands_from_astra_file`、TypeScript では `commandsFromAstraFile`)。分けられた各コマンドからは、1 つのインストールに属するフィールド(`id`、`enabled`、フォルダー、出所)が取り除かれます。デーモンはコマンドを Workshop 自身のリーダーで読みます — 厳密な JSON、既知のアクションとトリガーの型だけ、そうしたローカルなフィールドは捨てられるので、プラグインはコマンドの出所を偽ることも、コマンドを有効にすることもできません — そしてコマンドが使えるのは Astra の組み込みのアクションとトリガー、そして**あなたのプラグイン自身の**ものだけで、他のプラグインのものは決して使えません(`foreign_plugin`)。組み込みのものにはシェルコマンド、キー入力、ファイル操作も含まれます: シートはすべての手順をそれができることと共に見せ、本人が同意するのはそれです。

`key` は、そのコマンドに対するあなたのプラグイン自身の名前です: `a-z`、`A-Z`、`0-9`、`.`、`_`、`-` の 1〜64 文字。同じキーをもう一度提案すると同じコマンドで、本人が再び同意すればその場で更新されます — id とフォルダーはそのまま。そのキーで既に残されているまさにそのコマンドを提案しても誰にも尋ねません(`UNCHANGED`)。

Astra が覚えていることは見た目より狭いので、起動のたびにすべてのコマンドをそのまま提案しないでください:

- `DECLINED` が覚えられているのは Astra が再起動するまでだけ — その後は同じ提案が再びカードになる;
- 本人が削除したコマンドはもうそのキーの下にないので、もう一度提案すると新しい提案になる — 再びカード;
- あなたのプラグインがアンインストールされたときに無効にされたコマンドは、再インストール後も無効のままで、同じ提案には `UNCHANGED` が返る;
- `UNCHANGED` はあなたの提案を、そのキーで提案され残されたものと比べるので、本人が残されたコマンドを編集した後もその答えになる。

`SAVED` と `DECLINED` をキーごとにプラグイン自身の状態に記録し、起動時には答えのないキー — と、あなたが変更したコマンド — だけを提案してください。

本人には、あなたのプラグインとコマンドの名前、あなたの言葉での `reason`、そして「確認」と「拒否」の 2 つの選択肢があるカードが見えます。**コマンドが残されるのは Astra の Workshop のシートからだけです** — すべてのトリガーを完全な値で、すべての手順をそれができることと共に見せ、有効にするスイッチがあります — 単なる「許可」で残されることは決してなく、残されるのはシートが見せたものそのものです。残されたコマンドにはあなたのプラグインの印が付き、あなたのプラグインをアンインストールするとそのコマンドは無効になります。

**呼び出しは、本人が応答するかカードが期限切れになるまで続きます** — Astra の確認タイムアウトで、最短 30 秒、本人が変えていなければ 120 秒。SDK は独自の期限を付けません。すぐに応答しなければならない経路では決して await せず、**コマンドは 1 つずつ提案してください**: あなたの提案の 1 つが待っている間の 2 つ目の提案は、`UNCHANGED` になるはずのものでも `busy` として拒否されます。

| 結果 | 意味 | どうするか |
|---|---|---|
| `SAVED` | 本人が残した。`enabled` は残された後にコマンドが有効かどうかを示す(Astra が無効のまま残すこともある) | 記録する |
| `UNCHANGED` | このキーで残されているものは、まさにこの提案から来たもの — 本人が編集した後も同じ。誰にも尋ねていない | 何もしない |
| `DECLINED` | 本人が断った — 今、または以前にまさにこのコマンドを(Astra が再起動するまで) | 記録する。**頼まれもしないのに再び提案しない** |
| `TIMED_OUT` | カードが期限切れになる前に誰も応答しなかった(ウィンドウが 1 つも開いていなかった場合も含む) | 本人がいるときに、後で提案する |
| `REFUSED` | 尋ねなかった、または残さなかった: `code` が理由を示し、`error` は `PluginError` | 下のコードを読む |

| `code` | いつ |
|---|---|
| `not_compiled` | この Astra は提案を受け付けない: `plugin-requests` 機能なしでビルドされた |
| `locked` | Astra がパスコードでロックされている |
| `invalid_key` | `a-z`、`A-Z`、`0-9`、`.`、`_`、`-` の 1〜64 文字ではないキー |
| `reason_too_long` | **140 文字**を超える理由(`spec/limits.yaml` の `propose_command_reason_max_chars`)。全体が表示されるので、切り詰められずに拒否される |
| `too_large` | **1 MiB** を超える JSON(`propose_command_max_bytes`)。Workshop のコマンド自身の上限 |
| `invalid_command` | Workshop のリーダーが受け付けるコマンドではない。`error.message` はたいていそのリーダー自身のコードで始まる — `E_COMMAND_FORMAT`、`E_COMMAND_UNKNOWN_ACTION`、… — が、カード自体を表示できないとき(コマンドの名前とあなたの理由がカードに収まらないとき)はそうではない |
| `foreign_plugin` | コマンドが他のプラグインのアクションかトリガーを使っている |
| `busy` | あなたの提案の 1 つがすでに本人を待っている: カードはプラグインごとに同時に 1 枚 |
| `rate_limited` | **まとめて 2 件まで、その後は 2 分に 1 件**。`error.retry_after_ms` が次に空く時を示す。誰にも尋ねない提案(`UNCHANGED`、覚えられている `DECLINED`)は何も消費しない |
| `stopped` | あなたのプラグインの権限が先に終わった — 停止された、無効にされた、取り下げられた、またはアカウントが Astra を利用できなくなった |
| `stale` | 更新対象のコマンドが、カードが出ている間に変わったか消えたので、本人が見たものと書き込まれるものが一致しない。何も書き込まれていない |
| `write_refused` | コマンドを保存できなかった |

上限はデーモンのものです: SDK は `PROPOSE_COMMAND_MAX_BYTES` と `PROPOSE_COMMAND_REASON_MAX_CHARS` をエクスポートしますが、自分ではどちらも検査しません。許可に加えて、呼び出しには **Astra を利用できるアカウント** が必要です。許可がない、またはアカウントが Astra を利用できない場合は、他のホスト呼び出しと同じく失敗した呼び出しになり、結果ではありません。`propose_commands` は**高リスク**です — 残されたコマンドは後で、そのトリガーによって、本人自身のコマンドとして実行され、その手順はシェルコマンドのような組み込みのものも含めて改めて尋ねることなく実行されます — ので、専用の同意チェックボックスを持ちます。ローカルインポートでは拒否されません: 毎回のシートそのものが決定だからです。この呼び出しより古い Astra は `UNIMPLEMENTED` を返します。

## reason を書く

`reason` は Astra 自身のパーミッションのラベルの下に、視覚的に従属する
形で、引用符付き、プレーンテキストで、140 文字を上限に描画され、常に
*「The author says:」* というプレフィックスが付きます。ラベルは Astra の
ものであり、ユーザーの言語で書かれています; reason はあなたのものです。
ラベルはあなたが作れません。これは意図的なものです — 文言の修正は Astra
とともに出荷されるべきであり、リスト掲載によって書き換え可能であっては
いけません。

良い reason とは:

- API ではなく**ユーザーが認識できる機能を名指しする** — 「calls
  FireTrigger」ではなく「Fires the on_dice_roll trigger you configure」
- 常にではない場合は**いつなのかを言う** — 「only while a recording is
  in progress」
- **ラベルを繰り返さない。** Astra がすでに描画しています
- **押し付けない。** 緊急性なし、脅しなし、ユーザーへの指示なし。同意
  シートは例外を作るのに最も適さない場所であり、bidi オーバーライドや
  ゼロ幅接合子を含むテキストは、それがそのまま表示される場所では拒否
  されます。

| これの代わりに | こう書く |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — パーミッションを削除するか、それが何のためかを言ってください |

もっともらしい理由のないパーミッションは、マニフェストから削除すべき
パーミッションです。これを自動でチェックするものは何もありません。
あなたのリスト掲載を読む人だけが唯一の防波堤であり、`astra-plugin
check` は、あなたのケーパビリティが必要としないパーミッションを宣言
したときにそれを教えてくれます。

## パーミッションが欠けているとどうなるか

呼び出しは `permission_denied` として返ってきます。メッセージには
パーミッションの名前**と**許可された集合がどこから来たかが記されて
います。テストでは、まさにそれを仕込むことができます。

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

`astra-plugin doctor` は、あなたが実際に実行する前に、マニフェストに
ついて同じ問いに答えます。

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## 許可される集合はどこから来るか

| インストール経路 | 許可されるもの |
|---|---|
| ストアから、検証済み | 同意の後、マニフェストが要求したもの |
| 手動でインポートされた `.astraplugin` ファイル | マニフェスト、ただし**上限あり**: `send_chat_message`、`set_theme_contribution`、`dom_access`、`client` は無条件で拒否 |
| サイドロードされたソースディレクトリ、開発者モード有効 | マニフェスト、上限なし |
| `Untrusted` / `TamperDetected` / `Revoked` | なし |
| 信頼レコードが存在する前にインストールされたもの | マニフェスト、インポートされたファイルとして上限あり |

完全な表とその根拠: [`spec/permissions.md` §4](../spec/permissions.md)。

## 同意、ユーザー側の視点から

パーミッションはリスクによってグループ化されています。8 つの高リスクな
ものはそれぞれ独自のチェックボックスを持ち、そのすべてにチェックが入る
までインストールは無効のままです; `dom_access` には 2 つ目の画面が
あります。意図的に**タイプして確認**というパターンは**ありません**: それは
取り返しのつかない破壊のためのパターンであり、ユーザーをそれを打ち込んで
通り抜けることに慣れさせることは、チェックボックスが運ぶシグナルを破壊
します。

更新時: パーミッションが変わらないか狭まった場合は静かに適用されます;
パーミッションが**広がった**場合は、更新はインストールされないまま
ステージされ、ユーザーが差分をレビューするまで古いバージョンが動作を
続けます。拒否することのコストはゼロです。
