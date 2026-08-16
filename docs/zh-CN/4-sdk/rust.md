> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/4-sdk/rust.md)。如与英文版有出入，以英文版为准。

# Rust SDK

`astra-plugin-sdk` 0.6.0。只有一个依赖，宏展开出来的一切都经由它而来。

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 是第一个 `HostClient` 会附带 `x-session-token` 的版本。对 0.5
及更早版本，守护进程会对每一次 host 调用都返回 `unauthenticated`，所以
不要放宽这个下限。

## 插件的形态

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` 会根据它找到的钩子来实现 `PluginCapability`，并从
中推导出已声明的能力集合 —— 所以一个插件不可能声称拥有一个自己代码
根本没有提供的能力。`astra-plugin check` 会把这个结果和 `plugin.toml`
做对比。

## 宏这一层

| | 用途是什么 |
|---|---|
| `#[astra::plugin]` | 加在 `impl` 块上。把下面的成员转换成对应的 trait |
| `#[tool]` | 一个模型可以调用的函数。文档注释就是它的描述 |
| `#[action(label = "…")]` | 命令编辑器中的一个步骤 |
| `#[hook]` | 其他任何按名字识别的 `PluginCapability` 方法 |
| `#[ui_call]` | 你的 UI 贡献可以回调进来的一个方法 |
| `#[astra::args]` | 加在一个工具的参数结构体上 |
| `#[astra::config]` | 加在你的设置结构体上 —— 相当于 `args` 加上 `#[serde(default)]` |
| `astra::main!(Plugin::default())` | 运行它的那个 `main` |

**为什么是 `#[astra::args]` 而不是 `#[derive(Deserialize, JsonSchema)]`：**
serde 的 derive 会展开成 `extern crate serde as _serde`，这是在 extern
prelude 中解析的，无法通过重新导出（re-export）到达。所以直接用普通的
derive 会要求你自己的 `Cargo.toml` 里也有 `serde`——而这恰恰是"只有一个
依赖"这个承诺所要守护的东西。`#[astra::args]` 就是这两个 derive，外加
指向 SDK 自己那份拷贝的 `crate = "…"`。你自己额外添加 `serde` 依然是
可以的；这样一来，`use serde::Deserialize;` 会遮蔽掉 prelude 里的同名
项。

你也可以手动实现 `PluginCapability`。这个 trait 是公开的，每个方法都有
默认实现，而这些宏产出的正是你自己会写出来的东西。

## `PluginContext`

每一个处理函数都会拿到一个 `&PluginContext`。它永远不会是 `None`，把它
克隆进一个后台任务的代价很低，这也意味着你不需要把任何东西藏在锁后面
塞进你的结构体里。

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` —— 十个 host RPC。始终存在 |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` —— **只对 `client` 插件为 `Some`** |
| `ctx.language()` | Astra UI 的语言，由 `OnLanguageChanged` 更新 |
| `ctx.active_triggers()` | 你的哪些触发器类型正被某条命令监听 |
| `ctx.plugin_id()` | 你的 id |

在参数无法到达的地方 —— 一个 `Drop` 实现、来自 C 库的回调、启动时
spawn 出的一个 `std::thread` —— `astra_plugin_sdk::ctx()` 会返回正在
运行的插件的上下文，`try_ctx()` 是它的可失败版本。

### `Host` —— 十个对外调用

| 方法 | 权限 |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | 无 |
| `get_config` | 无 |
| `get_daemon_info` | 无 |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` 接受**三个**参数 —— 名字、值和作用域。事件订阅不在
`Host` 上：声明 `subscribed_events()`，运行时会自己持有这个流（见下）。

`Host` 是一个 trait，所以测试中可以替换成 `RecordingHost`，从而断言你的
插件到底告诉了 Astra 什么。

### `Daemon` —— SDK 中存在，但会被守护进程拒绝

> **`ctx.daemon()` 今天对任何插件都不起作用。** 守护进程那一侧的部分
> 还没有到位。每一个插件 —— 无论是否 `client = true` —— 都被注册为
> `ClientType::PluginClient`，而守护进程的认证拦截器会拒绝这个身份
> 访问任何不以 `/astra.PluginHostService/` 开头的路径，返回
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")`。`DaemonClient` 连接时用的正是这个令牌
> （`astra-plugin-sdk/src/host_client.rs` 把 `client_session_token`
> 交给了 `DaemonClient::connect`），所以下面这些调用 ——
> `submit_user_message`、`subscribe_chat_events`、`speak`、
> `get_settings` —— 在运行时全都会返回 `permission_denied`。守护进程
> 的 `consistency.rs` 中有一个金丝雀测试(canary)在守护这个作用域限制，
> 所以这是刻意如此，而不是一个回归 bug：反向认证的那一半还没有被
> 构建出来，而不是坏掉了。
>
> **`Host::send_chat_message` 是唯一一条能真正驱动 AI 对话轮次的可用
> 路径**，对任何已被授予 `send_chat_message` 权限的插件都有效。

留给守护进程侧落地后使用的 API 界面：只有当插件声明了 `client = true`
且 `is_client()` 返回 true 时，`ctx.daemon()` 才是 `Some`。它能到达
七个服务 —— core、chat、voice、command、config、media、monitor ——
方法包括 `submit_user_message`、`subscribe_chat_events`、
`stop_generation`、`list_conversations`、`speak`、`start_listening`、
`execute_command`、`get_settings`、`get_system_stats`。是
`submit_user_message`，不是 `send_message`。

