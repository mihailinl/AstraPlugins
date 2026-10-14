> **これは翻訳です。** 正式な情報源は [docs/en](../en/music-provider-plugins.md) です。内容に食い違いがある場合は英語版が優先されます。

# 音楽サービスプラグイン

音楽サービスプラグインは、`plugin.toml` の `[capabilities]` セクションで
`music_provider = true` を宣言します。するとプラグインは Astra の
**メディアセッション** の供給元になります。音楽ウィジェット、Dynamic Island、
アシスタントのメディアツール（`get_now_playing`、`control_media`、`play_music`、
`get_music_queue`）が、プラグインの接続先のサービス（Spotify の Web API、
デスクトッププレーヤーのローカル API、ブラウザへのブリッジ）に届き、サービス
**内で** 曲にいいねを付け、キューを読み、カタログを検索し、そこで再生を
始められるようになります。

そのための UI をプラグインは描きません。Astra のプレーヤーが描きます。

## プラグインがしなくてよいように Astra がすること

プラグインの周りのことは、すべてデーモンのメディアハブが引き受けます。

- **ペアリング。** サービスがこのコンピューターで再生しているとき、OS には
  たいてい同じ再生のメディアセッション（Spotify アプリ、ブラウザのタブ）が
  あります。ハブは両者を結び付けるので、1 曲は 1 セッションです。OS 側の
  セッションにあなたのいいねボタンとキューが加わり、二重に表示されることは
  ありません。何が **聞こえているか** の真実は OS のままで、あなたのタイトル、
  アートワーク、位置がそれを上書きすることはありません。
- **リモートセッション。** このデバイス **以外** で再生していると報告した
  セッション（スマートフォン、スピーカー）は、リモートと印を付けた独立した
  セッションとして表示されます。「このコンピューター」として扱われることは
  なく、アイランドには出ません。
- **振り分け。** ペアになったセッションでは、再生・一時停止・次へ・シークは
  どのアプリでも動く OS 経由で行い、いいね、いいねの解除、シャッフル、リピート、
  音量、キュー、再生の開始があなたに届きます。
- **上限と安全性。** アートワークはデーモンが取得します（https のみで、この
  コンピューターのネットワークには決して向けません）。リンクは https か既知の
  アプリスキームに限られ、文字列とリストは切り詰められ、モデルがあなたから
  読むものはすべて信頼できないテキストとして囲まれます。

つまりプラグインは、各サービスで何が再生されているかを報告し、1 度に 1 つの
操作を実行するだけです。

## プロバイダーを始める

<!-- doctest: cli -->
```bash
astra-plugin new my-music --lang python --template blank --capabilities music_provider --output ./my-music
```

`--lang` には `rust` や `typescript` も指定できます。音楽用のテンプレートは
ありません。ケーパビリティは `--capabilities` で入り、ひな形の `music_control` は
実装するまで `not_configured` を返します。`astra-plugin test` は、どの
プラグインも報告しないセッションと項目でフックを試します。プラグインが一度も
公開していないセッションキーには、フックが動く前に SDK が `not_found` を返す
ので、プローブが自分のプレーヤーで一時停止やいいねをすることはありません。
例外は `MusicSearch` で、実際の検索語を送るため、サインイン済みのプラグインは
本物のサービスから答えます (検索は何も変えません)。

`min_astra_version` を設定してください。`[capabilities]` は閉じた集合なので、
`music_provider` を導入したものより古い Astra はマニフェスト全体を拒否します。

## 報告: 毎回すべてを公開する

報告はプッシュです。どの SDK もパブリッシャーを持ち（Python と TypeScript では
`self.music`、Rust では `music_publisher` から返す `MusicPublisher`）、そこから
デーモンの長寿命ストリーム `MusicSubscribe` に応えます。最新のスナップショットを
すぐに送り、公開のたびに、そして `music_snapshot_heartbeat_secs`（15 秒）ごとに
送り直すので、黙ったプラグインは気付かれます。`music_session_stale_secs`
（45 秒）より古いスナップショットは信用されなくなります。

**公開は毎回 *すべて* です。** 含めなかったセッションは終了したとみなされます。

