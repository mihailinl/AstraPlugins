> **これは翻訳です。** 正式な情報源は [docs/en](../../en/reference/parity.md) です。内容に食い違いがある場合は英語版が優先されます。英語版のページは `tools/parity/gen.py` が生成しています。この翻訳は生成物ではなく手作業で保守されているスナップショットなので、英語版が再生成されたら手作業で訳し直してください。

# フックの対応表(Hook parity)

プロトコル **1** · **49** 個のフック · 正典は [`spec/hooks.yaml`](../../../spec/hooks.yaml)。

*フック* とは、プラグイン向けの 2 つのサービスのどちらか一方にある 1 つの
RPC のことです。`PluginCapabilityService` は **デーモン → プラグイン**方向
で動きます。あなたのプラグインがこれを提供し、デーモンが呼び出します。
`PluginHostService` は **プラグイン → デーモン**方向で動きます。デーモンが
これを提供し、あなたのプラグインが呼び出します。`PluginService` はここには
含まれません。デーモンはこれを Astra の UI に提供するもので、プラグインが
触れることは決してありません。

| 列 | 意味 |
|---|---|
| **Capability** | このフックが属する `plugin.toml` の `[capabilities]` のキー。すべてのプラグインが持つフックは `core` |
| **Permission** | `PluginHostService` のみ。デーモンがこの呼び出しをゲートする `[permissions]` のキー(§5.6)、あるいはすべてのプラグインが常に呼べる場合は `none`。**Capability とは別の問いです。** capability はその呼び出しがどの機能の一部かを示し、permission はユーザーが何に同意したかを示します。デーモンは*許可された*パーミッション集合に基づいて応答します。デーモンの `HOST_RPC_PERMISSIONS` に対してルール R6 で検証されています |
| **Req** | `required` — このフックなしでは capability が機能しません。`optional` — フックがなくてもデーモンは処理を続けます |
| **Routing** | `live` — デーモンが実際にこれを呼び出しており、呼び出し箇所が名指しされています。`unrouted` — proto には宣言されていますが、誰からも呼ばれていません。`deprecated` — 廃止予定です |
| **デーモン側の呼び出し箇所** | デーモンがこのフックを呼び出しているファイル。誰も呼んでいないときは **none**。行番号はここには意図的に載せていません。行番号は `spec/hooks.yaml` にあり、そこではルール R5 が実際の呼び出し箇所と照合し、`--fix-provenance` が貼り直します。ページ上の行番号は何にも検査されず、デーモンのコミットのたびに腐り、腐ったポインタは正しいものとまったく同じに読めます — 実際そのうちの一つは、誰も気づかないうちに別の rpc の呼び出し箇所までずれていました。ここに示されたファイルの中で、その rpc の snake_case 名を探してください |
| `stable` | SDK がこの rpc を実際に処理を行うハンドラに結びつけていることを示します — `tools/parity/check.py` のルール R1 によって、そのディスパッチ先(TypeScript の `.bind(this)`、Python のサービサーメソッド、Rust の `async fn`)を解決し、*その*本体を読むことで検証されています。実際のプラグインプロセスを通してその結びつきが何かに到達するかどうかは R1 ではなく R7 の問いです |
| `planned` | コミット済みだが未出荷です。日付は猶予期限であり、それを過ぎるとルール R4 がビルドを失敗させます |
| `n/a` | 実装されておらず、コミットもされていません。本体が `UNIMPLEMENTED` を返すだけの登録済みハンドラは `n/a` として扱われます。なぜならワイヤー上ではそれは*フックが存在しない*のと同じであり、R1 はまさにこれを確認するためにハンドラの本体を読んでいるからです |

## 検出事項(Findings)

以下の行から導出されたものであり、手書きではありません。それぞれが、
今日プラグイン作者のコードが失敗する具体的な原因です。

1. **`TtsSynthesizeStream` は unrouted です。** proto では宣言されている
   ものの、デーモン側の呼び出し箇所は存在しません — それにもかかわらず
   Rust、Python、TypeScript のいずれでも結びつけられています。配線する
   か廃止するかのどちらかにしてください。今のところ、これはデーモンが
   守っていない約束です。

