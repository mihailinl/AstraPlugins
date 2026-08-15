> **これは翻訳です。** 正式な情報源は [docs/en](../../en/1-orientation/platforms.md) です。内容に食い違いがある場合は英語版が優先されます。

# プラットフォーム

Astra は**2 つ**のホスト向けにデーモンを出荷しています。以下のすべては
そこから導かれます。

| プラットフォームキー | ホスト | Astra はデーモンを出荷しているか |
|---|---|---|
| `linux-x64` | Linux, x86_64 | はい |
| `windows-x64` | Windows, x86_64 | はい |
| `noarch` | 任意 — ネイティブコードを持たないインタプリタ型プラグイン | 該当なし、両方で動作します |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **いいえ** |

最後の行は*予約されているだけで、サポートはされていません*。これらの
名前がレジストリのスキーマに存在するのは、Astra が後にそれらのホストを
出荷したときにインデックス形式を変更せずに済むようにするためであり、
バリデータがタイポ(`mac-amd64`)を、どのデーモンも参照することのない
キーを書き込むのではなく、拒否できるようにするためです。これらのいずれか
の下で公開されたバンドルには、実行するホストがありません。
`astra-plugin build` は推測を拒否します: 対応するキーがないホスト上では、
`linux-x64` に解決されるものを黙って詰め込むのではなく、`--target` を
明示的に渡すよう伝えてきます。

## プラットフォームごとに 1 つのバンドル、そしていくつ必要かを決めるもの

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** はネイティブコードにコンパイルされるため、プラットフォームごと
  に 1 つのバンドルが必要です。リリースワークフローはこれらをマトリクス
  でビルドします — `ubuntu-24.04` と `windows-2022` です — なぜなら
  クロスビルドは別種のバグ集合だからです。
- **TypeScript と Python** は単一の `noarch` バンドルを生成します。
  インデックスは、サポートされているすべてのプラットフォームキーの下に
  同じ URL とダイジェストを書き込むため、`noarch` バンドルは他のものと
  同様に `linux-x64` と `windows-x64` の両方の下で見つかります。

`--all-targets` は、Astra が動くあらゆる場所でインストール可能になる
ために必要なものをすべてビルドします: TypeScript と Python は 1 ファイル、
Rust はプラットフォームごとに 1 ファイルで、それぞれ自身の
`cargo build --target` から生成されます。

## `[platform]`、そしてブロックの省略が主張になる理由

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

`[platform]` が空、あるいは存在しないことは*要件なし*を意味し、デーモンは
そのプラグインをどこでも互換性があるものとみなします。これは `noarch`
プラグインにとっては正しいですが、ネイティブバイナリを出荷するプラグイン
にとっては間違いです。`astra-plugin doctor` はまさにその言葉でそう伝え
ます。

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` は `--target` から実際の答えをバンドルの
`MANIFEST` に刻印するため、パッケージ化されたファイルは、マニフェストが
何と言っていようと `{os, arch}` を運びます。

## ビルドの前提条件

| 言語 | 必要なもの | 誰がチェックするか |
|---|---|---|
| Rust | Rust **1.85 以降** — SDK と雛形は edition 2024 です | `astra-plugin doctor` |
| Rust | **`PATH` 上の `protoc`。** `astra-plugin-sdk/build.rs` は `tonic_build::configure().compile_protos(…)` で `proto/plugin.proto` をコンパイルし、tonic-build 0.12 は `protoc` を同梱するのではなく外部呼び出しします。`apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | 実行には Node 20+、バンドルには `bun`(または `build` スクリプトのバンドラ) | `astra-plugin doctor` |
| Python | `python3`、加えて `requirements.txt` からの `grpcio` と `protobuf` | `astra-plugin doctor` |

`protoc` は最初に噛みついてくるもので、しかも別の何かのように読めます。
CLI は Rust SDK に依存しているため、*`astra-plugin` 自体をインストールする*
のに必要です — プロジェクトもマニフェストもなく、protobuf コンパイラを
疑う理由すらまだない段階でです。それがないと `cargo install` は
`error: failed to run custom build command for astra-plugin-sdk` で止まり、
数行下に `Could not find `protoc`` と出ます。このリポジトリ自身の CI は
すべての Rust ジョブでこれをインストールしています
(`arduino/setup-protoc@v3`、`.github/workflows/ci.yml` 内で 7 回)。
これがそれが任意ではないことの何よりの証拠です。

`astra-plugin doctor` はこれらすべてに、あなたが実際にいるマシン上で、
1 つのコマンドで答えます。

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### glibc の下限

CI でビルドされた Linux バンドルは **GLIBC_2.39** に対してチェックされ
ます — リリースワークフローは完成したアーカイブ内のすべての ELF オブジェクト
を逆アセンブルし、より新しいシンボルバージョンを必要とするものがあれば
ビルドを失敗させます。これによって `ubuntu-24.04` でビルドされたプラグイン
が、Astra がターゲットとするディストリビューションで動くことが保証されて
おり、これは本来ならユーザーのマシン上でしか現れない種類の失敗です。

新しいディストリビューション上で手動で Linux バンドルをビルドした場合、
これは一切チェックされません。これがリリース経路が CI である理由の 1 つ
です。

### TypeScript バンドルは `node_modules` を運びません

`.astraplugin` はバンドル済みの出力を出荷するのであって、依存関係ツリー
ではありません。リリースワークフローは、バンドルが自己完結していること
をアサートします: バンドラが追跡できなかった迷子の `require("chalk")`
は、インストール自体は問題なく成功し、誰も直せないマシン上で、初回起動
時に `MODULE_NOT_FOUND` で死にます。

## OS ごとに、何がどこにあるか

Astra は `directories` クレートを使い、`("com", "astra", "astra")`
からディレクトリを解決します — CLI も同一の呼び出しを使うため、両者が
食い違うことはありません(`astra-plugin-cli/src/daemon.rs`)。

| | Linux | Windows |
|---|---|---|
| 設定ディレクトリ | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| デーモンのポートファイル | `<config>/daemon.port` | 同じ |
| デーモンのブートストラップシークレット | `<config>/daemon.token` | 同じ |
| インストール済みプラグイン | `<config>/plugins/<id>/` | 同じ |
| プラグインの設定 | `<config>/plugins/<id>/config.json` | 同じ |
| デーモンのログ | `<config>/logs/` | 同じ |

想定するのではなく、尋ねてください — `doctor` はこのマシンが解決した
パスを出力します。

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

デーモンは 32000 が使用中のとき OS が割り当てたポートを使うため、
`127.0.0.1:32000` はフォールバックの推測にすぎず、`daemon.port` こそが
事実です。

## macOS

サポートされていません。それは省略によるものではありません。Astra 自身の
リリースワークフローは `linux-x64` と `windows-x64` のみをビルドしており、
`macos-arm64` プラグインバンドルには実行するホストがありません。macOS は
さらに、すべてのサードパーティ作者に Apple の公証(notarization)問題を
持ち込みます。キー名はインデックスのスキーマ内に予約されているだけで、
何もそれらを発行せず、扱われないホストはサイレントなフォールバックではなく
ハードエラーになります。Astra がそのターゲット向けにデーモンを出荷する
リリースの際に、改めて見直してください。
