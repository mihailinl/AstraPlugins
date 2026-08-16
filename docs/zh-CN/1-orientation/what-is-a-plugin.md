> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/1-orientation/what-is-a-plugin.md)。如与英文版有出入，以英文版为准。

# 什么是插件

插件是一个由 Astra 守护进程启动的**独立程序**，通过 localhost 上的 gRPC 与
守护进程通信。它不是一个库，不会被加载进 Astra 的地址空间，也不是 Astra 解释
执行的脚本。Astra 像 shell 那样把它 spawn 出来，通过命令行传参，并通过先请求
其关闭、若无响应则 kill 掉整个进程组来停止它。

这一个事实决定了剩下的大部分内容：

- **你可以用任何能说 gRPC 的语言来编写它。** 这里提供了三个 SDK ——
  Rust、Python、TypeScript —— 它们处于[完全一致](../reference/parity.md)
  的状态：全部 35 个钩子，三者都有。
- **它拥有和你一样的权限，不会更少。** 参见
  [安全模型](security.md)。
- **它自己的 bug 熬不过去，Astra 却完全不受影响。** 处理函数中的 panic
  会被捕获并作为错误返回，而不是杀死进程
  （`astra-plugin-sdk/src/panics.rs`）；整个进程的崩溃会在 15 秒内被
  守护进程的健康检查发现。

## 两个方向

插件所做的一切都属于以下两者之一，它们是两套独立的系统，在 `plugin.toml`
中也有各自独立的名字。

| | 方向 | 清单中的段 | 回答什么问题 |
|---|---|---|---|
| **Capabilities（能力）** | 守护进程 → 插件 | `[capabilities]` | 插件实现了什么，Astra 可以*调入*哪些内容 |
| **Permissions（权限）** | 插件 → 守护进程 | `[permissions]` | 插件可以*调出*到哪些 host RPC |

它们曾经共用同一个词，这正是 `dom_access` —— 系统中最危险的东西 —— 曾经
沦为插件只需声明就能自我授予的东西的由来。现在它们是两个不同的词了。声明
`[capabilities] event_handlers = true` 并不能让你订阅事件；能做到这一点的
是 `[permissions] subscribe_events`，而且只有在用户同意之后才行。

`[permissions]` 是**默认拒绝**的：完全没有这个段时，插件只能调用
`Register`、`PluginLog`、`GetPluginSelfConfig` 和 `GetDaemonInfo`，其他
一律不行（[`spec/permissions.md` §2](../spec/permissions.md)）。

## 十种能力(capability)

每个键都是布尔值，默认 `false`，一旦声明就有义务提供某些钩子。右边一列
是*必须*提供的钩子；可选的钩子在[对照表](../reference/parity.md)中。

| `[capabilities]` 键 | 你的插件会成为 | 必须提供的钩子 |
|---|---|---|
| `tools` | 一组模型可以调用的函数 | `ListTools`、`CallTool` |
| `tts` | Voice 设置中的文本转语音提供者 | `TtsSynthesize`、`TtsListVoices` |
| `stt` | 语音转文本提供者 | `SttProcess`、`SttGetLanguages` |
| `ai_provider` | 一个模型后端 | `AiComplete` |
| `actions` | 命令编辑器中的步骤 | `ExecuteAction`、`GetPluginActionTypes` |
| `triggers` | 命令可以监听的触发器类型 | `GetPluginTriggerTypes`、`FireTrigger` |
| `ui_contributions` | Astra 窗口中的面板、页面和覆盖层 | `GetUiContributions` |
| `event_handlers` | 守护进程事件的订阅者 | `SubscribeEvents` |
| `client` | 一个属于自己的聊天前端 | `SendChatMessage` |
| `dom_access` | 在 Astra 窗口内运行的代码 | 无 —— 这是渲染层面的决定，不是一个钩子 |

来源：[`reference/manifest.md`](../reference/manifest.md)，从守护进程
用来解析你的清单文件的那个 crate 生成而来。`ui_panels` 从来都不是一种
能力(capability)——曾有三个已发布的示例声明过它，serde 悄悄丢弃了这个
未知的键，唯一的症状就是 `astra-plugin check` 报告没有任何能力。
`[capabilities]` 正是为了这个原因才拒绝未知的键。

## 清单文件长什么样

最小可用的例子 —— 一个只有工具、没有权限、也没有其他任何东西的插件：

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat."
author = "You"
license = "MIT"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
```

一个会触发触发器的插件必须申请相应权限，而 `reason` 就是 Astra 请求用户
同意时用户会看到的文字：

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice, and fire a trigger when one comes up."
author = "You"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

每个段和每个键的完整说明：[`reference/manifest.md`](../reference/manifest.md)。

## 插件做不到的事

- **一旦安装完成，它就不能给自己授予权限。** `[permissions]` 段只是一份
  申请。对于从注册表安装或以文件形式导入的插件，最终被授予的权限集合由
  守护进程根据插件的来源来解析，并保存在插件无法写入的地方 —— 清单文件
  本身位于插件自己的目录中，而插件是可以编辑那个目录的。**侧载
  (sideload)的插件是例外**：在那个层级，清单文件本身就是同意记录，
  没有上限，所以它可以通过编辑自己的文件来扩大自己的权限。参见
  [安全模型](security.md#插件的来源决定它的权限上限)。
- **它无法直接访问 Astra 的 `ChatService`。** 插件在注册时获得的会话
  令牌被限定在 `PluginHostService` 范围内。要驱动一次 AI 对话轮次，必须
  经过 `SendChatMessage`，这受 `send_chat_message` 权限的限制，属于高
  风险权限之一。
- **它不能依赖一个 unrouted 的钩子。** 一个钩子可能同时存在于 proto 和
  全部三个 SDK 中，却在守护进程侧没有任何调用点：今天的
  `TtsSynthesizeStream` 就是这样。实现它本身是没有代价的；但依赖它会被
  调用，在[对照表](../reference/parity.md)标明 `live` 之前是不受支持的。
- **它不能被安装到一个它没有对应包(bundle)的平台上。** 参见
  [平台](platforms.md)。

## 接下来

如果你想了解进程是如何启动和认证的，请看
[架构](architecture.md)；否则可以直接前往
[快速上手](../2-tutorial/getting-started.md)。
