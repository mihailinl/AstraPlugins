> **これは翻訳です。** 正式な情報源は [docs/en](../../en/2-tutorial/getting-started.md) です。内容に食い違いがある場合は英語版が優先されます。

# はじめに

サイコロを振り、テストがあり、リリース用にパッケージ化されたプラグインまで
ゼロから。だいたい 15 分、そのほとんどは `cargo` の待ち時間です。

このページのすべてのコードブロックは CI で
[`docs/tools/doctest.py`](../../tools/doctest.py) によって実行されます。
どれか 1 つでも間違っていれば、あなたが読む前にビルドは red になります。

## 1 · CLI をインストールする

1 行です。数分かかり、最後にバージョンを出力して終わります。

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

この番号は意図的なプレースホルダです。`--git` は実行時点で `master` が持って
いるコミットをビルドするので、表示されるのはあなたが選んだ番号ではなく、その
コミットのバージョンです。

クローンからなら `cargo install --path astra-plugin-cli --locked` で同じ
ことができます。

**Rust 1.85 以降と、`PATH` 上の `protoc` が必要です。** `protoc` が
なければ、ビルドは ``Could not find `protoc` `` で止まります。
`apt install protobuf-compiler`、`pacman -S protobuf`、
`brew install protobuf`、または `winget install Google.Protobuf` で
インストールしてから、もう一度この行を実行してください。