## PluginCapabilityService — デーモン → プラグイン

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | デーモン側の呼び出し箇所 |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **none** |
| `TtsListVoices` | `tts` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsGetConfigFields` | `tts` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsActivate` | `tts` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttProcess` | `stt` | required | live | bidi | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetLanguages` | `stt` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetConfigFields` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttLoad` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttUnload` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetLoadState` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `AiComplete` | `ai_provider` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/capability_bridge.rs` |
| `AiGetModels` | `ai_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `WebSearch` | `web_search` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `ImageGenerate` | `image_provider` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `ImageGetModels` | `image_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `MusicSubscribe` | `music_provider` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicControl` | `music_provider` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicGetQueue` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicSearch` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicPlay` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `ExecuteAction` | `actions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `GetPluginActionTypes` | `actions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `GetPluginTriggerTypes` | `triggers` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `OnActiveTriggers` | `triggers` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `GetUiContributions` | `ui_contributions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `CallFromUi` | `ui_contributions` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `OnConfigChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `OnLanguageChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `Shutdown` | `core` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/instance.rs` |
| `HealthCheck` | `core` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/health.rs` |

## PluginHostService — プラグイン → デーモン

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | デーモン側の呼び出し箇所 |
|---|---|---|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetPluginSelfConfig` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `PluginLog` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetDaemonInfo` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SetVariable` | `core` | `set_variable` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `FireTrigger` | `triggers` | `fire_trigger` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SendChatMessage` | `client` | `send_chat_message` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetAiSettings` | `core` | `read_ai_settings` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `Speak` | `core` | `speak` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `StopSpeaking` | `core` | `speak` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetUserIdentity` | `core` | `read_user_identity` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `RequestSettingsChange` | `core` | `request_settings_change` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `ProposeCommand` | `core` | `propose_commands` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |

## ケーパビリティの実装可否

この言語で書かれたプラグインは、今日この capability をそもそも実装できる
か?

| Capability | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | yes | yes | yes |
| `tts` | yes | yes | yes |
| `stt` | yes | yes | yes |
| `ai_provider` | yes | yes | yes |
| `web_search` | yes | yes | yes |
| `image_provider` | yes | yes | yes |
| `music_provider` | yes | yes | yes |
| `actions` | yes | yes | yes |
| `triggers` | yes | yes | yes |
| `ui_contributions` | yes | yes | yes |
| `core` | yes | yes | yes |
| `event_handlers` | yes | yes | yes |
| `client` | yes | yes | yes |

## 適合性テストのカバレッジ

適合性テストの実行が行使すべき 24 個の受信側フック — デーモンが実際に
呼び出すすべての `daemon → plugin` フックです。`astra-plugin test` は
プラグインが宣言している capabilities から暗黙に決まる各フックを呼び出し、
`required` のものについて `UNIMPLEMENTED` が返らないことをアサートします。
`optional` なフックは対象外です。なぜなら `Unimplemented → フックが存在
しない` は前方互換の契約であり、そうでなければすべてを宣言する雛形は
壊れたプラグインと区別がつかなくなってしまうからです。機械可読なコピー:
[`spec/generated/conformance.json`](../../../spec/generated/conformance.json)。

