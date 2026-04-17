# Python SDK

Python SDK 采用**声明式、基于装饰器**的 API。继承 `Plugin`，用 `@tool`、`@action` 或 `@trigger` 装饰方法，SDK 会根据你的类型提示自动构建能力元数据。

Package：`astra-plugin-sdk`，位于 `AstraPlugins/astra-plugin-sdk-python`。
权威源：`astra_plugin_sdk/plugin.py` 和 `astra_plugin_sdk/decorators.py`。

## 安装

需要 Python 3.10+。添加到你的 `pyproject.toml`：

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

加载包时，守护进程会使用 [`uv`](https://docs.astral.sh/uv/) 将插件的依赖安装到隔离的虚拟环境中。你无需手工管理 venv。

## 最小插件示例

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` 负责解析 CLI 参数（`--daemon-addr`、`--plugin-id`、`--auth-token`），在随机本地端口上启动 gRPC 服务器，向守护进程注册，分发传入的调用，并处理关闭信号。

## 装饰器

### `@tool(description)`

将方法注册为一个 AI 工具。类型提示会被自动转换为 JSON Schema（`decorators.py:28-92`）。

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

受支持的类型提示：

| 提示 | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | 生成 `T` 的 schema，字段标记为非必填 |

无默认值的参数被标记为 `required`。返回值会自动包装为 `{"success": True, "result": ...}`。

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

注册一个命令图操作类型。当命令执行该操作时，方法会被调用。

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

注册一个触发器类型。被装饰的方法仅承载元数据 —— 请在你自己的后台任务中通过 `self.fire_trigger` 触发该触发器。

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

## `Field` 构建器

所有构建器都是 `Field` 的静态方法（`decorators.py:189-319`）：

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` 接受元组、字典或普通字符串：

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

可见性条件：

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## 生命周期钩子

可以在子类上重写以下任意方法：

| 钩子 | 用途 |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | 对 client 插件在注册后调用 —— 保持对 `client` 的引用以访问守护进程 API。 |
| `async def on_config_changed(self, config: dict)` | 配置更新（由 UI 或 `ConfigService.SetConfig` 引起）。 |
| `async def on_language_changed(self, language: str)` | 守护进程 UI 语言变更 —— 调用 `self.i18n.set_language(language)`。 |
| `async def on_active_triggers(self, active_types: list[str])` | 更新 `self.active_triggers` —— 用它来跳过无监听方的触发器。 |
| `async def on_shutdown(self)` | 守护进程请求关闭 —— 在此释放资源。 |
| `async def health_check(self) -> (bool, str)` | 返回 `(healthy, status_message)`。 |

## 事件

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

## Client 插件

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

`DaemonClient` 暴露 `CoreService`、`ChatService`、`VoiceService`、`CommandService`、`ConfigService`、`MediaService` 和 `MonitorService`。全部方法详见 `daemon_client.py`。

## 日志

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

日志消息会进入守护进程的日志缓冲区，并显示在插件 UI 中。

## 触发触发器

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` 将事件发送至守护进程，由守护进程与已注册的命令进行匹配。即使没有监听方也可安全调用，但建议先检查 `self.active_triggers` 以避免无用的 RPC 调用。

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

语言文件位于 `locales/en.json`、`locales/ru.json` 等。未知键会回退到英文文件，再回退到键名本身。

## UI contributions

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## 完整示例 —— text-utils

请参阅 `AstraPlugins/examples/text-utils`。要点：

- Tools：`word_count`、`case_convert`、`regex_match`。
- Action：`transform_text`，使用 `Field.dropdown`。
- Trigger：`on_time`，带有后台 asyncio 循环。
- 配置：通过 `plugin.toml` 中的 `[config].schema` 配置 `max_text_length`。
- `on_config_changed` 更新运行时限制。

清单：

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

## 下一步

- [能力](capabilities.md) —— 每种能力的完整行为。
- [清单](manifest.md) —— 每个 `plugin.toml` 字段。
- [发布](publishing.md) —— 构建、签名、分发。