**バージョン番号ではこのビルドが良いものだと判断できませんし、`0.2.0` が悪い
ビルドだというわけでもありません。** `init-ci` はかつて、GitHub がコミットを
必要とする箇所にタグ*オブジェクト*を固定しており、プラグインの最初の
`git push --tags` はそこで死んでいました。修正はコミット `5b8ab22` で、これは
番号を `0.2.1` に上げたバージョン更新よりも*前*に `master` へ入りました — つまり
`master` からのビルドは修正を含みながら `0.2.0` と表示することがあり、修正を
欠く `0.2.1` は存在しません。今日 `master` からインストールすれば、番号が何で
あれ修正は入っています。信じるのではなく確かめるには、`astra-plugin init-ci` を
実行して表示されるピンを読んでください —
`e3329df252a46d747676cb540ae4b986af68a3ad` がコミットで、これが正しいもの。
`dc1a044876926e9cf1170f034e2eab533ec07641` はタグオブジェクトで、これがバグです。
詳しい説明:
[CLI をインストールする](../install-cli.md#最初のリリースを壊すバグと自分のビルドに修正が入っているかの見分け方)。

補足で、これ自体はあなたをブロックしません: CLI は crates.io になく、
ビルド済みバイナリもないため、ビルドすることが入手する唯一の方法です。
ビルド済みバイナリは計画されています。うまくいかないときにどうするかを
含む詳細: [CLI をインストールする](../install-cli.md)。

コードのせいにする前に、マシンを確認してください。

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

これは 1 回のパスで 16 個の質問に答えます — どの CLI を実行しているか、
どの設定ディレクトリを解決したか、Astra に到達可能か、どのツールチェーン
を持っているか(`protoc` を含む)、リリースワークフローがピン留めされて
いるか。何かが混乱しているときに最初に実行すべきものです。

## 2 · 雛形を作る

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

6 つのファイル:

<!-- doctest: illustrative reason="an annotated tree of what `astra-plugin new` wrote, not a command; the run that produced it is the output block above" -->
```
dice-roller/
├── plugin.toml      マニフェスト — id、バージョン、ケーパビリティ、エントリポイント
├── Cargo.toml       依存は 1 つ、そしてなぜ 1 つだけなのかの長いコメント
├── src/main.rs      プラグイン本体: 15 行と、テストモジュール
├── README.md        ストアがあなたのプラグインの隣に表示するもの
├── icon.svg         差し替える前提のプレースホルダのアイコン
└── .gitignore       `target/` と `*.astraplugin`
```

`README.md` と `icon.svg` は飾りではありません。パッカーは両方を名前で拾い、
レジストリは検証済みバンドルからそれらを読み出して、あなたのリスティングの
カードとページを組み立てます。これらは、人がインストールを決める前に目にする
ものです。公開する前に差し替えてください —
[一覧に載せる](../5-publish/get-listed.md) がそれぞれに何が必要かを説明します。

`--lang` は `rust`、`python`、`typescript` を取り、`--template` は
ケーパビリティとサンプルコードを選び、`--capabilities tools,triggers` は
テンプレートが何を含意していようとそれを上書きします。

### 雛形が固定するもの

| 言語 | 雛形が固定するもの | 公開されているもの |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

これらはレジストリから解決されるため、`cargo build`、
`pip install -r requirements.txt`、`bun install` は、何も設定しなくても
新規プロジェクトで動作します。

**下限バージョンは意味を持っています。** Rust 0.6 は `HostClient` が
`x-session-token` を付加する最初のリリースであり、Python と TypeScript
の 0.5.0 もそれぞれ同様です。それより古いものに対しては、デーモンは
すべてのホスト呼び出しに `unauthenticated` を返します。下限を緩めることは、
リゾルバのエラーを実行時のエラーに交換することであり、これはより悪い
取引です — プラグインは起動し、フックには応答するのに、静かに応答を
返せなくなります。

Python: `astra-plugin test` は `PATH` 上にある `python` を使ってあなたの
プラグインを実行するため、先にインストール先の virtualenv を有効化して
ください。そうしなければ、プラグインは登録される前に
`ModuleNotFoundError: astra_plugin_sdk` で終了します。

## 3 · プラグインを書く

`src/main.rs` をこれに置き換えます。これがプラグインのすべてです — 型付き
の引数、ツール、トリガー、そして 3 つのテストです。

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

5 つ、名指しする価値があります。

- **`#[derive(Deserialize, JsonSchema)]` ではなく `#[astra::args]`。**
  serde の derive は `extern crate serde` を発行し、これは extern
  prelude を経由して解決されるため、re-export 経由では到達できません
  — つまり素の derive を使うには *あなたの* `Cargo.toml` に `serde`
  が必要になり、それこそ雛形が「あなたには不要だ」と約束していることの
  1 つです。`#[astra::args]` は、この 2 つの derive を SDK 自身のコピー
  に向けたものです。
- **doc コメントはモデルが読む説明です。** ツール自体にも、各フィールド
  にも当てはまります。ツールがどう動くかではなく、いつ使うべきかを
  書いてください。
- **ハンドラは `Result<_, ToolError>` を返します。** 呼び出しごとの失敗は
  *データ*です: AI ループはそれを読んで何をするか決めるため、gRPC
  ステータスとしてではなくレスポンスの中を伝わっていきます。`?` は
  `serde_json::Error`、`std::io::Error`、`tonic::Status`、
  `anyhow::Error` に対して機能します。
- **`ctx.host()` は常にそこにあります。** コンテキストはホストクライアント、
  UI の言語、有効なトリガー集合を運びます。バックグラウンドタスクに
  クローンするコストは低く、`None` になることは決してありません。ロック
  の背後に何かを構造体に持つ必要はありません。
- **`h.host().deny("fire_trigger")` は拒否を仕込みます。** これが同意
  しなかったユーザーの姿であり、テストする価値があります — そうしなければ
  それはあなたの issue トラッカーが受け取ることになる失敗です。

`cargo test` は、記録用ホストに対してこの 3 つを実行します: デーモンなし、
ソケットなし、Astra のインストールなしです。

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · 必要なものを宣言する

このツールは `fire_trigger` を呼び出しており、`[permissions]` はデフォルト
拒否であるため、申請しなければなりません。`reason` は、Astra がユーザーに
同意を求めるときにユーザーが読む文言です — パーミッションについてでは
なく、*あなたのプラグイン*について、1 文で書いてください。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

それから確認します。

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` はデーモン自身のパーサー — 同じクレートで、vendor され、バイト
同一に保たれています — でマニフェストを読むため、インストール時に実際に
起こることと食い違うことはあり得ません。`--fix` は証明できる修正を適用
し、残りを報告します。

## 5 · 適合性スイートを実行する

<!-- doctest: cli -->
```bash
astra-plugin test
```

これは `cargo test` より 1 段上のレベルです: デーモンがそうするのと同じ
方法で、`PluginHostService` を提供するモックデーモンに対してあなたの
プラグインを起動し、宣言されたケーパビリティが含意するすべての受信側
フックを呼び出します。

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

`GetPluginTriggerTypes` は、プラグインがトリガーを発火するにもかかわらず
**0** を報告します。発火することと*提供すること*は別のことです: コマンド
エディタは、プラグインが宣言しているもの — つまり
`#[hook] async fn trigger_types(&self) -> Vec<TriggerTypeDef>` — を
一覧表示しますが、上のプラグインにはそれがありません。
`--capabilities tools,triggers` で雛形を作れば、そのフックはあなたの
代わりに書かれます。§3 では、ファイルを 1 画面に収めるためにそれを
省いています。宣言せずに発火しても、トリガーは実際に発火します — しかし
誰もコマンドをそれに配線できません。

`required` なフックは `UNIMPLEMENTED` を返してはいけませんが、
`optional` なフックはそれが許されます。なぜならワイヤー上では
`UNIMPLEMENTED` は「このフックは存在しない」ことを*意味する*からです。

## 6 · Astra の中で実行する

このステップには実行中の Astra と**開発者モード**が必要です。なぜなら
未署名のディレクトリをサイドロードするからです。

<!-- doctest: cli -->
```bash
astra-plugin dev
```

これは `check --strict` を実行し、ビルドし、そのディレクトリをデーモンに
渡します — デーモンがプロセスを spawn し、そのトークンを発行し、その
ライフサイクルを所有します — その後、変更を監視し、再ビルドし、再起動し、
ログを追跡します。

開発者モードを有効にする前に[サイドロード](../5-publish/sideload.md)を
読んでください。これは開発者向けツールです: あなたのフルユーザー権限で
未署名のローカルコードを実行し、そのスイッチはこのプラグインだけでなく
マシン上のすべてのプラグインに対して敷居を下げます。これは誰かがプラグイン
をインストールする方法ではありません。

`dev` が Astra に到達できない場合、`astra-plugin doctor` が、デーモンが
動いていないのか、それとも CLI とは異なる設定ディレクトリを解決したのか、
どちらが問題かを教えてくれます。

## 7 · パッケージ化する

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" unrun="needs a scaffolded, compiled plugin on disk; re-run it in the project this page builds" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` は `build` がたった今書いたものを読み直し、別の問いに答えます:
`MANIFEST.json` がエントリ 0 で無圧縮(stored)であること、ファイル一覧が
両方向で網羅的であること、そして一覧にあるすべてのダイジェスト、サイズ、
モードがアーカイブと一致すること、です。誰がそれを書いたかについては
何も言いません — それはレジストリの仕事です。

ファイル名は飾りではありません: `<id>-<version>-<target>.astraplugin`
は、公開されるバンドルが持たなければならない名前であり、target の部分は
レジストリのプラットフォームキーです。

**`build` は署名しません。あなたに鍵は不要です。** Astra にプラグインを
インストールさせるのは、ファイル全体の sha256 に副署名するレジストリ
レコードであって、あなたが持つどんな鍵でもありません。
[セキュリティモデル](../1-orientation/security.md) を参照してください。

## 8 · 公開する

さあ重要な部分です。たった 2 つのコマンドです。

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` は、Astra の再利用可能なリリースワークフローに対してコミット
SHA でピン留めされた `.github/workflows/release.yml` を書き出します。
それ以降、**タグがリリースプロセスのすべてです**: CI がすべてのターゲット
をビルドし、GitHub のビルド来歴で各バンドルを証明し、GitHub Release に
添付します。

その後は 1 回きりの提出で、それ以降のすべてのリリースはノータッチに
なります。

公開が**何ではないか**に注意してください: このリポジトリを GitHub に
push してもあなたのプラグインは公開されませんし、たった今ビルドした
`.astraplugin` を誰かに送っても同じです。レジストリは CI が生成した
ファイルのダイジェストを固定し、それに添付されたビルド証明を読みますが、
あなたのラップトップでビルドされたファイルにはそのどちらもありません。

**→ [プラグインを公開する](../publishing.md)** — ここからリスト掲載
済みプラグインまでの全行程を 1 ページで、すべてのコマンドとその期待される
出力とともに。その先にある各層のページ:
[CI でリリースする](../5-publish/release-with-ci.md) ·
[リストに掲載してもらう](../5-publish/get-listed.md)

## Python での同じもの

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

エントリポイントは `[entry] command = "python"`、
`args = ["-m", "src.plugin"]`、`runtimes = ["python"]` であり、バンドル
は `noarch` です。

## TypeScript での同じもの

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## 次にどこへ行くか

| 知りたいこと | 読むもの |
|---|---|
| Rust の API 全体 | [Rust SDK](../4-sdk/rust.md) |
| すべての `plugin.toml` のキー | [マニフェストリファレンス](../reference/manifest.md) |
| すべての SDK のすべてのフック | [パリティ](../reference/parity.md) |
| 出荷する方法 | [CI でリリースする](../5-publish/release-with-ci.md) |
| 何かが壊れている | [トラブルシューティング](../6-operate/troubleshooting.md) |
| 実際に動くサンプル | [サンプル](../7-examples/README.md) — 11 個 |