| RPC | Capability | Req | Stream | Phase |
|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | probe |
| `CallTool` | `tools` | required | unary | probe |
| `TtsSynthesize` | `tts` | required | unary | probe |
| `TtsListVoices` | `tts` | required | unary | probe |
| `TtsGetConfigFields` | `tts` | optional | unary | probe |
| `TtsActivate` | `tts` | optional | unary | probe |
| `SttProcess` | `stt` | required | bidi | probe |
| `SttGetLanguages` | `stt` | required | unary | probe |
| `SttGetConfigFields` | `stt` | optional | unary | probe |
| `SttLoad` | `stt` | optional | unary | probe |
| `SttUnload` | `stt` | optional | unary | probe |
| `SttGetLoadState` | `stt` | optional | unary | probe |
| `AiComplete` | `ai_provider` | required | server | probe |
| `AiGetModels` | `ai_provider` | optional | unary | probe |
| `WebSearch` | `web_search` | required | unary | probe |
| `ImageGenerate` | `image_provider` | required | unary | probe |
| `ImageGetModels` | `image_provider` | optional | unary | probe |
| `MusicSubscribe` | `music_provider` | required | server | probe |
| `MusicControl` | `music_provider` | required | unary | probe |
| `MusicGetQueue` | `music_provider` | optional | unary | probe |
| `MusicSearch` | `music_provider` | optional | unary | probe |
| `MusicPlay` | `music_provider` | optional | unary | probe |
| `ExecuteAction` | `actions` | required | unary | probe |
| `GetPluginActionTypes` | `actions` | required | unary | probe |
| `GetPluginTriggerTypes` | `triggers` | required | unary | probe |
| `OnActiveTriggers` | `triggers` | optional | unary | probe |
| `GetUiContributions` | `ui_contributions` | required | unary | probe |
| `CallFromUi` | `ui_contributions` | optional | unary | probe |
| `OnConfigChanged` | `core` | optional | unary | probe |
| `OnLanguageChanged` | `core` | optional | unary | probe |
| `HealthCheck` | `core` | required | unary | probe |
| `Shutdown` | `core` | required | unary | teardown |

## 注記

- **`TtsSynthesizeStream`** — 発話 1 件を、初回音声のレイテンシのために
  チャンクストリームとして合成します。検出事項: astra-rs にデーモン側の
  呼び出し箇所は存在しません。3 つの SDK すべてがこれを提供していますが
  誰も呼んでいません — このファイルが検出しようとしているズレは消えて
  いますが、unrouted な rpc であること自体は消えていません。
- **`TtsGetConfigFields`** — Voice ページで DynamicField によって描画
  される、追加の TTS 設定フィールドです。デーモンの `optional_hook`
  ヘルパー(manager/voice.rs:450)を経由してルーティングされているため、
  UNIMPLEMENTED は「存在しない」ことを意味し、本物の障害は今も障害の
  ままです。
- **`TtsActivate`** — ライセンス済みボイスのコンテンツキーを、1 回限りの
  マシン固定シーリングのために渡します。proto の説明では UNIMPLEMENTED
  は「有効化不要」として扱われるとされていますが、デーモンはこれを
  `optional_hook` 経由でルーティングしていません — manager/voice.rs:131 は
  エラーを伝播させ、vox_activation.rs:319 は有効化を失敗させます。proto
  のコメントのほうが間違っています。
- **`SttProcess`** — 音声チャンクが入り、書き起こしイベントが出ます。
  単発と ストリーミング両方の STT を担います。manager/voice.rs:342 でも
  実際に駆動されています。両端のチャンネル容量は
  spec/limits.yaml:stt_audio_channel_capacity です。
- **`SttLoad`** — デーモンが解決したパスと GPU 切り替えとともに、
  認識器モデルをロードします。manager/voice.rs:488 が `optional_hook` 経由で
  ルーティングしているため、これは optional です。
- **`SttGetLoadState`** — デーモンがアイドル時アンロードを駆動できる
  よう、Loaded / NotLoaded / NotNeeded を報告します。manager/voice.rs:530 は
  フックが存在しない場合を NotNeeded に写像します。これはフック導入前の
  挙動です。
- **`AiComplete`** — モデルの補完をストリームします。プラグインが AI
  プロバイダになれる唯一の方法です。Python と TypeScript は非同期
  ジェネレータとしてこれを結びつけ、Rust はチャンネル供給型の server
  stream として結びつけています。最初のチャンクを待ってからレスポンスを
  開くため、オーバーライドされていないフックでも UNIMPLEMENTED を返せ
  ます。3 つの SDK すべてが 5.4 の時点でこれを結びつけているため、
  `ai_provider` はどの言語でも実装可能です。
