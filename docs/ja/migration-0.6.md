> **これは翻訳です。** 正式な情報源は [docs/en](../en/migration-0.6.md) です。内容に食い違いがある場合は英語版が優先されます。

# プラグインを 0.6 系 SDK に移行する

動作している 0.5 系のプラグインを持っている人向けです。問題に出会う順番どおりに
並んでいます。**1 行も変更していないのに実行時に壊れるもの**、次にコンパイル時に
壊れるもの、次にコンパイルは通るが挙動が変わるもの、最後に警告が出るだけのもの、
という順です。

リリーストレインは `sdk-v0.6.0` です。Rust クレートは 0.6.0 に、Python と
TypeScript のパッケージは 0.5.0 になります。番号がなぜ異なるかは
[versioning.md](versioning.md) を参照してください。

以下のスニペットはすべてこのリポジトリの実際のコードです — 9 つの Rust の
サンプルはコミット `134f6d1` で 0.6 に移植されたので、すべての差分の両側が
git 上に存在し、そこから引用しています。

---

## 0. なぜ今のままではいられないか

これは「素敵な新 API が出ました」というだけのリリースではありません。
**0.5 プラグインは、何も変更していない時点ですでに現在のデーモンに対して
壊れています**。

> 0.5 の `HostClient` は `x-session-token` を送信せず、デーモンは `Register`
> 以外のすべてのホスト RPC に対して `unauthenticated` を返します。

そのため `fire_trigger`、`set_variable`、`log`、`push_to_ui` などは、あなたの
ものではないマシン上で、ユーザーには「プラグインが壊れている」としか読めない
メッセージとともに実行時に失敗します。登録(Registration)自体は成功して
しまうため、これが混乱を招きます。プラグインは起動しているように見えて、
実は何もしていないのです。

これが 0.6 が存在する理由のすべてであり、同じリリースで作成用 API の変更が
許された理由です。

---

## 1. 近道(Rust): 1 行変えるだけでビルドが通る

今日プラグインを動かす必要があり、移行は来週でよいのであれば、import を
変更してください。

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

差分はこれで全部です。`compat` は 0.5 のトレイト、0.5 の結果型、0.5 の
`HostClient`/`DaemonClient` の形を、blanket impl によって 0.6 のトレイトに
転送します。実際の 0.5 版 dice-roller(255 行、この 1 行以外は無変更)で
検証済みです。

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

(触れた非推奨項目 1 つにつき警告が 1 つ — ここでは 11 個、それに加えて
古い `let mut h = host.lock().await` がもう不要になったことによる
`unused_mut` が 1 つ。)

ビルドは通り、ツールは応答し、`set_host` に保存していたホストも引き続き
デーモンに届きます。SDK 自身のテストスイートがそれを裏付けています。
*0.5 のトレイトに対して*書かれた 7 つのテストが、0.6 のハーネスを通して
`astra-plugin-sdk/src/capability.rs`(`mod compat::tests`)で実行されます。

これに頼る前に知っておくべきことが 3 つあります。

- **`compat::*` は `prelude::*` の代わりであり、追加ではありません。** 両方を
  import すると、スコープ内に `PluginCapability` という名前のトレイトが 2 つ
  存在することになり、`impl PluginCapability for MyPlugin` は非推奨扱いでは
  なく曖昧(E0659)になります。
- **0.8 でなくなります** — [versioning.md](versioning.md) の規定どおり
  2 マイナー分です。
- **0.5 に存在しなかったフックは、そのまま存在しません。** `ai_complete`、
  `tts_activate`、`stt_load` / `stt_unload` / `stt_load_state` はシムを
  通して `UNIMPLEMENTED` を返し、プロトコルはこれを*フックが存在しない*と
  解釈します。これらを実装するにはトレイトを移行する必要があります。

`compat::*` は 0.6 の名前 — `PluginContext`、`ToolError`、`Host`、`Daemon`、
`Config`、`NoConfig` — も再エクスポートしているため、import の行を再度
変更することなく、フックを 1 つずつ新しいシグネチャに移していくことが
できます。最後の 1 つが移り終わったら、`compat::*` を `prelude::*` に戻せば
警告は消えます。

この文書の残りの部分が、その移行についての説明です。

---

## 2. コンパイル時に壊れるもの(Rust)

これらは、無変更の 0.5 版 dice-roller を 0.6 に対してビルドしたときの実際の
エラーです — 5 種類、合計 15 個です。

### 2.1 `Config` は必須の関連型になった

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

