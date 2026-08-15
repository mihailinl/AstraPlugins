> **これは翻訳です。** 正式な情報源は [docs/en](../../en/5-publish/sideload.md) です。内容に食い違いがある場合は英語版が優先されます。

# サイドロード — 開発者向けツール

> **これはプラグインのインストール方法ではありません。** サイドロード
> は、ディスク上のソースディレクトリを Astra に指し示し、それを未署名
> のまま、あなたのフルユーザーアカウントの権限でネイティブプロセスとして
> 実行します。これはあなたがプラグインを開発できるようにするために存在
> します。明示的なオプトインの背後にあり、そのオプトインはあなたの
> プラグインだけでなく、マシン上の**すべての**プラグインの敷居を下げ
> ます。
>
> ユーザーは Astra の中からインストールします。作者は
> [`init-ci` とタグ](release-with-ci.md) で公開し、その後
> [1 回だけリストに掲載してもらいます](get-listed.md) —
> [全行程は 1 ページ](../publishing.md) にまとまっています。
>
> 誰かにあなたのリポジトリをクローンしてサイドロードするよう伝えること
> は、公開することではありません。それは相手に、自分自身として未署名の
> コードを実行するよう頼むことであり、届く範囲はあなたが直接話せる人
> だけです。

自分が書いた、あるいは監査していないプラグインは決してサイドロードしない
でください。誰かがディレクトリと開発者モードを有効にする手順を送って
きたなら、それはあなたに、自分自身として彼らのコードを実行するよう
頼んでいるのです。

## 有効にする

`safety.allow_unsigned_plugins` が true でない限り、サイドロードは
拒否されます。デーモンはまさにその言葉でそう言います:

<!-- doctest: illustrative reason="the daemon's refusal, quoted from astra-daemon/src/plugins/manager.rs; reproducing it needs a running Astra with the setting off" -->
```
Sideloading is disabled. It runs an unsigned local plugin as native code with
your full privileges. Turn on Settings -> Privacy -> "Allow unsigned plugins"
(`safety.allow_unsigned_plugins`) to sideload (local plugin development only).
```

CLI はそれを、修正方法を自身の行に持つ同じ指示に変換します
(`astra-plugin-cli/src/daemon.rs`)。この 2 つのメッセージは設定内の
異なるセクション名を挙げています — デーモンは Privacy と言い、CLI は
Safety と言います。**設定キーは `safety.allow_unsigned_plugins`**
であり、検索すべきはこれです。

## 使う

[CLI](../install-cli.md) からの 1 つのコマンドです:

<!-- doctest: cli -->
```bash
astra-plugin dev
astra-plugin dev . --daemon-addr 127.0.0.1:32000
```

`dev` は順番に 4 つのことを行い、最初の失敗で止まります:

1. `astra-plugin check --strict` — すでに不正なマニフェストをデーモン
   に渡すことはありません;
2. ビルドします;
3. **ディレクトリ**を `SideloadPlugin` 経由でデーモンに渡します。
   デーモンはプロセスを spawn し、その認証トークンを発行し、それ以降
   そのライフサイクルを所有します;
4. 変更を監視し、再ビルドし、プラグインを停止/開始し、その出力を追跡
   します。

<!-- doctest: output from="astra-plugin dev . with no Astra running" unrun="needs a machine with no Astra daemon listening, which a CI runner cannot promise either way" -->
```
Dev mode: plugin 'dice-roller'
  Directory: /tmp/dice-roller
Checking plugin at /tmp/dice-roller...
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 2.48s
Error: Could not read /home/you/.config/astra/daemon.token. Astra does not look
like it is running — start the app first.
```

**デーモンがプロセスを所有しており、これはスタイルの問題ではありません。**
プラグインは、デーモンがそのプロセスを spawn するときに発行するトークン
で `PluginHostService` に認証し、デーモンは自分が発行していないトークン
を運ぶ `Register` をすべて拒否します。CLI が spawn したプラグインには
それを得る手段がありません — これが置き換えた、自己 spawn する dev
ループは、誰とも話さないプロセスを起動していました。

