> **これは翻訳です。** 正式な情報源は [docs/en](../../en/7-examples/README.md) です。内容に食い違いがある場合は英語版が優先されます。

# サンプル

[`examples/`](../../../examples/) にある 11 個のプラグイン、すべて
現行の SDK に移植され、すべて CI でビルドされています。あなたがやりたい
ことをしているものを読んでから、そのサンプルからではなく雛形から始めて
ください — サンプルには、あなたが削除しなければならないような雛形部分
は含まれていません。

以下の各項目は、それぞれのプラグイン自身の `plugin.toml` から読み取ら
れています。

## 最初に読むべきもの

| | 言語 | ケーパビリティ | パーミッション | これを読む理由 |
|---|---|---|---|---|
| [`dice-roller`](../../../examples/dice-roller/) | Rust | `tools`、`actions`、`triggers` | `fire_trigger` | リファレンスプラグイン。3 つのケーパビリティ、1 つのパーミッション、そしてそれぞれがどうテストされるかを示すテストスイート |
| [`json-tools`](../../../examples/json-tools/) | TypeScript | `tools`、`actions`、`triggers` | `set_variable` | TypeScript での同じ形、そしてテストがワイヤーレベルまで届くサンプル |
| [`text-utils`](../../../examples/text-utils/) | Python | `tools`、`actions`、`triggers` | `fire_trigger` | Python での同じ形 |

この 3 つは意図的に、同じプラグインを 3 通りに書いたものです。言語を
選ぼうとしているなら、3 つすべてを読んで、どのエコシステムからライブラリ
を引いてきたいかで選んでください — すべてのケーパビリティがすべての
SDK で利用可能です。

## ボイスプロバイダ

| | 言語 | ケーパビリティ | これを読む理由 |
|---|---|---|---|
| [`tone-tts`](../../../examples/tone-tts/) | Rust | `tts` | ビープ音で話すテキスト読み上げプロバイダ。声ではなく配線のテストです |
| [`mock-stt`](../../../examples/mock-stt/) | Rust | `stt` | 受け取った音声を説明する決定論的な書き起こしを返します。認識器を除いた bidi ストリームです |
| [`echo-stt`](../../../examples/echo-stt/) | Rust | `stt` | 何も書き起こさず、あなたのマイクをプラグインプロセス経由で再生します。デーモンが実際に何を送ってくるかを聞くためのものです |

`tone-tts` と `mock-stt` は、適合性テストジョブがすべての CI 実行で
駆動する 4 つのプラグインのうちの 2 つです。まさに、他の何も行使しない
フックを行使するからです。

## UI と `dom_access`

これらは Astra ウィンドウの中でコードを実行します。これらが
[サイドロードにパーミッションの上限がない](../5-publish/sideload.md)
理由です: `dom_access` は他の方法では開発できません。

| | 言語 | ケーパビリティ | これを読む理由 |
|---|---|---|---|
| [`companion`](../../../examples/companion/) | Rust | `ui_contributions`、`dom_access` | ウィンドウの周りを飛び回って何か言う猫。最小の完全な UI コントリビューション |
| [`bad-apple`](../../../examples/bad-apple/) | Rust | `ui_contributions`、`dom_access` | 4 つのレンダリングモードによる *Bad Apple!!* アニメーション。独自のフレームデータを出荷します; `SETUP.md` を参照してください |
| [`doom`](../../../examples/doom/) | Rust | `ui_contributions`、`dom_access` | WebAssembly エンジンを実行する Doom ページ。UI コントリビューションが取り得る最も極端な形です |

`companion` は、適合性テストジョブが `ui_contributions` のために駆動
する 4 番目のプラグインです。

## クライアント

`client` プラグインは、独自のセッション、独自のサーフェスを持つ独立
したチャットフロントエンドです。これは高リスクなケーパビリティであり、
[ローカルでインポートされたファイル](../5-publish/local-install.md)
には無条件で拒否されます。

