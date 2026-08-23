> **これは翻訳です。** 正式な情報源は [docs/en](../en/install-cli.md) です。内容に食い違いがある場合は英語版が優先されます。

# CLI をインストールする

公開への道のりはすべて 1 つのコマンドから始まります。このページはそのコマンドを
手に入れるためのものです。バイナリの名前は **`astra-plugin`** です — クレート名にすぎない
`astra-plugin-cli` ではありません。

## 2 つの方法、どちらを選ぶか

**バイナリをダウンロードします。** リリース [`cli-v0.2.1`][rel] には Linux と
Windows 向けのビルド済みアーカイブ、チェックサムファイル、そして検証できる
Sigstore バンドルが含まれています。コンパイルは不要で、ツールチェーンも一切
関わりません。これがほとんどの人が求める道であり、以下で説明します。

**あるいはソースからビルドします。** これには Rust 1.85 以降と `protoc` が
必要です。アーカイブのないプラットフォーム — 今日で言えば macOS と ARM
Linux — にいる場合や、CLI を実行するだけでなく読んだり変更したりしたい
場合はこちらを選んでください。

**`cargo install astra-plugin-cli` はどちらの方法でもなく、機能しません。**
このクレートは vendor された `astra-plugin-manifest` にパスで依存しており
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`)、
cargo はパス依存関係のソースを決してパッケージ化しないため、公開は
*all dependencies must have a version requirement specified* で失敗します
— つまりこのクレートはそもそも crates.io に存在しません
(`https://index.crates.io/as/tr/astra-plugin-cli` は今日 `404` を返し、
同じインデックスの `astra-plugin-sdk` は `200` を返します)。これを解消
するには先に Astra からマニフェストクレートをリリースする必要があり、
このページはそれについて日付を約束しません。

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## バイナリをダウンロードする

### どのアーカイブを選ぶか

| あなたの環境 | 選ぶもの |
|---|---|
| **Linux 全般** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux で、特に glibc ビルドが欲しい | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl が安全なデフォルトであり、その理由は好みではありません。** gnu
ビルドは動的リンクされており、そのシンボルテーブルは **glibc 2.39 以降**
を要求しますが、Ubuntu 22.04(2.35)、Debian 12(2.36)、RHEL 9(2.34)は
それを持っていません — これらのどれでも、微妙に誤動作するのではなく
起動に失敗します。musl アーカイブは libc への依存がまったくない
`static-pie` 実行ファイルなので、そのすべてで動作します。gnu を選ぶのは、
それが欲しいと分かっているときだけにしてください。

そのリリースのアセット一覧全体、つまり公開されているものすべてです:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### 取得して検証する

Linux では `curl` を使います — ここでは `gh` も GitHub アカウントも
不要です:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

これはそれらのコマンドの実際のトランスクリプトです:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**`--ignore-missing` を使ってください。** `SHA256SUMS.txt` は 3 つの
アーカイブすべてを列挙しているため、素の `sha256sum -c SHA256SUMS.txt`
はダウンロードしなかった 2 つを `FAILED open or read` として報告し、
**終了コード 1** になります — これは破損したダウンロードそのものに
見えますが、実際はそうではありません:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

アーカイブはバイナリとそのライセンスファイルを含むディレクトリに展開
されます:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

`astra-plugin` を `PATH` 上のどこかへ移動してください — `~/.local/bin`
がよくある選択で、`sudo` は不要です:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

Windows では、リリースページから `.zip` をダウンロードして展開し、
`astra-plugin.exe` を `PATH` に置いてください。`certutil -hashfile
<file> SHA256` は組み込みのチェックサムツールで、その出力を
`SHA256SUMS.txt` と目視で比較します。

### 誰がビルドしたか検証する

チェックサムは、バイト列がリリースに記載されたファイルと一致することを
証明します。誰がそのファイルを生成したかは証明しません — そのためには
Sigstore バンドルがあり、`gh` がそれを GitHub のビルド証明と照合します:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**成功時は、出力がターミナルでないとき何も表示せず、終了コード `0` を
返します。** これは初めて見ると戸惑いますが、チェックマークを探すのでは
なく `echo $?` を確認してください。失敗は騒がしく、終了コード `1` に
なります:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

これはアーカイブに 1 バイト追加することで発生させたものです。それを
ビルドしていないリポジトリを `--repo` に指定した場合も同じように失敗
します。1 つのバンドルが 3 つのアーカイブすべてをカバーしており、
それが証明する内容は `--format json` で読み取れます: 署名する
ワークフローは
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`
で、issuer は `https://token.actions.githubusercontent.com`、そして
3 つの subject ダイジェストは `SHA256SUMS.txt` の 3 行です。`gh
attestation verify` には信頼のルートを取得するためのネットワークアクセス
が必要ですが、GitHub のログインは不要です。

## ソースからビルドする

アーカイブがまだない macOS や ARM Linux ではこちらを選ぶか、CLI 自体に
手を入れる場合に選んでください。これはダウンロードに失敗したときの
フォールバックではありません — 上のバイナリと同じプログラムです。

