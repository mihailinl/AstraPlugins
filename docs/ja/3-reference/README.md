> **これは翻訳です。** 正式な情報源は [docs/en](../../en/3-reference/README.md) です。内容に食い違いがある場合は英語版が優先されます。

# リファレンス

2 つの層があり、その違いには意味があります。

## 生成される — ずれることがない

これらは [`tools/docgen`](../../../tools/docgen/) によって、それらが
説明しているコードから生成されます。CI は
`python3 tools/docgen/gen.py --check` を実行します: チェックイン済みの
ページが再生成した結果と異なると、差分とともにビルドは失敗します。CLI の
ページは `main.rs` をパースするのではなく `astra-plugin --help` を*実行*
することで生成されます。なぜなら、clap の derive マクロのための 2 つ目の
パーサーは、ツールと静かに食い違いかねないもう 1 つの要因になるからです。

これらは 1 つ上のディレクトリ、[`../reference/`](../reference/) にあり、
そこにジェネレータが書き出します。

| ページ | 生成元 |
|---|---|
| [`plugin.toml`](../reference/manifest.md) | `astra-plugin-manifest` — デーモンがマニフェストをパースするのに使うクレート |
| [CLI](../reference/cli.md) | `clap` の定義、バイナリを実行して |
| [プロトコル](../reference/protocol.md) | [`proto/plugin.proto`](../../../proto/plugin.proto) |
| [エラー](../reference/errors.md) | 3 つの SDK すべてのエラー分類 |
| [フックの対応表](../reference/parity.md) | [`spec/hooks.yaml`](../../../spec/hooks.yaml) — 35 個のフック、3 つの SDK |

同じ仕様から描画された、SDK ごとのフック表:
[Rust](../hooks/rust.md) · [Python](../hooks/python.md) ·
[TypeScript](../hooks/typescript.md)。

## 手書き — 人によってレビューされる

2 つのページが、どんなジェネレータも型から読み取ることのできないことを
説明しています: パーミッションが、それを許可するよう求められるユーザーに
とって*何を意味するか*、そして「設定(config)」と呼ばれる 3 つの異なる
ものがどう組み合わさっているか、です。

| ページ | |
|---|---|
| [パーミッション](permissions.md) | 各 id、それが何を許可するか、`reason` の書き方 |
| [設定とフィールド](config-fields.md) | `[config]`、型付き設定、TTS/STT のフィールドフック |
| [ローカライズ](localisation.md) | `locales/<code>.json`、`$key` マーカー、英語ゲートが働く場所 — **英語のみ** |

どちらのページのすべてのコードサンプルも、CI で
[`docs/tools/doctest.py`](../../tools/doctest.py) によって実行されます。

## 規範仕様

プラグインではなく、検証ツール、パッカー、レジストリを実装する人向け
です。これらはガイドではなく、ゴールデンベクタを伴う RFC 2119 文書です。

[Bundle v2](../spec/bundle-v2.md) · [Registry index](../spec/registry-index.md) ·
[Permissions](../spec/permissions.md)
