> **これは翻訳です。** 正式な情報源は [docs/en](../../en/4-sdk/python.md) です。内容に食い違いがある場合は英語版が優先されます。

# Python SDK

PyPI 上の `astra-plugin-sdk` 0.5.0。`Plugin` をサブクラス化し、メソッドを
デコレートし、実行します。

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Python プラグインは **`noarch`** としてパッケージ化されます: すべての
プラットフォームに対して 1 つのバンドルです。その `[entry]` は
`command = "python"`、`args = ["-m", "src.plugin"]`、
`runtimes = ["python"]` です。

## プラグインの形

<!-- doctest: python-plugin -->
```python
"""Timer — an Astra plugin."""

from astra_plugin_sdk import BadArguments, Plugin, TriggerTypeDef, tool


class Timer(Plugin):
    """Start countdowns from chat."""

    @tool("Start a countdown. Use it when the user asks to be reminded in N minutes.")
    async def start_timer(self, minutes: int, label: str = "") -> str:
        # The signature IS the schema. `minutes` is required because it has no
        # default; `label` is optional because it has one; the type hints become
        # the JSON types the model is shown.
        if minutes <= 0:
            raise BadArguments("give me at least a minute")
        await self.log_info(f"timer for {minutes}m")
        await self.fire_trigger("timer_started", {"minutes": minutes, "label": label})
        return f"timer set for {minutes} minutes"

    async def get_trigger_types(self) -> list[TriggerTypeDef]:
        return [TriggerTypeDef(type="timer_started", label="Timer started")]


if __name__ == "__main__":
    Timer().run()


# ── tests ─────────────────────────────────────────────────────────────────────
# Plain `def test_*` functions: the harness is synchronous on purpose, so a
# plugin's test suite needs no pytest-asyncio, no event-loop fixture and no
# "coroutine was never awaited" to decode.

def test_it_starts_a_timer():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=5)
        assert result.unwrap() == "timer set for 5 minutes"

        fired = h.host.fired_triggers("timer_started")
        assert len(fired) == 1
        assert fired[0].payload["minutes"] == 5


def test_zero_minutes_is_a_bad_argument():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=0)
        assert not result.success
        assert result.code == "BAD_ARGUMENTS", result.code


def test_the_tool_is_registered_under_the_name_the_daemon_uses():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        assert h.tool_names() == ["start_timer"]
        h.assert_schema_accepts("start_timer", "minutes", "label")
```

## デコレータ

| | |
|---|---|
| `@tool("description")` | モデルが呼び出せる関数です。パラメータがスキーマになります |
| `@action("label")` | コマンドエディタ内のステップです |
| `@trigger(...)` | トリガー種別です |
| `@ui_call` | プラグイン自身の UI iframe が呼び出せるメソッドです |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | **クラス**デコレータです。バンドルの `ui/` ディレクトリ、あるいはプラグインが提供する URL から配信される UI コントリビューションを登録します |
| `Field(...)` | 1 つのパラメータのスキーマ — 説明、範囲、enum — を絞り込みます |

それ以外はすべて `Plugin` に対するオーバーライドです: `tts_synthesize`、
`tts_list_voices`、`tts_config_fields`、`stt_transcribe`、
`stt_transcribe_stream`、`stt_get_languages`、`stt_load` /
`stt_unload` / `stt_load_state`、`ai_complete`、`get_action_types`、
`execute_action`、`get_trigger_types`、`get_ui_contributions`、
`handle_ui_call`、`on_config_changed`、`on_language_changed`、
`on_active_triggers`、`on_shutdown`、`health_check`。

## Astra への呼び出し

`Plugin` 上の便利メソッド — `self.log_info`、`self.log_warn`、
`self.log_error`、`self.fire_trigger(type, payload_dict)`、
`self.push_to_ui(event, payload_dict)` — と、それ以外のすべては
`self.host` 上にあります:

| `self.host.…` | パーミッション |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | なし |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` は今日、どのプラグインに対しても機能しません。**
> デーモンはすべてのプラグインを `ClientType::PluginClient` として登録
> し、その認証インターセプターは `/astra.PluginHostService/` の外にある
> あらゆるパスでこのアイデンティティを
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")` で拒否します — `client = true` はこれに何の
> 変化ももたらしません。そのため `submit_user_message`、
> `subscribe_chat_events`、`speak`、`get_settings` はすべて実行時に
> 失敗します。デーモン側の半分がまだ構築されていないのであって、壊れて
> いるのではありません。
>
> **`host.send_chat_message` だけが AI のターンを駆動する動作する方法
> です。**

