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
が必要です。ビルド済みの `linux-x64` と `windows-x64` バイナリの配布は既知の、別扱いの、
未完了のタスクです。それが実現するまで、このページが現状のすべてを説明します。

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

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release -p astra-plugin-sdk" -->
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
コミットは実行した時点で `master` にあるものになります。下の山括弧の 2 か所が、
あなたの環境で変わる部分です。

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" -->
```
   Compiling astra-plugin-cli v<version> (/home/you/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in 23.60s
  Installing /home/you/.cargo/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<sha>)` (executable `astra-plugin`)
```

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
astra-plugin 0.2.1
```

シェルが見つけられない場合、`cargo install` は `~/.cargo/bin`(Windows なら
`%USERPROFILE%\.cargo\bin`)にインストールしており、そのディレクトリが `PATH` に
入っていません。そうなった場合、`cargo` はその旨をはっきり警告として表示します。

### 0.2.1 以降を使うこと、そしてそれが重要な理由

**`0.2.0` には最初のリリースを壊すバグがあります。** `astra-plugin init-ci` は、
GitHub がコミットを要求する箇所に、注釈付きタグの*オブジェクト* SHA を固定して
しまっていました。そのため最初の `git push --tags` は、ジョブが始まる前に
`invalid value workflow reference` で失敗していました。これが
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2) であり、
`0.2.1` で修正されています。

気まずい部分を率直に言うと、`0.2.0` は修正コミット `5b8ab22` の前後どちらでも
公開されていたため、しばらくの間はバージョン番号だけでは動くビルドと壊れたビルドを
区別できませんでした。`0.2.1` はそれを終わらせるために存在します。フラグは増えず API も
変わりません。唯一変わった振る舞いは `publish --notify` で、そのリンクは
レジストリがすでに無効化したブランク issue に頼るのをやめ、release-ping
フォームを名指しするようになりました。

`--version` が `0.2.0` と表示する場合、まず `which astra-plugin`(Windows では
`where`)を実行してください。よくある原因は古いバイナリが `PATH` 上で前に来ている
ことで、`--version` だけではその区別がつきません。それが今インストールしたパスで
あり、それでもなお `0.2.0` と表示されるなら、ビルド元の `master` はまだ `0.2.1` を
持っていません — 修正コミット `5b8ab22` は、それを名指しするバージョン更新よりも
先に `master` に入ったため、修正を含んでいながら `0.2.0` と表示されるビルドが
ありえます。推測しないでください。下の `init-ci` による確認は CLI が実際に書き込む
ピンを読みます。バグはまさにそこにありました。

バージョンをまったく信用せずに確認する方法として、`init-ci` が何を書き込むかを
見ることもできます。

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

修正済みのビルドはピン `e3329df252a46d747676cb540ae4b986af68a3ad` — コミット — を
報告します。`0.2.0` のビルドは `dc1a044876926e9cf1170f034e2eab533ec07641` を報告し、
これはタグオブジェクトであり、GitHub が拒否するものです。`init-ci` は再実行しても
安全です。入力値は保持したまま、ピンだけを書き換えます。既存のファイルはその場で
修復されないため、既存の `release.yml` は再実行するまで悪い SHA を保持し続けます。

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
| 最初のタグ push で `invalid value workflow reference` | `release.yml` を書いた CLI が `0.2.0` で、タグオブジェクトを固定してしまっていた。[0.2.1 以降を使うこと](#021-以降を使うことそしてそれが重要な理由) を参照 |

## 次に読む

- **[公開とは何か](publishing.md)** — 空のディレクトリからリスト掲載までの全行程を
  1 ページで。
- [はじめに](2-tutorial/getting-started.md) — プラグイン本体を書く。
