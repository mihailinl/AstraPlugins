> **これは翻訳です。** 正式な情報源は [docs/en](../../en/5-publish/release-with-ci.md) です。内容に食い違いがある場合は英語版が優先されます。

# CI でリリースする

**タグがリリースプロセスのすべてです。** 1 つのコマンドがそれを設定
すれば、あとはあなたが二度と手動でバンドルをビルドすることはありません。

このページのすべては `astra-plugin` バイナリから始まります。持っていな
ければ、先に [CLI をインストールする](../install-cli.md) を行ってくだ
さい — ビルド済みのアーカイブをダウンロードするか、お好みならソースから
ビルドしてください。この階層ではなく全行程を 1
ページで見たい場合は
[プラグインを公開する](../publishing.md) を参照してください。

## なぜ `astra-plugin build` してアップロードするだけではだめなのか?

自分のラップトップでビルドしたファイルを誰も保証してくれないからです。
レジストリは GitHub の**ビルド証明** — ワークフローの OIDC アイデンティ
ティから発行される Sigstore の keyless 署名 — を読み取り、これが
*正確にこのバイト列が、あのリポジトリの、あのコミットの、あのワークフロー
から来た*と述べます。手でビルドしたバンドルにはそのようなものが一切なく、
どれだけ出来がよくても、名指しの `E_ATTESTATION_MISSING` で拒否されます。

同じ理由で、**あなたのソースを GitHub に push することはリリースする
ことではありません**。ローカルでビルドした `.astraplugin` を誰かに送る
ことも同様です。レジストリはあなたのソースツリーを一切読みません; タグ
付きリリースにあるアセットを読み、それらをダイジェストで固定します。

署名鍵は不要であり、求められることもありません。
[セキュリティモデル](../1-orientation/security.md) を参照してください。

## 1 · ワークフローを書く

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

**これは今日機能しており、その半分ずつが検証可能です。**
`.github/workflows/plugin-release.yml` は `mihailinl/AstraPlugins` の
デフォルトブランチにあります — `git ls-tree -r master --name-only
.github/workflows` がそれを一覧表示します — そしてリリースされたタグ
は存在します: `git ls-remote --tags origin` は `plugin-release/v1` を
`e3329df252a46d747676cb540ae4b986af68a3ad` に解決します。タグが存在する
ため、`init-ci` は動くブランチの先端ではなくそのコミットをピン留めし、
このページの以前のバージョンが引用していた「Not verified」という留保
はもう表示されません。

その SHA は、レジストリの root 署名済み `trust.json` がビルド証明の
中で許可しているものと同じです — `astra-registry` の
`node tools/sign-trust.mjs --verify registry/v1/trust.json` は、これを
*許可されている再利用可能ワークフローの SHA* の下に出力します。他の
ワークフローで生成されたビルドは、取り込み時に `E_WORKFLOW_NOT_ALLOWED`
で拒否されます。そのためこのピンは単なる気配りではありません; あなたの
証明が、レジストリが行動できる意味を持つようにするものです。

より新しい `plugin-release/vN` が公開されたら、いつでも `init-ci` を
再実行してください; 入力値は保持され、ピンだけが動きます。

これが作者側の CI のすべてです。委譲しているため短いのです:

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

ピンを進めるには `init-ci` を再実行してください; あなたが設定した入力値
は保持されます。`--offline` はファイル内にすでにあるピンを保持し、
`--ref <sha-or-ref>` は特定のものをピン留めします。