### 前提条件

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

### ビルドする

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

`master` が今持っているものではなく、公開されたバイナリのビルド元と
まったく同じコードをビルドするには、先にリリースタグをチェックアウト
してください:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

ダウンロードしたバイナリは `astra-plugin 0.2.1` と表示します。アーカイブは
タグ `cli-v0.2.1` からビルドされており、それ以外の何ものでもないからです。
`<version>` がプレースホルダなのはソースからの道だけです: `cargo install
--git` はその時点で `master` が持っているものをビルドするので、手に入る
のはそのコミットの `Cargo.toml` にあるバージョンであり、それは最新の
リリースより先を行っている場合があります。`0.2.1` は
[CLI の changelog](../../astra-plugin-cli/CHANGELOG.md) の最新エントリです。

シェルが見つけられない場合: ダウンロードしたバイナリはあなたがコピーした
場所にあり、`cargo install` は `~/.cargo/bin`(Windows なら
`%USERPROFILE%\.cargo\bin`)に置きます。いずれにせよそのディレクトリが
`PATH` に入っていません。そうなった場合、`cargo` はその旨をはっきり警告
として表示します。

### 最初のリリースを壊すバグと、自分のビルドに修正が入っているかの見分け方

**`astra-plugin init-ci` はかつて、GitHub がコミットを要求する箇所に注釈付きタグの
*オブジェクト* SHA を固定していました。** そのため最初の `git push --tags` は、
ジョブが始まる前に `invalid value workflow reference` で失敗していました。これが
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2) です。

**`0.2.1` バイナリをダウンロードすればこの問題は解決します。これが短い
答えです。** アーカイブはタグ `cli-v0.2.1` からビルドされており、
`5b8ab22` はその祖先なので、ダウンロードしたバイナリには修正が含まれて
います。この節の残りは、番号だけでは解決しないソースからのビルドに
ついてです。

**修正はコミット `5b8ab22` であって、バージョン番号ではありません。** そしてここが
人のつまずくところです。ソースからのビルドは、選んだリリースではなく
クローンしたコミットをインストールします。`5b8ab22` は、番号を `0.2.1`
に上げたバージョン更新よりも*前*に `master` に入りました。つまり:

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
  locale   Manage `locales/` — the plugin's translations, and its store card's text
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

バイナリをダウンロードした場合は、次のリリースのアーカイブをダウンロード
してファイルを置き換えてください — 新しいリリースは新しいバイト列を
意味するので、チェックサムをもう一度確認します。ソースからビルドした
場合は、同じ `cargo install` の行を再実行すれば cargo がバイナリをその場で
置き換えます。**自己更新の仕組みはなく**、このツールチェーンの何も、
新しいバージョンが存在するかどうかを確認するために外部へ通信すること
はありません。

## うまくいかないとき

| 症状 | 原因 |
|---|---|
| `sha256sum -c` からの `FAILED open or read` | 1 つのアーカイブしかダウンロードしていないのに、ファイルは 3 つを列挙しています。`--ignore-missing` を追加してください |
| `Error: verifying with issuer "sigstore.dev"` | アーカイブがバンドルと一致しないか、`--repo` がそれをビルドしていないリポジトリを指しています。理由を考える前に、まずダウンロードし直してください |
| `gh attestation verify` が何も表示しなかった | それは成功です。出力がターミナルでないときは無言になります; `echo $?` で `0` を確認してください |
| バイナリが起動せず、ローダーが `GLIBC_2.39` のバージョンが見つからないと文句を言う | 古い glibc のシステムで gnu アーカイブを選んでしまいました。libc を必要としない musl のほうを使ってください |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` は機能できず、これがそのエラーメッセージです。このページの冒頭を参照してください |
| `Could not find` protoc` ` | `protoc` が `PATH` にありません。上の表を参照してください |
| `feature `edition2024` is required` | Rust が 1.85 より古い |
| インストールが成功したのに `astra-plugin: command not found` | バイナリがあるディレクトリが `PATH` に入っていません — ソースからのビルドなら `~/.cargo/bin` です |
| リポジトリのルートで `cargo install --path .` を実行したときの `error: could not find `Cargo.toml`` | ルートにワークスペースマニフェストが存在しません。`--path` は `astra-plugin-cli/` を指してください |
| `unrecognized subcommand 'new'` | 古い `astra-plugin` が `PATH` 上でより前にあります。`--version` では区別できないので、`which astra-plugin`(Windows では `where`)で実際に実行されているファイルを確認してください |
| 最初のタグ push で `invalid value workflow reference` | `release.yml` を書いた CLI が `5b8ab22` より古く、タグオブジェクトを固定してしまっていた。[自分のビルドに修正が入っているかの見分け方](#最初のリリースを壊すバグと自分のビルドに修正が入っているかの見分け方) を参照 |

## 次に読む

- **[公開とは何か](publishing.md)** — 空のディレクトリからリスト掲載までの全行程を
  1 ページで。
- [はじめに](2-tutorial/getting-started.md) — プラグイン本体を書く。
