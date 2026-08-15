> **これは翻訳です。** 正式な情報源は [docs/en](../../en/6-operate/troubleshooting.md) です。内容に食い違いがある場合は英語版が優先されます。

# トラブルシューティング

CLI とデーモンが実際に出力する文字列に対応しています。目の前にエラーが
ある場合は、このページでその一部を検索してください。

## まずここから

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

15 個のチェック、それぞれが答える問いとして表現されています。どの
CLI を実行しているか、どの設定ディレクトリを解決したか、デーモンに
到達可能か、どのツールチェーンを持っているか、あなたのマニフェストが
パースできるか、エントリポイントが存在するか、あなたのパーミッションが
あなたのケーパビリティをカバーしているか、あなたの `[platform]` ブロック
が正しいか、あなたのリリースワークフローがピン留めされているか。すべて
の失敗には `fix:` の行が付きます。まだビルドしていないプロジェクトでは、
そのうちの 1 つで非ゼロ終了します — 「Will the daemon find something
to start? … does not exist」— これは正しい挙動です: まだ何もバイナリ
を生成していないからです。

## プロジェクトが SDK を解決できない

**`error: failed to select a version for the requirement astra-plugin-sdk = "^0.6"`**
**`ERROR: No matching distribution found for astra-plugin-sdk<0.6,>=0.5`**
**`error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)`**

3 つの言語、同じ形のエラー — ただし原因はもう SDK が無いことではありません。
`astra-plugin new` は `astra-plugin-sdk` を Rust では `0.6`、Python では
`>=0.5,<0.6`、TypeScript では `^0.5.0` にピン留めし、公開レジストリは
crates.io **0.6.0**、PyPI **0.5.0**、npm **0.5.0** を持っています。これらの
ピンはいずれも、何も設定していない新規プロジェクトで解決します。解決しない
場合、原因はあなたのマシンとレジストリの間にあります。

- **古いインデックス、ロックファイル、または同期されていないミラー。**
  リゾルバがリリース以前のキャッシュされたレジストリの状態、あるいは同じ状態の
  社内プロキシから答えています。`cargo update -p astra-plugin-sdk`、
  `pip install --upgrade --no-cache-dir -r requirements.txt`、npm なら
  `node_modules` とロックファイルを削除して入れ直してください。
  `cargo --offline` と `npm --offline` は仕様上このエラーになります。
- **誰かが下限を緩めた。** `0.5`(Rust)や `0.4`(Python、TypeScript)まで
  下げられたピンは、その制約の下ではどのレジストリも提供していないものを
  要求します。さらに広げるのではなく、スキャフォールドのピンに戻してください。
  0.6 は `HostClient` が `x-session-token` を付加する最初の Rust リリースで
  あり、より古い SDK では、このエラーがすべてのホスト呼び出しでの
  `unauthenticated` に置き換わります — 下のセクションを参照してください。

`doctor` も `check` もこれには触れません。どちらも `plugin.toml` を読み、
ピンはその言語自身のビルドファイルにあるからです。

## プラグインが起動しない

**`Could not read /…/astra/daemon.token. Astra does not look like it is running — start the app first.`**
まさにその通りです。`dev`、`logs`、インストールには実行中の Astra が
必要です; `new`、`build`、`check`、`test`、`sign`、`publish` には不要
です。Astra が*実行されている*場合は、CLI とは異なる設定ディレクトリ
を解決しています — `doctor` が出力するパスと、Astra が設定画面に表示
するパスを比較してください。