- **`AiGetModels`** — このプロバイダが動かせるモデルと、それぞれをどう動かしてほしいか(ヒント)を、Astra のモデル選択のために一覧します。 プラグインの起動時に他の定義と一緒に、そして AI ページが更新されるたびに問い合わせられます。UNIMPLEMENTED またはエラーは「リストなし」です。選ばれたモデルは AiComplete の `model` で届き、空なら `default_model` を意味します。モデルの `hints`(なければリストの `provider_hints`)が変えるのは、そのモデルでの Astra のターンだけで、しかも `plugin-provider-slots` 付きでビルドされたデーモンでだけです。`accepts_images` を宣言するプラグインは 64 MiB のメッセージを受け取れなければならず、各 SDK の capability サーバーはそうなっています。
- **`OnActiveTriggers`** — このプラグインのトリガー種別のうち、あるコマンド
  が現在listenしているものはどれか。manager/capabilities.rs:438 が `optional_hook`
  経由でルーティングしています。
- **`OnLanguageChanged`** — Astra UI の言語が変わりました。ユーザーに
  見えるものを再描画してください。manager/ui_surface.rs:352 が `optional_hook`
  経由でルーティングしています。
- **`Shutdown`** — きれいに停止します。猶予期間の後、プロセスグループは
  kill されます。猶予期間は spec/limits.yaml:plugin_stop_grace_secs
  です。応答してから終了してください。
- **`HealthCheck`** — 15 秒ごとの生存確認です。最も強い意味で required
  です。このフックは `optional_hook` を経由して**いません**。そのため
  UNIMPLEMENTED を含むいかなるエラーもプラグインを死んでいるとマーク
  します(manager/health.rs:337)。
- **`Register`** — ハンドシェイクです。spawn トークンを証明し、プラグイン
  ごとのセッショントークンを受け取ります。認証インターセプターの対象外と
  なる唯一の経路です。それ以降のすべてのホスト rpc は、返されたトークンを
  x-session-token として運ばなければなりません。
- **`SendChatMessage`** — このプラグインとしてチャットメッセージを送信し、
  アシスタントの返信をストリームで受け取ります。セッショントークンは
  PluginHostService にスコープされているため、SDK がかつて作者に案内して
  いた DaemonClient/ChatService の経路は permission_denied になります —
  この rpc だけが動作する経路です。5.4 の時点で 3 つの SDK すべてに
  結びつけられています。