プラグインに設定がないなら、1 行で済みます。

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

設定がある場合は、型を宣言して `on_config` を実装してください — SDK が
デーモンの JSON をあなたの代わりにパースします。bad-apple の、変更前
(`examples/bad-apple/src/main.rs`、`134f6d1^` 時点):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

変更後(`examples/bad-apple/src/main.rs`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

20 行が 2 行になり、型の違うフィールドはスキップされるのではなく報告される
ようになりました。

> **`#[serde(default)]`(またはそれを付加する `#[astra::config]`）を使って
> ください。** デーモンが新規インストールされたプラグインに最初に送る設定
> ペイロードは `{}` です。必須フィールドを持つ設定型はこれを拒否し、
> `on_config` は一度も呼ばれず、あなたのプラグインはすべての呼び出しを
> `Config::default()` で処理することになります — 空の API キー、空文字列
> のトリガー名、といった具合です。SDK はまさにこのケースについて大きく
> 警告しますが、それはあなたが見ているログペインではないかもしれません。

`Config<T>` はそれを保持するロックフリーストアです。`self.config.load()` は
1 回のアトミック読み取りであり、ツール呼び出しの途中で設定が書き換わっても
それをブロックしません。

### 2.2 ハンドラは `&PluginContext` を受け取る

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

`&self` の後に `ctx: &PluginContext`(または `_ctx`）を追加してください。
これは `plugin_id`、`language`、`active_triggers`、`host`、`daemon` を
持っており、クローンのコストは低く、`None` になることは決してありません。
mock-stt の変更前後:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS も同時に 4 つの引数を 1 つの `TtsRequest` にまとめました — tone-tts は
`(&self, text, voice_id, speed, _pitch)` から
`(&self, _ctx, req: TtsRequest)` になり、`req.text`、`req.voice_id`、
`req.speed` を読み取ります。

パラメータが届かない場所 — spawn したタスク、`Drop`、他人のクレートからの
コールバック — からは、`astra_plugin_sdk::ctx()` が同じコンテキストを
返します。

### 2.3 `set_host` と `set_daemon_client` は廃止

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

このフックを削除し、フィールドを削除し、`ctx.host()` を使ってください。
これはシム経由で済ませず、きちんと直す価値があります。なぜなら 0.5 の形には
欠陥があったからです。dice-roller の変更前
(`examples/dice-roller/src/main.rs`、`134f6d1^` 時点):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

2 つ目のツール呼び出しがそのロックを保持しているとき、`try_lock` は
`None` を返し、プラグインは「host client not available yet」とログを
出し、**何も発火しませんでした**。変更後:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

`Arc<dyn Host>` には失うロックがありません。同じことがクライアント系の
プラグインにも当てはまります。`client` ケーパビリティを持つプラグインでは、
その生涯を通じて `ctx.daemon()` は常に `Some` であるため、「daemon client
not ready」という分岐はすべて不要になります。telegram-client は
`SharedDaemon` フィールドとこのチェックを失いました。

> `Some` であることはハンドルについてであって、それが到達できる先について
> ではありません。デーモンはすべてのプラグインのセッショントークンを
> `PluginHostService` にスコープしているため、`ctx.daemon()` 経由の呼び出しは
> 現在のところ `permission_denied` を返します — 詳しくは
> [Rust SDK のページ](4-sdk/rust.md#daemon-sdk-には存在するがデーモンには拒否される)
> を参照してください。この節は移行の形についての説明であり、今日エンド
> ツーエンドで動く経路についての説明ではありません。

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` は削除された

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

ハンドラは `Result<String, ToolError>` を返します(`ActionError` は
`ToolError` のエイリアスです)。対応関係は機械的です。

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`、またはパース箇所で単に `?` |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

この種類分けは飾りではありません。これは AI ループに、リトライすることで
何か改善する見込みがあるかどうかを伝えるものであり、`NotConfigured { field }`
こそが「ツールが失敗しました」を、まさにその設定入力欄へのリンクに変える
ものです。bad-apple の変更後:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

`serde_json::to_string` に付いている `?` に注目してください。
`serde_json::Error`、`std::io::Error`、`tonic::Status`、`anyhow::Error` に
対する `From` 実装が存在し、それぞれの変換は失敗の種類についての主張に
なっています — `call_tool` の中の `serde_json::from_str(args)?` は
`BAD_ARGUMENTS` を意味し、これはモデルが別の引数で再試行すれば直せる唯一の
失敗です。

代わりにシムを経由すると、0.5 のすべての失敗は同じ一文を運ぶ
`ToolError::Internal` になります。これは、著者が何であるかを一度も言わ
なかった文字列の、正直な解釈であり、あなたが 5 分で自分で言えることよりも
悪いものです。

### 2.5 小さなコンパイル時の変更

| 内容 | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | フックだった | **削除。** デーモンがマニフェストの `[capabilities]` を `ASTRA_PLUGIN_CAPABILITIES` で伝えます |
| `ActiveTriggers::contains` / `update` | `async`、`tokio::RwLock` | 同期的(`ArcSwap`）になり、`update` は `set` に |
| `HostClient::new(..)` | 構築可能だった | `connect_bootstrap` → `register` → 認証済みクライアント、という経路のみ |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | 動いていた | 一文のエラーで失敗するプレースホルダーに: `#[astra::args]` を使うか、自分の `Cargo.toml` に `serde` を追加してください |
| `on_shutdown()`、`on_event()`、`on_state_changed()` などのイベントフック | `ctx` なし | 他のすべてと同様、最初に `ctx` |

---

## 3. 実行時に壊れるもの(コンパイルは通るが挙動が変わる)

### 3.1 `[permissions]` はデフォルト拒否

これはユーザーのマシンで最初に噛みつくもので、これは SDK の変更ではなく
Phase 4 そのものです。`[permissions]` セクションのないマニフェストは、
`Register`、`PluginLog`、`GetPluginSelfConfig` だけを呼ぶことができ、
**それ以外は何もできません**。`fire_trigger`、`set_variable`、
`push_to_ui`、`send_chat_message`、`subscribe_events`、
`set_theme_contribution` はそれぞれ、宣言され許可されたパーミッションを
必要とし、拒否は `PERMISSION_DENIED` → `ToolError::Unauthorized` として
届きます。

ケーパビリティを宣言するだけでは不十分です。`examples/dice-roller/plugin.toml`
から:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

`reason` はインストール時にユーザーへ表示されます。ユーザーのために書いて
ください。

### 3.2 起動順序と `on_start`

0.6 は順序を修正しました: bind → register → ctx を構築 → `on_config` →
`on_language_changed` → `on_start` → 提供開始、です。`on_start` は新規で、
`Err` を返すと**起動が中断されます**。デーモンが健全だと思い込んでいる
プラグインをそのまま残してすべての呼び出しを同じように失敗させるのでは
なく、プロセスは非ゼロで終了します。

ウォームアップやバックグラウンドタスクはここに置くべきです。echo-stt は
オーディオスレッドを `main` からここに移動しました。telegram-client は
bot の起動全体を `set_daemon_client` から移動し、これによって
`on_config_changed` との競合が取り除かれました。

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 静かに変わった挙動

- **`ActiveTriggers` に書き手が付きました。** 0.5 では誰も書き込まなかった
  ため、`contains()` は常に false を返していました。もし高コストな
  ペイロードをこれでガードしていたなら、そのガードは常に閉じていたのが、
  今は開きます — ペイロードが実際に構築されます。
- **STT のオーディオチャンネルは 32 ではなく 500 チャンクを保持します。**
  負荷がかかると静かにオーディオを取りこぼしていたストリーミング
  認識器は、もう取りこぼしません。取りこぼしを補償していたなら、それは
  もう不要です。
- **`source_id()` は何にも影響しません。** デーモンは source id による
  フィルタリングをやめました。すべてのクライアントがすべてのイベントを
  見ます。0.6 で非推奨、0.8 で削除。代わりに id を `Host::send_chat_message`
  に渡してください。
- **ケーパビリティはデーモンから来ます**。`ASTRA_PLUGIN_CAPABILITIES` に
  よってであり、あなたのどのメソッドが空でないベクタを返すかを内省する
  ことによってではありません。以前はマニフェストと食い違う可能性が
  あった、プラグインが表明するケーパビリティは、今はマニフェストの
  内容そのものを表明します。これはユーザーが同意した内容です。

---

## 4. 警告が出るだけのもの

| 警告 | 期限 | 代わりにすること |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | 0.6 のトレイト — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | オーバーライドを削除 |
| Python `DeprecationWarning: … returned a dict` | 0.7 | データクラスを返す |
| `AiGetModels` / `ai_models()` | 0.8 | 何もしなくてよい — デーモンは決して尋ねません |

この表にあるものはまだどれもエラーではなく、どれも 1 マイナーの中でエラーに
なることはありません。保証の内容と、それがどう強制されるかは
[versioning.md](versioning.md) を参照してください。

---

## 5. Python

パッケージは 0.4.0 → 0.5.0 になります。クラスは今も `Plugin` で、デコレータも
今も `@tool` / `@action` / `@trigger` のままなので、ほとんどのファイルはごく
わずかしか変わりません。

**失敗はコード化されました。** `call_tool` と `execute_action` はかつて
すべての `Exception` を捕捉して `{"success": False, "error": str(e)}` に
平坦化していました — これがすべての失敗が同じに見えていた理由です。
代わりに 8 種類のエラーのいずれかを送出してください。SDK が古い形式の
文字列と構造化された `error_detail` の両方を埋めてくれます。

`examples/text-utils/src/plugin.py` から:

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` は、まさにその設定フィールドへのリンクに
変わる特別なものです。

その他に確認すべきこと。

- **`stt_transcribe` は 3 番目の引数 `options: SttOptions | None` を
  取ります。** 2 引数のオーバーライドも引き続き動作します — サービサーは
  あなたのシグネチャを一度検査し、受け付けられるものだけを渡すからです —
  なのでこれは任意であり、`options=None` を追加することで、デーモンの
  言語ヒントとウェイクワードのバイアスを受け取れるようになります。
- ケーパビリティのフックからは **dict ではなくデータクラスを返してください**。
  dict は引き続き動作し、返すべきクラス名を示す `DeprecationWarning` が
  出ますが、これは 0.7 でなくなります。
- **`HostClient` は未認証では構築できません。**
  `HostClientBootstrap(addr, plugin_id).register(...)` が本物を返します。
- **`@ui_call` / `@ui_page` は登録します。** 以前はこれらは、呼び出し元が
  捨ててしまう dict を返す `@staticmethod` でした。
- CI を警告でゲートしてください: `python -W error::DeprecationWarning -m pytest`。

## 6. TypeScript

パッケージは 0.4.0 → 0.5.0 になり、公開名は `astra-plugin-sdk` です —
以前 4 か所で書かれていた `@astra/plugin-sdk` ではありません。

- **失敗はコード化されています**。他の言語と同じ 8 種類で、`code` は
  クラスごとの文字列リテラルなので、`switch (err.code) { case
  "NOT_CONFIGURED": … }` はサブクラスへ絞り込まれ、キャストなしで
  `err.configField` に到達できます。
- **`HostClient` のコンストラクタは private です**。`HostClient.register(...)`
  が唯一の取得方法であり、デーモンが拒否した場合は `RegistrationError` を
  投げます。
- **クライアントは、2 つの手書きインラインの proto 文字列の代わりに
  SDK 自身が生成した descriptor を読み込み**、接続時に呼び出すすべての
  メソッドをチェックします — 食い違いは、最初の呼び出し時の
  `TypeError` ではなく、起動時の `ProtoContractError` になります。
- **`UiPanel` は非推奨です**。`UiContribution` のエイリアスです。
- あなたの `package.json` が 0.5.0 より前のものなら、新しい `exports`
  マップ、`"type": "commonjs"`、`engines: { node: ">=20" }`、そして
  CJS+ESM のデュアル出力に注意してください。

---

## 7. 移行を検証する

移植がうまくいったかどうかを知るために Astra をインストールする必要は
ありません。0.6 系 SDK には、あなたのハンドラを記録用のホストに対して
インプロセスで実行するテストハーネスが同梱されています。

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

このテストこそが、シムが受け入れられた根拠です。ここでの `DiceRoller` は
**0.5** 版の dice-roller そのもので、import の行以外は無変更のまま 0.6 上で
動いています。デーモンなし、ソケットなし、Astra のインストールなし —
`Harness` は記録用ホストを取り巻く `PluginContext` を構築するので、
`fired_triggers()` はあなたがアサートできるリストになります。

簡単なチェックリストです。

1. `compat::` の import なしでビルドが通る。
2. `plugin.toml` に、呼び出すすべてのホスト RPC に対応する `[permissions]`
   セクションがあり、それぞれにユーザー向けの `reason` が書かれている。
3. `on_config` が `{}` を受け取っても倒れない — それが新規インストール
   です。
4. かつて `set_host` / `set_daemon_client` で行っていたことはすべて
   `on_start` の中で行われており、プラグインが本当に動作できない場合は
   `on_start` が `Err` を返す。
5. すべての `ToolResult::err` が、理由を語る `ToolError` のバリアントに
   なっている。