デーモン側が実装されたときのために: `DaemonClient` 上にあるのは
`send_message` ではなく **`submit_user_message`** です。完全な
クライアントは `on_daemon_client_ready(client)` に渡されますが、これは
`client = true` を宣言し、`is_client()` から `True` を返すプラグインに
対してのみです。

## エラー

送出(raise)してください。SDK はそれらを他の 2 つの SDK と同じ wire
コードにマッピングします。

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` ·
`RateLimited` · `Unavailable` · `Timeout` · `InternalError`、すべて
`PluginError` のサブクラスで、`ErrorCode` が列挙型です。
[`reference/errors.md`](../reference/errors.md) を参照してください。

## ケーパビリティの型はデータクラスです

`ToolDef`、`VoiceInfo`、`AiModelInfo`、`FieldDef`、`DropdownOption`、
`FieldCondition`、`ActionTypeDef`、`TriggerTypeDef`、`UiContribution`。

データクラスが期待される場所で生の `dict` を返すことは今も動作し、
`DeprecationWarning` を発します: 0.5.0 で非推奨、0.7.0 から削除可能です。
CI では `python -W error::DeprecationWarning` でこれをゲートしてください。

## テスト

| | |
|---|---|
| `testing.Harness` | このプロセス内で、実際のケーパビリティサービサーを通してプラグインを動かします |
| `testing.WireHarness` | gRPC 経由で、プロセスとしてのプラグインを動かします |
| `testing.RecordingHost` | あなたのプラグインが Astra に伝えたこと: `fired_triggers()`、`logs()`、`variables()`、`ui_pushes()`、`chat_messages()`、加えて `fail_next` / `fail_always` |
| pytest フィクスチャ | pytest を使うなら `astra_harness` と `astra_wire` |

`h.call_tool("name", **args)` はツール名を**位置引数**として取ります —
シグネチャ内の `/` には意味があります。なぜなら、自身のパラメータが
`name` という名前のツールは、そうでなければ呼び出し不可能になって
しまうからです。

このハーネスは実際のサービサーを呼び出すため、メソッドを直接呼び出す
だけではカバーできないことをカバーします: そのツールがデーモンが使う名前
で登録されていること、そのスキーマがパースできること、引数が
`json.dumps` → `json.loads` を生き延びること、戻り値がシリアライズ
できること、そして送出されたエラーがデーモンが処理するコードになること、
です。

## この SDK がまだできないこと

- **`DaemonClient` は機能しません。** デーモンはすべてのプラグインの
  セッショントークンを `PluginHostService` にスコープしているため、
  デーモン側のすべてのサービスが — `client = true` のプラグインを
  含めて — `permission_denied` を返します。`host.send_chat_message`
  を使ってください。
- **独自の `stdout` は持てません。** SDK は stdout を行バッファリング
  に再設定します。なぜならデーモンのスーパーバイザーがそれを読んで
  プラグインが生きていることを確認しているからです; ブロックバッファ
  リングは、開始タイムアウトでスーパーバイザーにプロセスを回収させて
  しまいました。`print` ではなくロギングブリッジ
  (`install_logging_bridge`)を使ってください。
- **他の 2 つより起動が遅い** — インタプリタに加えて `grpcio` の
  インポートがあります。デーモンの予算は最初の出力行まで 20 秒と寛容
  ですが、モジュールスコープで大きな ML スタックをインポートする
  プラグインはこれを逃す可能性があります。必要なフックで遅延インポート
  してください。
- **`ai_get_models` は非推奨です**(0.5.0、dict 形式は 0.7.0 から削除
  可能; フック自体は 0.8 で廃止)、誰もこれを呼び出しません。
- **`tts_synthesize_stream` は結びつけられていますが unrouted です**
  — デーモン側の呼び出し箇所はありません。
- **Python SDK は 0.5.0 で公開されています**。そのため新規の雛形は
  PyPI から解決されます(`https://pypi.org/pypi/astra-plugin-sdk/json`
  に対して検証済み)。0.5.0 以降を使ってください: これは、`Register`
  以外のすべてのホスト RPC でデーモンが要求する `x-session-token` を
  付加する最初のリリースであり、それより古いものはすべてのログ行と
  すべてのホスト呼び出しに `unauthenticated` を返します。

## 関連ページ

[Python のフック表](../hooks/python.md) ·
[パリティ](../reference/parity.md) · [エラー](../reference/errors.md) ·
[バージョニング](../versioning.md)
