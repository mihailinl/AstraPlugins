> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/4-sdk/python.md)。如与英文版有出入，以英文版为准。

# Python SDK

PyPI 上的 `astra-plugin-sdk` 0.5.0。继承 `Plugin`，用装饰器标注方法，
运行它。

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Python 插件打包为 **`noarch`**：每个平台共用一个包。它的 `[entry]` 是
`command = "python"`、`args = ["-m", "src.plugin"]`、
`runtimes = ["python"]`。

## 插件的形态

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

## 装饰器

| | |
|---|---|
| `@tool("description")` | 一个模型可以调用的函数。参数会变成 schema |
| `@action("label")` | 命令编辑器中的一个步骤 |
| `@trigger(...)` | 一种触发器类型 |
| `@ui_call` | 插件自己的 UI iframe 可以调用的一个方法 |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | **类**装饰器。注册一个 UI 贡献，服务来自包内的 `ui/` 目录，或者插件自己提供的一个 URL |
| `Field(...)` | 细化某一个参数的 schema —— 描述、范围、枚举值 |

其他一切都是对 `Plugin` 的重写：`tts_synthesize`、`tts_list_voices`、
`tts_config_fields`、`stt_transcribe`、`stt_transcribe_stream`、
`stt_get_languages`、`stt_load` / `stt_unload` / `stt_load_state`、
`ai_complete`、`get_action_types`、`execute_action`、
`get_trigger_types`、`get_ui_contributions`、`handle_ui_call`、
`on_config_changed`、`on_language_changed`、`on_active_triggers`、
`on_shutdown`、`health_check`。

## 调用 Astra

`Plugin` 上的便捷方法 —— `self.log_info`、`self.log_warn`、
`self.log_error`、`self.fire_trigger(type, payload_dict)`、
`self.push_to_ui(event, payload_dict)` —— 以及其余所有内容都在
`self.host` 上：

| `self.host.…` | 权限 |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | 无 |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` 今天对任何插件都不起作用。** 守护进程把每一个插件
> 都注册为 `ClientType::PluginClient`，它的认证拦截器会拒绝这个身份
> 访问 `/astra.PluginHostService/` 之外的任何路径，返回
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")` —— `client = true` 对此没有任何改变。所以
> `submit_user_message`、`subscribe_chat_events`、`speak` 和
> `get_settings` 全都会在运行时失败。守护进程那一侧的部分还没有被
> 构建出来，而不是坏掉了。
>
> **`host.send_chat_message` 是唯一一条能真正驱动 AI 对话轮次的可用
> 路径。**

留给守护进程侧落地后使用：在 `DaemonClient` 上是
**`submit_user_message`**，不是 `send_message`。完整的客户端会被交给
`on_daemon_client_ready(client)`，但只针对声明了 `client = true` 且
`is_client()` 返回 `True` 的插件。

## 错误

抛出(raise)它们；SDK 会把它们映射为和另外两个 SDK 相同的传输层错误码。

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` ·
`RateLimited` · `Unavailable` · `Timeout` · `InternalError`，全都是
`PluginError` 的子类，`ErrorCode` 是对应的枚举。参见
[`reference/errors.md`](../reference/errors.md)。

## 能力相关的类型是数据类(dataclass)

`ToolDef`、`VoiceInfo`、`AiModelInfo`、`FieldDef`、`DropdownOption`、
`FieldCondition`、`ActionTypeDef`、`TriggerTypeDef`、
`UiContribution`。

在期望一个数据类的地方返回一个原始的 `dict` 依然能用，会发出一个
`DeprecationWarning`：0.5.0 中弃用，0.7.0 起可移除。在 CI 中用
`python -W error::DeprecationWarning` 来卡住这类情况。

## 测试

| | |
|---|---|
| `testing.Harness` | 在本进程内，通过真实的能力服务端(servicer)驱动插件 |
| `testing.WireHarness` | 把插件作为一个独立进程，通过 gRPC 驱动 |
| `testing.RecordingHost` | 你的插件告诉 Astra 的内容：`fired_triggers()`、`logs()`、`variables()`、`ui_pushes()`、`chat_messages()`，外加 `fail_next` / `fail_always` |
| pytest 夹具(fixture) | 如果你用 pytest，有 `astra_harness` 和 `astra_wire` |

`h.call_tool("name", **args)` 把工具名当作**位置参数**接收 —— 签名中的
那个 `/` 是有实际作用的，因为如果一个工具自己的参数恰好也叫 `name`，
否则它就会变得无法调用。

这个测试工具调用的是真正的服务端(servicer),所以它能覆盖到直接调用方法
本身覆盖不到的东西：这个工具是否以守护进程将会使用的名字注册、它的
schema 能否解析、参数能否在 `json.dumps` → `json.loads` 之间存活、
返回值能否被序列化，以及一个被抛出的错误最终会变成守护进程据以行动的
哪个错误码。

## 这个 SDK 目前还做不到的事

- **`DaemonClient` 不能正常工作。** 守护进程把每个插件的会话令牌都
  限定在了 `PluginHostService` 范围内，所以守护进程侧的每一个服务都
  会返回 `permission_denied` —— 包括 `client = true` 的插件在内。
  请使用 `host.send_chat_message`。
- **没有属于你自己的 `stdout`。** SDK 会把 stdout 重新配置为行缓冲
  模式，因为守护进程的监督进程要读取它来确认插件还活着；块缓冲会导致
  监督进程在启动超时时把这个进程回收掉。请使用日志桥接
  (`install_logging_bridge`),而不是 `print`。
- **启动比另外两个 SDK 慢**——需要启动解释器再加上导入 `grpcio`。
  守护进程给到首行输出的预算是 20 秒，相当宽松，但如果一个插件在模块
  作用域就导入了一个庞大的 ML 技术栈，还是有可能超时。请把导入延迟到
  真正需要它的那个钩子内部。
- **`ai_get_models` 已被弃用**（0.5.0 起弃用，dict 形式 0.7.0 起可
  移除；钩子本身在 0.8 中被淘汰），没有任何东西调用它。
- **`tts_synthesize_stream` 已经绑定，但是 unrouted 的** —— 没有守护
  进程侧的调用点。
- **Python SDK 发布在 0.5.0**，所以一个全新的脚手架会从 PyPI 解析
  （已对照 `https://pypi.org/pypi/astra-plugin-sdk/json` 验证）。请
  使用 0.5.0 或更新版本：这是第一个会在除 `Register` 之外的每个 host
  RPC 上附带守护进程所要求的 `x-session-token` 的版本，比它更旧的版本
  会对每一行日志和每一次 host 调用都返回 `unauthenticated`。

## 另请参阅

[Python 钩子表](../hooks/python.md) ·
[对照表](../reference/parity.md) · [错误](../reference/errors.md) ·
[版本管理](../versioning.md)
