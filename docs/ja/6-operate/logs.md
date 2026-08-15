> **これは翻訳です。** 正式な情報源は [docs/en](../../en/6-operate/logs.md) です。内容に食い違いがある場合は英語版が優先されます。

# ログ

プラグインの出力が行き着く場所は 3 か所あり、どれがどれかを知っている
ことで 1 時間節約できます。

| | どこへ行くか | 誰が見られるか |
|---|---|---|
| `tracing::info!` / `logging.info(...)`(SDK のログブリッジ) | `PluginLog` としてデーモンに転送**され**、stderr にも出力される | あなた*と*ユーザー、Astra のログペインで |
| `ctx.host().log_info(...)` — 明示的な呼び出し | デーモン | あなたとユーザー |
| `println!` / 素の stderr | プロセスの stdout/stderr で、デーモンがキャプチャする | あなた、`astra-plugin logs` を通して |

このブリッジが存在する前は、これらは 2 つの異なる集合であり、興味深い
行 — panic、失敗したリクエスト、リトライ — はほぼ常にユーザーが見られ
ない側の集合にありました。

## 読む

<!-- doctest: cli -->
```bash
astra-plugin logs
astra-plugin logs dice-roller -f
astra-plugin logs dice-roller -n 500 --daemon-addr 127.0.0.1:32000
astra-plugin logs --json
```

id を指定しないと、`--path` にあるマニフェストから `plugin.id` を読み
ます。これは**インストール済み**のプラグインに対して機能します。これは
`astra-plugin dev` がまったく対応できないケースです。

デーモンはプラグインごとに**上限のあるリングバッファ**を保持しており、
`GetPluginLogs` はそれに対する単項呼び出しです — そのため `-f` は
750ms ごとのポーリングであり、「新しい」行とは、このテールのうち前回
の続きにならなかった末尾部分のことです。再起動するとバッファはリセット
されます。

バッファが保持している以上の行数を要求しても害はありません。`--json`
は 1 つのドキュメントを出力して終了します。これはスナップショット形式
であり、`-f` と `--json` を組み合わせても意味はありません。

## SDK が何を転送し、何を転送しないか

SDK がインストールする `tracing` レイヤーはデーモンに転送します:

- デフォルトでは**`INFO` 以上**。`ASTRA_PLUGIN_LOG_LEVEL` で変更でき
  ます; `DEBUG` は `RUST_LOG` と stderr のものです。なぜならペインは
  ユーザー向けだからです。
- **転送しないもの:** トランスポートスタック — `h2`、`hyper`、
  `tonic`、`tower`、`rustls`、`tokio`。ログ行を送信すること自体が RPC
  であり、ログを出す RPC はログ行を生成します: この除外がなければ、
  `h2` からの 1 つの `WARN` が無限ループになってしまいます。
- **キューが保持できる以上は転送されません。** チャンネルには上限が
  あり、送信はノンブロッキングであるため、ホットループに陥ったプラグイン
  は、自分のハンドラをデーモンに逆圧するのではなく、行を落とします。

### Python

`install_logging_bridge()` は標準の `logging` モジュールを同じように
経路づけます。`print` の代わりにこれを使ってください: SDK は stdout
を**行バッファリング**に再設定します。なぜなら、デーモンのスーパー
バイザーは stdout を読んでプラグインが生きていることを知るからであり、
以前はブロックバッファリングされた出力のせいで、スーパーバイザーが
開始タイムアウトで健全なプラグインを回収してしまうことがありました。

## CLI 自身のトレースを上げる

`RUST_LOG` は `astra-plugin` 自体を制御します。これは 0.1 から文書化
されていましたが、サブスクライバーがインストールされるまで何もして
いませんでした — CLI とその依存関係が発行するすべての `tracing` イベント
はどこにも行きませんでした。

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

デフォルトは `warn` であり、**stderr** に出力されます — CLI のユーザー
向け出力は stdout にあり、そこにトレース行があると `--json` のドキュメント
が壊れてしまうからです。

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why do I see no trace output from the CLI?
         RUST_LOG is unset, so only warnings and errors are printed.
         `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace;
         `RUST_LOG=debug` turns on its dependencies' too.
```

## ディスク上のファイル

| | Linux | Windows |
|---|---|---|
| デーモンのログ | `~/.config/astra/logs/` | `%APPDATA%\astra\astra\config\logs\` |
| CLI が解決した設定ディレクトリ | `astra-plugin doctor` に尋ねる | `astra-plugin doctor` に尋ねる |

デーモンのログファイルには日付が付きます(`daemon.log.2026-08-05`)。
プラグイン自身の行は `PluginLog` 経由でそこに現れ、その生の
stdout/stderr は `astra-plugin logs` がデーモンのインメモリバッファ
から読むものです — そのバッファはファイルではないため、デーモンの
再起動を生き延びません。

このマシンがどのディレクトリを使っているかは、想定するのではなく尋ねて
ください: `doctor` は CLI が解決したものを出力し、もし Astra がそれと
食い違うなら、両者が異なるディレクトリを解決しているということであり、
それ自体がバグです。

## ログがまったくないとき

そのプロセスは、SDK が自身のロギングをインストールする前に失敗して
います。手動で実行してください:

<!-- doctest: cli -->
```bash
astra-plugin dev --standalone
```

これはデーモンに頼む代わりに、プラグインを直接 spawn します。その方法
ではできないことを出力します — プラグインは登録できません。なぜなら
`Register` が必要とするトークンを発行できるのはデーモンだけだからです。
