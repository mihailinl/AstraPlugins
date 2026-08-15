> **これは翻訳です。** 正式な情報源は [docs/en](../en/install-cli.md) です。内容に食い違いがある場合は英語版が優先されます。

# CLI をインストールする

公開への道のりはすべて 1 つのコマンドから始まります。このページはそのコマンドを
手に入れるためのものです。バイナリの名前は **`astra-plugin`** です — クレート名にすぎない
`astra-plugin-cli` ではありません。

## 正直な現状

**ビルド済みバイナリはまだなく、`astra-plugin-cli` は crates.io にもありません。**
今日確認した内容: `https://index.crates.io/as/tr/astra-plugin-cli` は `404` を返し、
同じインデックスの `astra-plugin-sdk` は `200` を返すので、これは検索の失敗ではなく
本当に存在しないということです。`gh release list --repo mihailinl/AstraPlugins` は
何も表示しません。

したがって CLI を入手する唯一の方法はビルドすることであり、ビルドには Rust ツールチェーン
が必要です。ビルド済みバイナリの配布は既知の、別扱いの、未完了のタスクです — そのための
リリース自動化は今まさに書かれているところで、ダウンロードできるリリースが存在した日に
このページはダウンロード用の 1 行を得ます。それまでは現状のすべてを説明するだけであり、
ここにはあなたに何かをダウンロードさせる記述はありません。

このコストは実在するものですが、それでも払う価値がある理由をはっきり言っておきます。
CLI は何か別のもっと簡単な経路の上に乗った便利ラッパーではありません。正しいリリース
ワークフローを書く唯一の手段であり、マニフェスト間でバージョンが食い違わないようにする
唯一の手段であり、レジストリの bot が実際に見てくれるリスティング申請を開く唯一の手段
です。これを迂回した結果、実際に 2 件の申請が沈黙のまま終わりました — 詳しくは
[公開とは何か](publishing.md) を参照してください。

## 前提条件

| | 理由 | 確認方法 |
|---|---|---|
| **Rust 1.85 以降** | ここにあるすべてのクレートは `edition = "2024"` であり、1.85 がそれを理解する最初のリリースです | `cargo --version` |
| **`PATH` 上の `protoc`** | CLI は `astra-plugin-sdk` に依存しており、その `build.rs` は `tonic-build` を使って `proto/plugin.proto` をコンパイルし、外部の `protoc` を呼び出します | `protoc --version` |
| **`git`** | `cargo install --git` はこれを使ってクローンします | `git --version` |

どのクレートも `rust-version` を宣言しておらず、CI は `stable` でビルドしているため、
実際に強制される下限は edition のみです。

見落とされがちな `protoc` のインストール方法。

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

これがないと `astra-plugin-sdk` のビルドスクリプトでビルドが失敗し、エラーが修正方法を
名指しします。

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## インストールする