## 2 · タグを打つ

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` は `plugin.toml` **と**プロジェクト内の他の
すべてのマニフェスト — `Cargo.toml`、`package.json`、`pyproject.toml`
— を 1 回の編集で書き換えるため、それらが食い違うことはありません。
現在のバージョンより順序が下がるバージョンは、`--allow-downgrade` を
渡さない限り拒否されます。Astra はダウングレードのインストールを拒否
するため、そのようなリリースはインストール不可能になってしまうからです。

タグは `tag-prefix` にマニフェストのバージョンを加えたものと一致しな
ければならず、CI は何かをビルドする前にそれをアサートします。
`astra-plugin version` は使うべき正確なタグを表示します:

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

## 3 · CI が行うこと

このセクションは、`.github/workflows/plugin-release.yml` が、
`plugin-release/v1` が指すコミットの `master` において、このリポジトリ
内でどう書かれているかを説明します — それがあなたの `release.yml` が
呼び出すコミットです。

3 つのジョブがあり、この分割こそがセキュリティ特性です。

| ジョブ | あなたのコードを実行するか | 書き込みトークンを持つか | 何をするか |
|---|---|---|---|
| **plan** | **しない** | 持つ | Python の `tomllib` で `plugin.toml` を*データ*として読み、タグ == バージョンをチェックし、ビルドマトリクスを決め、ドラフトリリースを作成する |
| **build**(マトリクス) | する | **持たない** | `astra-plugin check --strict`、`astra-plugin build`、検証、展開、glibc の下限と TypeScript バンドルの自己完結性をアサートする |
| **publish** | しない | 持つ | すべてのダイジェストを自分で再計算し、`SHA256SUMS.txt` を書き、証明し、アップロードし、リリースのドラフトを解除する |

`plan` はリポジトリの外にある何も実行しません — サブモジュールなし、
`.git/config` に永続化される資格情報なし。`build` はあなたの
`build.rs` とあなたのライフサイクルスクリプトを実行しますが、盗まれる
トークンを持ちません。`publish` はアーティファクトをダウンロードし、
自分でハッシュを取り、自分がハッシュしたものを証明します。

マトリクスはあなたのプラグインの言語から決まります: Rust には
`linux-x64` + `windows-x64`、TypeScript と Python には単一の `noarch`
の脚です。

### Release に何が付くか

| アセット | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | プラットフォームキーごとに 1 つ |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | 証明バンドル。GitHub へのネットワークがないユーザーでも確認できるように |
| `SHA256SUMS.txt` | レジストリが記録するのと同じダイジェスト |

Release は、すべてのアセットが添付されて初めて表示されるようになります。

### 証明には公開リポジトリが必要

ビルド証明は公開の透明性ログに発行されます; プライベートリポジトリでは
GitHub Enterprise が必要です。ワークフローはあなたのリポジトリの可視性
を解決し、それが公開でない場合、ジョブサマリーにその旨を記載し、
**証明のない**バンドルを生成します — そしてレジストリはそれを掲載しま
せん。これは実在する制約であり、問題なさそうに見えるリリースを生み出す
のではなく、大きな声で失敗します。

### 再現性

`astra-plugin build --reproducible` は決定論的なパッキングをアサート
します: ソートされたエントリ、固定された mtime、固定された圧縮レベル。
同じ入力からの 2 回のビルドは同じ sha256 を生成します。CI はすべての
リリースで再現性のカナリアを実行しており、これがサードパーティによる
再ビルドを意味あるものにしています。

## 4 · 自分で確認する

Astra やレジストリを信用せずとも、誰でもリリースを検証できます:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` はバンドル自体を読み、見つけたものを出力します:

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

ここでの終了コードは意味があり、すべてのリリースワークフローはこれで
分岐します: **1** はバンドルが不正であること、**2** は CLI が判定でき
なかったこと(例えばファイルが見つからない場合)を意味します。アーカイブ
形式と、検証ツールが拒否すべき内容は
[`spec/bundle-v2.md`](../spec/bundle-v2.md) にあります。

## 5 · そしてリストに掲載してもらう

1 回だけ。→ [リストに掲載してもらう](get-listed.md)。

## うまくいかないとき

| 症状 | 原因 |
|---|---|
| ワークフローがまったく開始しない | `on: push: tags:` と `tag-prefix:` が食い違っている。prefix より狭い glob は決して発火しない |
| 「tag does not match the manifest version」 | タグを打つ前に `astra-plugin version <v>` を実行してコミットしてください |
| Linux ビルドがヘッダーの欠落で失敗する | 呼び出し側ワークフローで `linux-packages: "libasound2-dev pkg-config"` を設定してください |
| バンドルが未証明である | リポジトリがプライベートです |
| 初回起動時の `MODULE_NOT_FOUND` | バンドラが追跡できなかった TypeScript の依存関係です。CI はこれに対してアサートします; バンドラの externals を確認してください |
| ユーザーのマシンでの glibc エラー | アーカイブ内の何かが `GLIBC_2.39` より新しいシンボルを必要としています。CI はこれもアサートします |
| どのジョブも始まる前の `invalid value workflow reference` | ピンが `plugin-release.yml` を持たないコミットを名指ししています。`astra-plugin init-ci` を再実行して `plugin-release/v1` に再ピンしてください |
| レジストリが `E_WORKFLOW_NOT_ALLOWED` でリリースを拒否する | ビルドがピン留めされた Astra の再利用可能ワークフローを実行しなかった。`init-ci` を再実行し、再タグして、CI に再ビルドさせてください |

さらに: [トラブルシューティング](../6-operate/troubleshooting.md)。
