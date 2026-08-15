> **これは翻訳です。** 正式な情報源は [docs/en](../../en/4-sdk/rust.md) です。内容に食い違いがある場合は英語版が優先されます。

# Rust SDK

`astra-plugin-sdk` 0.6.0。依存は 1 つだけで、マクロが展開するものは
すべてこれを経由してきます。

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 は、`HostClient` が `x-session-token` を付加する最初のリリースです。
0.5 以前に対しては、デーモンはすべてのホスト呼び出しに `unauthenticated`
を返すため、この下限を緩めないでください。

## プラグインの形

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` は、見つけたフックから `PluginCapability` を実装し、
そこから宣言済みのケーパビリティ集合を導出します — そのため、プラグインが
自分のコードが提供していないケーパビリティを名乗ることはできません。
`astra-plugin check` はこれを `plugin.toml` と比較します。

## マクロの層

| | 何のためのものか |
|---|---|
| `#[astra::plugin]` | `impl` ブロックに付けます。以下のメンバをトレイトに変換します |
| `#[tool]` | モデルが呼び出せる関数です。doc コメントがその説明になります |
| `#[action(label = "…")]` | コマンドエディタ内のステップです |
| `#[hook]` | 名前で判別されるその他の `PluginCapability` メソッドです |
| `#[ui_call]` | あなたの UI コントリビューションがコールバックできるメソッドです |
| `#[astra::args]` | ツールの引数構造体に付けます |
| `#[astra::config]` | あなたの設定構造体に付けます — `args` に加えて `#[serde(default)]` |
| `astra::main!(Plugin::default())` | これを実行する `main` です |

**なぜ `#[derive(Deserialize, JsonSchema)]` ではなく `#[astra::args]`
なのか:** serde の derive は `extern crate serde as _serde` に展開
され、これは extern prelude で解決されるため、re-export 経由では到達
できません。したがって、素の derive を使うには、あなた自身の
`Cargo.toml` に `serde` が必要になり、それこそが「依存 1 つ」という
約束の対象です。`#[astra::args]` は、SDK 自身のコピーを指す
`crate = "…"` を伴った、その 2 つの derive です。自分で `serde` を
追加しても引き続き動作します; その場合は `use serde::Deserialize;` が
prelude の名前をシャドウします。

`PluginCapability` を手で実装することもできます。このトレイトは
public であり、すべてのメソッドにデフォルト実装があり、マクロはあなたが
手で書くのとまったく同じものを生成します。

## `PluginContext`

すべてのハンドラには `&PluginContext` が渡されます。これは決して
`None` にならず、バックグラウンドタスクへのクローンのコストは低く、
ロックの背後に何かをあなたの構造体上に持つ必要がないことを意味します。

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — 10 個のホスト RPC。常に存在します |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **`client` プラグインに対してのみ `Some`** |
| `ctx.language()` | Astra UI の言語、`OnLanguageChanged` によって更新されます |
| `ctx.active_triggers()` | あなたのトリガー種別のうち、あるコマンドが現在listenしているもの |
| `ctx.plugin_id()` | あなたの id |

パラメータが届かない場所 — `Drop` の実装、C ライブラリからのコールバック、
起動時に spawn された `std::thread` — からは、`astra_plugin_sdk::ctx()`
が動作中のプラグインのコンテキストを返し、`try_ctx()` はその失敗可能な
バージョンです。

### `Host` — 10 個の外向き呼び出し

| メソッド | パーミッション |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | なし |
| `get_config` | なし |
| `get_daemon_info` | なし |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` は**3 つ**の引数 — 名前、値、スコープ — を取ります。
イベント購読は `Host` にはありません: `subscribed_events()` を宣言する
と、ランナーがストリームを所有します(下記)。

`Host` はトレイトなので、テストでは `RecordingHost` に差し替えて、
あなたのプラグインが Astra に何を伝えたかをアサートできます。

### `Daemon` — SDK には存在するが、デーモンには拒否される

> **`ctx.daemon()` は今日、どのプラグインに対しても機能しません。**
> デーモン側の半分がまだ整っていません。すべてのプラグイン —
> `client = true` であろうとなかろうと — は `ClientType::PluginClient`
> として登録され、デーモンの認証インターセプターは `/astra.PluginHostService/`
> で始まらない**あらゆる**パスでこのアイデンティティを
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")` で拒否します。`DaemonClient` はまさにそのトークン
> で接続するため(`astra-plugin-sdk/src/host_client.rs` は
> `client_session_token` を `DaemonClient::connect` に渡します)、以下の
> 呼び出しはすべて — `submit_user_message`、`subscribe_chat_events`、
> `speak`、`get_settings` — 実行時に `permission_denied` を返します。
> デーモンの `consistency.rs` にあるカナリアがこのスコープ制限を維持
> しているため、これは意図的なものであり、リグレッションではありません:
> 逆方向の認証の半分がまだ構築されていないのであって、壊れているのでは
> ありません。
>
> **`Host::send_chat_message` だけが AI のターンを駆動する動作する
> 方法です**。そしてこれは `send_chat_message` を許可されたどんな
> プラグインでも機能します。

デーモン側が実装されたときのための API サーフェス: `ctx.daemon()` は、
プラグインが `client = true` を宣言し、`is_client()` が true を返す
場合にのみ `Some` になります。これは、core、chat、voice、command、
config、media、monitor の 7 つのサービスに到達し、
`submit_user_message`、`subscribe_chat_events`、`stop_generation`、
`list_conversations`、`speak`、`start_listening`、`execute_command`、
`get_settings`、`get_system_stats` を含むメソッドを持ちます。
`send_message` ではなく `submit_user_message` です。