## 错误

处理函数返回 `Result<_, ToolError>`（`ActionError` 是同一类型的别名）。
单次调用的失败是 AI 循环会读取并据此行动的数据，所以它是随响应本身
传递的，而不是作为一个 gRPC 状态码。

| 变体 | 何时使用 |
|---|---|
| `BadArguments(String)` | 模型可以通过改变调用方式来修复这个问题 |
| `NotFound(String)` | 未知的 id，404 |
| `NotConfigured { field, message }` | 缺少某项设置。`field` 是深链接（deep-link）的目标 |
| `Unauthorized(String)` | 凭证被拒绝，或者某项权限未被授予 |
| `RateLimited { retry_after, message }` | 上游配额限制。`None` 表示未知，不是"立即" |
| `Unavailable(String)` | 某个依赖项挂了；稍后原样重试 |
| `Timeout(String)` | 超时了 |
| `Internal(String)` | 一个 bug。模型对此无能为力 |

`?` 对 `serde_json::Error`、`std::io::Error`、`tonic::Status` 和
`anyhow::Error` 都能用。`with_doc_url(…)` 可以把这些错误中的任意一个
包装上一个记录*那个*失败的页面链接，UI 会把它渲染成一个链接。

完整的分类，包括传输层字符串以及 Python/TypeScript 中对应的写法：见
[`reference/errors.md`](../reference/errors.md)。

## 事件

声明你想要的内容；运行时负责订阅、重连和分发。

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

今天已有类型的事件：`StateChangedEvent`、`CommandTriggeredEvent`、
`CommandCompletedEvent`。聊天事件是另一条独立的流 ——
`on_conversation_event`，由守护进程的事件洪流(firehose)供给，面向
`client` 类型的插件。

`on_chat_sync` / `ChatSyncEvent` 不存在。这个事件已被淘汰，没有任何
SDK 拥有这个方法；如果你正在移植使用过它的代码，请改用
`is_client()` 加上 `on_conversation_event`。

## 测试

有两个层级，都随 SDK 一起提供，所以你的 `Cargo.toml` 依然只有一行。

| | 驱动什么 | 能看到什么 |
|---|---|---|
| `testing::Harness` | 各个钩子，在进程内，针对一个 `RecordingHost` | 工具、动作、触发器、配置、事件、UI 调用，以及你发出的每一次 host 调用 |
| `testing::WireHarness` | 一个真实进程，以守护进程启动它的方式启动 | 注册过程、会话令牌、流式音频，只有在传输层才能看到的东西 |

`RecordingHost` 提供 `fired_triggers()`、`logs()`、`variables()`、
`ui_pushes()`、`chat_messages()`，外加 `deny(rpc)`、`fail(rpc, err)`
和 `fail_next(rpc, err)`，用来模拟你的用户将会遇到的各种失败。

在这两者之上还有更高的一个层级：`astra-plugin test` 会针对一个模拟
守护进程启动你构建出的二进制文件，并驱动你所声明能力隐含的每一个钩子。
它不关心插件是用哪种语言写的。

## 这个 SDK 目前还做不到的事

- **`ctx.daemon()` / `DaemonClient` 不能正常工作。** 守护进程把每一个
  插件的会话令牌都限定在了 `PluginHostService` 范围内，所以全部七个
  服务都会返回 `permission_denied` —— 即便是 `client = true` 的插件
  也一样。请使用 `Host::send_chat_message`。参见上面的
  [`Daemon`](#daemon--sdk-中存在但会被守护进程拒绝)。
- **`TtsSynthesizeStream` 已经被绑定，但是 unrouted 的。** SDK 提供了
  它；但守护进程侧不存在任何调用点。如果你愿意可以实现它 —— 但在
  [对照表](../reference/parity.md)显示 `live` 之前，不会有任何东西去
  调用它。
- **`AiGetModels` 已被弃用**（0.6 弃用，0.8 移除），没有任何人调用它：
  模型选择器把 `supports_model_discovery = false` 写死了。没有替代
  方案；`AiComplete` 的请求里会直接携带已选定的模型。
- **0.5 的 trait 接口以 `astra_plugin_sdk::compat` 的形式继续存在**，
  0.6 中弃用，0.8 中移除。参见
  [迁移到 0.6](../migration-0.6.md)。
- **`PluginCapability::source_id()`** 已被弃用：请把 id 传给
  `Host::send_chat_message`，因为守护进程已经不再按 source id 过滤了。
- **能力服务端(capability server)的入站认证不需要任何设置。** 守护
  进程会在每次调用时出示 `x-plugin-token`，并设置
  `ASTRA_PLUGIN_CAPABILITY_AUTH=require`，所以 SDK 会拒绝没有携带它的
  调用。只有一个老到不会发送这个头的守护进程，才会让你停留在 `warn`
  阶段；详见
  [架构](../1-orientation/architecture.md)。

## 另请参阅

[Rust 钩子表](../hooks/rust.md) · [对照表](../reference/parity.md) ·
[错误](../reference/errors.md) ·
[版本管理与弃用策略](../versioning.md)