`--standalone` はその古い挙動を、それがまだ有用な場合(バイナリが起動
するかの確認、手動での駆動)のために残しますが、その方法ではプラグイン
が Astra に登録できないことを最初に明言します。

`dev --json` は意図的に拒否されます: `--json` は 1 回の実行につき 1 つ
のドキュメントを約束しますが、`dev` は決して終了しません。
`astra-plugin check --json`、`astra-plugin test --json`、
`astra-plugin logs --json` が、これが行うことの機械可読な半分です。

## サイドロードの正確なコスト

| | |
|---|---|
| **署名** | なし。コードを保証するものは何もありません |
| **権限** | あなたのフルユーザーアカウント。サンドボックスはありません — [フェーズ 7 は存在しません](../1-orientation/security.md) |
| **スイッチの影響範囲** | `allow_unsigned_plugins` は、後でインポートする未署名ファイルも含め、マシン上のすべてのプラグインに適用されます |
| **自動起動** | **決してしません。** 開発者モードはロード時に必要であり、再起動するとサイドロードされたプラグインは、あなたが再度起動するまで止まったままです |
| **パーミッションの上限** | **なし** — 下記参照 |
| **ユーザーに表示される来歴** | 来歴パネル内のティア `sideloaded` — 「フォルダから読み込まれた」 |

### なぜここにパーミッションの上限がないのか

[ローカルでインポートされた `.astraplugin`](local-install.md) は 4 つの
パーミッションが無条件で拒否されます。サイドロードされた**ソース
ディレクトリ**はそうではなく、この例外は見落としではなく意図的なもの
です: これは UI プラグインの作成用ループであり、`dom_access` はまさに
`companion`、`doom`、`bad-apple` が必要とするものです。ティア 3 に
上限を設けると、これらは開発不可能になってしまいます。

その代償として、ティア 3 は明示的な設定によってゲートされ、決して
自動起動せず、あなた自身が指し示したディレクトリです — これら 3 つの
事実は、ティア 2(どこかから届いたファイル)には言えないことです。

計画には、`dom_access` が有効になっているときは常に、プラグインカード
とウィンドウの chrome 上に恒久的で消せない「DEVELOPER — unverified
code from a local directory」バッジを表示することも求められています。
**そのバッジは今日 UI にはありません**。このページはそれがあると
主張してはいません。

## 動作しないこと、そしてこれからも動作しないこと

**プラグインディレクトリに `sideload.json` マーカーを手書きすること。**
デーモンは、自分が許可した記録を持たないマーカーを拒否します:

<!-- doctest: illustrative reason="a daemon log line, quoted from astra-daemon/src/plugins/manager.rs; it is emitted on a machine with a planted marker" -->
```
Refusing sideload marker in <path>: this daemon never authorised a sideload of
'<id>' from <source> (no matching record in <registry path>). A marker file
alone does not authorise running unsigned native code.
```

古い指示では、作者に `~/.config/astra/astra/plugins` にマーカーを
置くよう伝えていましたが — これは存在しないパスであり、しかももう
機能しない仕組みの上に、`allow_unsigned_plugins` の前提条件にも言及
せずに、です。これらは修正されるのではなく削除されました。代替は
1 行です: `astra-plugin dev`。

## 開発が終わったら

この経路は、他の人がインストールできる何かを一切生み出しません。
出荷するには:

1. [`astra-plugin init-ci`](release-with-ci.md)、そしてタグ — CI が
   ビルドし証明します;
2. [`astra-plugin publish`](get-listed.md) — 1 回だけ、それきり;
3. ユーザーは Astra の中からインストールし、ダイジェストが固定されます。

開発していないときに `allow_unsigned_plugins` を元に戻しておくことは、
2 回のクリックの価値があります。
