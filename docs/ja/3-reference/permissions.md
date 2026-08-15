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

   <!-- doctest: output from="astra-plugin check --strict ." -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
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

## 8 つの id

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

`dom_access` と `client` はどの RPC もゲートしません。それがまさに
ポイントです: これらは**サーフェス**です。`dom_access` は、UI コントリビュー
ションが Astra ウィンドウ内のスクリプトとして描画されるか、サンドボックス
化された iframe として描画されるかを決めます; `client` は、プラグインが
何になれるかの上限です。これらは呼び出しのゲートではなく、そのサーフェス
が渡される場所で拒否されます。

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

<!-- doctest: output from="astra-plugin doctor ." -->
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

パーミッションはリスクによってグループ化されています。5 つの高リスクな
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