- **`PushToUi`** — このプラグイン自身の iframe にイベントを push します
- **`GetAiSettings`** — ユーザーのチャットのプロバイダー、モデル、エンドポイント(キーは含まない)。プラグインが Astra のファイルを読まずに済む。 2026-11-10 より古い Astra は UNIMPLEMENTED を返す。保存されたエンドポイントは openai_compatible、Astra 自身のサービスは URL なしの astra として読める。
- **`Speak`** — プラグイン自身の言葉を Astra の声で読み上げます。言い終えた、止められた、または拒否された時点で応答します。 speak は高リスク(専用の同意チェックボックス)。Astra を利用できるアカウントと、本人の応答音声がオンであることが必要。最大 300 文字で、超えれば拒否され、切り詰められることはない(spec/limits.yaml:speak_text_max_chars)。発話時間は一度に 450 文字、その後は毎秒 3 文字で、それを超えると NOT_SPOKEN が RATE_LIMITED と retry_after_ms を運ぶ。STOPPED はエラーではない。2026-11-12 より古い Astra は UNIMPLEMENTED を返す。
- **`StopSpeaking`** — このプラグインが言わせようとしたもの — 鳴っているものもキューにあるものも — をすべて止め、Astra が話している他のものは何も止めません。 speak によってゲートされる。2 つのホスト rpc が共有する唯一のパーミッション。誰かがサインインしているかどうかに関係なく許可される。これが止めた各 Speak は STOPPED を返す。
- **`GetUserIdentity`** — このインストールとサインイン中のアカウントの、このプラグイン専用に作られた仮名 ID。アカウント自身の id、名前、メールアドレス、ハードウェアのシリアル番号であることは決してありません。 account_id は authorized でなければ空で、本人がサインインするどのデバイスでも同じ。同じ値がこのプラグインの auth_changed イベントに account_id として届く。2026-11-12 より古い Astra は UNIMPLEMENTED を返す。
- **`RequestSettingsChange`** — Astra の設定の一部を変えるよう、本人が応答するカードで頼みます — 頼めるのはアシスタント自身が変更できる設定だけ。本人が許可しない限り何も変わりません。 Astra を利用できるアカウントと、plugin-requests ビルド機能付きでビルドされた Astra が必要(そうでなければコード not_compiled の REFUSED)。変更は 1〜8 件、各パスは 1 回、すべてかゼロか。理由は最大 140 文字で、超えれば拒否され、切り詰められることはない(spec/limits.yaml:settings_change_max_changes、settings_change_reason_max_chars)。カードはプラグインごとに同時に 1 枚(1 枚出ている間の 2 つ目のリクエストは busy)、リクエストはまとめて 2 件まで、その後は 120 秒に 1 件(rate_limited と retry_after_ms)。応答は APPLIED、UNCHANGED(誰にも尋ねていない)、DECLINED(本人が以前に断った設定にも、それが別の方法で変わるか Astra が再起動するまで)、TIMED_OUT、またはコード付きの REFUSED で、現在の値は決して返さない。呼び出しは本人が応答するかカードが期限切れになるまで続く。2026-11-13 より古い Astra は UNIMPLEMENTED を返す。
- **`ProposeCommand`** — 持ち運べるコマンドを 1 つ、このプラグイン自身のキーで本人に「提案」します。本人がそれを残せるのは Astra の Workshop のシートからだけで、そこにはすべてのトリガーと手順が表示されます。 propose_commands は高リスク(専用の同意チェックボックス): 残されたコマンドは後で、そのトリガーによって、本人自身のコマンドとして実行される — その手順は、シェルコマンドのような組み込みのものも含め、改めて尋ねることなく実行される。Astra を利用できるアカウントと、plugin-requests ビルド機能付きでビルドされた Astra が必要(そうでなければコード not_compiled の REFUSED。2026-11-13 より古い Astra では呼び出しが UNIMPLEMENTED で失敗する)。キーは a-z A-Z 0-9 . _ - の 1〜64 文字で、同じキーをもう一度提案すると同じコマンドが更新される。コマンドは最大 1 MiB のポータブルな JSON で、Workshop 自身のリーダーが読み(ローカルなフィールドは取り除かれる)、使えるのは Astra の組み込みのアクションとトリガー、そしてこのプラグイン自身のもの — 他のプラグインのものは決して使えない(foreign_plugin)。理由は最大 140 文字で、超えれば拒否され、切り詰められることはない(spec/limits.yaml:propose_command_max_bytes、propose_command_reason_max_chars)。カードはプラグインごとに同時に 1 枚(1 枚出ている間の 2 つ目の提案は busy)、提案はまとめて 2 件まで、その後は 120 秒に 1 件(rate_limited と retry_after_ms)。応答は SAVED(enabled: 残された後にコマンドが有効かどうか)、UNCHANGED(そのキーで残されているものはまさにこの提案から来たもの — 本人が編集した後も同じ。誰にも尋ねていない)、DECLINED(以前に断られたまさにこのコマンドにも、Astra が再起動するまで)、TIMED_OUT、またはコード付きの REFUSED。呼び出しは本人が応答するかカードが期限切れになるまで続く。
  — CallFromUi の戻り経路です。今では 3 つすべてに結びつけられています。
  Python は 3 リリースの間 CallFromUi はあるが PushToUi はない状態
  だったため、Python 製の UI プラグインは呼び出されても非同期に応答
  できませんでした。
- **`SetThemeContribution`** — アクティブな Astra テーマに色、壁紙、
  シェーダーを提供します。Phase 4 はこれを高リスクに分類し、Tier 1 未満
  では拒否するため、許可されたパーミッションを持たない結びつきは、
  テーマが再描画されるのではなく permission_denied になります。5.4 の
  時点で 3 つの SDK すべてに結びつけられています。