**1 行、クローン不要。** 基本的にはこちらを使います。

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` は、すべての依存関係を最新リリースに再解決するのではなく、チェックイン済みの
`Cargo.lock` に対してビルドします。これは、ここで動いたのと同じようにビルドが動くか、
それとも手元のマシンで破壊的なパッチリリースに突然出会うかの違いです。

`--git` はその時点で `master` が保持しているものをビルドするので、報告されるバージョンと
コミットは実行した時点で `master` にあるものになります。下の山括弧の中身はすべて、
マシンごと・実行ごとに変わります — バージョンと SHA は `master` から、パスはあなたの
ホームディレクトリから、所要時間はあなたの CPU から来ます。

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

この記録は、採取のために誰かのインストール済みバイナリを上書きしてしまわないよう
`--root <scratch>` を付けて取得したものです。**`--root` は付けないでください** —
上のコマンドがそうしているとおりです — そうすると最後の 2 行が変わります。
`Installing` は `<home>/.cargo/bin/astra-plugin` を指し、`PATH` の警告は
`~/.cargo/bin` がまだ `PATH` に入っていない場合にのみ出ます。2 つの SHA は同じ
コミットを長さ違いで表示しているだけで、cargo の仕様であり不一致ではありません。

CLI 自体を読んだり変更したりもしたい場合は、**クローンから**。

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

素の `git clone` は `master` をチェックアウトします。そして現在の CLI があるのはまさに
`master` です — 覚えておくべき特別なブランチはありません。

## 動作確認する

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

この番号がプレースホルダなのは、どちらのインストール行でもバージョンを選べないから
です。どちらもリリースではなくコミットをビルドするので、手に入るのはそのコミットの
`Cargo.toml` にあるバージョンです。`0.2.1` は
[CLI の changelog](../../astra-plugin-cli/CHANGELOG.md) の最新エントリで、そこには
このクレートにリリース列車がないこと — crates.io もタグもバイナリもないこと — も
記録されています。

シェルが見つけられない場合、`cargo install` は `~/.cargo/bin`(Windows なら
`%USERPROFILE%\.cargo\bin`)にインストールしており、そのディレクトリが `PATH` に
入っていません。そうなった場合、`cargo` はその旨をはっきり警告として表示します。

### 最初のリリースを壊すバグと、自分のビルドに修正が入っているかの見分け方

**`astra-plugin init-ci` はかつて、GitHub がコミットを要求する箇所に注釈付きタグの
*オブジェクト* SHA を固定していました。** そのため最初の `git push --tags` は、
ジョブが始まる前に `invalid value workflow reference` で失敗していました。これが
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2) です。

**修正はコミット `5b8ab22` であって、バージョン番号ではありません。** そしてここが
人のつまずくところです。ここにリリース列車はありません — 何も公開されていないので、
誰も選んだバージョンをインストールしません。全員がクローンしたコミットをビルドします。
`5b8ab22` は、番号を `0.2.1` に上げたバージョン更新よりも*前*に `master` に入りました。
つまり:

- `5b8ab22` より後の `master` から作ったビルドは、**修正を含みながらそれでも `0.2.0`
  と表示します** — それは壊れたビルドではありません;
- `0.2.1` のビルドが修正を*欠く*ことはありえません。`5b8ab22` はバージョン更新
  コミットの祖先だからです;
- `5b8ab22` より*前*に作られた `0.2.0` のビルドが壊れたもので、`--version` では
  最初のケースと区別できません。

ですから `0.2.1` には価値があります — この問いに自力で答えられる最初の番号であり、
まさにそのために存在します — が、`0.2.0` と表示される `0.2.0` は何の証拠にも
なりません。`0.2.1` はフラグを増やさず API も変えません。唯一変わった振る舞いは
`publish --notify` で、そのリンクはレジストリがすでに無効化したブランク issue に
頼るのをやめ、release-ping フォームを名指しするようになりました。

`--version` が `0.2.0` と表示する場合、まず `which astra-plugin`(Windows では
`where`)を実行してください。最もよくある原因は古いバイナリが `PATH` 上で前に来て
いることで、`--version` だけではそれを「古いコミットの新しいビルド」と区別できません。
そのうえで番号から推測するのはやめ、ピンを読んでください — `init-ci` はバグの核心
そのものを書き込みますし、1 行で答えが出ます。

これがバージョンにまったく依存しない確認方法です。

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

修正が入ったビルドはピン `e3329df252a46d747676cb540ae4b986af68a3ad` — コミット — を
報告します。入っていないビルドは `dc1a044876926e9cf1170f034e2eab533ec07641` を報告し、
これは `plugin-release/v1` のタグ*オブジェクト*であり、GitHub が拒否するものです。
後者が見えたら、上の行で `master` から入れ直し、`init-ci` を再実行してください。
再実行しても安全です。入力値は保持したまま、ピンだけを書き換えます。既存のファイルは
その場で修復されないため、既存の `release.yml` は再実行するまで悪い SHA を保持し
続けます。

コマンド一覧の全体はこちらです。

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

**`astra-plugin login` は存在しません**。これは未完成なのではなく意図的なものです。
このツールチェーンのどこも、あなたに資格情報を尋ねることはありません。
[リストに掲載してもらう](5-publish/get-listed.md) を参照してください。

## 最新に保つ

同じ `cargo install --git` の行を再実行してください。Cargo がバイナリをその場で
置き換えます。自己更新の仕組みはなく、署名済みのリリースバイナリが登場するまでは
実装される予定もありません。

## うまくいかないとき

| 症状 | 原因 |
|---|---|
| `Could not find` protoc` ` | `protoc` が `PATH` にありません。上の表を参照してください |
| `feature `edition2024` is required` | Rust が 1.85 より古い |
| インストールが成功したのに `astra-plugin: command not found` | `~/.cargo/bin` が `PATH` に入っていない |
| リポジトリのルートで `cargo install --path .` を実行したときの `error: could not find `Cargo.toml`` | ルートにワークスペースマニフェストが存在しません。`--path` は `astra-plugin-cli/` を指してください |
| `unrecognized subcommand 'new'` | 古い `astra-plugin` が `PATH` 上でより前にあります。`--version` では区別できないので、`which astra-plugin`(Windows では `where`)で実際に実行されているファイルを確認してください |
| 最初のタグ push で `invalid value workflow reference` | `release.yml` を書いた CLI が `5b8ab22` より古く、タグオブジェクトを固定してしまっていた。[自分のビルドに修正が入っているかの見分け方](#最初のリリースを壊すバグと自分のビルドに修正が入っているかの見分け方) を参照 |

## 次に読む

- **[公開とは何か](publishing.md)** — 空のディレクトリからリスト掲載までの全行程を
  1 ページで。
- [はじめに](2-tutorial/getting-started.md) — プラグイン本体を書く。
