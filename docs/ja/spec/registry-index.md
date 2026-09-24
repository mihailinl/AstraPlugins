> **これは翻訳です。** 正式な情報源は [docs/en](../../en/spec/registry-index.md) です。内容に食い違いがある場合は英語版が優先されます。

# 署名済みレジストリ文書 — 規範仕様

**ステータス:** 文書フォーマットと検証ルールについて規範的。
**一部発効:** ここに記述されている署名チェーンは仕様化され、両端で実装され、
カタログまでは固定されていますが、撤回リストまではまだです — このファイル内の
どの文をセキュリティ保証として頼る前にも、まず §0.1 を読んでください。

4 つの文書、3 つのスキーマ、1 つの署名構成:

| 文書 | スキーマ文字列 | 誰が署名するか | このリポジトリのコピー |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **何も署名しない** — Astra にコンパイルされた鍵の書き起こし | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | **root** 鍵 | カタログの隣に公開される |
| `index.json` | `astra.registry.index/1` | `trust.json` が委譲する **index** 鍵 | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | 同じ index 鍵 | `astra-registry/registry/v1/revocations.json` |

要求語は RFC 2119 に従います。

---

## 0. このチェーンが答えること、答えないこと

これが答えるのは: *このカタログは Astra レジストリが公開したものか、
最新か、その中の何かが撤回されていないか?* です。これは、キャッシュ
されたレコードから安全にインストールできるようにする唯一のものです。
なぜなら、そのレコードはアーティファクトダイジェストを固定し、
ダイジェストは期限切れにならないからです。

これは*誰がプラグインをビルドしたか*には答え**ません**。それは
GitHub のビルド証明であり、取り込み時にレジストリ bot によってチェック
され(§7)、デーモンによっては決してチェックされません。デーモンが
保持するのは、作者についてのレジストリの*主張*であり、最初のインストール
時に固定され(TOFU)、ダウンロード URL に紐づけられます — §7.3 を参照
してください。UI の文言は「前回と同じ作者」と言うことが求められ、
「検証済みビルド」とは決して言ってはいけません。

### 0.1 チェーンの現状 — まずこれを読んでください

* `astra-registry/registry/v1/root.json` は `"status": "provisioned"`
  と 2 つの Ed25519 鍵を持っています。`astra-registry/SECURITY.md`
  §4 の儀式(`tools/keygen-root.sh`)は 2026-08-11 にオフラインで実行
  されました。
* `astra-daemon` の `PRODUCTION_ROOT_KEYS` は同じ 2 つを列挙します。
  レジストリのコピーは公開されているため、第三者がバイナリを逆アセンブル
  することなくそれらを読むことができ、両者の不一致が可視化されます;
  秘密鍵の半分はネットワークにつながったマシンに置かれたことは一度も
  ありません。
* **root 鍵はカタログに署名しません。** それは `trust.json` に署名し、
  それが index 署名鍵に委譲します。**その文書は今では署名されています。**
  `registry/v1/trust.json` は `astra-root-2026a` の下で検証され、
  index 署名鍵 `astra-index-2026a` に委譲し、bot がビルド証明で受け
  入れる再利用可能ワークフローのコミットを名指しします — 2026-08-19 に
  タグが動いて以来 2 つあり、`plugin-release/v1` が今指すものと、その前に
  指していたものです。レジストリ自身の
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` は
  これら 3 つの事実すべてを出力します。そのため `E_TRUST_UNPROVISIONED`
  はもう取り込み時に発生しません。
* **クライアントに配信されるカタログは、その鍵で署名されています。**
  2026-09-20 以降、レジストリの署名者
  (`astra-registry/.github/workflows/sign.yml`) が、クライアントが読むもの
  の唯一の発行者です。署名者は `index.json` と `revocations.json` に
  `astra-index-2026a` で署名し、ブランチ `signed` にコミットし、そのブランチ
  の文書を Pages にデプロイします。2026-09-24 に確認済み: Pages が配信する
  `index.json` は、その隣で配信される `trust.json` に照らして
  `astra-index-2026a` の下で検証されます(シリアル 52)。デーモンの
  `classify_signature` は、カタログがなお未署名で届きうる 2 つの場合を厳密
  に分けています: `NoTrustAnchor` は、検証済みの `trust.json` がそのビルド
  に届いておらず、どの署名も照合する鍵が存在しないという意味です。
  `NoSignatures` は、信頼のアンカーはあるのにカタログ自体が署名を 1 つも
  持っていないという意味です。
* レジストリの `main` にコミットされたコピー — `registry/v1/index.json` と
  `registry/v1/revocations.json` — は、意図的に `"signatures": []` を
  持っています: 「未署名」がはっきりと述べられており、存在しないメンバーと
  取り除かれたメンバーが区別できない状態にはなっていません。これを読む
  クライアントはありません。署名済みのコピーは `signed` と Pages にあります。
* 1 つの帰結はまだ有効で、決して曖昧にしてはいけません。レジストリが
  署名済みの撤回リストを Pages で有効にするまで、Pages はコミット済みの
  未署名の撤回リストを配信し続けます。そして
  `verify_revocations_document` が厳格である(§6.4)ため、**未署名の撤回
  リストは拒否され、そのため失効の強制はまだ発効していません** — 署名が
  有効なリストが一度取得されるまで `RevocationFreshness::NotEnforced` の
  ままです。

以下のすべてはフォーマットとアルゴリズムを記述しており、残りのリンク
が着地しても、その内容は何も変わりません。root の儀式は実行され、委譲は
署名され、クライアントに配信される `index.json` はその `signatures` 配列
に署名を持っています。そのため、チェーンのうちカタログの半分はユーザーの
マシン上で重みを持っています。残っているのは撤回リストの半分、つまり
Pages 上の署名済みリストです。

## 1. エンベロープ

すべての署名済み文書は同じ外側の形を持ちます:

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **`signed` だけが認証されます。** その外側にあるものは事実として
  読まれてはいけません — `$comment` も、`key_id` の文字列も、署名
  リスト自体の形も。
* `sig` は生の**64 バイトの Ed25519 署名**の base64 です。index の
  スキーマはその綴りを固定します: `^[A-Za-z0-9+/]{86}==$`。
* `key_id` はロギングと鍵選択のための**ヒント**です。検証ツールは、
  信頼されたすべての鍵を、提供されたすべての署名に対して試さなけれ
  ばならず(MUST)、実際に検証した鍵の `key_id` を、文書が主張していた
  ものではなく報告しなければなりません(MUST)。誰が署名したかについて
  嘘をつく文書も、信頼された鍵が実際に署名していれば検証され、正しい
  鍵を名指ししたからといって検証されることはありません。
* 空の `signatures` 配列は未署名を意味します。これはエラー形状では
  なく、儀式前の状態であり、手書きのローカルカタログの状態でもあります。

## 2. 署名入力

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` は文書のスキーマ文字列です: `astra.registry.trust/1`、
  `astra.registry.index/1`、または `astra.registry.revocations/1`。