> **この 2 つはどちらもデーモンより先を行っています。** クライアント
> 経路のデーモン側の半分はまだ構築されていません: すべてのプラグイン
> は `ClientType::PluginClient` として登録され、認証インターセプター
> は `/astra.PluginHostService/` の外にあるあらゆる gRPC パスでこの
> アイデンティティを拒否します。そのため、これら 2 つが対象として
> 書かれている `DaemonClient` は、すべての呼び出しで
> `permission_denied` を返します。これらは、今日エンドツーエンドで
> 実行できるものとしてではなく、クライアントプラグインの形 — サーフェス、
> イベントフロー、I18n — を読むために読んでください。
> [Rust SDK の `Daemon` セクション](../4-sdk/rust.md#daemon-sdk-には存在するがデーモンには拒否される)
> を参照してください。

| | 言語 | ケーパビリティ | これを読む理由 |
|---|---|---|---|
| [`telegram-client`](../../../examples/telegram-client/) | Rust | `client` | 各 Astra の会話が、ストリーミング返信付きの Telegram トピックになります |
| [`web-chat`](../../../examples/web-chat/) | Rust | `client` | Astra と話すブラウザウィンドウ。マルチクライアント同期が起きるのを見るためのものです |

## プラットフォーム

11 個のうちどれも `[platform]` ブロックを宣言していません。つまり、
デーモンは各プラグインをどこでも互換性があるとみなします — インタプ
リタ型の 2 つには正しいですが、*公開された*ネイティブプラグインは
これを絞り込むべきです。[プラットフォーム](../1-orientation/platforms.md)
を参照してください。

| 言語 | リリースが何をビルドするか |
|---|---|
| Rust(9 個) | `linux-x64` **と** `windows-x64`、それぞれ 1 バンドルずつ |
| TypeScript(`json-tools`) | `noarch` バンドル 1 つ |
| Python(`text-utils`) | `noarch` バンドル 1 つ |

`doom` と `bad-apple` はさらにデータ — WebAssembly エンジン、数
メガバイトのフレーム — を出荷しており、その `SETUP.md` に、それが
どこから来て、どう再生成するかが書かれています。

## 何によってテストされているか

| レベル | 何が実行されるか | どのサンプルか |
|---|---|---|
| ユニット | SDK のインプロセスハーネス、各サンプル自身のテスト内で | `dice-roller`、`mock-stt`、`text-utils`、`json-tools` |
| ビルド | すべての CI 実行で、すべてのサンプルがビルドされる | 11 個すべて |
| 適合性 | `astra-plugin test` が実プロセスをモックデーモンに対して起動し、そのケーパビリティが含意するすべてのフックを駆動する | `dice-roller`、`mock-stt`、`tone-tts`、`companion` |

適合性の集合は、多様性のためではなく、フック表のカバレッジのために
選ばれています — tools/actions/triggers、STT の bidi ストリーム、
TTS、UI コントリビューション。**`ai_provider` にはサンプルがなく、
そのためカバーされていません**。これは声に出して言う価値があります:
誰も名指ししないカバレッジの穴は、誰もが埋まっていると思い込む穴に
なります。

Python と TypeScript のサンプルはまだ適合性テストジョブに含まれて
いません。なぜなら、それらの SDK はまだ公開されておらず、SDK を
半端にインストールした状態での適合性テストは、プラグインについてでは
なくインストールについて報告することになるからです。`astra-plugin
test` はプロセスを駆動するのであって、それがどの言語で書かれたかを
気にしないため、SDK が公開された日にこのジョブに加わります。

## 1 つを実行する

<!-- doctest: cli -->
```bash
cd examples/dice-roller
astra-plugin check --strict
astra-plugin test
astra-plugin dev
```

`dev` には実行中の Astra と開発者モードが必要です — 先に
[それが何を代償にするか](../5-publish/sideload.md) を読んでください。