**デーモンが起動時にプロセスを回収してしまった。** 予算は最初の出力行
まで `plugin_start_timeout_secs` = **20 秒**です。モジュールスコープで
大きな ML スタックをインポートする Python プラグインはこれを逃す可能性
があります; 必要とするフックの中で遅延インポートしてください。
`astra-plugin test` はこれを測定し、その数値を出力します:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
```

**プラグインが起動して即座に死ぬ。** まず `astra-plugin logs -f` を
確認してください; そこに何もなければ、プロセスは SDK が自身のロギング
をインストールする前に失敗しています。バイナリを手動で実行してください
— `astra-plugin dev --standalone` がそれを行い、その方法でできない
ことを教えてくれます。

**`HealthCheck` のエラーはプラグインを死んでいるとマークします。**
これは 15 秒ごとに実行され、デーモンの任意フックヘルパーを経由して
ルーティングされていません: `UNIMPLEMENTED` を含む*あらゆる*エラーが
死んでいることを意味します。`health_check` をオーバーライドした場合は、
それが決して throw しないようにしてください。

## ホスト呼び出しが `permission_denied` を返す

メッセージにはパーミッションの名前と、許可された集合がどこから来たか
が記されています。可能性の高い順に 3 つの原因があります:

1. **それを宣言していない。** `[permissions]` はデフォルト拒否です。
   `[capabilities] event_handlers = true` を宣言しても
   `SubscribeEvents` は得られません; `[permissions] subscribe_events`
   がそれをもたらします。
2. **ユーザーがそれを許可していない**、あるいはインストール経路が
   それに上限を設けた。[ローカルでインポートされたファイル](../5-publish/local-install.md)
   では `send_chat_message`、`set_theme_contribution`、
   `dom_access`、`client` が無条件で拒否されます。
3. **サインアウトしているか、アプリがロックされている。** Astra は
   どちらの状態でもプラグインの RPC を拒否し、CLI はそう伝えます:
   「Astra refuses plugin RPCs while signed out or locked — sign in
   and unlock the app, then try again.」

`astra-plugin doctor` は何も実行せずに 1 に答えます:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## ホスト呼び出しが `unauthenticated` を返す

`Register` を除くすべての `PluginHostService` の呼び出しは、
`x-session-token` にセッショントークンを載せなければなりません。
3 つの SDK すべてがこれを付加します — **Rust は 0.6 から、Python と
TypeScript は 0.5 から**です。より古い SDK に対しては、すべてのホスト
呼び出しがこの方法で失敗します。これがスキャフォールドの依存下限を
それより下げない理由です。

`astra-plugin test` はこれをエンドツーエンドでアサートします:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`
```

## サイドロードが拒否される

**`Sideloading is disabled.`** `safety.allow_unsigned_plugins` が
オフです。有効にする前に
[有効にすると何を失うか](../5-publish/sideload.md) を読んでください。

**`Refusing sideload marker in …: this daemon never authorised a sideload of …`**
誰かが `sideload.json` を手で仕込みました。デーモンが自分の許可した
ことの記録を独自に持つようになって以来、これは機能していません。
`astra-plugin dev` を使ってください。

## インストールが拒否される

レジストリ経路でのすべての検証失敗は**オーバーライドのないハードブロック**
であり、それぞれが 2 つのうちどちらが起きたかを名指しします。

| 見えるもの | 意味 |
|---|---|
| ダウンロードされたファイルが、レジストリが署名したものと一致しない | `DIGEST_MISMATCH` — ダウンロードは破棄されました。報告してください |
| Astra がプラグインカタログの署名を検証できなかった | `SIGNATURE_INVALID` — 未検証データにフォールバックするのではなく、ストアが無効化されます |
| この更新は、あなたがインストールした先とは異なるリポジトリから来ている | `IDENTITY_CHANGED` — オーバーライドは決してありません。アンインストールだけがピンを解除します |
| プラグインが撤回された | `REVOKED` — 勧告とワンクリックアンインストール付き。ファイルが静かに削除されることは決してありません |
| このバンドルは別のプラットフォーム向けである | `PLATFORM_UNSUPPORTED` |
| このプラグインには新しい Astra が必要 | `PROTOCOL_UNSUPPORTED` |
| ネットワーク、またはあなたの時計が狂っている | リトライ可能で、そのように表現されます。これらは決して検証失敗のように見えてはいけません |

ローカルファイルでの **`nothing here vouches for these bytes`**:
代わりに Plugins ページからインストールするか、
[ローカルインストール](../5-publish/local-install.md) でそれを
インポートすることの代償を読んでください。

今日、信頼チェーンは**1 リンク分だけ**固定が足りません: ルートキーは
存在し、インデックス署名キーに委譲する root 署名済みの `trust.json`
も今では存在しますが、`registry/v1/index.json` と `revocations.json`
はまだ `"signatures": []` を持っています。カタログに署名がないため、
委譲されたキーがチェックできるものが何もなく、カタログは未署名として
分類され、失効は強制されません。
[`spec/registry-index.md` §0.1](../spec/registry-index.md) を参照して
ください。

## ツール呼び出しがモデルには直せない形で失敗する

正しいコードを使ってください; それがモデルが読むものです。

| コード | いつ使うか |
|---|---|
| `BAD_ARGUMENTS` | 別の引数で再試行すればうまくいく可能性がある場合 |
| `NOT_CONFIGURED` | 設定が欠けている場合 — そして**`config_field` を設定してください**。これがエラーをその正確な入力欄へのリンクに変えるものです |
| `UNAUTHORIZED` | 値は存在しており、それが拒否された場合。`NOT_CONFIGURED` とは異なります |
| `RATE_LIMITED` | 上流がそう言った場合、`retry_after_ms` とともに |
| `UNAVAILABLE` / `TIMEOUT` | 一時的なもの。後で同じ呼び出しをすればうまくいくかもしれません |
| `INTERNAL` | バグです。モデルにできることは何もありません |

`UNIMPLEMENTED` はエラーでは**ありません**: 「このフックは存在しない」
を意味し、デーモンはそう解釈します。あなたの TTS がクラッシュしたから
という理由でこれを返すと、デーモンはあなたに TTS がないと信じ込んで
しまいます。完全な分類:
[`reference/errors.md`](../reference/errors.md)。

## `astra-plugin check` が文句を言う

**`config.schema is not valid JSON`** または
**`should have "type": "object" at root`** — 設定フォームはそのスキーマ
から生成されます。

**`[capabilities]` 内の未知のキーはマニフェスト全体を失敗させます。**
このセクションは、未知のキーが拒否される唯一の場所です。なぜなら、
すべてのキーはオプトインの真偽値であり、そうでなければタイポが
`false` とまったく同じように読めてしまうからです。`ui_panels` が
典型例です: 正しくは `ui_contributions` であり、出荷済みの 3 つの
サンプルがこれのせいで何か月もの間、何もケーパビリティを宣言していない
状態になっていました。

**未知の `[permissions]` の id は保持され、警告されます**が、拒否は
されません — 新しい id は新しい Astra とともに出荷され、
permissions ブロックは 3 つの実装によってバイト単位でハッシュされる
ため、キーを落とすと、それらが何に署名したかについて食い違ってしまい
ます。

`astra-plugin check --fix` は証明できるものを適用し、残りを報告します。

## CLI が何も有用なことを出力しない

`RUST_LOG` は今は機能します — これは 0.1 から文書化されていましたが、
サブスクライバーがインストールされるまで無効でした:

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

トレースは**stderr** に出力されるため、stdout 上の `--json` はクリーン
な単一ドキュメントのままです。

## 終了コード

| | |
|---|---|
| `0` | 成功 |
| `1` | プラグインまたはバンドルが不正 |
| `2` | CLI がチェックを実行できなかった — ファイルの欠落、ツールチェーンの欠落 |

この分割には意味があります: 「バンドルが悪い」と「確認できなかった」
を同じものとして扱うリリースワークフローは、そのどちらか一方を出荷して
しまいます。

## それでも解決しないとき

- [ログ](logs.md) — OS ごとにそれらがどこにあるか
- [パフォーマンス](performance.md) — タイムアウトとその背後にある数値
- [サンプル](../7-examples/README.md) — 11 個の動作するプラグイン、
  その多くはあなたがデバッグしている経路を行使しています
