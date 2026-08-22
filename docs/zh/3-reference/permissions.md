> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/3-reference/permissions.md)。如与英文版有出入，以英文版为准。

# 权限

每个 `[permissions]` id 各自授予什么、它要用户付出什么代价，以及如何写出
一句值得被读的 `reason`。

这是面向插件作者的一页。规范性的规则 —— 授权、上限、`permissions_hash`、
精确的拒绝语义 —— 在 [`spec/permissions.md`](../spec/permissions.md)
中。哪个 id 限制哪个 RPC 的生成表，在
[`reference/manifest.md`](../reference/manifest.md) 和
[`reference/parity.md`](../reference/parity.md) 中，两者都源自
`spec/hooks.yaml`，并通过一致性规则 R6 与守护进程自身的表进行校验。

## 它的形状

`[capabilities]` 说明守护进程可以**调入**你插件的哪些内容。
`[permissions]` 说明你的插件可以**调出**到哪些 host RPC。两个不同的
问题，两个不同的段；一个能力(capability)从不隐含任何权限。

有三个特性，每一个最终都会让某人感到意外。

1. **默认拒绝。** 没有 `[permissions]` 段，就意味着除了引导用的那四个
   调用之外，没有任何 host RPC。
2. **声明是提出申请，而不是获得授权。** 你的清单文件是一份申请。被
   授予的权限集合由守护进程根据插件的来源来解析，对于已安装或已导入的
   插件，会保存在插件无法写入的地方 —— 清单文件本身位于你插件自己的
   目录中，而你的插件是可以编辑那个目录的。**侧载(sideload)会反转这一点**：
   对于开发者模式下的源码目录，清单文件本身*就是*授权，每次加载时都
   重新读取，没有上限。这正是让创作循环得以运作的原因，也是为什么侧载
   是一个开发工具而不是一条安装途径。
3. **未知的 id 会被保留，但不起作用。** 新的 id 会随着新版本的 Astra
   一起出现，所以一个更旧的守护进程会保留一个它不认识的键，而不是拒绝
   你的清单文件。它不会授予任何东西。`astra-plugin check` 会发出警告 ——
   在解析阶段，一个拼写错误和一个向前兼容的 id 是无法区分的，所以这是
   一个警告而不是错误，`--strict` 会把它变成一个失败的退出码：

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Astra 的安装同意页面也会在它自己的 `permission.unrecognised` 标签
   下展示同一个 id，所以在进入的路上它也不会被悄悄丢弃。

## 不需要任何权限的四个调用

| RPC | 为什么是免费的 |
|---|---|
| `Register` | 握手过程。此时还没有插件可以拥有权限 |
| `PluginLog` | 写入你自己的日志 |
| `GetPluginSelfConfig` | 读取你自己的设置 |
| `GetDaemonInfo` | `version`、`state`、`grpc_port`、`language` —— 这些全都已经在注册的响应里给过你了 |

`GetDaemonInfo` 是免费的，这是一个决定，不是疏漏：一个什么都保护不了的
勾选框，只会教会用户去随手勾选各种框。

## 八个 id

| Id | 限制哪个调用 | 有独立的勾选框 | 在本地导入时被拒绝 | 它能让你做什么 |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | 否 | 否 | 运行用户已保存的自动化流程 |
| `subscribe_events` | `SubscribeEvents` | 否 | 否 | 接收守护进程事件 —— **需要一个 `types` 白名单** |
| `set_variable` | `SetVariable` | 否 | 否 | 写入守护进程的变量上下文，限定在你自己的命名空间内 |
| `send_chat_message` | `SendChatMessage` | **是** | **是** | 像用户亲口说了一样，驱动一次 AI 对话轮次 |
| `push_to_ui` | `PushToUi` | **是** | 否 | 向你自己的面板推送一个事件 |
| `set_theme_contribution` | `SetThemeContribution` | **是** | **是** | 重新设置整个应用的样式 |
| `dom_access` | —（一个界面层） | **是** | **是** | 在 Astra 窗口内运行你的代码，能访问对话内容以及每一个其他插件的界面 |
| `client` | —（一个界面层） | **是** | **是** | 成为一个拥有自己会话的聊天前端 |