* **検証ツールは `domain` を自身の定数から供給し、読んでいるファイル
  の `schema` メンバーからは決して供給しません。** そうでなければ、
  `trust.json` に対する署名は、1 つの文字列を編集するだけで
  `index.json` に対する署名として再生可能になってしまいます — そして、
  1 つのカタログに署名させることができた誰もが、*空の*撤回リストを
  公開してこの仕組みをオフにできてしまいます。
* `0x00` は、ある domain が別の domain のプレフィックスであるときの
  衝突を防ぐものです。
* Ed25519 検証は厳格であるべきです(SHOULD)(`ed25519_dalek::verify_strict`
  または同等のもの): 小位数の公開鍵や、寛容な検証ツールが受け入れて
  しまう可鍛性のあるエンコーディングを拒否してください。
* 署名は SHA-256 ダイジェストに対して行われ、通常のメッセージとして
  Ed25519 に渡されます。「事前ハッシュ済み」モードを有効にしないで
  ください; Ed25519 は内部でハッシュを行い、この構成はそれに 32
  バイトを与えます。

これの両端は存在し、テストによって一致が保証されています:
`astra-registry/bot/lib/sign.mjs`(`signingDigest`、`signEnvelope`、
`verifyEnvelope`)と `astra-daemon/src/plugins/trust.rs`
(`signing_digest`、`verify_envelope`)です。
`astra-registry/bot/fixtures/index/` は、JavaScript の署名者が生成し、
Rust の検証ツールがバイト単位でチェックする文書を保持しているため、
どちらもビルドを red にすることなくずれることはできません。

## 3. 正規化(JCS プロファイル)

`JCS(signed)` は RFC 8785 の正準 JSON であり、1 つの意図的な絞り込み
があります。

* **オブジェクトのキーは UTF-16 コードユニットでソートされます**
  (RFC 8785 §3.2.3)。これは JavaScript のデフォルトの
  `Array.prototype.sort()` が行うことであり、Rust 側はバイト順を仮定
  するのではなくそれを明示的に綴っています
  (`a.encode_utf16().cmp(b.encode_utf16())`)。すべて ASCII のキーで
  は 2 つの順序は一致しますが、BMP を超えると一致しません。
