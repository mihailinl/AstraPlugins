> **これは翻訳です。** 正式な情報源は [docs/en](../../en/1-orientation/architecture.md) です。内容に食い違いがある場合は英語版が優先されます。

# アーキテクチャ

プラグインのプロセスがどのように起動され、どのように自分の身元を証明し、
2 つの gRPC サービスのどちらがどの呼び出しを運ぶか、についてです。

## プロセスモデル

<!-- doctest: illustrative reason="an ASCII diagram of the two services, not code" -->
```
   ┌──────────────────────────┐                  ┌──────────────────────────┐
   │      Astra daemon        │                  │     your plugin          │
   │                          │   spawns with    │     (a separate OS       │
   │  plugin manager ─────────┼──── argv ───────▶│      process, your       │
   │                          │                  │      user account)       │
   │                          │                  │                          │
   │  PluginHostService       │◀── plugin calls ─┤  HostClient              │
   │  (the daemon serves)     │   x-session-token│                          │
   │                          │                  │                          │
   │  capability client ──────┼── daemon calls ─▶│  PluginCapabilityService │
   │                          │   x-plugin-token │  (your plugin serves)    │
   └──────────────────────────┘                  └──────────────────────────┘
             both ends are gRPC over loopback TCP
```

デーモンは 4 つの引数とともにプロセスを spawn します。以下は実際の
`astra-plugin test` の実行からコピーした、正確なコマンドラインです。

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

これらは SDK があなたの代わりにパースします。`--auth-token` は特に
興味深いものです。これはデーモンがこの spawn のために発行した秘密であり、
**両方向**で使われます。

## 起動順序

SDK は固定された順序で処理を実行します(`astra-plugin-sdk/src/runner.rs`)。

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **register の前に bind します。** なぜなら、`Register` の間にデーモンに
  ポートが伝えられ、デーモンはすぐにコールバックしてくる可能性があるから
  です。リスナーはすでに立ち上がっているため、それらの呼び出しは拒否
  されるのではなく accept のバックログにキューされます。
- **`on_start` の前に `on_config` を実行します。** なぜなら、バックグラウンド
  ループを起動するプラグインは、まず自分の設定を必要とするからです。
- **`serve` の前に `on_start` を実行し、そこからの `Err` は起動を中断
  させます。** 自分の仕事を遂行できないプラグインは、デーモンが健全だと
  思い込んでいる状態にしてはいけません。

これを制約する 2 つの数値があり、どちらも
[`spec/limits.yaml`](../../../spec/limits.yaml) で 1 回だけ宣言され、
各 SDK に生成されて配られます。

| 制限 | 値 | 超えるとどうなるか |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | デーモンは起動失敗と判断し、プロセスを回収します |
| `plugin_stop_grace_secs` | 5 | `Shutdown` の後、プロセスグループが kill されます |

## ハンドシェイク

1. デーモンは `--auth-token=<spawn token>` を渡してプロセスを spawn します。
2. プラグインは OS が割り当てた loopback ポートで gRPC サーバーを bind
   します。
3. プラグインは `PluginHostService.Register` を呼び出し、spawn トークン、
   自身のポート、プロトコルバージョン、ケーパビリティ一覧を提示します。
4. デーモンは**セッショントークン**を返します。
5. それ以降のすべてのプラグイン → デーモンの呼び出しは、そのセッション
   トークンを `x-session-token` メタデータヘッダーに載せて運びます。
   `Register` だけが唯一の例外です(`astra-plugin-sdk/src/auth.rs`)。
   それがないその他の呼び出しはすべて `unauthenticated` として返って
   きます。

`astra-plugin test` が起動するモックデーモンに対する実際の実行での登録:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### 逆方向

デーモン → プラグイン方向は、*同じ* spawn トークンを使い、すべての呼び出し
で `x-plugin-token` ヘッダーとしてプラグインに送り返されます。あなたの
ケーパビリティサーバーがこれをチェックしますが、これは SDK があなたの
代わりに行います。