`dom_access` 和 `client` 不限制任何 RPC，这正是关键所在：它们是
**界面层(surface)**。`dom_access` 决定一个 UI 贡献是被渲染为 Astra
窗口中的一段脚本，还是一个沙箱化的 iframe；`client` 是插件能成为什么的
一道上限。它们是在界面层被分发的那个环节被拒绝的，而不是在某个调用关卡
上。

`dom_access` 还会额外触发第二个同意界面。如果你正打算使用它，请先阅读
[安全模型](../1-orientation/security.md)，并确认在自己面板里用
`push_to_ui` 真的不够用。

## 参数

有两个 id 接受参数，两者都是用来收窄你能获得的范围。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` 是一个白名单，由守护进程强制执行** ——
  而不是靠你的插件发送的过滤器。没有它，每个订阅者会收到每一个事件，
  包括携带用户转写内容的 `speech_recognized`。空列表意味着什么都不
  允许。
- **`set_variable.scopes`** 的取值是 `"plugin"`、`"session"` 或
  `"persistent"`。

## 编写 reason

`reason` 会显示在 Astra 自己给这项权限起的标签下方，视觉上处于从属
位置，带引号，纯文本，上限 140 个字符，并且总是带有前缀
*"The author says:"*。标签是 Astra 的，使用用户所用的语言；reason 是
你的。你无法自己制作标签，这是刻意的设计 —— 措辞的修正随 Astra 一起
发布，绝不能被某个上架条目改写。

一个好的 reason：

- **点名用户能认出来的功能**，而不是 API 名字 —— 是"Fires the
  on_dice_roll trigger you configure"，不是"calls FireTrigger"；
- 如果不是一直如此，**说明是什么时候** —— 比如"only while a recording
  is in progress"；
- **不要重复标签的内容。** Astra 已经渲染过了；
- **不要施加压力。** 不要制造紧迫感，不要威胁，不要给用户下指令。同意
  页面是最不适合搞例外的地方，包含双向文字覆盖(bidi override)或零宽
  连接符的文本，在原样展示的地方会被拒绝。

| 不要写 | 改写成 |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | —— 要么去掉这项权限，要么说清楚它是干什么用的 |

一项找不出站得住脚理由的权限，就是一项应该从清单文件中删掉的权限。没有
任何东西会自动检查这一点；阅读你上架条目的那个人，是唯一的最后防线，而
当你声明了一项你的能力(capability)根本用不到的权限时，`astra-plugin
check` 会告诉你。

## 权限缺失时会发生什么

调用会返回 `permission_denied`，消息中会点名这个权限**以及**被授予的
权限集合是从哪里来的。在测试中你可以精确地模拟出这种情况：

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

在你实际运行清单文件之前，`astra-plugin doctor` 就能回答关于它的同一个
问题：

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## 被授予的权限集合来自哪里

| 安装路径 | 被授予的内容 |
|---|---|
| 从商店安装，已验证 | 经用户同意后，清单文件所申请的内容 |
| 手动导入的 `.astraplugin` 文件 | 清单文件的内容，但**有上限**：`send_chat_message`、`set_theme_contribution`、`dom_access`、`client` 会被直接拒绝 |
| 侧载的源码目录，开发者模式开启 | 清单文件的内容，没有上限 |
| `Untrusted` / `TamperDetected` / `Revoked` | 什么都没有 |
| 在信任记录出现之前就已安装的 | 清单文件的内容，按导入文件的上限处理 |

完整表格及其推理依据：[`spec/permissions.md` §4](../spec/permissions.md)。

## 从用户的角度看同意机制

权限按风险分组。五种高风险权限各自有独立的勾选框，只要还有一个没被
勾选，"安装"按钮就保持禁用；`dom_access` 还会有第二个界面。这里刻意
**没有"输入以确认"**这种设计：那是用于不可逆的破坏性操作的模式，让用户
习惯于打字敲过去，只会摧毁勾选框本应承载的那个信号。

关于更新：如果权限不变或收窄，会静默地应用；如果权限**扩大**了，更新会
被暂存而不会安装，旧版本会继续运行，直到用户审阅了这个差异为止。拒绝
更新不会有任何代价。