* **意味のない空白はありません。** コンパクト形式です。
* **文字列**は RFC 8785 §3.2.2.2 が要求するとおりにエスケープされ
  ます: `"`、`\`、C0 制御文字(存在する場合は短い形式)をエスケープし、
  `/` とすべての非 ASCII をリテラルの UTF-8 のままにします。
* **数値は ±(2^53 − 1) の範囲の整数でなければなりません(MUST)** —
  JavaScript の `Number.MAX_SAFE_INTEGER` です。どちらの実装も、
  §3.2.2 の浮動小数点正規化を実装するのではなく、それ以外を**拒否**
  します。レジストリは整数(`serial`、`size`、`protocol`)しか発行せ
  ず、§3.2.2 を*ほぼ*正しく実装した実装は、片側では検証されるがもう
  片側では検証されない署名を生成してしまいます。`1.0` と `1` は同じ
  JSON の数値であり、どちらも `1` としてシリアライズされます。
* **重複するオブジェクトキーはパース時に拒否されなければならず**
  (MUST)、解決されてはいけません(RFC 8785 §3.1)。`{"a":1,"a":2}`
  は 2 つのことを意味しますが、署名済み文書は 1 つを意味さなければ
  なりません。文書の後の末尾バイトも同じ理由で拒否されます。
* 値が `undefined` であるメンバーは存在しません; JSON にはそのような
  ものがありません。(レジストリのシリアライザはそれらを落とします;
  JSON パーサーがそれを生成することは決してありません。)

リポジトリにコミットされている整形されたファイルは、*同じ*シリアラ
イザ(`stableStringify`)で同じキー順を使って生成されているため、
差分を読むレビュアーは、空白を除けば、署名されるバイト列を読んでい
ることになります。

## 4. 鍵、委譲、ローテーション

### 4.1 Roots

* Ed25519 です。公開鍵の半分は**Astra にコンパイルされ**、生の 32
  バイトの base64 です。
* **2 つのスロット**があり、1 回のオフライン儀式で生成されます: 1 つ
  は `Active`、もう 1 つは、root を交換しなければならなくなるまで一
  度も使われない `Reserve` です。両方とも初日から出荷されるため、
  root の交換は署名 1 つで済み、フラグデーにはなりません。
* root は**`trust.json` だけに署名し、それ以外には署名しません**。
  root の署名が `index.json`、`revocations.json`、あるいはバンドル
  に現れることは決してありません。
* `root.json` は権威ではなく書き起こしです: これは意図的に未署名です
  — 自己署名の root 文書は、コンパイルされた鍵がすでに証明していない
  ことを何も証明しません。これが存在するのは、2 つのコピーを比較でき
  るようにするためです。各エントリの `fingerprint_sha256` は生の
  32 バイト公開鍵に対する SHA-256、小文字 16 進数です; これは
  `tools/keygen-root.sh` が出力し、root 署名が検証されたときにデーモン
  がログに記録するのと同じ値です。
* テスト用の root が存在します(`astra-registry/tools/testkeys/`、
  秘密鍵の半分も意図的にコミットされており、`key_id` には
  `TEST-ONLY-DO-NOT-TRUST-` が接頭辞として付きます)。デーモンは、
  デフォルトでない `insecure-test-trust-roots` フィーチャーの背後
  でしか、**デバッグプロファイルで**しかそれらをコンパイルできません;
  リリースプロファイルでそれを要求すると `compile_error!` になります。

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

検証ルール:

* `serial` は 0 であってはいけません(MUST NOT) — 0 は検証ツール側の
  「まだ何も受け入れていない」センチネルであるため、公開された文書
  はそれを主張できません。
* `schema` は `astra.registry.trust/1` と等しくなければなりません
  (MUST)。誤って提出された文書が「root がこれに署名していない」で
  はなく「スキーマが間違っている」と言うようにするためだけに、署名
  より先にこれをチェックしてください; ダイジェストの domain は検証
  ツール自身の定数なので、これが結果を変えることはできません。
* 未知のメンバーは**保持され無視されます**。新しいレジストリがフィー
  ルドを追加しても古いデーモンをレンガにしてはならず、生の検証済み
  `signed` は往復を生き延びるため、何も静かに落とされて再署名される
  ことはありません。
* パースできない鍵、あるいはパースできないウィンドウを持つ
  `index_keys` エントリは、致命的ではなく**警告付きでスキップされ
  ます**: 1 つの不正な行が、他の鍵で検証できたはずのカタログを犠牲に
  してはいけません。パースできない `not_before` は*まだ有効でない*
  として扱われ、パースできない `not_after` は*期限切れ*として扱わ
  れます — 行についてはフェイルクローズ、文書についてはフェイル
  オープンです。
* `reusable_workflow_shas` は、**レジストリ bot**が強制する(§7)、
  解決済みの再利用可能ワークフローコミット SHA の許可リストです。
  デーモンはこれを運びますが使用しません。これを変更することは
  root 鍵の儀式であり、これがここに置かれている理由のすべてです。

**ローテーション。** 四半期ごとに、そして疑わしいと判断され次第
即座に。計画されたローテーションは、退出する鍵と入ってくる鍵が**30
日間重複するウィンドウ**を持つ `trust.json` を公開するため、
`index_keys_valid_at(now)` が 2 つの鍵を返すことは、切り替え中の
異常ではなく通常の状態です。

### 4.3 どの時計が鍵のウィンドウを判定するか

2 つの時計の読み取りが存在します: このマシンのものと、文書を生成した
フェッチの HTTP `Date` です。

* **鮮度**(§5)は `now = server_date ?? local` で判定されます — 1
  回のフェッチの間はレジストリの読み取りを信じます。これは攻撃者に、
  彼らがすでに持っていなかった何かのコストを負わせません(彼らは自分
  が制御していない時計を持つマシンに古い文書を提供できてしまう)し、
  はるかによくあるケース — 時計が狂ったラップトップが自分のカタログ
  が期限切れだと告げられる — を救います。
* **鍵の有効ウィンドウ**は `window_now = max(local, server)` で判定
  されます — ネットワークは「今」を*前に*引っ張ることはできますが、
  *後ろに*押すことは**決してできません**。`not_after` は、侵害された
  index 鍵を退役させる唯一の仕組みであり、それをネットワークが提供
  する瞬間で判定すると、盗んだ者に、古い `Date` で答えることで永遠に
  その日を選ぶことも許してしまいます。より遅い読み取りを採用することで、
  盗まれ退役した鍵は、攻撃者がどちらの読み取りを制御していても、より
  期限切れになります。
* **2 時間**(`CLOCK_SKEW_TOLERANCE_HOURS`)を超える不一致は、それ
  自体がシグナルです: 判定は文書についての主張ではなく `CLOCK_SKEW`
  になります。CMOS 電池切れがすぐに引っかかるほど小さく、通常の
  NTP なしのドリフトでは引っかからないほど大きい値です。
* 時計から書き込まれる**永続的な**もの(最終フェッチのタイムスタンプ、
  フロア)はすべて、まずローカルの時計にクランプされます。
  `Date: Fri, 01 Jan 2100 …` を運ぶ 1 回のレスポンスは、そうでなけれ
  ば、デーモンの「現在」の概念を永久に 2100 年へ動かしてしまいます
  — 1 回のフェッチに答えられる誰にでも書き込める永続的なサービス拒否
  です。

## 5. `index.json`

### 5.1 形

`signed` は:

| メンバー | 型 | ルール |
|---|---|---|
| `schema` | 定数 `astra.registry.index/1` | 必須 |
| `serial` | integer ≥ 0 | 必須、単調増加(§5.4) |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | **署名時**に刻印され、コミットされたツリーにはない |
| `expires_at` | 同上 | `issued_at + 30 日` |
| `plugins` | array | 掲載された各プラグインにつき 1 レコード、`id` でソート |
| `publishers` | object, GitHub login → `signed.publishers.<owner>` | optional: one record per account a listing's `publisher` names, and absent when none does |

タイムスタンプは RFC 3339 UTC、**秒精度、ミリ秒なし、オフセットなし**
です。1 つの瞬間の 2 通りの綴りは 2 つの異なる署名済み文書です。

プラグインレコードは `id`、`name`、`version`、`description`、
`license`、`capabilities`、`repository_url`、`source`、`icon_url`、
`downloads`、`stars`、`updated_at`、`download_url`、
`platform_downloads`、`releases[]` を運びます。完全な JSON Schema は
`astra-registry/schema/index-v1.json` です; これは
`additionalProperties: false` であり、フィールドリストに関する権威
です。

2 つのルールは、検証ツールがそれらに依存しているため、改めて述べる
価値があります:

* **`releases[]` が権威のある半分です**。semver の優先順位で新しい
  ものから並びます。各リリースは `version`、`published_at`、
  `release`(`{kind: "github_release", repo, tag}` または
  `{kind: "direct", base_url}`)、`artifacts`(プラットフォームキー →
  `{url, filename, sha256, size}`)を持ちます。
* **フラットなフィールドは、同じジェネレータのパスで計算された
  `releases[0]` の射影です**。したがってそれと食い違うことはあり
  ません。`version`、`platform_downloads`、`download_url` が存在す
  るのは、出荷されるデーモンがまさにそれらを読むからです。

プラットフォームキー: `linux-x64`、`windows-x64`、`noarch`、加えて
予約された `linux-arm64`、`windows-arm64`、`macos-x64`、
`macos-arm64`。`noarch` のアーティファクトは**サポートされている
すべてのプラットフォームキー**の下に書かれるため、どのクライアント
もこの言葉を知る必要がありません
(`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`)。

`downloads` と `stars` は署名済みカタログでは常に `0` で、`0` のままです: カウント
が署名されることはなく、信頼・インストール・アップデートの入力になることも
ありません。**2026-09-27 に修正(ROLL-47 の行 B1):** このページは以前、レジストリは
何もカウントしないとも述べていました。プラグインサービスのインストール対応の
デプロイ以降、インストールとアップデートはプラグインごとの集計として数えられ、
カタログの隣の `https://registry.minice.ai/stats/v1/stats.json`
(`astra.plugins.stats/1`: `generated_at`、`catalogue_serial`、そして
プラグインごとの `installs`、`updates`、評価が 5 件以上なら `ratings` の
ヒストグラム)で公開されます。この文書に `downloads` や `stars` という名前の
メンバーはありません。