<!-- doctest: illustrative reason="needs a running service account; shows the publish call shape only" -->
```python
self.music.publish(
    [MusicService("spotify", "Spotify", can_search=True, can_play=True)],
    [MusicSession(
        session_key="spotify",
        service_id="spotify",
        this_device=True,
        device_name="DESKTOP-1",
        exclusive_app_hints=["spotify", "spotify.exe"],
        status="playing",
        title="Believer",
        artist="Imagine Dragons",
        artwork_url="https://i.scdn.co/image/…",
        position_seconds=42.0,
        duration_seconds=204.0,
        liked=True,
        controls=["play", "pause", "next", "previous", "seek", "like", "unlike", "queue", "play_into"],
    )],
)
```

ペアリングを決めるフィールド:

| フィールド | 意味 |
|---|---|
| `this_device` | 音が **この** コンピューターから出ている可能性がある。OS のセッションとペアになれるのはこの種のセッションだけ |
| `exclusive_app_hints` | このサービスしか再生しないアプリの OS セッション ID（Spotify の実行ファイル、MPRIS プレーヤー名）。一致するだけでペアになる |
| `shared_app_hints` | 多くのものを載せるホスト（ブラウザなど）。タイトルとアーティストも一致したときだけペアになる |

ヒントは大文字と小文字を区別せず、OS セッション ID、その最後のパスまたは
AppUserModelId のセグメント、そのセグメントから `.exe` を除いたもの、MPRIS
プレーヤー名と比べられます。したがって `spotify` は `C:\…\Spotify.exe`、
`SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify`、`org.mpris.MediaPlayer2.spotify`
のどれも指します。

`controls` はセッションが受け付ける操作を決まった一覧から示し、それ以外は
デーモンが捨てます: `play`、`pause`、
`next`、`previous`、`seek`、`like`、`unlike`、`shuffle`、`repeat`、`volume`、
`queue`（`MusicGetQueue` に応える）、`play_into`（`MusicPlay` に応える）。

## 応答: 4 つのフック

| フック | 必須かどうか | 内容 |
|---|---|---|
| `MusicControl` | 必須 | 1 つのセッションへの 1 つの操作。`value` には `seek` なら秒、`volume` なら `0`–`100`、`shuffle` なら `on`/`off`、`repeat` なら `off`/`track`/`context` が入る |
| `MusicGetQueue` | 任意 | 再生中の項目の前後にあるセッションのキューと `current_index` |
| `MusicSearch` | 任意 | カタログ検索。各項目の `item_ref` はあなた自身のもので、`MusicPlay` に戻ってくる |
| `MusicPlay` | 任意 | 項目、または語句に最初に一致したものを開始する。`mode` は `now`、`next`、`end` のいずれか |

**意図した拒否はエラーではなく応答です。** ユーザーがサインインしていない、
サービスがサブスクリプションを求める、どこでも何も再生していない、など。SDK の
拒否（3 つとも `MusicRefusal`）を、`not_supported`、`not_found`、
`no_active_device`、`auth`、`premium_required`、`rate_limited`、`unavailable`、
`not_configured` のいずれかとともに投げるか返してください。デーモンはそれを
本人の言語で表示します。それ以外のエラーは、プラグインが壊れていると報告します。

<!-- doctest: illustrative reason="the service calls are placeholders; shows the refusal shape only" -->
```python
async def music_control(self, request):
    if not self.signed_in:
        raise MusicRefusal(MusicErrorCode.NOT_CONFIGURED, "Connect Spotify in the plugin's settings")
    device = self.devices.get(request.session_key)  # act on THE session named
    if device is None:
        raise MusicRefusal(MusicErrorCode.NOT_FOUND, "That player has gone")
    await device.do(request.action, request.value)
```

## 間違えやすい点

- **位置は読んだとおりに報告し、先まで外挿しないこと。** 再生中のセッションは、
  その位置が最初に報告された時点からデーモンが外挿します。変更なしで再送された
  セッション (ハートビートがそうします) は時刻を保ち、新しい位置の公開で
  やり直されます。
- **同じ再生である間はセッションキーを変えないこと**（`[A-Za-z0-9._-]{1,64}`）。
  新しいキーは新しいセッションです。
- **ブラウザのタブを排他的と報告しないこと。** ブラウザはさまざまなものを再生し、
  あなたのいいねボタンが他人の動画に付いてしまいます。
- **サインイン用のトークンを `[config]` に入れないこと。** Astra は設定を素の
  JSON で保存し、プラグインのページに表示します。OS のキーリングを使ってください。