## エラー

ハンドラは `Result<_, ToolError>` を返します(`ActionError` は同じ型の
エイリアスです)。呼び出しごとの失敗は、AI ループが読み取って行動する
データであるため、gRPC ステータスとしてではなく、レスポンス内を伝わって
いきます。

| バリアント | 使うべきとき |
|---|---|
| `BadArguments(String)` | モデルが別の呼び出し方をすることでこれを直せる場合 |
| `NotFound(String)` | 未知の id、404 |
| `NotConfigured { field, message }` | 設定が欠けている。`field` はディープリンクの対象です |
| `Unauthorized(String)` | 資格情報が拒否された、またはパーミッションが許可されていない |
| `RateLimited { retry_after, message }` | 上流のクォータ。`None` は「不明」を意味し、「即座に」ではありません |
| `Unavailable(String)` | 依存先が落ちている。変更なしで後で再試行してください |
| `Timeout(String)` | 時間切れになった |
| `Internal(String)` | バグです。モデルにできることは何もありません |

`?` は `serde_json::Error`、`std::io::Error`、`tonic::Status`、
`anyhow::Error` に対して機能します。`with_doc_url(…)` はこれらのいずれ
かを、*その*失敗を説明するページで包み、UI はそれをリンクとして描画
します。

wire 上の文字列と Python/TypeScript での綴りを含む完全な分類は
[`reference/errors.md`](../reference/errors.md) にあります。

## イベント

欲しいものを宣言してください。ランナーが購読し、再接続し、ディスパッチ
します。

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

今日型付けされているイベント: `StateChangedEvent`、
`CommandTriggeredEvent`、`CommandCompletedEvent`。チャットイベントは
別のストリームです — `on_conversation_event` で、デーモンのファイア
ホースから供給され、`client` プラグイン向けです。

`on_chat_sync` / `ChatSyncEvent` は存在しません。このイベントは廃止され、
どの SDK にもそのメソッドはありません; それを使っていたコードを移植して
いる場合は、`is_client()` と `on_conversation_event` を使ってください。

## テスト

2 つのレベルがあり、どちらも SDK に同梱されているため、あなたの
`Cargo.toml` は 1 行のままです。

| | 何を駆動するか | 何が見えるか |
|---|---|---|
| `testing::Harness` | フックを、インプロセスで、`RecordingHost` に対して | ツール、アクション、トリガー、設定、イベント、UI 呼び出し、あなたが行ったすべてのホスト呼び出し |
| `testing::WireHarness` | 実際のプロセスを、デーモンが起動するのと同じ方法で | 登録、セッショントークン、ストリーミングオーディオ、ワイヤーでしか見えないもの |

`RecordingHost` は `fired_triggers()`、`logs()`、`variables()`、
`ui_pushes()`、`chat_messages()` を提供し、加えて `deny(rpc)`、
`fail(rpc, err)`、`fail_next(rpc, err)` で、あなたのユーザーが遭遇する
であろう失敗を仕込むことができます。

そして両方の上に立つもう 1 つのレベル: `astra-plugin test` は、あなたが
ビルドしたバイナリをモックデーモンに対して起動し、あなたのケーパビリティ
が含意するすべてのフックを駆動します。これはどの言語でプラグインが書か
れたかを気にしません。

## この SDK がまだできないこと

- **`ctx.daemon()` / `DaemonClient` は機能しません。** デーモンはすべて
  のプラグインのセッショントークンを `PluginHostService` にスコープして
  いるため、7 つのサービスすべてが — `client = true` のプラグインで
  あっても — `permission_denied` を返します。`Host::send_chat_message`
  を使ってください。上の
  [`Daemon`](#daemon--sdk-には存在するがデーモンには拒否される) を
  参照してください。
- **`TtsSynthesizeStream` は結びつけられていますが unrouted です。**
  SDK はこれを提供しますが、デーモン側の呼び出し箇所は存在しません。
  好きなら実装してもかまいません — [パリティ表](../reference/parity.md)
  が `live` と言うまで、誰もそれを呼び出しません。
- **`AiGetModels` は非推奨で**(0.6、0.8 で削除)、誰も呼び出していません:
  モデルピッカーは `supports_model_discovery = false` をハードコード
  しています。代替はありません; `AiComplete` はリクエストに選択済みの
  モデルを載せます。
- **0.5 のトレイト表面は `astra_plugin_sdk::compat` として存続して
  います**。0.6 で非推奨、0.8 で削除です。
  [0.6 への移行](../migration-0.6.md) を参照してください。
- **`PluginCapability::source_id()`** は非推奨です: id を
  `Host::send_chat_message` に渡してください。デーモンは source id に
  よるフィルタリングをやめました。
- **ケーパビリティサーバーの受信側認証は設定を必要としません。**
  デーモンはすべての呼び出しで `x-plugin-token` を提示し、
  `ASTRA_PLUGIN_CAPABILITY_AUTH=require` を設定するため、SDK はそれの
  ない呼び出しを拒否します。ヘッダーを送るには古すぎるデーモンだけが
  あなたを `warn` 段階に留めます; 詳しくは
  [アーキテクチャ](../1-orientation/architecture.md) を参照してください。

## 関連ページ

[Rust のフック表](../hooks/rust.md) · [パリティ](../reference/parity.md) ·
[エラー](../reference/errors.md) ·
[バージョニングと非推奨ポリシー](../versioning.md)