**ステージングエントリ** — リリースが紙の上には存在するが、まだアー
ティファクトダイジェストを持たないリスト掲載 — は `staging: true`
とマークされ、**`platform_downloads` と `download_url` から省かれ**、
構造上インストール不可能です: ダイジェストがなければ、インストール
もありません。

> **These tables are in English in every language.** The `publishers` row of the
> table above and every table below are the English page's, copied as they are:
> they document `astra-registry/schema/index-v1.json` member for member, C21 in
> `tools/check-registry-mirrors.py` holds the English page to that file, and nobody
> on this side can review a translation of them. Each table is one object, named in
> the line above it; a rule begins with *required*, *optional* or *required when*,
> which are the schema's `required` lists. A translation is welcome; English stays
> authoritative either way.

A plugin record, `signed.plugins[]`, is:

| member | type | rule |
|---|---|---|
| `id` | string, 2–64 characters of `a-z`, `0-9` and `-`, beginning and ending with a letter or digit | required: the listing's directory name in the registry; records are sorted by it |
| `name` | string, 1–64 characters | required: the card's title, in English |
| `version` | string | required: the latest listed release, `releases[0].version` |
| `description` | string, ≤ 200 characters | required: the one-line card text, in English — `plugin.json`'s `summary`, under the name the daemon already reads. It is not `plugin.json`'s own `description`, which the index does not carry |
| `i18n` | object, locale code → `signed.plugins[].i18n.<code>` | optional: the card in other languages, read out of the attested bundle's `locales/<code>.json`. The codes are `ru`, `uk`, `de`, `fr`, `es`, `pt`, `ja`, `zh` and `ko`; `en` is never one, because `name` and `description` are the English. A client that does not read this member renders English |
| `readme` | string, ≤ 16384 characters | optional: the plugin's own README, inlined so the signature covers it and opening the store asks no third party for anything. GitHub-flavoured markdown with no raw HTML and no image outside GitHub's asset hosts. The registry's own cap is 16384 UTF-8 **bytes** (`MAX_README_BYTES`), and the schema's character bound is its backstop. Absent when the plugin ships no README |
| `author` | string, ≤ 64 characters | optional: `plugin.json`'s `author.name` — whatever the author typed, not an identity the registry proves (that is `publisher`) |
| `author_url` | string, `^https://` | optional: `plugin.json`'s `author.url` |
| `license` | string, ≤ 64 characters | required: `plugin.json`'s `license`, which `tools/validate.mjs` holds to `policy/spdx-allowlist.json` |
| `capabilities` | array of unique strings | required: `releases[0].capabilities`, or `[]` when that release declares none |
| `categories` | array of unique strings | optional: `plugin.json`'s `categories`, sorted |
| `keywords` | array of unique strings | optional: `plugin.json`'s `keywords`, sorted |
| `homepage` | string, `^https://` | optional: `plugin.json`'s `homepage` |
| `repository_url` | string, `^https://github\.com/` | required: `https://github.com/` followed by `source.repo` |
| `icon_url` | string: a `data:image/…;base64,…` URI, or empty | required: the store card's picture, inlined from the icon committed beside the listing so that it is inside the signature; the empty string when there is none. Never an `https://` URL |
| `source` | object, `signed.plugins[].source` | required: where the bytes come from |
| `downloads` | integer ≥ 0 | required: always `0` |
| `stars` | integer ≥ 0 | required: always `0` |
| `updated_at` | `YYYY-MM-DDTHH:MM:SSZ` | required: `releases[0].published_at` |
| `added_at` | `YYYY-MM-DD` | optional: the day the plugin was first listed. `schema/plugin-v1.json` requires it of every listing, and the generator copies it through |
| `staging` | boolean | optional: `true` when the latest listed release has no artifact digest yet (*Staging entries*, above); never written as `false` |
| `download_url` | string | required: the legacy platform-agnostic URL. Empty except for an installable `noarch` release, which has one artifact for every host |
| `platform_downloads` | object, platform key → `https://` URL | required: the projection of `releases[0].artifacts`. `{}` when that release is not installable — staging, or any artifact without both `sha256` and `size` |
| `releases` | array of `signed.plugins[].releases[]`, at least one | required: newest first by semver precedence. A yanked version is not listed |
| `publisher` | string | optional: the key into `signed.publishers` — the login of the reviewed publisher record that the owner half of `source.repo` resolves to, case-insensitively, as that record's own login or one it `covers`. **Absent** when no reviewed record exists, and the absence is the answer: a client that badges on this member being present badges every listing. Never the `author` string |

The card in one other language, `signed.plugins[].i18n.<code>`, is:

| member | type | rule |
|---|---|---|
| `name` | string, 1–64 characters | required: the card's title in that language, from the locale's `listing.name` |
| `description` | string, 1–200 characters | required: the one-line card text in that language, from the locale's `listing.description`. A half the locale does not translate is filled from English, so a block always has both, and a block identical to the English card is left out |

Where a plugin's bytes come from, `signed.plugins[].source`, is:

| member | type | rule |
|---|---|---|
| `kind` | const `github` | required |
| `repo` | string, `owner/name` | required: the GitHub repository the plugin is published from. `repository_url` is built from it, and `publisher` is resolved from its owner half |
| `subdirectory` | string | optional: copied through from `plugin.json`'s `source.subdirectory` |

One release, `signed.plugins[].releases[]`, is:

