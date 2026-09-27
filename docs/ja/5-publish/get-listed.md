> **これは翻訳です。** 正式な情報源は [docs/en](../../en/5-publish/get-listed.md) です。内容に食い違いがある場合は英語版が優先されます。

# リストに掲載してもらう

**プラグインは 1 回だけ、それきりリストに掲載されます。** その後、
リリースはノータッチになります: タグを打ち、CI にビルドと証明をさせれば、
レジストリがそれを取り込みます。

前提条件: **公開**リポジトリ上での [CI によるリリースビルド](release-with-ci.md)
で、`.astraplugin` アセットが添付され証明されていること。この前提条件は
タグを打つことで満たされます — 再利用可能ワークフローは
`mihailinl/AstraPlugins` のデフォルトブランチにあり、`plugin-release/v1`
としてリリースされているため、タグの push がビルドと証明を行います。この
ページのすべては、あなたがそれをすでに終えていることを前提としています;
まだの場合は、先に [CI でリリースする](release-with-ci.md) を行うか、
全行程を 1 ページにまとめた [プラグインを公開する](../publishing.md) を
読んでください。

**これでは代わりにならないもの**、なぜならそれぞれが試されたことがある
からです: あなたのソースを含むリポジトリ、誰かに送った `.zip`、あなたの
ラップトップでビルドしたバンドル、あるいはメンテナーにビルドを頼む
メッセージ。レジストリは CI が証明したリリースアセットだけを掲載し、それ
以外は一切掲載しません。

以下の手順はすべて、`astra-plugin`、あなた自身のリポジトリでのコミット、
または Minice アカウントでサインインした https://astra.minice.ai/plugins の
パネルのどれかです。CLI を持っていなければ、先に
[インストールしてください](../install-cli.md) — ビルド済みバイナリが
あります。

## 1 · 事前確認する

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

