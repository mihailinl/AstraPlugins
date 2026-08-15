> **これは翻訳です。** 正式な情報源は [docs/en](../en/versioning.md) です。内容に食い違いがある場合は英語版が優先されます。

# バージョニングと非推奨ポリシー

番号が何を意味するか、あなたが依存しているものがどれだけの期間動き続けることを
保証されているか、そしてその保証が誰かが覚えておかねばならない口約束ではなく
データとしてどこに書かれているか、についてのページです。

## 4 つの番号、そのうち SDK 自身のものは 1 つだけ

| 番号 | どこにあるか | 何を教えてくれるか |
| --- | --- | --- |
| **SDK バージョン** | `astra-plugin-sdk/Cargo.toml`、`astra-plugin-sdk-python/pyproject.toml`、`astra-plugin-sdk-ts/package.json` | あなたが書くことになる作成用 API。各パッケージがそれぞれ自分のバージョンを持ちます |
| **リリーストレイン** | `sdk-v<VERSION>` という git タグ | 1 つのタグで 3 つの SDK すべてが同時に公開されます。このタグ名は **Rust クレート**のバージョンを名乗ります |
| **プロトコルバージョン** | `proto/PROTO_VERSION`(`protocol=1`）。各 SDK 内で `PROTOCOL_VERSION` として反映されます | プラグインとデーモンの間の通信契約 |
| **あなたのプラグインのバージョン** | あなたの `plugin.toml` | あなた自身のもの。レジストリはこれでリリースを並べます |

3 つの SDK バージョンは意図的に揃えられていません。現行のトレインは
`sdk-v0.6.0` で、公開されているのは次のものです。

| パッケージ | レジストリ | バージョン |
| --- | --- | --- |
| `astra-plugin-sdk`(Rust) | crates.io | 0.6.0 |
| `astra-plugin-macros` | crates.io | 0.6.0 — SDK が バージョン指定で依存しているため、SDK **より先に**公開されます |
| `astra-plugin-sdk`(Python) | PyPI | 0.5.0 |
| `astra-plugin-sdk`(TypeScript) | npm | 0.5.0 |

バージョン番号は「自分がどの API に対して書いているか」に答えるものなので、
破壊的リリースが少ないパッケージほど番号は小さくなります。トレインが保証する
のは、同じタグを共有するパッケージが**同じプロトコル**を話し、同じフックを
実装していることです — これが `spec/hooks.yaml` とパリティチェッカーの目的
です。

## SemVer、0.x のうちは

3 つのパッケージはすべて 1.0 未満で、SemVer の 0.x の読み方に従います。

- **マイナー**(`0.5 → 0.6`）— ソース互換性を壊す可能性があります。CHANGELOG
  を読んでください。
- **パッチ**(`0.6.0 → 0.6.1`）— バグ修正と追加のみです。パッチリリースで
  あなたのプラグインがコンパイルできなくなったなら、それは SDK 側のバグです。
  報告してください。

プロトコルバージョンは別枠で、それ自身のペースで進みます。これは整数であり
SemVer ではなく、そのルールは「CHANGELOG を読む」ではなく、次のような仕組み
です。

- 相手が持っていないフックは `UNIMPLEMENTED` を返し、プロトコルはこれを
  *存在しない*と定義します。デーモンはそう解釈して処理を続けます。これが、
  新しいプラグインが古いデーモンに対して動き、その逆も動く理由です。
- 各 SDK の `MIN_SUPPORTED_DAEMON_PROTOCOL` は、その SDK が登録可能な最古の
  デーモンです。それより古い場合、プラグインは最初の呼び出しで失敗するの
  ではなく、修正方法を名指しした文で終了します。

## 非推奨ポリシー

作成用 API の何かが廃止されようとしているとき、次のようになります。

1. **少なくとも 2 回のマイナーリリース、かつ少なくとも暦の上で 1 四半期の
   どちらか長いほう、非推奨として残ります。** 0.6 で非推奨になったものは
   0.8 で削除可能になりますが、3 か月経過する前には削除されません。今日
   ビルドできるプラグインは、計画を立てられる少なくとも 1 回のリリースを
   挟んでもビルドし続けられます。
2. **非推奨の注記は代替を名指しします。** 「非推奨です」でも「新しい API を
   使ってください」でもなく、実際に代わりに書くべき識別子、あるいは
   *代替なし*という言葉とその理由です。行き先を示さずにやめろとだけ言う
   非推奨は、あなたを issue トラッカーに送り込むだけです。
3. **削除は、削除したパッケージの CHANGELOG の `BREAKING` という見出しの
   下に、何が削除され何に置き換わったかを名指しして記載されます。** パッチ
   リリースでは何も削除されません。

各言語で「非推奨」がどう見えるか。

| | どう印がつくか | 何が見えるか |
| --- | --- | --- |
| Rust | `#[deprecated(since = "0.6.0", note = "…")]` | 使用箇所でのコンパイラ警告と、その注記 |
| Python | 呼び出し箇所での `DeprecationWarning` | `python -W error::DeprecationWarning` で CI をゲートできる失敗に変えられます |
| TypeScript | `/** @deprecated … */` | エディタ上の取り消し線と、ホバー時の注記 |

非推奨は警告であり、決してエラーではありません。あるリリースで非推奨コードが
*コンパイルできなくなった*場合、それは削除であり、削除はルール 3 に従います。

### 現在非推奨になっているもの

| 対象 | 非推奨化 | 削除 | 代替 |
| --- | --- | --- | --- |
| Rust: 0.5 のトレイト表面全体、`astra_plugin_sdk::compat` として | 0.6.0 | 0.8.0 | `PluginCapability`(0.6）: `&PluginContext`、`Result<_, ToolError>`、`type Config`。[migration-0.6.md](migration-0.6.md) を参照 |
| Rust: `PluginCapability::source_id()` | 0.6.0 | 0.8.0 | id を `Host::send_chat_message` に渡す。デーモンは source id によるフィルタを行わなくなりました |
| Rust: `compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.6.0 | 0.8.0 | `Result<String, ToolError>` |
| Rust: `compat::HostClient` / `DaemonClient` のエイリアス | 0.6.0 | 0.8.0 | `ctx.host()` / `ctx.daemon()` |
| Python: ケーパビリティのデータクラスが期待される箇所での `dict` | 0.5.0 | 0.7.0 | データクラス — `VoiceInfo`、`ToolDef` など — またはその `to_proto()` |
| TypeScript: `UiPanel` 型エイリアス | 0.5.0 | 0.7.0 | `UiContribution` |
| フック: `AiGetModels` | 0.6.0 | 0.8.0 | 代替なし — デーモンはプラグインにどんなモデルを持っているか尋ねません |

2 つの補足事項です。どちらもこのポリシーが防ごうとしている類のことだから
です。

- dict に対する Python の `DeprecationWarning` は「あと 1 回のマイナー
  リリースの間は受け付けられます」と言っています。**拘束力を持つのは表の
  数字です**: 2 回のマイナーと 1 四半期、つまり早くとも 0.7.0 です。
- `UiPanel` は TypeScript でバージョンの記録なしに非推奨になりました。ここ
  では 0.5.0 と日付づけられています — これは文書としてそう明記された最初の
  リリースです — 0.7.0 から削除可能です。

## ポリシーはデータである

文書だけに存在するルールは、それがまさに重要になる瞬間 — 誰かがその何かを
削除するリリース — に忘れられます。そのため、フックごとのポリシーの半分は
[`spec/hooks.yaml`](../../spec/hooks.yaml) の 1 列になっています。

<!-- doctest: illustrative reason="one row of spec/hooks.yaml, quoted; the file it belongs to is the source of truth and is checked by tools/parity/check.py" -->
```yaml
  - rpc: AiGetModels
    ...
    routing: deprecated
    deprecated_in: "0.6"
    removed_in: "0.8"
    note: "… Deprecated in 0.6, removed in 0.8, and there is no replacement: nothing in the daemon asks a plugin what models it has, and AiComplete carries the chosen model on the request."
```

`tools/parity/spec.py` はパースするたびにこれを検証します — つまり
`gen.py` の実行ごと、`check.py` の実行ごと、したがって CI の実行ごとに、
です。

| ルール | それが防ぐ失敗 |
| --- | --- |
| `routing: deprecated` には `deprecated_in` が必須 | 日付なしで何年も「非推奨」のままになっているフック |
| `deprecated_in` には `removed_in` が必須 | 終わりのない非推奨。それはただの失礼なコメントです |
| `removed_in` ≥ `deprecated_in` + 2 マイナー | 誰も移行するリリースを持てないうちに削除が着地すること |
| 非推奨行の `note` は別の rpc を名指しするか、`no replacement` と述べる | 転送先のない「非推奨です」 |

どれか 1 つを間違えると、チェッカーが行番号付きでそう言ってきます。

<!-- doctest: output from="python3 tools/parity/check.py on a row whose removed_in violates the policy" -->
```
spec/hooks.yaml is malformed:
  hooks.yaml:336: `AiGetModels` is deprecated in 0.6 and removed in 0.7 — the policy is
  2 minors and one quarter minimum, so the earliest removal is 0.8
```

それらの列にあるバージョンは**プロトコルバージョンではなく SDK のマイナー
バージョン**です。`0.6` はあなたの `Cargo.toml` にある番号であり、CHANGELOG
の見出しがまとめられている番号です。ポリシーの「1 四半期」の半分はデータで
はなくカレンダーによるものです — リリーストレインがその日付を決め、この
文書はそれが書き記される場所です。

## これに含まれないもの

- **デーモン自身の振る舞い。** Astra の UI、その設定レイアウト、その内部
  サービスはプラグイン API ではありません。プラグインが依拠してよいのは、
  プロトコル、`spec/hooks.yaml` にあるフック、そしてマニフェスト内の
  パーミッションです。
- **`#[doc(hidden)]`、`_private`、あるいはテストハーネス向けにエクスポート
  されているとマークされたもの。** これらはパッチリリースで変わり得ます。
- **`unrouted` なフック。** フックが proto と 3 つの SDK すべてに存在して
  いても、デーモン側の呼び出し箇所がない場合があります — 今日の時点では
  `TtsSynthesizeStream` がそれです。実装すること自体は安全でコストも
  かかりませんが、デーモンがそれを呼ぶことに*依存する*ことは、その
  `routing:` が `live` になるまでサポートされません。

## 非推奨の猶予期間で足りない場合

猶予期間が閉じる前にそう言ってください。すでに着地した削除は削除ですが、
`spec/hooks.yaml` の中でまだ `removed_in` に留まっている削除は単なる日付
であり、日付は誰かが期限内に理由を言えば動かすことができます。