| member | type | rule |
|---|---|---|
| `version` | string | required: this release's semver version |
| `published_at` | `YYYY-MM-DDTHH:MM:SSZ` | required: the GitHub Release's publication time, recorded in the version file rather than read from a clock |
| `protocol` | integer, 0–65535 | optional: the plugin protocol version the bundle speaks |
| `min_astra_version` | string | optional: the lowest Astra version the plugin's manifest says it needs |
| `capabilities` | array of unique strings | optional: the daemon's capability names, verbatim, sorted |
| `permissions` | object | optional: the manifest's `[permissions]` section, copied through unchanged. The one open object in this document (`additionalProperties: true`): its ids are the app's vocabulary, so an id this schema has never heard of is carried rather than refused. `schema/version-v1.json` says what the daemon reads from it |
| `changelog_url` | string, `^https://` | optional: copied through from the version file |
| `staging` | boolean | optional: `true` on a release that exists on paper and has no artifact digest yet; never written as `false` |
| `staging_reason` | string | optional: written only beside `staging: true`, copied through from the version file |
| `release` | object, `signed.plugins[].releases[].release` | required: where the artifacts are served from, which is what their URLs must sit under (§5.2) |
| `artifacts` | object, platform key → `signed.plugins[].releases[].artifacts.<platform>`, at least one | required |

Where a release is served from, `signed.plugins[].releases[].release`, is:

| member | type | rule |
|---|---|---|
| `kind` | `github_release` or `direct` | required |
| `repo` | string, `owner/name` | required when `kind` is `github_release`: the repository whose release serves the artifacts |
| `tag` | string | required when `kind` is `github_release`: that release's tag |
| `commit` | string, 40 lowercase hex digits | optional: the source commit that built the artifacts, recorded at ingest. The bot refuses a Release whose commit disagrees with its build attestation's |
| `base_url` | string, `^https://` | required when `kind` is `direct`: the prefix every artifact URL of this release sits under. Policy keeps `direct` out of the public catalogue (§5.2) |

One artifact, `signed.plugins[].releases[].artifacts.<platform>`, is:

| member | type | rule |
|---|---|---|
| `url` | string, `https://`, ≤ 1024 characters | required: where the file is downloaded from. It must sit under the prefix its release implies and end in `filename` (§5.2) |
| `filename` | string, ending `.astraplugin` | required |
| `sha256` | string, 64 lowercase hex digits | optional: the SHA-256 of the whole `.astraplugin` file (§5.2). Absent only on a staging release, which is uninstallable by construction |
| `size` | integer, 1 byte to 256 MiB | optional: that file's length in bytes (§5.2) |

A publisher record, `signed.publishers.<owner>`, is what the registry knows about the account behind a listing, keyed by that account's GitHub login. It is inside `signed`, so the signature a client already checks covers it — a badge is a claim the registry makes, and a claim outside the signature is one whoever serves the bytes could invent:

| member | type | rule |
|---|---|---|
| `display_name` | string, 1–64 characters | required: what a person sees beside the badge |
| `description` | string, 1–120 characters | optional: one line saying who this publisher is to Astra. A client renders nothing when it is absent rather than inventing a default |
| `tier` | `astra_team` or `verified` | required: a client **MUST** render on explicit membership — equal to `astra_team` or equal to `verified` — and never on the value merely being present or non-empty. An unrecognised tier is not a badge |
| `verified_at` | `YYYY-MM-DD` | required: when the evidence behind the tier was first accepted |
| `last_confirmed_at` | `YYYY-MM-DD` | optional: when that evidence last held |

### 5.2 アーティファクトダイジェスト、そして URL がどこを指してよいか

