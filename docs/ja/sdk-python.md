# Python SDK

Python SDK は**宣言的でデコレータベース**の API を採用しています。`Plugin` を継承したクラスで、メソッドに `@tool`、`@action`、`@trigger` を付けるだけで、SDK が型ヒントから機能のメタデータを自動生成します。

パッケージ: `AstraPlugins/astra-plugin-sdk-python` にある `astra-plugin-sdk`。
正式な仕様: `astra_plugin_sdk/plugin.py` および `astra_plugin_sdk/decorators.py`。

## インストール

Python 3.10 以上が必要です。`pyproject.toml` に追加してください。

```toml
[project]
name = "my_plugin"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "astra-plugin-sdk",
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
]
```

デーモンはバンドルをロードする際に [`uv`](https://docs.astral.sh/uv/) を使ってプラグインの依存関係を隔離された仮想環境にインストールします。venv を手動で管理する必要はありません。

## 最小構成のプラグイン

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` は、CLI 引数（`--daemon-addr`、`--plugin-id`、`--auth-token`）の解析、ローカルのランダムなポートでの gRPC サーバー起動、デーモンへの登録、受信コールのディスパッチ、およびシャットダウンシグナルの処理を行います。

## デコレータ

### `@tool(description)`

メソッドを AI ツールとして登録します。型ヒントは自動的に JSON Schema に変換されます（`decorators.py:28-92`）。

```python
from typing import Literal

@tool("Count words in text")
async def word_count(self, text: str) -> dict:
    return {"words": len(text.split())}

@tool("Convert case")
async def convert_case(
    self,
    text: str,
    mode: Literal["upper", "lower", "title"] = "upper",
) -> dict:
    return {"result": getattr(text, mode)()}
```

サポートされる型ヒント:

| ヒント | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | `T` のスキーマで、フィールドは必須にマークされません |

デフォルト値のないパラメータは `required` と扱われます。戻り値は自動的に `{"success": True, "result": ...}` でラップされます。

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Command Graph のアクション型を登録します。コマンドがこのアクションを実行するときにメソッドが呼び出されます。

```python
from astra_plugin_sdk import action, Field

@action(
    "Transform text",
    icon_svg='<svg>…</svg>',
    fields=[
        Field.text("input", "Input text"),
        Field.dropdown("op", "Operation", options=[
            ("upper", "UPPER"), ("lower", "lower"),
        ]),
    ],
    ai_available=True,
    ai_description="Transform a block of text via upper/lower/title case",
    ai_primary_field="input",
)
async def transform_text(self, input: str, op: str):
    return {"success": True, "result": getattr(input, op)()}
```

### `@trigger(label, *, icon_svg="", fields=[])`

トリガー型を登録します。デコレートされたメソッドはメタデータのみを保持します。トリガーは `self.fire_trigger` を介して、バックグラウンド処理の中から発火させてください。

```python
from astra_plugin_sdk import trigger, Field

@trigger("Scheduled time", fields=[
    Field.text("time", "Time", default="09:00", placeholder="HH:MM"),
])
def on_time(self):
    pass

async def tick(self):
    if "on_time" in self.active_triggers:
        await self.fire_trigger("on_time", {"time": "09:00"})
```

## `Field` ビルダー

すべてのビルダーは `Field` の静的メソッドとして提供されています（`decorators.py:189-319`）。

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` はタプル、辞書、あるいは単なる文字列を受け付けます。

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

表示条件:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## ライフサイクルフック

サブクラスでこれらのいずれかをオーバーライドできます。

| フック | 目的 |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | クライアントプラグインで登録後に呼び出されます。デーモン API にアクセスできるよう `client` を保持してください。 |
| `async def on_config_changed(self, config: dict)` | 設定が更新されました（UI または `ConfigService.SetConfig` から）。 |
| `async def on_language_changed(self, language: str)` | デーモン UI の言語が変更されました。`self.i18n.set_language(language)` を呼び出してください。 |
| `async def on_active_triggers(self, active_types: list[str])` | `self.active_triggers` を更新します。リスナーのいないトリガーの発火を避けるために使用します。 |
| `async def on_shutdown(self)` | デーモンがシャットダウンを要求しました。ここでリソースを解放してください。 |
| `async def health_check(self) -> (bool, str)` | `(healthy, status_message)` を返します。 |

## イベント

```python
def subscribed_events(self) -> list[str]:
    return ["chat_message_sync", "command_completed"]

async def on_chat_sync(self, event):
    # event has id, conversation_id, role, content, source_id,
    # is_streaming, is_complete
    ...

async def on_command_triggered(self, event): ...
async def on_command_completed(self, event): ...
async def on_state_changed(self, event): ...

async def on_event(self, event_type: str, payload: dict):
    # Raw fallback for event types not covered by typed handlers
    ...
```

## クライアントプラグイン

```python
class MyClientPlugin(Plugin):
    def is_client(self) -> bool:
        return True

    async def on_daemon_client_ready(self, client):
        self.daemon = client
        state = await self.daemon.get_state()
        async for chunk in self.daemon.send_message(conversation_id, "Hello!"):
            print(chunk.text)
```

`DaemonClient` は `CoreService`、`ChatService`、`VoiceService`、`CommandService`、`ConfigService`、`MediaService`、`MonitorService` を公開します。すべてのメソッドは `daemon_client.py` を参照してください。

## ログ出力

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

ログメッセージはデーモンのログバッファに記録され、Plugins UI に表示されます。

## トリガーの発火

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` はイベントをデーモンに送り、デーモンは登録済みのコマンドと照合します。リスナーがなくても安全に呼び出せますが、無駄な RPC を避けるため事前に `self.active_triggers` をチェックしてください。

## i18n

```python
from astra_plugin_sdk import I18n

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.i18n = I18n("locales")  # loads locales/*.json

    async def on_language_changed(self, language: str):
        self.i18n.set_language(language)

    @tool("…")
    async def greet(self, name: str):
        return {"msg": self.i18n.tf("greeting", name)}
```

ロケールファイルは `locales/en.json`、`locales/ru.json` などに配置します。未知のキーは英語ファイル、それでも見つからなければキー自身にフォールバックします。

## UI コントリビューション

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## 実例 — text-utils

`AstraPlugins/examples/text-utils` を参照してください。要点は次のとおりです。

- ツール: `word_count`、`case_convert`、`regex_match`。
- アクション: `Field.dropdown` を用いた `transform_text`。
- トリガー: バックグラウンドの asyncio ループで動く `on_time`。
- 設定: `plugin.toml` の `[config].schema` で定義される `max_text_length`。
- `on_config_changed` が実行時の上限値を更新します。

マニフェスト:

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
```

## 次に進むには

- [機能](capabilities.md) — 各機能の完全な動作仕様。
- [マニフェスト](manifest.md) — `plugin.toml` の全フィールド。
- [公開](publishing.md) — ビルド、署名、配布。