**これはあなたが設定するものではありません。** デーモンはあなたのプラグイン
の環境に `ASTRA_PLUGIN_CAPABILITY_AUTH=require` を設定し、これによって SDK
はトークンを運ばないケーパビリティ呼び出しをすべて拒否するようになります。
これはバージョン番号を照合する誰かによるものではなく、デーモン自身が自分の
半分をアナウンスするものです。ヘッダーを送らないほど古いデーモンは変数を
一切設定せず、SDK は `CapabilityAuth::Warn` の状態のままになります —
**間違った**トークンは拒否されますが、**欠落した**トークンは 1 回の警告
とともに受け入れられます — そのため、そのようなデーモン上でもあなたの
プラグインは動き続けます。

これが重要なのは、loopback が境界ではないからです。あなたのケーパビリティ
サーバーは、OS が割り当てたポートで `127.0.0.1` をリッスンしており、
あなたのユーザーとして動くすべてのプロセスがそれを見つけられます。ヘッダー
がなければ、それを見つけるだけで `CallTool`、`OnConfigChanged`(あなたの
API のベース URL を他人のホストに向け直し、その後あなたのプラグインが
本物の資格情報をそこへ送ってしまう)、あるいは `Shutdown` を呼び出すのに
十分でした。

`astra-plugin test` は同じ変数を設定し同じトークンを提示するので、あなたが
ローカルでテストしたものが、ユーザーのマシン上で動くものと同じです。

## 2 つのサービス

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| 提供者 | あなたのプラグイン | デーモン |
| 呼び出し元 | デーモン | あなたのプラグイン |
| 統制するもの | `[capabilities]` | `[permissions]` |
| フック数 | 25 | 10 |

`PluginService` — proto にある 3 つ目のサービス — は、デーモンが Astra の
UI に提供するものです。プラグインがこれを呼び出すことは決してありません。
`astra-plugin dev` と `astra-plugin logs` はローカルクライアントとして
これを呼び出します。

各フックについて、その capability、permission、必須かどうか、そしてそれを
呼び出すデーモン側のソース行までのすべて:
[パリティ表](../reference/parity.md)。

## ヘルス、シャットダウン、再起動

- `HealthCheck` は 15 秒ごとに実行され、**任意扱いではありません**:
  `UNIMPLEMENTED` を含むいかなるエラーも、プラグインを死んでいるとマーク
  します。
- `Shutdown` に応答した後、あなたは終了します。猶予は 5 秒です。
- ハンドラ内の panic は捕捉され、gRPC サーバーを巻き込んで巻き戻る
  のではなくエラーとして返されます(`astra-plugin-sdk/src/panics.rs`)。
  panic は依然としてバグですが、それは障害(outage)ではありません。

## 設定

プラグインの設定は JSON であり、デーモンによって保存され、あなたの
`[config]` セクションの JSON Schema をもとに Astra の設定 UI で編集
されます。デーモンは `OnConfigChanged` でそれを届けますが、プラグイン側
からも `GetPluginSelfConfig` — パーミッションを必要としない 4 つの呼び
出しの 1 つ — で尋ねることができます。

新規インストールの最初のペイロードは `{}` です。これが SDK の設定型が
すべてのフィールドをデフォルト値にする理由です。
[config fields](../3-reference/config-fields.md) を参照してください。

設定ファイルは `<astra config dir>/plugins/<id>/config.json` です
([platforms](platforms.md) に OS ごとのディレクトリがあります)。これは
**更新を生き延びます** — 更新とは stop、install、start のことであり、
以前の install はユーザーの設定が置かれていたディレクトリを
`remove_dir_all` していました。今ではデーモンがそのファイルを保護し、
テストでそれをアサートしています(`config_survives_update`、
`astra-daemon/src/plugins/manager.rs`)。新しいアーカイブに詰め込まれた
コピーがそれを上書きすることはできません。ただしアンインストールは
**生き延びません**: `uninstall_plugin` は最終的に `remove_dir_all` を
実行します。アンインストールより長く生き延びる必要のあるものは、あなたが
所有する別の場所に置いてください。

## 各要素がどこにあるか

| もの | パス |
|---|---|
| `plugin.toml` のスキーマ | `astra-plugin-cli/vendor/astra-plugin-manifest/` — デーモンが使うクレートのバイト同一のコピー |
| ワイヤー | [`proto/plugin.proto`](../../../proto/plugin.proto)、Astra の `astra.proto` から生成された一部 |
| フック表 | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| 共有の数値 | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| バンドル形式 | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