これはレジストリが実行するチェックのうち、ローカルで実行できるものを
すべて実行し、そのうえで — 重要な半分ですが — **レジストリでしかでき
ないチェックを名指しし**、まだ証明されていないものが何かを教えてくれ
ます。

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**このうち 1 つは前もって片付けるもので、片付けなければなりません。**
バインディングの判定は、[リポジトリをバインドする](#リポジトリをバインドする)
が書き込む行を読みます。タグを打つ前にそれをコミットしておけば、チェックには
見つけるものがあります。省くと、最初の答えは `B_UNBOUND` になります。

### あなたのリスト掲載がどう見えるか

これを決めるのは 2 つのファイルで、どちらもすでに `plugin.toml` の隣に
あるものです。マニフェストのどこにもこれらの名前は書かれていません —
パッカーはこれらの名前だけを見て拾い上げ、レジストリはたった今検証した
バンドルからそれらを読み戻します。あなたが URL を入力することはなく、
誰もあなたの代わりに入力することもできません。

**アイコン** — あなたのプラグインのカードに表示される画像です。次の
どれか 1 つ:

<!-- doctest: illustrative reason="the accepted filenames, not a command; spec/icon-formats.yaml is the list both the packer and the registry read" -->
```
icon.png    icon.webp    icon.svg    icon.jpg    icon.ico
```

`astra-plugin new` はプレースホルダーの `icon.svg` を雛形として生成する
ので、差し替える対象があります。正方形で描いてください; おおよそ 64
ピクセルで表示されるため、細かいディテールよりも大胆なシルエットが
求められ、ストアはユーザーのテーマに従うため、明るい背景でも暗い背景
でも読み取れる必要があります。透過背景の PNG がよくある答えです。

SVG を出荷する場合は、静的なものにしてください: `<script>` なし、
`on*` ハンドラなし、`<foreignObject>` なし、あなたのマシンの外にある
何かへの参照なし。これらのいずれかを含むアイコンは落とされ、あなたの
プラグインは画像なしで掲載されます。これはあなたのリリースを失敗させ
ません — 装飾的なファイルはソフトウェアの出荷を止めるゲートでは
ありません — ですが、その旨の警告が出て、誰もあなたのアイコンを見る
ことはできません。

**`README.md`** — あなたのプラグインのページで、誰かがカードをクリック
したときに表示されます。これは、人がインストールするかどうかを決める
際に読むものであり、1 行の要約よりも価値があります。

これは GitHub 風の markdown としてレンダリングされ、テーブルも含みます。
スクリーンショットも動作し、画像だけで構成された段落はギャラリー行に
なります:

<!-- doctest: illustrative reason="markdown an author writes in their own README; there is nothing here for a runner to execute" -->
```markdown
![The command editor, mid-roll](docs/editor.png)
![The trigger firing on a natural 20](docs/trigger.png)
```

3 つのルールがあり、レジストリはあなたのリストを導出する際にすべてを
適用します:

- **画像は相対パスでリンクし**、リポジトリにコミットしてください。
  これらは、あなたのリリースがビルドされた正確なコミットを指すように
  書き換えられるため、誰かがリスト掲載を承認した後に画像が変わることは
  ありません。
- **GitHub 以外でホストされている画像は落とされ**、その alt テキストに
  置き換えられます。ビルドバッジも含みます。これはセキュリティルール
  というよりプライバシールールです: レンダリングされた README 内の
  すべてのリモート画像は、ユーザーが何もインストールしていない段階で、
  そのマシンからのリクエストになるからです。
- **生の HTML は取り除かれます。** レイアウトには markdown を使って
  ください。

長い README は行の境界で 16 KB に切り詰められ、続きへの GitHub 上の
リンクが付きます。

## リポジトリをバインドする

**掲載は Minice アカウントのものです。** すべての最初の掲載と、掲載が
バインディングを持つならそのすべてのリリースは、**バインディング**に照らして
読まれます: リポジトリのルートにある `.well-known/astra-plugin-owner` の
1 行で、公開を行う Minice アカウントでサインインしたパネルであなたが発行した
トークンから、CLI が書き込みます。このページでコマンドではない唯一の手順で
あり、これを飛ばすのが、正しく誠実な最初の提出が拒否されるいちばんよくある
道筋です。

**1 · トークンを発行する。** 掲載の所有者となる Minice アカウントで
https://astra.minice.ai/plugins にサインインし — Astra の所有に伴う
`astraUser` が必要です — このリポジトリ用のバインディングトークンを発行します。

**2 · 行を書き込む。** リポジトリ内のどこででも:

<!-- doctest: cli -->
```bash
astra-plugin init-ci --binding <token>
```

これはリポジトリのルートにある `.well-known/astra-plugin-owner` の**1 行目**に
`astra-binding: <token>` を書き込み、どんな綴りであれ以前のバインディング行を
削除し、あなたのログイン行を残し、ネットワークは使いません:

<!-- doctest: output from="astra-plugin init-ci --binding k3Vq9ZtW2xLr8NfBcY5pHd" unrun="rewrites .well-known/astra-plugin-owner in a git repository; re-run it at the root of your own" -->
```
  Rewrote: .well-known/astra-plugin-owner
    line 1   astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd
    kept     1 other line(s), byte for byte

  This token is public once you push it. It records one Minice account's consent
  to publish from this repository, and it authenticates no release: never merge a
  binding line you did not mint yourself. What that means, and what a rename or a
  transfer does to it:
    https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository

  Next: commit this file on your default branch, then tag. Before you push the tag,
    astra-plugin check --tag <tag>
  reads the line back from the tagged commit, as the registry will.
```

**3 · デフォルトブランチにコミットしてから、タグを打つ。** タグを push する
前に、レジストリと同じやり方で行を読み戻してください — 作業ツリーからでは
なく、タグのコミットから:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
```

不正な行はここで、`B_BINDING_MALFORMED` として失敗します。直すのにまだ何も
かからないうちに。行がなければ `B_UNBOUND` を予測する警告になります。
レジストリにしか出せない 4 つの答えは、毎回「チェックしていない」と名指し
されます。

**4 · パネルで提出する。**
`astra-plugin publish` がリポジトリとタグを記入済みのパネルの提出ページを
開きます。たとえば
https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0 です。
あなたがサインインして提出するまで、このページは何も提出しません。

**トークンとは何で、何ではないか。** バインディングトークンは**公開**されて
います。公開リポジトリのファイルの中にあるからです。それはこのリポジトリから
公開するという **1 つのアカウントの同意**を記録するもので、**どのリリースも
認証しません** — 何にも遅延されないリリースは、アカウントに知らされる前に
公開されます。だから**自分で発行していないバインディング行は決してマージ
しないでください**。それを追加または変更するプルリクエストは、あなたの掲載を
他人のアカウントに渡すよう求めているのです。

**行がなければならない場所。** プラグインがどのディレクトリにあっても
リポジトリのルートに、リリースタグが指すコミットの中に、そしてファイルの
最初の 4096 バイト以内に。1 行でリポジトリ内のすべてのプラグインを
カバーします。後でデフォルトブランチから削除しても、すでにバインドされた
ものは何も終わりません。

**発行したトークンの有効期間。** 発行したトークンは、発行から 30 日後に失効
します。ただし、生きている提出がそれを指名しているか、ルールが適用される
時点でその行がリポジトリのデフォルトブランチにある場合は別です — ルールは
失効の判断のたびに改めて確認されます。したがって、デフォルトブランチに行が
ないままずっと後でタグを打つ作者は発行し直すことになり、ルールが適用される
時点で行がまだそのブランチにある作者はその必要がありません。コミットして
後で削除した行は、トークンを生かし続けません。

**サインイン。** レジストリはアカウントの適格性を最後の検証済みサインイン
から読み取り、それは 12 時間有効です。バインドされたリポジトリのリリースは、
その時間内にアカウントがサインインしていない間は待機します。パネルがそう
表示し、`notice.sign_in` 通知がサインインを求めます。サインインするまで何も
公開されません。

**通知の届け先。** Minice アカウントの検証済みメールアドレスと、パネルです。
Telegram は連携できる任意の追加チャネルで、何もそれを必要としません。

**名前の変更や移管は、インストール済みのコピーを取り残します。** Astra は
インストール済みのプラグインをそのリポジトリ `github:owner/name` で識別
します。リポジトリの名前を変えたり別の所有者へ移管したりすると、インストール
済みのコピーはすべて、新しい名前から再インストールされるまで更新を受け取らなく
なります。これを覆す手段はありません。

**すでに掲載されているプラグインの場合。** バインドされていない掲載は
`grandfathered` です。バインディング期限とレジストリのカットオーバーのうち
遅いほうまで、今日と同じように公開を続けます。期限はサードパーティの
バインディングが始まる前に定められ、レジストリが公開します。その後、
バインドされていない掲載は `frozen` になります。インストール済みのコピーは
動き続け、インストールもできますが、バインディング行を持つリリースが公開
されるまで、新しいリリースは公開されません — バインドされたリリースで凍結は
解け、ペナルティはありません。バインディング行を持つ最初のリリースは、人による
レビューのために一度保留されます(`R_FIRST_BINDING`)。そしてカットオーバー
以降、`grandfathered` の掲載の遅延またはレビュー対象のリリースは、掲載が
バインドされるまで待機します。

**事前確認。** `astra-plugin check` は、レジストリが拒否する ID — 予約済みの
ID や、レジストリの ID パターンから外れるもの — と、不正なバインディング行を
拒否します。`astra-plugin dev` と `astra-plugin build` はどちらも拒否しません。
レジストリのルールが決めるのは何が掲載されるかであって、あなたが何を実行して
よいかではありません。

## 2 · パネルで提出する

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

これはパネルの**提出ページ**を、リポジトリとタグを記入済みの状態でブラウザに
開きます。**何もアップロードせず、資格情報も一切保持しません** —
`astra-plugin login` はなく、シェル履歴に残るトークンもなく、連携すべき
キーリングもありません。ページはリンクから自分で記入されますが、何も提出
しません。提出するのはあなたで、リポジトリがバインドされている Minice
アカウントでサインインして行います。`--print-url` は代わりにリンクを表示
します:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

バインディング行のないリポジトリには、リンクの上でそのことと、バインドの
方法を読める場所が示されます。タグのないチェックアウトには、タグを push する
必要があるという 1 行が出ます。どちらも注意書きであってエラーではありません。
レジストリはタグのコミットとリリースを GitHub から読むので、大事なのはあなたが
push したものです。

提出が運ぶのは**2 つの事実**です:

| フィールド | 読み取るのではなく入力する理由 |
|---|---|
| ソースリポジトリ(`you/dice-roller`) | バンドルは、自分がどこから配信されるかを保証できない |
| リリースタグ(`v0.1.0`) | 同上 |

**それ以外はすべて、証明済みのバンドルから読み取られます** — ID、バージョン、
表示名、概要、ライセンス、ケイパビリティ、パーミッション、プラットフォーム、
ダイジェスト、サイズ。これは利便性の話ではありません。バンドル内のすべては
証明によってカバーされているので、フォームに入力されたどんなものよりも厳密に
信頼できます。また、`plugin.toml` と食い違いうるフォームが存在しないので、
拒否の一群がまるごと消えます。

## 3 · 提出後に何が起きるか

パネルはあなたの提出の状態と、それに付いたすべての理由を表示し、同じ節目が
通知としても届きます: Minice アカウントの検証済みメールアドレスとパネルに、
そして Telegram にはそれを連携している場合にのみ届きます — Telegram を必要と
するものはありません。以下のルールはレジストリのもので、その `docs/POLICY.md`
で公開されています。コードはパネルが表示するもので、開始時点では英語の
タイトルです。

### 提出がたどる状態

| 状態 | 意味 |
|---|---|
| `received` | パネルがあなたの提出を受け付け、まだ何も読んでいない |
| `checking` | レジストリの bot がリリースを読み、すべてのアセットをゼロから検証している |
| `held` | 機械が決められることはすべて通り、1 つの判断が人のものになっている — 下記参照 |
| `approved` | モデレーターが保留を承認した。ほかに待っているものがなくなれば公開される |
| `delayed` | すべて通った。パネルが示す時刻に自動で公開される |
| `published` | レジストリにコミットされた |
| `served` | Astra がインストール元にする署名済みカタログに入った |
| `refused` | チェックが失敗した。パネルがコードと、Recheck で解消できるのか新しいタグが必要なのかを示す |
| `stopped` | 公開される前にあなたが止めたので、公開されない |

次のすべてが成り立つとき、リリースは人を介さずに自動で公開されます: その
プラグインにすでに掲載されているリポジトリから、同じアカウントにバインド
されたまま来ていること。bot のチェックがすべて緑であること。バージョンが
厳密に新しいこと。以前は持っていなかった高リスクのパーミッションを求めて
いないこと。そして、新しいパーミッションやケイパビリティを一切求めていない
こと。最後の条件だけを外しても、遅延の後に自動で公開されます。

**最初の掲載は決してそのどれにも当たりません。** 一度だけ、永久に一度、人の
ために保留されます。なので「最初のプラグインが掲載されるまでどのくらい
かかるか」への答えは *モデレーターが読んだとき* であり、パネルは待っている
ことを示します。

### 答えがコードのとき

拒否はあなたのプラグインへの評決ではありません。名前の付いた、直せる状態で
あり、パネルは 2 つのうちどちらの方法で解消するかを示します。**Recheck** は
パネルのボタンで、同じタグに対してすべてのチェックをゼロから再実行します —
タグ付けされたバイトの外側の修正、たとえば添付し忘れたリリースアセットの
ためのものです。**新しいタグ** は、そのバイトの内側を変える唯一の方法です。
証明はまさにそのバイトをカバーしているからです。バインディングのコード:

| コード | 意味 | 直し方 |
|---|---|---|
| `B_UNBOUND` | タグ付けされたコミットにバインディング行がなく、この掲載には必要 | リポジトリをバインドしてタグを打ち直す: [リポジトリをバインドする](#リポジトリをバインドする) |
| `B_BINDING_MALFORMED` | バインディング行が 2 つある、またはバインディングのつもりの行がそうなっていない(`Astra-Binding:`、短すぎるトークン) | `astra-plugin init-ci --binding <token>` がちょうど 1 行でファイルを書き直す。タグを打ち直す。`astra-plugin check --tag` は push する前にこれを示す |
| `B_BINDING_UNUSABLE` | 行のトークンが、このリリースに使えるものを何もバインドしていない: 取り消された、期限切れ、別のリポジトリ用に発行された、またはそのアカウントが公開できない | パネルでこのリポジトリ用の新しいトークンを発行し、タグを打ち直す。下の 2 つのどちらに当たるかはパネルが示す |
| `B_BINDING_INVALID` | あなたとモデレーターにだけ表示される: トークンそのものが問題 — 不明、取り消し済み、期限切れ、または別のリポジトリ用に発行されたもの | このリポジトリ用に新しいものを発行する |
| `B_ACCOUNT_INELIGIBLE` | あなたとモデレーターにだけ表示される: トークンの背後のアカウントが公開できない。たとえば `astraUser` を持たなくなったため | アカウントを直してから Recheck |
| `B_OWNER_CHANGED` | リポジトリが、この掲載が記録されている所有者とは別の所有者のものになっている | 移管は作者の交代です。モデレーターを待ちます。インストール済みのコピーは再インストールされるまで古い名前を保ちます |
| `B_REPOSITORY_RECYCLED` | リポジトリ名が、掲載されているものとは別のリポジトリのものになっている | 永続的: Recheck、タグ、承認のどれでも解消しない。掲載の ID をリセットできるのはモデレーターだけ |

そして、作者がいちばんよく当たるリリースのコード:

| コード | 意味 | 直し方 |
|---|---|---|
| `E_ATTESTATION_MISSING` | バンドルにビルド証明がない | 自分でビルドしたバンドルをアップロードした。CI にビルドさせる: [CI でリリースする](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | リリースに `.astraplugin` アセットがない | ワークフローが実行されなかったか、実行されて失敗した。Actions タブを確認し、アセットを添付してから Recheck |
| `E_RELEASE_NOT_FOUND` | そのリポジトリにそのタグのリリースがない | 下書きのリリースはあなた以外の誰にも見えず、非公開のリポジトリは存在しないものと同じに見える。公開してから Recheck |
| `E_WORKFLOW_NOT_ALLOWED` | ビルドがこのレジストリの許可しないワークフローで実行された | Astra の再利用可能ワークフローをコミット SHA でピン留めし — `astra-plugin init-ci` がそうする — タグを打ち直す |
| `E_ASSET_URL_FOREIGN` | アセットの URL があなた自身のリポジトリのリリース配下にない | ダウンロード URL はすべて `https://github.com/<owner>/<repo>/releases/download/<tag>/` の下になければならない |
| `E_INPUT_REPO` / `E_INPUT_TAG` | リポジトリかタグが想定された形ではない | `you/dice-roller` であって URL ではない。`v0.2.0` であってコミット SHA やブランチではない |

各コードのタイトルと直し方を含む完全な一覧は、レジストリの
`docs/BOT-CHECKS.md` です。

止まった提出に見えて、実はそうではない待機が 2 つあります:

| コード | 意味 |
|---|---|
| `W_ELIGIBILITY_UNREADABLE` | レジストリはアカウントの適格性を最後の検証済みサインインから読み取り、それは 12 時間有効です。パネルにサインインすればリリースは先へ進みます。`notice.sign_in` 通知も同じことを伝えます |
| `W_REGISTRY_UNACKNOWLEDGED` | レジストリの bot が変更され、オペレーターの承認を待っています。あなたのリリースには何の問題もなく、あなたに求められることもありません |

### 人を必要とする 3 つのこと

ちょうど 3 つで、レジストリの公開ポリシーを変えない限りこのリストは増えません:

| 出来事 | コード | 理由 |
|---|---|---|
| **プラグインの最初の掲載**、またはすでに掲載されているもののバインディング行を持つ最初のリリース | `R_FIRST_LISTING`、`R_FIRST_BINDING` | 一度だけ、永久に一度。まだ何もピン留めされていないので、後で照合できるものがない |
| **新たに要求された高リスクのパーミッション** | `R_NEW_HIGH_RISK` | ユーザーはそれへの同意を求められる。その前に、何のためのものかを誰かが読んでおくべき |
| **リポジトリ、その ID、またはそのバインディングが変わった** | `R_IDENTITY_CHANGED`、`R_BINDING_CHANGED` | インストール済みのコピーはすべて古いリポジトリへのピンを持っている。誰かがそうでないと言うまで、変更は作者の交代である |

ここでの高リスクは 4 つの名前です: `client`、`dom_access`、
`send_chat_message`、`set_theme_contribution` — `[capabilities]` と
`[permissions]` のどちらでも同じように照合されます。どのセクションで宣言
したかは問題ではないからです。`push_to_ui` には同意のチェックボックスが付き
ますが、レビューはありません: あなたのプラグインがすでに所有するパネルの中に
描画するだけだからです。

チェックが別途、判断を人に委ねることもあります — 掲載済みのプラグインと
1 編集しか違わない名前や、それと衝突する表示名です。それは `R_CHECK_HELD` と
して届き、3 つのうちには入りません。

モデレーターはパネルで承認または却下し、却下には理由が付き、それはあなたに
届きます。待っている間、あなたは何もしません。パネルが保留を表示します。

### リリースが代わりに待機するとき

すべてを通過しても、すぐには公開されないリリースがあります:

| 状況 | コード |
|---|---|
| このリリースが変えたかどうかに関係なく、プラグインが**何らかの**高リスクのパーミッションを持っている | `P_DELAY_HIGH_RISK` |
| 高リスクでない範囲で、前のリリースになかったパーミッションやケイパビリティを求めている | `P_DELAY_WIDENED` |
| 上のどちらかで、このレジストリでのリリース履歴がきれいな作者のもの | `P_TRUSTED_AUTHOR` |

パネルは正確な公開時刻を示し、時間が来ると、その時点のバイトに対してチェック
全体がゼロから再実行されます。**承認が遅延を縮めることはありません。** 遅延が
買うのは 1 つだけで、レジストリはそれ以上を主張しません: アカウントを乗っ取
られた作者が、自分の作っていないリリースを見て、止められる時間枠です。長さは
レジストリの `docs/POLICY.md` にあります。

まだ `grandfathered` の掲載 — バインディング以前に掲載され、まだバインド
されていないもの — には、もう 1 つ待機があります: カットオーバー以降、その
遅延またはレビュー対象のリリースは、掲載がバインドされるまで待ちます。

### 止める、取り下げる、異議を申し立てる、報告する

- **止める。** リリースが公開されるまでは、パネルで止められます。止めたものは
  公開されません。
- **取り下げる(yank)。** 公開後は、パネルでバージョンを取り下げられます。
  yank は決して元に戻せません — 代わりに新しいバージョンを公開してください —
  そして、掲載についての他のすべての判断と同じく、判断記録とともに記録され
  ます。掲載がまだバインドされていない間は、パネルでモデレーターに代わりに
  取り下げてもらうよう頼んでください。
- **異議申し立て。** 掲載についての判断が間違っていると思うなら、パネルで
  異議を申し立て、その答えはそこに記録されます。
- **評価** は星だけです: テキストも、返信も、名前もありません。
- **報告** — 他人のプラグインについてのもの — は GitHub ではなく
  https://astra.minice.ai/plugins を通します。Astra、デーモン、レジストリ、
  署名チェーンのセキュリティ問題は security@minice.ai へ —
  [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#security) を参照してください。

## 4 · それ以降のすべてのリリース

何もありません。タグを打てば、あとは CI がやります: レジストリは掲載済みの
プラグインの新しいタグを自分で検出して検証し、パネルがその状態を表示します。
提出するものも、ping するものもありません。現れないリリースは、パネルの
あなたのプラグインのページに、その状態と理由とともに載っています。

**バインディングは最初だけでなく、すべてのリリースで確認されます。** どの
リリースも、タグ付けされたコミットのバインディング行と掲載の ID 記録に
照らして読まれるので、行が変わったリポジトリや、別の所有者に移ったリポジトリは
公開されずに人を待ちます — それが、盗まれたトークンや移管されたリポジトリを、
誰かの目に留まる出来事にしています。

## リスト掲載が意味しないこと

リスト掲載は安全性のレビューではありません。誰もあなたのコードを読み
ません。レジストリ自身のポリシーもそう明言しています: パーミッションは
デーモンがプラグインの*ために*何をするかを決めるものであり、プラグイン
のプロセスがマシンに対して何ができるかについては何も決めません。
サンドボックスはありません。[セキュリティモデル](../1-orientation/security.md)
を参照してください。

## 今日の状況

読者がこのページに従う前に知っておくべきことが 1 つあります。

**署名チェーンはカタログまでは固定されていますが、撤回リストまでは
まだです。** 正確には、各部分は検証可能です:

- ルートキーは両側に存在します — `registry/v1/root.json` は
  `"status": "provisioned"` と 2 つの Ed25519 キーを持ち、デーモンの
  `PRODUCTION_ROOT_KEYS` にも同じ 2 つがコンパイルされています;
- `registry/v1/trust.json` は**今では**`astra-root-2026a` によって
  **署名されており**、インデックス署名キー `astra-index-2026a` に
  委譲しています。レジストリ自身の
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` がこれを
  確認し、bot が証明として受け入れる再利用可能ワークフローの SHA を
  出力します — 2026-08-19 にタグが動いて以来 2 つあり、`plugin-release/v1`
  が今指すコミットと、その前に指していたコミットです。そのため、以前は
  すべての取り込みを止めていた `E_TRUST_UNPROVISIONED` はもう発生しません;
- **クライアントに配信されるカタログは署名されています。** 2026-09-20
  以降、レジストリの署名者が `index.json` に `astra-index-2026a` で署名し、
  Pages にデプロイしています。`main` にコミットされたコピー、
  `registry/v1/index.json` と `revocations.json` は、意図的に
  `"signatures": []` を持っており、これを読むクライアントはありません。
  Pages が配信する撤回リストは今もコミット済みの未署名のものなので、失効の
  強制はまだ機能していません。

[`spec/registry-index.md` §0.1](../spec/registry-index.md) と
[セキュリティモデル](../1-orientation/security.md) を参照してください。

これがあなたにとって何を意味するか: このページの提出経路は、今日、
エンドツーエンドで機能します — あなたの提出は読まれ、チェックが
実行され、パネルが答えを表示し、リスト掲載はコミットされます。まだ保留中なのは、
Pages 上の署名済みの撤回リストで、これによりレジストリは、すでにインストール
されたコピーからバージョンを撤回できるようになります。それが着地しても、
このページの内容は何も変わりません。

## 関連ページ

- [`spec/registry-index.md`](../spec/registry-index.md) — インデックス、失効、検証アルゴリズム
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — bot があなたのアーカイブから何を読み取るか
- [バージョニング](../versioning.md) — 番号の意味と非推奨期間の長さ