`artifacts.<key>.sha256` は、`.astraplugin` ファイル全体の `sha256`
であり、証明の主体、そしてデーモンがハッシュするものと同じ数値です
([`bundle-v2.md` §3.1](bundle-v2.md#31-アーティファクトダイジェスト))。`size`
はそのファイルの長さです; スキーマはこれを 256 MiB に制限します。

すべてのアーティファクト URL は `https://` でなければならず(MUST)、
自身の `release` オブジェクトが含意するプレフィックスの下になければ
なりません(MUST):

* `github_release` → `https://github.com/<repo>/releases/download/<tag>/`、
* `direct` → そのリリースの `base_url`、

そして宣言された `filename` で終わらなければなりません(MUST)。これ
はスキーマのパターンではなく `astra-registry/tools/validate.mjs` で
強制されます。なぜなら、GitHub しか記述できないパターンは、自己ホスト
のケースを表現不可能にしてしまうからです。`direct` は自己ホストと
ステージングのカタログのために存在します; ポリシーはこれを公開カタログ
から締め出します。

### 5.3 決定性 — 監査者が頼る性質

`index.json` の `signed` メンバーは `plugins/**` から
`tools/build-index.mjs` によって生成され、**時計を一切読みません**:
同じソース + 同じ serial → 同じバイト列。キーは UTF-16 コードユニット
でソートされ、プラグインは id で、リリースは semver で。コミットされ
たファイルが 1 バイトでも異なると `--check` は失敗し、CI がこれを
実行します。

`issued_at`/`expires_at` は、ジェネレータではなく、署名時に
`bot/sign-index.mjs` によって追加されます。理由は 2 つです: これらは
*公開*の性質であり、時計を読むジェネレータは再現できないからです。
これが §8 の監査をそもそも可能にしているものです — 第三者は git ツリー
からカタログの内容を再構築し、署名されたものと比較できます。

### 5.4 Serial

* デフォルトブランチ上の `git rev-list --count HEAD -- plugins` から
  導出される**単調増加**の値です。ファイルから読み取ってインクリメント
  することは決してありません: 同じ分でマージが 2 回起きると、両方
  とも *N* を読み、両方とも *N+1* を書いてしまい、2 番目が 1 番目
  を静かに打ち消してしまいます。コミット数は履歴の性質であるため、
  同時のマージは構造上異なる値を得ます。パスを制限することで、ドキュ
  メントのコミットがカタログのバージョン番号を動かすことはありません。
* 検証ツールはカタログ URL ごとに**シリアルフロア**を保持し、それを
  下回るものはすべて拒否します。このフロアは `max(in-memory,
  on-disk)` であり、インデックスキャッシュには**なく**、デーモンが
  所有し MAC された状態(`astra.registry.state/1`)にあります: キャッ
  シュはいつでも削除され得る便宜的なものであり、フロアは、攻撃者が
  まさに行うであろう削除を生き延びなければならないセキュリティ上の
  決定です。これは*コード内で*単調増加なので、状態ファイルを破損させ
  ることはファイルをリセットするだけで、実行中のプロセスをリセット
  することはありません。

3 つの文書、3 つの serial ルール、そしてその違いは意図的です:

| 文書 | 受理される条件 | 理由 |
|---|---|---|
| `trust.json` | 保持しているものより**厳密に大きい** | これは鍵のローテーションでのみ変わるため、「同じ serial、異なるバイト列」はロールバック攻撃以外の何ものでもない |
| `index.json` | フロア**を下回らない** | 通常の再公開 |
| `revocations.json` | ディスク上のものと**同等以上**; **厳密に大きい** serial は集合を置き換え、以下または同等の serial は**追加のみ**可能 | このリストは 7 日間のウィンドウ内に収まるようスケジュールで再署名されるため、同じものを拒否すると静かな週ごとにインストールがブロックされてしまう。「同じ serial、少ないエントリ」はリプレイであり、追加のみがそれを打ち負かす |

状態ファイルの MAC は**トリップワイヤーであり、境界ではありません**:
その鍵は、自身が認証するファイルと同じ 0700 ディレクトリにあるため、
そのディレクトリを読める攻撃者はそれを偽造できます。これは、「ファイル
を編集する」から「鍵を見つけて使う」へと敷居を上げます。本当の境界
はディレクトリです — `plugins/` の兄弟であり、決してその子ではあり
ません。そのため、これらの決定の主体は、その作者でもありません。

### 5.5 鮮度、そして最も重要な非対称性

| 文書 | TTL | 古くなることのコスト |
|---|---|---|
| `index.json` | **30 日**(`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`) | **バナー**。閲覧画面はカタログが古いと告げる。**キャッシュされ、ダイジェストで固定されたレコードはインストール可能なままです。** |
| `revocations.json` | **7 日**(`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`) | 新規インストールに対する**ハードブロック** |

この非対称性が鮮度ポリシーのすべてであり、それは各文書が何のために
あるかから導かれます。カタログレコードは*ダイジェスト*であり、
ダイジェストは期限切れになりません: レジストリを凍結させ、あなたが
すでに検証したレコードを持ち続けさせても、攻撃者は何も得ません。
撤回リストはその逆です — そこで「続行する」は「私たちがすでに撤回した
かもしれない何かをインストールし続ける」ことを意味します — そのため
これがブロックの対象です:

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

最後の文に注目してください。古さがすでに実行中のプラグインを止める
ことは決してありません。

準拠するクライアントが発する判定コード、最も深刻なものから
(`IndexVerdict::code`):

| コード | 意味 |
|---|---|
| `SIGNATURE_INVALID` | 署名が提供されたが、どれも信頼された鍵によるものではない。**改ざんを意味する唯一のコード。** これに到達するのに時計は関与しないため、時計はこれを言い訳にできません。 |
| `SIGNATURE_KEY_EXPIRED` | 委譲された鍵が署名したが、そのウィンドウの外であり、手元にあるサーバーの `Date` で判定された(そのためスキューは説明になりません) |
| `CLOCK_SKEW` | このマシンの時計と文書のタイムスタンプの両方が正しいことはあり得ず、署名は検証された — そのため疑わしいのは時計 |
| `CATALOG_STALE` | `expires_at` を過ぎている |
| `FRESHNESS_UNKNOWN` | `issued_at` も `expires_at` もない — 手書きのローカルカタログ |
| `UNSIGNED` | 署名がない、あるいはそれをチェックする信頼アンカーがない |

`SIGNATURE_INVALID` と `SIGNATURE_KEY_EXPIRED` は**拒否**です: 文書
はまったく読まれず、それに対して提供されるキャッシュされたフォール
バックもありません。`UNSIGNED` は拒否では**ありません** — これは
世界とすべてのローカルカタログの儀式前の状態です — しかし、レコード
を完全に信頼される状態に決して引き上げることはできません。

文書が**どこから取得されたかは決して入力になりません**。カタログが
信じられるのは、委譲された鍵がそれに署名したからであり、
`plugins.registry_url` は通常の設定であり、カタログがホストを移動
することは想定内です。デーモンの検証経路にはホスト名チェックが含
まれておらず、そのようなものを追加してはいけません。

## 6. `revocations.json`

### 6.1 形

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

`astra-registry/tools/revocations/` の下にある勧告 1 ファイルにつき
1 つずつから `tools/build-revocations.mjs` によって生成されます; 1
つの勧告は、それが名指しする鍵ごとに 1 つのエントリになり、すべての
エントリはその勧告の id、severity、action、reason、URL を運びます。
なぜなら、クライアントはそれらのうちちょうど 1 つ — 最初に一致した
もの — を表示するため、それぞれが単独で完結していなければならない
からです。エントリは `(kind, value)` でソートされているため、この
文書は決定論的です。

### 6.2 種別の語彙

`astra-daemon/src/plugins/trust.rs` の `RevocationKind` が権威です;
レジストリの `KINDS` テーブルが存在するのは、レジストリがデーモンが
静かに無視してしまうような種別を公開できないようにするためです —
未知の種別は起きない撤回です。

| kind | `value` | 一致するもの |
|---|---|---|
| `digest` | 64 桁小文字 16 進数 | `.astraplugin` 全体の `sha256`、大文字小文字を区別せず比較 |
| `binary` | 64 桁小文字 16 進数 | **解決された `entry.command` ファイル**の `sha256` |
| `id` | プラグイン id | そのプラグインのすべてのバージョン |
| `id_version` | `<id>@<semver>` | その正確なリリース |
| `version_range` | プラグイン id + `versions` ウィンドウ | §6.3 参照 |
| `identity` | `github:owner/repo` または `origin:host` | 固定された発行者アイデンティティ |
| `publisher_key` | 鍵 id | 信頼レコードの `signer_key_id` |

`action` は `block_install`、`disable`、`warn` のいずれかです。
`warn` はインストールをブロックしません; `disable` は、すでにインス
トールされたコピーも停止し無効化します。`severity`(`critical` /
`high` / `moderate` / `low`)は勧告のみです — どんな振る舞いもそれに
依存しません。

`reason` は、デーモンが恒久的とマークする通知の中で、ユーザーに
**そのまま**表示されます。そのためジェネレータは bidi オーバーライド
やゼロ幅接合子を含むテキストを拒否し、300 文字を上限とします。

### 6.3 バージョンウィンドウ

OSV の形と OSV のセマンティクス: `introduced` は**包括的**、`fixed`
は**排他的**、どちらも任意で、`{}` はすべてのバージョンを意味します
— これにより `version_range` は `id` の厳密な一般化になります。
`introduced == fixed` は何もカバーせず、ビルド時に拒否されます。

順序は標準の semver 優先順位に従うため、`1.0.0-rc.1 < 1.0.0` です:
「1.0.0 で修正」と言う勧告は `1.0.0-rc.1` を撤回されないままにして
はいけません。ビルドメタデータは無視されます(semver §10)。**どちら
の側もパースできないバージョン文字列は、ウィンドウの*内側*にあり
ます** — 代替案は、`version = "totally-fine"` が勧告が表現し得る
どんな境界もすり抜けてしまい、攻撃者がその文字列を選ぶことになる
ことです。

### 6.4 検証はカタログとは異なり厳格です

`verify_index_document` は段階的な判定を返します; `verify_revocations_document`
は `Err` を返します。信頼アンカーがない、署名がない、見知らぬ者から
の署名、あるいはウィンドウの外にある鍵からの署名は、すべて失敗です。
撤回リストは何かを*拒否*するためだけに参照されるため、誰も帰属を
証明できない文書には、唯一安全な読み方 — 「これは撤回リストではない」
— があり、それを空集合として返すことは、何のファイルでも配信すれば
到達できる、攻撃者が望む結果になってしまいます。

使用可能なリストがないことは、1 段上の 7 日間のブロック(§5.5)で
処理されます。寛容なパーサーではなく、それこそが、レジストリの障害
が静かな強制の喪失にならないようにしているものです。

キャッシュされたリストは、このデーモンがかつてそれを書いたからという
理由で信頼されることは決してなく、**ロードのたびに再検証されます**
— これが、キャッシュされたコピーがインストール級の入力になり得る理由
であり、鍵のローテーションが、稼働中のリストを退役させるのと同じ瞬間
にキャッシュされたリストも退役させる理由です。

### 6.5 サイドロードの穴、発生源で閉じられる

ダイジェストのみの勧告は、デフォルトで穴を残します: ダイジェストで
撤回すると、ユーザーはアンインストールでき(ダイジェストが読まれた
信頼レコードを落とす)、`plugin.toml` とバイナリをディレクトリに
コピーし、同じコードをサイドロードできてしまいます。ディレクトリには
アーカイブがないため、バンドルダイジェストも署名者もありません。

そのためジェネレータは、**すべてのエントリがディレクトリの持ち得ない
何かでキーづけされている勧告を拒否します。** 少なくとも 1 つのエント
リは `binary`、`id`、`id_version`、`version_range` のいずれかで
なければなりません(MUST)。`identity` と `publisher_key` は明示的
にカウントされません。

5 つの強制ポイントがこのリストを消費します: インストール(計画の
§5.3-A.4)、更新解決、インポート経路、サイドロード経路、そして記録
された `artifact_sha256` によるインストール済みプラグインとの定期的
な集合の交差。

## 7. 出所 — デーモンにはできないことをレジストリがチェックすること

### 7.1 取り込み時(レジストリ bot、`bot/lib/attestation.mjs`)

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`。これは、そのリポジトリ内のワークフローがこれらの
   バイト列をビルドし、Sigstore がそれを記録したことを証明します。
2. **証明の主体ダイジェストはアーティファクトの `sha256` と等しく
   なければなりません(MUST)** — その数値が現れる 3 か所のうちの
   3 番目(`E_ATTESTATION_SUBJECT_MISMATCH`)。
3. 証明書のソースリポジトリは `https://github.com/<repo>` でなければ
   なりません(MUST)(`E_ATTESTATION_REPO_MISMATCH`)。
4. **解決された再利用可能ワークフローのコミット SHA** が証明書から
   読み戻され、`trust.json` の `reusable_workflow_shas` に現れなけ
   ればなりません(MUST)(`E_WORKFLOW_NOT_ALLOWED`)。SHA の欠落は
   デフォルトではなく失敗です(`E_ATTESTATION_INVALID`)。

ステップ 4 こそが、可変な `@v1` タグをサプライチェーンとして使用不能
にするものです: タグは任意のコミットに再指定でき、それでも証明は
正しいリポジトリとワークフローファイルを名指ししてしまうでしょう。
その許可リストを変更することは root 鍵の儀式です。

その許可リストは今では存在します: 2026-08-19 にタグが動いて以来、署名済みの
`trust.json` は 2 つのコミット — `plugin-release/v1` が今指すものと、その前に
指していたもの — を名指しします。このページはそのどちらも書きません。仕様に
コピーされた SHA は、誰も比較しないリモートの複製だからです。そのため
`E_TRUST_UNPROVISIONED` はもう取り込みを止めず、
ステップ 4 は稼働しています — 他のどんなワークフローで生成されたビ
ルドも `E_WORKFLOW_NOT_ALLOWED` で拒否されます。デーモン側の半分は
別の理由で今も fail-closed です: カタログ自体に署名が運ばれていない
からです(§0.1)。

### 7.2 未実装: リリースごとの副署名

`PRODUCTION_PLAN` §5.2 は、以下に対するリリースごとの副署名を仕様
化しています

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**今日、これを計算またはチェックするものは何もありません。** この
文字列は計画には現れますが、3 つのリポジトリのどこにもありません。
レコードの真正性は現在、カタログ全体をカバーするインデックスエンベ
ロープの署名から来ています。このセクションに対して検証ツールを実装
する際、そのようなフィールドが見つかると期待しないでください。

### 7.3 デーモンが代わりに行うこと

デーモンは Sigstore の検証を**まったく**行いません: 証明は、ネット
ワーク、GitHub API、`gh` がすべて存在する bot の CI でチェックされ
ます。ローカルでは 2 つのことを行い、その組み合わせこそが、レジス
トリキーの侵害を「新しいプラグインの公開」に限定するものです:

* **TOFU ピン。** 最初のインストール時に、リスト掲載が宣言したアイ
  デンティティ(`{kind: "github", repo}` または
  `{kind: "origin", host}`)を記録します。アイデンティティが異なる
  更新は、**決して例外のないハードブロック**です。
* **URL とアイデンティティのバインディング。** アーティファクト URL
  は、固定されたリポジトリのリリース名前空間の下になければならず、
  リダイレクト解決後のホストとパスプレフィックスで比較されます。
  アイデンティティは、レコードが**宣言する**リポジトリであり、URL
  が含意するリポジトリでは決してありません — URL からそれを導出す
  ることは、最初のインストール時にそのチェックを同語反復にしてしま
  います。

残存リスク、UI が過大に主張してはいけないため述べます: `identity`
はレジストリが主張する文字列です。侵害された index 鍵は、真実の
アイデンティティと、捏造された来歴ブロックを持つレコードを公開でき
ます。URL チェックは、バイト列が固定されたリポジトリのリリース名前空
間から来ることを強制します; リポジトリとレジストリの両方の侵害は、
両方を打ち負かします。

## 8. 監査手順

公開されたカタログ内のすべては、どんな秘密鍵へのアクセスもない第三
者によって検証可能です。これがその手順です。**tooling** とマークさ
れたステップには `astra-registry` にスクリプトがあります; **manual**
とマークされたステップにはまだありません。`PRODUCTION_PLAN` §5.5
で名指しされている `registry/tools/audit-index.sh` は、**今日は存在
しません** — ここでは、それが自動化することになる手順として記述して
います。

**A. カタログの内容を再現する。** *(tooling)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

その後、公開された `signed` メンバーを再生成されたものと比較し、
`issued_at` と `expires_at`(§5.3)だけを無視してください。それ以外
の違いは、自身の git 履歴と一致しないカタログです。

*今日これが何を出力するか*(この文書を書く際に検証済み): どちらの
`--check` 実行も、serial 1、署名 0 件で「新規生成とバイト単位で同一」
と報告し、`validate.mjs` は**失敗します** — 11 件のリスト掲載すべて
がステージングエントリでアーティファクトダイジェストを持たず、
`--allow-staging` を渡さない限り拒否されます。これは、まだプラグイン
がリリースされていないカタログにとって正しい答えであり、その中の
何もインストール不可能である理由です。

**B. 署名チェーンをチェックする。** *(tooling)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

そして手動で、`trust.json` が `registry/v1/root.json` 内の、あなたの
Astra バイナリがログに記録するものと fingerprint が一致する鍵の下で
検証されることを確認してください。お好みであれば独立して再計算して
ください: `SHA-256(domain ‖ 0x00 ‖ JCS(signed))`、Ed25519 検証、
§2–§3 に従って。

*今日これが何を出力するか:* `FAIL … no trusted key was supplied
(offered: none; trusted: none)` — 渡すべき `trust.json` がなく、
それを検証する root もありません(§0.1)。現在のツリーに対してそれ
以外の何かを報告する検証ツールは嘘をついていることになります。

**C. serial とウィンドウをチェックする。** *(manual)* `serial` は、
あなたが最後に見たもの以上でなければならず; `expires_at −
issued_at` はカタログでは 30 日、撤回リストでは 7 日でなければなら
ず; `key_id` は、`issued_at` を含むウィンドウを持つ `trust.json` が
名指しする鍵でなければなりません。

**D. すべてのアーティファクトを公開の透明性ログに対してチェックする。**
*(manual)* インデックス内の各リリースについて — `<…>` はインデックス
レコードから読み取られるプレースホルダーであるため、以下の 2 つの
コマンドはコピーペーストではなくテンプレートです:

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` は、インデックスレコードの `release.repo` からの**作者の**
リポジトリです。`--signer-workflow` は、それをビルドした**共有され
た再利用可能な**ワークフローです — `astra-plugin init-ci` が呼び出し
元を固定する対象であり、bot が `astra-registry/bot/ingest.mjs` の
`DEFAULT_SIGNER_WORKFLOW` として保持し、`AstraPlugins/.github/workflows/`
に存在するファイルに対してアサートされます。それを再構築するのでは
なく、その定数から正確な文字列を取ってください; パスが入れ替わって
いると、どんな証明とも一致せず、すべての正直なアーティファクトが証明
を持たないように見えてしまいます。

`gh attestation verify` は、そのアーティファクトダイジェストに対する
Sigstore バンドルを取得し、Sigstore の信頼 root に対してそれをチェッ
クします。**Rekor の透明性ログへの包含証明も含めて。** その JSON
出力から、bot が取り込み時にアサートすること(§7.1)を手動でアサート
してください: 主体ダイジェストがファイルのダイジェストと等しいこと、
ソースリポジトリがインデックスが名指しするリポジトリであること、そし
て解決された signer-workflow のコミット SHA が `trust.json` の
`reusable_workflow_shas` に含まれていること。

証明が**まったくない**、あるいは異なるリポジトリを名指しする証明を
持つアーティファクトに対してレジストリが公開したレコードは、まさに
この手順が存在する目的である事後検出です: 侵害されたレジストリ鍵が
*新しい*プラグインを公開することを止めるものは何もなく、監査可能性
こそが緩和策のすべてです。

**E. バンドル自体をチェックする。** *(tooling)*
ダウンロードしたファイルに対して
[`bundle-v2.md` §13](bundle-v2.md#13-検証アルゴリズム)
を実行し、その `MANIFEST.json` の `plugin_id`、`version`、
`platform`、`permissions_hash` がインデックスレコードと一致すること
を確認してください。

## 9. 今日発効しているもののまとめ

| 性質 | 状態 |
|---|---|
| 文書フォーマット、エンベロープ、署名構成、JCS プロファイル | 両端で実装済み、フィクスチャによる相互テスト済み |
| root 鍵 | 2026-08-11 に**プロビジョニング済み** — 両側で同じ 2 つ |
| `trust.json` | `astra-root-2026a` の下で**署名済み**、`astra-index-2026a` に委譲し、1 つのワークフローコミットを許可リスト化 |
| `index.json` / `revocations.json` の署名 | コミットされたツリーでは空の配列 — **これが今、欠けているリンクです** |
| カタログの判定、serial のフロア、鮮度、時計の扱い | デーモンで実装済み、テスト済み |
| 失効の語彙、マッチング、5 つの強制ポイント | 実装済み; **署名が有効なリストが一度取得されるまでは無効** |
| 取り込み時のビルド証明チェック | 実装済みで稼働中; ワークフローの許可リストは署名済みの `trust.json` から来る |
| リリースごとの副署名 | 計画にのみ仕様化されている; **実装なし** |
| `audit-index.sh` | 存在しない; §8 が手動の手順 |

---

*この文書を書く際に確認したソース:
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`;
`astra-registry/tools/lib/canonical.mjs`;
`astra-registry/tools/lib/revocations.mjs`;
`astra-registry/tools/build-index.mjs`; `astra-registry/bot/lib/sign.mjs`;
`astra-registry/bot/sign-index.mjs`; `astra-registry/bot/lib/attestation.mjs`;
`astra-registry/registry/v1/{root,index,revocations}.json`;
`astra-registry/SECURITY.md`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs`
(`refresh_revocations`)。*
