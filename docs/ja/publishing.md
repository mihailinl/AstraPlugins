> **これは翻訳です。** 正式な情報源は [docs/en](../en/publishing.md) です。内容に食い違いがある場合は英語版が優先されます。

# プラグインを公開する

**1 ページで、空のディレクトリからユーザーがインストールできるプラグインまで。**
すべてのコマンドが順番どおりにここにあり、それぞれの出力も添えてあります。公開に
ついて 1 ページだけ読むならこのページを読んでください。より深いページは関係する
箇所でリンクしていますが、どれもこのページを終えるのに必須ではありません。

---

## 他は読まなくてもここだけは読んでください

Astra にプラグインを公開するとは、**1 つの具体的なこと**を意味します。自分の
GitHub リポジトリでリリースにタグを打つと、GitHub の CI がバンドルをビルドして
証明し、あなたはレジストリに 1 回だけ、それきりリスティング申請を送ります。

以下は公開**ではありません**。それぞれ実際に試みられたことがあります。

| 公開ではないもの | うまくいかない理由 |
|---|---|
| ソースを GitHub に push する | レジストリはあなたのソースツリーを一切読みません。リリースに添付された `.astraplugin` ファイルを読みますが、それが存在しません |
| `.zip` を誰かに送る、あるいは自分のラップトップでビルドしたバンドルを送る | そのバイト列にはビルド証明が付いておらず、プラグインの出来がどれだけよくてもレジストリは拒否します |
| メンテナーに「代わりにビルドしてほしい」という issue を開く | あなたのリポジトリ自身の CI 以外、誰もあなたのプラグインをビルドしません。他にビルドする者はいません |
| リスティングフォームを通さずに、プラグインの説明を書いた issue をレジストリに開く | `listing` ラベルを付けるのはフォームだけで、取り込みを始めるのはそのラベルだけです。ブランク issue は現在は無効化されており、ラベルなしの申請には沈黙ではなくラベル名を挙げた返信が付きます — ただし返信は掲載ではありません。[提出する](#8--1-回だけ提出する) を参照 |

**なぜそうでなければならないか、2 文で。** レジストリは、ユーザーがダウンロード
することになる正確なファイルの SHA-256 でプラグインを固定し、GitHub のビルド
証明 — ワークフロー自身の OIDC アイデンティティから発行される Sigstore 署名 —
を読み取り、それがどのワークフローの、どのコミットの、どのリポジトリから出た
正確なバイト列であるかを確認します。自分のラップトップでビルドして誰かに渡した
ファイルには、そのどちらもありません。したがって、ユーザーのマシン上で Astra が
チェックできるものも、レジストリが固定できるものも何もありません。

これはどれも、あなたのコードが安全であるという主張ではありません。このページ末尾の
[何が信頼を確立するか](#何が信頼を確立するか) を参照してください。

---

## 始める前に

<!-- doctest: cli -->
```bash
astra-plugin --version
```

何も表示されない場合は、ここで止まって先に **[CLI をインストールする](install-cli.md)**
を行ってください。今ではビルド済みバイナリがあります — Linux か Windows 用の
アーカイブをダウンロードし、`SHA256SUMS.txt` と照合すれば、ツールチェーンは一切
不要です。ソースからのビルドも引き続き動作し、macOS と ARM Linux ではそちらが唯一の道です。
`cargo install astra-plugin-cli` はそもそも道ではありません — そのページに理由が
書かれています。

> **ビルドの健全さをバージョン番号から読み取らないでください。** コミット
> `5b8ab22` より前にビルドされた CLI は、最初のタグを push した瞬間に GitHub が
> 拒否するリリースワークフローを書き出します。この修正は `0.2.1` への番号更新
> よりも*前*に `master` へ入ったため、修正を含みながら `0.2.0` と表示する
> ビルドがありえますし、修正を欠く `0.2.1` は存在しません。今日 `master` から
> インストールすれば、番号が何であれ修正は入っています。実際に決着をつけるのは
> `init-ci` が表示する SHA であり、このページでは
> [ステップ 3](#3--リリースワークフローを設定する) でそれを実行します。

また **公開の** GitHub リポジトリが必要です。証明(attestation)は公開の透明性ログ
(transparency log)に発行されます。プライベートリポジトリでは GitHub Enterprise
が必要で、リリースワークフローは、証明のないバンドルを黙って生成するのではなく、
その旨をはっきり伝えてきます。

---

## 1 · 雛形を作る

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

`--lang python` と `--lang typescript` は他の 2 つの SDK で雛形を作ります。
`--template` は何をベースに始めるかを選びます(`tool`、`tts`、`stt`、
`stt-streaming`、`ai-provider`、`ui`、`action-trigger`、`client`、`blank`)。
プラグイン本体を書くことは [はじめに](2-tutorial/getting-started.md) と
[SDK のページ](4-sdk/rust.md) の話です。

**先に進む前に `plugin.toml` の 2 つのフィールドを埋めてください。** 雛形は
`author` を空のまま、`description` を汎用的な文言のままにしており、どちらも
あなたのストアカードに表示されます。

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

雛形が書き出す `icon.svg` はプレースホルダーです。差し替え方は
[リストに掲載してもらう §リスト掲載がどう見えるか](5-publish/get-listed.md#あなたのリスト掲載がどう見えるか)
にあります。

## 2 · 動くことを証明する

<!-- doctest: cli -->
```bash
astra-plugin test .
```

これは適合性(conformance)スイートで、あなたのテストファイル内の型に対してでは
なく、**実際のプロセス**として実行されたあなたのプラグインをモックデーモンと
対話させて実行します。判定部分だけ抜粋すると次のとおりです。

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

代わりに実際に動いている Astra の中で動かすには `astra-plugin dev .` を使います
— それが[サイドロード](5-publish/sideload.md)であり、開発中のループであって、
他の誰かにプラグインを渡す方法**ではありません**。

## 3 · リリースワークフローを設定する

YAML を自分で書く必要はありません。1 つのコマンドがやってくれます。

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

このコミット SHA は飾りではありません。これはリリース済みの再利用可能ワークフロー
`plugin-release/v1` が指す先そのものであり、レジストリの root 署名済み
`trust.json` が許可する SHA の 1 つです — 他のワークフローで生成されたビルドは
`E_WORKFLOW_NOT_ALLOWED` で拒否されます。ピンを進めたいときはいつでも `init-ci`
を再実行してください。設定した入力値は保持されます。

**先に進む前に、表示された SHA を確認してください。** それは
`e3329df252a46d747676cb540ae4b986af68a3ad` でなければなりません。もし
`dc1a044876926e9cf1170f034e2eab533ec07641` であれば、あなたの CLI はコミット
`5b8ab22` より古いものです。それは `plugin-release/v1` の*タグオブジェクト*の
SHA であり、`uses: …@<sha>` はコミットを必要とするため、最初の
`git push --tags` はジョブが始まる前に `invalid value workflow reference` で
失敗します。やる価値があるのはこの確認です。修正は番号が変わるより前に
`master` に届いたので、バージョン番号ではこの問いに答えられません。
[CLI をインストールする](install-cli.md)
の `cargo install` の行を再実行し、それから `astra-plugin init-ci` をもう一度
実行してください — ピンを書き換え、入力値は保持されます。既存のファイルはその場で
修復されないため、既存の `release.yml` は再実行するまで悪い SHA を保持し続けます。
これが実在する著者の最初のリリースを壊したバグです。

生成されるファイルの中身と、その 3 つの権限それぞれがなぜ必要かについての詳細は
[CI でリリースする](5-publish/release-with-ci.md) にあります。

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` は機械的に直せるものをすべて修正します。`--resolve-pin` は、あなたの
ワークフローピンが今も最新かどうかを GitHub に問い合わせます。`dev` にも CI にも
チェックを走らせるのにネットワークが不要であるように、デフォルトでは無効です。

## 4 · push する、公開で — 所有権ファイルとともに

<!-- doctest: cli -->
```bash
mkdir -p .well-known
echo 'your-github-login' > .well-known/astra-plugin-owner
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

このステップに特別なことは何もありません — ごく普通のリポジトリです。ただし、
これが*何ではないか*に注意してください。これを push することはプラグインを
公開することではなく、このページのきっかけとなった 2 件の実際の申請はここで
止まってしまったことが誤りでした。公開済みプラグインにするのは次のステップの
タグです。

**冒頭に追加された 2 行が所有権の証明であり、これは省略できません。**
`.well-known/astra-plugin-owner` は、あなたのデフォルトブランチ上に、あなたの
GitHub ログインを 1 行につき 1 つ保持します。これは、リスト掲載を申請している
人物が掲載対象のリポジトリを制御していることをレジストリが確立する方法であり、
ビルド証明では言えない唯一のことです。どうせコミットするついでに今のうちに
作成しておけば、ステップ 8 は 1 回目で通ります。

これを省くと、最初の提出は `E_OWNERSHIP_UNPROVEN` で拒否されます。なぜなら、
より強い 2 つのチェックは普通のリポジトリでは答えられないからです: GitHub は、
可視性を持たないリポジトリの `admin` を誰が持っているかレジストリが尋ねると
`403` を返しますし、リリースの作者は `github-actions[bot]` です — ステップ 3
のワークフローがリリースを公開するのであって、あなたではありません。詳しい
説明は
[リストに掲載してもらう §2](5-publish/get-listed.md#2--リポジトリを制御していることを証明する)
にあります。

## 5 · タグを打つ — これがリリースです

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

`astra-plugin version` は `plugin.toml` **と**プロジェクト内の他のすべての
マニフェスト — `Cargo.toml`、`package.json`、`pyproject.toml` — を 1 回の
編集で書き換えるため、それらが食い違うことはありません。現在のバージョンより
順序が下がるバージョンは、`--allow-downgrade` を渡さない限り拒否されます。
Astra はダウングレードのインストールを拒否するため、そのようなリリースは
インストール不可能になってしまうからです。

**タグがリリースプロセスのすべてです。** タグを push すると `release.yml` が
起動し、それがピン留めされた再利用可能ワークフローを呼び出し、それが 3 つの
ジョブを実行します — マニフェストをデータとして読むだけであなたのコードを一切
実行しない `plan` ジョブ、あなたのコードを実行するが書き込みトークンを一切
持たない `build` マトリクス、そしてすべてのダイジェストを自分で再計算し、
自らハッシュした内容を証明する `publish` ジョブです。この分割こそがセキュリティ
特性であり、[CI でリリースする §3](5-publish/release-with-ci.md#3--ci-が行うこと)
に説明があります。

完了すると、あなたの GitHub Release には次のものが付きます。

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

Release は、すべてのアセットが添付されて初めて表示されるようになります。Rust
プラグインはプラットフォームごとに 1 ファイル、TypeScript と Python は単一の
`noarch` ファイルになります。

**ワークフローがまったく走らなかった場合**、よくある原因は `on: push: tags:`
と `tag-prefix:` が食い違っていることです — prefix より狭い glob は決して
発火しません。それ以外の失敗パターンは
[CI でリリースする §うまくいかないとき](5-publish/release-with-ci.md#うまくいかないとき)
にあります。

## 6 · リリースを自分で確認する

Astra やレジストリを信用せずとも、誰でもできます。

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

`astra-plugin verify` は、バンドルが不正なときは **1**、CLI が判定できなかった
とき(例えばファイルが見つからないとき)は **2** で終了します。アーカイブ形式と
検証ツールが拒否すべき内容は [`spec/bundle-v2.md`](spec/bundle-v2.md) にあります。

## 7 · 掲載申請の事前確認をする

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

これはローカルで実行できるレジストリのチェックをすべて実行し、そのうえで —
重要な半分ですが — レジストリでしかできないチェックを名指しし、まだ証明されて
いないものが何かをあなたに教えます。

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that `.well-known/astra-plugin-owner` on your default branch names the account opening the listing request
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

このリストの中で、あなた自身の作業が決めるものは所有権の行であり、それは
[ステップ 4](#4--push-する公開で--所有権ファイルとともに)で行いました。
残りは、ワークフローがビルドしたリリースにタグを打ったことから導かれます。

## 8 · 1 回だけ提出する

**これを実行する前に**、[ステップ 4](#4--push-する公開で--所有権ファイルとともに)
の所有権ファイルがデフォルトブランチにあることを確認してください。これは、
他のすべてを正しく行っていても失敗しうる、このページで唯一のチェックです:

<!-- doctest: illustrative reason="gh against the author's own repository; `cli` blocks must contain an astra-plugin command, and this one is deliberately shell-only" -->
```bash
gh api repos/you/dice-roller/contents/.well-known/astra-plugin-owner \
  --header 'Accept: application/vnd.github.raw+json'
```

これはあなたのログインを表示するはずです。`Not Found (HTTP 404)` は、
レジストリもそれを見つけられないことを意味します。

<!-- doctest: cli -->
```bash
astra-plugin publish
```

これはブラウザで**あらかじめ内容が入力された issue** をレジストリ上に開きます。
何もアップロードせず、資格情報も一切保持しません — `astra-plugin login` は
存在せず、シェル履歴にトークンが残ることもなく、連携すべきキーリングもありません。
`--print-url` はブラウザを開く代わりにリンクを表示します。

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **そのリンクを使ってください。** その中の `template=plugin-listing.yml` は
> 意味を持っています。issue テンプレートは `labels: ["listing", "needs-triage"]`
> を宣言しており、レジストリの bot は `listing` ラベルが付いた issue に対して
> しかサブミッションパスに入りません。それを付けるものは他にありません — bot
> 自身も、意図的に付けません。あのリポジトリではこのラベルは分類ではなく権限の
> トークンだからです。
>
> 以前はこれが黙って失敗していました。実在する著者からの 2 件の申請がラベルなし
> で届き、トリアージは `mode: "none"` を返し、チェック・公開・コメントのどの
> ステップもスキップされ、**拒否ですらなく、まったく何の応答もありませんでした** —
> それがこのページの存在理由です。今はその両方が塞がれています。レジストリは
> ブランク issue を無効化したのでフォームが唯一の入り口であり、それでもラベル
> なしで届いた申請には、ラベル名と、同じ issue 上で検証を開始させるワンクリック
> を挙げたコメントが付きます。それでもこのリンクを使ってください。誰も介入せずに
> 取り込みが始まる経路はこれです。

この提出には **2 つの事実** — あなたのソースリポジトリ(`you/dice-roller`)と
リリースタグ(`v0.1.0`) — と、3 つの必須確認事項 — `.well-known/astra-plugin-owner`
をデフォルトブランチにコミットし、そこに自分のログイン名があること、あなたが
そのリポジトリの所有者またはメンテナーであること、ポリシーを読んだこと — が
含まれます。それ以外は
すべて証明済みバンドルから読み取られます。バンドル内のすべてが証明の対象と
なっているため、フォームに入力された何よりも厳密に価値が高いからです。

## 9 · そのあと何が起きるか

詳細と理由コードの全一覧は [リストに掲載してもらう §提出後に何が起きるか](5-publish/get-listed.md#4--提出後に何が起きるか)
にあります。要約すると次のとおりです。

| 結果 | 意味 | 誰が関わるか |
|---|---|---|
| **公開済み(Published)** | コミット済みで、次のインデックスビルドでカタログに載る | 誰も関わらない |
| **遅延(Delayed)** | すべて通過。指定された時刻に自動的に公開される | 誰も関わらない |
| **保留(Held)** | レジストリが自動で下してよい判断ではない | メンテナーが **48 時間以内**に対応 |
| **拒否(Refused)** | いずれかのチェックが失敗した | あなた: 直して issue に `/recheck` とコメントする |

**最初のリスト掲載は必ず人による保留になります** — これは、新たに要求された
高リスクパーミッションおよびリポジトリの変更と並んで、人の判断が必要な
ちょうど 3 つのイベントのうちの 1 つです。48 時間はそのすべてに対して公表
されている SLA です。

保留は、メンテナーがあなたの issue に `/approve` とコメントすることで解除
されます。これはキャッシュされた何かを信用するのではなく、すべてのチェックを
ゼロからやり直します。あなたがそのコマンドを打つことはなく、待っている間に
すべきこともありません。[保留がどう解除されるか](5-publish/get-listed.md#保留はどう解除されるか)
を参照してください。

bot はいずれの場合も結果と理由をあなたの issue にコメントします。そして今では、
処理を*開始しない*とき — つまりステップ 8 で説明した失敗のとき — にもコメント
します。1 時間経ってもコメントが付かない場合は `listing` ラベルを確認して
ください。付いていなければ、メンテナーに付けてもらってください。ラベル付けは
新規申請と同じイベントを発生させるので、その issue 上で検証が始まり、打ち直す
ものは何もありません。

## 10 · それ以降のすべてのリリース

何もありません。タグを打てば、あとは CI がやってくれます。レジストリがリリース
に気づき、インデックスを再生成します。

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

数分経ってもレジストリが気づいていない場合。

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

これは**すでにリストに掲載されている**プラグイン向けの手動 ping です。
`--notify` を付けないと、`publish` は代わりに最初のリスティング申請を開いて
しまいます。2 回目以降のリリースではそれは望むものではありません。

---

## 何が信頼を確立するか

`astra-plugin build` がここにリンクしているため、そのリンクが動かなくなるまでは
この見出し(アンカー)に答えを置いておきます。

**あなたが持つどんな鍵でもありません。** `astra-plugin keygen` と
`astra-plugin sign` は任意の第 2 要素を生成します — GitHub アカウントの乗っ取り
に対して有用です。なぜならその鍵は、盗まれた GitHub セッションが存在し得ない
場所にあるからです。しかし Astra はそれをあなたの鍵に対して検証するわけでは
ありません。デーモンは ZIP 内の `SIGNATURE`/`PUBKEY` ペアを *固定された Astra
発行者鍵* に対して検証するため、自分の鍵で署名したバンドルは、未署名のものと
まったく同じように信用されません。このコマンドと、それが書き込むフォーマットの
項目は、いずれも廃止されつつあります。

**Astra が実際に判断材料にしているのは**、ファイル全体の SHA-256 を副署名する
レジストリレコードと、そのバイト列がどのワークフローの、どのコミットの、どの
リポジトリから生成されたかを示す GitHub のビルド証明です — これはデーモンでは
なく、取り込み(ingest)時にレジストリの bot によってチェックされます。

**今日、このチェーンがどこまで固定されているか。** ルートキーは両側に存在
します。`astra-registry/registry/v1/root.json` は `"status": "provisioned"`
と 2 つの Ed25519 キーを持っており、デーモンの `PRODUCTION_ROOT_KEYS` にも
同じ 2 つがコンパイルされて含まれています。`registry/v1/trust.json` は今では
`astra-root-2026a` によって署名されており、インデックス署名キー
`astra-index-2026a` に委譲しています — これはレジストリ自身の
`node tools/sign-trust.mjs --verify registry/v1/trust.json` で検証済みであり、
これは同時に、bot が証明として受け入れる再利用可能ワークフローの SHA
(`e3329df252a46d747676cb540ae4b986af68a3ad`、`plugin-release/v1` が指す
コミット)も 1 つだけ出力します。**まだ欠けているリンクはカタログ自身の署名
です。** `registry/v1/index.json` と `revocations.json` は `"signatures": []`
を持っており、デフォルトの Astra ビルドにはチェックするものがなく、すべての
カタログを未署名として分類します。ここでは、まだ実装されていない保証を約束
しているものは何もありません。[セキュリティモデル](1-orientation/security.md)
と [`spec/registry-index.md` §0.1](spec/registry-index.md) を参照してください。

**どれも、コードが安全であるとは言っていません。** プラグインはあなたのフル
ユーザー権限を持つネイティブプロセスであり、サンドボックスはありません。
リスト掲載は安全性のレビューではありません — 誰もあなたのコードを読みません。
レジストリ自身のポリシーもそう明言しています。

---

## プラグインがマシンに届く他の 2 つの方法

どちらも開発者向けで、どちらも代償があり、**どちらも公開ではありません**。

- [ローカルの `.astraplugin` ファイルをインストールする](5-publish/local-install.md)
  — 帯域外で受け取ったバンドル。マニフェストが何を要求していても、4 つの
  パーミッションは無条件で拒否されます。
- [ソースディレクトリをサイドロードする](5-publish/sideload.md) — 開発中の
  ループ用。開発者モードが必要で、未署名コードをあなたのフルユーザー権限で
  実行し、自動起動することは決してありません。

## 関連ページ

- [CLI をインストールする](install-cli.md) — このページのすべてのコマンドの出どころ
- [CI でリリースする](5-publish/release-with-ci.md) — ワークフローの全容
- [リストに掲載してもらう](5-publish/get-listed.md) — 提出とその後
- [バージョニング](versioning.md) — 番号の意味と非推奨期間の長さ
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)
