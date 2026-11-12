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
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client, read_ai_settings, speak, read_user_identity, receive_attachments, request_settings_change
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

## 十三个 id

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
| `read_ai_settings` | `GetAiSettings` | 否 | 否 | 读取用户聊天所用的提供方、模型和端点——绝不包含密钥 |
| `speak` | `Speak`, `StopSpeaking` | **是** | 否 | 用 Astra 的声音说出你自己的话，并能让它停下 |
| `read_user_identity` | `GetUserIdentity` | 否 | 否 | 读取这次安装和已登录账号的假名 id，专为你的插件生成 |
| `receive_attachments` | —（一种投递） | **是** | 否 | 在请求它的工具里收到本人附上的图片 |
| `request_settings_change` | `RequestSettingsChange` | 否 | 否 | 在一张由本人作答的卡片上，请本人更改助手可以更改的某项设置 |

`dom_access` 和 `client` 不限制任何 RPC，这正是关键所在：它们是
**界面层(surface)**。`dom_access` 决定一个 UI 贡献是被渲染为 Astra
窗口中的一段脚本，还是一个沙箱化的 iframe；`client` 是插件能成为什么的
一道上限。它们是在界面层被分发的那个环节被拒绝的，而不是在某个调用关卡
上。`receive_attachments` 同样不限制任何 RPC，只是方向相反：没有什么需要你
去调用，它决定的是 Astra 会向你的某个工具*发送*什么——见[下文](#接收本人附上的图片)。

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

## 读取用户的 AI 设置

自己调用用户模型的插件——自带的助手、摘要工具——需要知道用户选了哪个提供方、哪个模型和哪个端点。**向 Astra 询问；绝不要读取 Astra 的文件。** 声明 `read_ai_settings`，然后调用 `GetAiSettings`（Rust 和 Python 中是 `get_ai_settings()`，TypeScript 中是 `getAiSettings()`）：

| 字段 | 含义 |
|---|---|
| `provider` | 聊天的提供方 id。用户保存的端点是 `openai_compatible`；Astra 自己的服务是 `astra` |
| `model` | 聊天的模型 id |
| `api_base_url` | 端点。userinfo、query 和 fragment 已被移除；路径按本人配置的原样发送（把令牌放进路径的中继会把它交给你）。`astra` 时为空，它的端点不该由你来调用 |
| `is_loopback` | 端点就在本机（`127.0.0.0/8`、`::1`、`localhost`）——本地模型 |

它从不携带 API 密钥、用户保存的其他端点、系统提示词，也不携带聊天以外的任何角色。需要密钥的插件应在自己的 `[config]` 里向用户索取（标记为 secret）。它既不是高风险，也不会在本地导入时被拒绝：这是获取这些信息的诚实途径，把它定得比读取 `settings.json` 更高，只会把插件推向错误的方向。读取 Astra 自己的文件是发布时人工审核会查的内容。早于该调用的 Astra 会返回 `UNIMPLEMENTED`。

## 用 Astra 的声音说话

有事要播报的插件——一个计时器、一次完成的构建、一条刚到的消息——可以让 Astra 把它说出来。声明 `speak`，然后调用 `Speak`（Rust 和 Python 中是 `speak(text)`，TypeScript 中是 `ctx.speak(text)`）。

`speak` 是**高风险**权限：你的话会以 Astra 的声音被听到，就像是 Astra 说的一样，所以它有自己独立的同意勾选框。它不会在本地导入时被拒绝——播报是插件很常见的需求，勾选框就是那个决定。除了授权之外，`Speak` 还需要**一个有权使用 Astra 的账号**，以及**本人开启了回复语音**；Astra 锁定期间它会被拒绝。

这个调用会持续到语音结束，并返回语音的结果：

| 结果 | 含义 | 该怎么做 |
|---|---|---|
| `SPOKEN` | 已被听到 | 什么都不用做 |
| `STOPPED` | 在说完之前有人要求安静：唤醒词、关闭回复语音、停止、你自己的 `StopSpeaking` | 什么都不用做——**这不是错误**。不要在没人要求时再说一遍 |
| `NOT_SPOKEN` | 没有说出来；`error`（与聊天分块携带的同一个 `PluginError`）说明原因 | 查看下面的代码。被拒绝的内容不会进入队列 |

| `error.code` | 何时 |
|---|---|
| `PLUGIN_ERROR_BAD_ARGUMENTS` | 去掉不可见字符后文本为空，或超过 **300 个字符**（`spec/limits.yaml` 中的 `speak_text_max_chars`）。更长的文本会被拒绝，绝不会被截断 |
| `PLUGIN_ERROR_RATE_LIMITED` | 你的说话时间用完了。它按字符计算——**一次 450 个，之后每秒 3 个**，每次调用至少计 20 个——`retry_after_ms` 告诉你何时再有余量 |
| `PLUGIN_ERROR_UNAVAILABLE` | 本人关闭了 Astra 的语音、Astra 已锁定、没有可用的语音，或者语音队列无法接收它。改为显示这段文本；不要要求本人去更改设置 |

你的话会排在你自己之前的话后面，走一条独立的通道，所以它们绝不会打断 Astra 的回复。`StopSpeaking` 会停止你要求说出的一切——正在播放的和排队中的——此外什么都不停；它与 `speak` 共用同一个权限，无论是否有人登录都能使用。限制由守护进程执行：SDK 导出 `SPEAK_TEXT_MAX_CHARS` 以便你显示一个计数器，自身不做任何检查。早于该调用的 Astra 会返回 `UNIMPLEMENTED`。

## 知道谁在使用 Astra

按人或按机器限制使用的插件——试用期、配额、许可证——需要为每个人或每台机器提供一个稳定的 id。**向 Astra 询问；绝不要读取硬件序列号或 Astra 的文件。** 声明 `read_user_identity`，然后调用 `GetUserIdentity`（Rust 和 Python 中是 `get_user_identity()`，TypeScript 中是 `ctx.getUserIdentity()`）：

| 字段 | 含义 |
|---|---|
| `install_id` | 这次 Astra 安装：在 Astra 和你的插件重启、更新之后保持不变，在另一次安装上则不同。Astra 还没有安装密钥时为空 |
| `signed_in` | 有人登录了 Astra |
| `authorized` | ……并且其账号有权使用 Astra |
| `account_id` | 已登录的账号：在本人登录的每台设备上都相同。除非 `authorized`，否则为空 |

两个 id 都是**专为你的插件生成的假名**：另一个插件对同一个人、同一台机器读到的是不同的 id，因此两个插件无法凭它们把各自的记录关联起来。这只对诚实使用该 API 的插件成立：插件的原生代码可以读取 Astra 的文件。它们都不是秘密，也绝不会是账号本身的 id、本人的姓名或电子邮件，或硬件序列号。它既不是高风险，也不会在本地导入时被拒绝：这是机器序列号的诚实替代方案，把它定得太高只会把插件推回序列号。早于该调用的 Astra 会返回 `UNIMPLEMENTED`。

**`auth_changed` 也随之收窄**（Astra，2026-11-12）。被授予 `auth_changed` 事件的插件，过去会收到账号本身的 id、本人的显示名称和其套餐。现在它收到的是 `authenticated`、`authorized`、`timestamp` 和 `account_id`——与 `GetUserIdentity` 返回的是同一个假名；除非你持有 `read_user_identity` 且该账号有权使用 Astra，否则为 `""`。`user_id` 和 `user_name` 仍然会到达，值为 `null`，`subscription_tier` 为 `""`，这样为旧格式编写的解析器仍能继续解析；它们都不再携带任何值。

## 接收本人附上的图片

处理图片的工具——读一张收据、认出一种植物、描述一张照片——可以请求本人附在 Astra 正在回答的那条消息上的图片。**目前还没有任何 Astra 发行版会这样做：** 守护进程只有在以 `plugin-provider-slots` 构建特性构建时才会发送图片。其他任何 Astra 都会忽略这一请求，你的工具收不到图片。

需要两件事。在 `[permissions]` 中声明 `receive_attachments`，并标记每个需要图片的工具；然后在它的处理函数里读取图片：

| SDK | 标记工具 | 读取图片 |
|---|---|---|
| Rust | `#[tool(wants_attachments)]`，或 `ToolDef::new(…).with_attachments(true)` | `ctx.attachments()` |
| Python | `@tool("…", wants_attachments=True)`，或 `ToolDef(…, wants_attachments=True)` | `current_attachments()` |
| TypeScript | 在 `tool({…})` 中或在 `ToolDef` 上写 `wantsAttachments: true` | `ctx.attachments`，或 `currentAttachments()` |

每张图片带有 `mime_type`（TypeScript 中为 `mimeType`）、`data`（字节本身）和 `filename`（附上时用的文件名本身，绝不包含文件夹）。没有请求图片的工具读到的是空列表，不带图片的调用也是如此。

只有以下条件全部满足时，Astra 才会把图片交给一次调用：

- 该工具在其 `ListTools` 应答中声明了 `wants_attachments`；
- 你的插件持有 `receive_attachments`；
- 这次调用发生在回答本人在某个对话中发送的消息时——调用的 invocation 指明了该对话。报告唤醒、命令的 AI 步骤或子代理的轮次中绝不会交付；当 Astra 因为一条本人尚未批准的 Workshop 命令而扣留该轮次时也不会。

到达的只有附在**那一条消息**上的图片：绝不会有对话中更早的图片，绝不会有工具生成的图片，也绝不会有模型点名的图片。最多 **4** 张（`spec/limits.yaml` 中的 `image_input_max_images`），总计 20 MiB，保留最新的，按附上的顺序排列；无法读取的图片绝不会发送。若有图片没有发送——超出了上限，或你的插件没有该授权——会在你的结果之后告知**模型**；你的工具只是收到的更少，或者一张也收不到。

目前，Astra 的聊天输入框会把每张附上的图片缩放到最多 768 像素，并重新编码为 JPEG，同时保留原始文件名，所以你的工具收到的就是这样的图片。请以 `mime_type` 为准，而不是 `filename` 的扩展名。

一次调用最多可携带 20 MiB 的图片，超过了 gRPC 默认的 4 MiB 接收上限。三个 SDK 的 capability 服务器最多可接收 64 MiB（`plugin_max_message_bytes`）；不借助 SDK 自行实现该协议的插件，必须把自己服务器的接收上限调到 4 MiB 以上。

`receive_attachments` 属于**高风险**权限：本人的照片会到达并非 Astra 的代码，因此它有自己独立的同意勾选框。本地导入时它不会被拒绝——和 `speak` 一样，勾选框就是决定。

## 请本人更改某项设置

插件如果确有理由希望 Astra 的某项设置被更改——它的工具所适配的模型、适合它的声音——就去**请求**，由本人在一张卡片上决定。绝不要自己去写 Astra 的 `settings.json`，也绝不要为此借用 Astra 自己的会话：那是在本人背后改动本人的 Astra，而发布时的人工审核正是要找这种行为。声明 `request_settings_change` 并调用 `RequestSettingsChange`（Rust 和 Python 中为 `request_settings_change(changes, reason)`，TypeScript 中为 `ctx.requestSettingsChange(changes, reason)`）。**目前还没有任何 Astra 发布版本会响应它：**只有以 `plugin-requests` 构建功能构建的守护进程才接受请求；其他任何 Astra 都会返回带代码 `not_compiled` 的 `REFUSED`。

每项更改是一个以点分隔的设置路径和想要的值（JSON 形式）——SDK 会替你把值序列化。只能请求更改助手自己可以更改的那些设置——声音、AI 模型、语言；绝不包括权限模式、密钥或 Tool Search——而且每个值都会像助手自己的更改一样接受完全相同的检查。卡片会写明你的插件，显示每项设置现在的值和将要变成的值，以及你用自己的话写的 `reason`。要么全部更改，要么全不更改，而被更改的正是卡片上显示的内容。

**调用会一直持续到本人作答或卡片过期**——即 Astra 的确认超时，至少 30 秒，本人未改动时为 120 秒。SDK 不会为它设置自己的截止时间。绝不要在必须快速作答的路径上等待它，例如模型正在等待的工具调用。

| 结果 | 含义 | 该怎么做 |
|---|---|---|
| `APPLIED` | 本人允许了；设置现在就是你请求的值 | 什么都不用做 |
| `UNCHANGED` | 设置本来就是这个值。没有询问任何人 | 什么都不用做 |
| `DECLINED` | 本人拒绝了——现在拒绝，或以前就拒绝过你的插件更改其中某项设置。只有当这样的设置以别的方式改变之后，或重启之后，Astra 才会再次询问 | 按本人现有的设置继续。**不要在没人要求时再次询问** |
| `TIMED_OUT` | 卡片过期前没有人作答（没有打开任何窗口也算在内） | 等本人在场时再问 |
| `REFUSED` | 没有询问，或没有应用：`code` 说明原因，涉及某项设置时 `refused_path` 会写明它，`error` 是一个 `PluginError` | 查看下面的代码 |

| `code` | 何时 |
|---|---|
| `not_compiled` | 这个 Astra 不接受请求：它在构建时没有启用 `plugin-requests` 功能 |
| `locked` | Astra 被其密码锁定 |
| `invalid` | 没有任何更改、同一路径出现两次、某个值不是 JSON，或内容多到一张卡片无法完整显示 |
| `too_many` | 超过 **8** 项更改（`spec/limits.yaml` 中的 `settings_change_max_changes`） |
| `reason_too_long` | 理由超过 **140 个字符**（`settings_change_reason_max_chars`）。理由会完整显示，所以超长会被拒绝，绝不截断 |
| `busy` | 你的某个请求已在等待本人作答：每个插件同一时间只有一张卡片 |
| `rate_limited` | **一次最多两个请求，之后每两分钟一个**；`error.retry_after_ms` 说明何时会再有空位 |
| `not_assistant_editable` | 助手不能更改的路径 |
| `invalid_value`, `unknown_choice` | 该设置无法容纳的值，或它不提供的选项 |
| `needs_api_key`, `needs_stt_provider`, `provider_unreachable` | 这项更改会让 Astra 缺少它所需要的东西：该 AI 提供商的密钥、语音识别器、能够响应的提供商 |
| `stale` | 卡片显示期间设置发生了变化，因此本人允许的内容与将要写入的内容不同。什么都没有写入 |
| `stopped` | 你的插件的权限先结束了——它被停止、被禁用或被撤下，或者账号不再有权使用 Astra |
| `write_refused` | 无法写入设置 |

当前值永远不会被返回：你的插件得知的只是结果。限制由守护进程掌握：SDK 导出 `SETTINGS_CHANGE_MAX_CHANGES` 和 `SETTINGS_CHANGE_REASON_MAX_CHARS`，自己不检查其中任何一个。除了授予之外，调用还需要**一个有权使用 Astra 的账号**；缺少授予，或账号无权使用 Astra，都和任何 host 调用一样是一次失败的调用，而不是一个结果。它既不属于高风险，在本地导入时也不会被拒绝：每个请求都是一张由本人作答的卡片，所以每次都会征求同意。早于这个调用的 Astra 会返回 `UNIMPLEMENTED`。

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

权限按风险分组。七种高风险权限各自有独立的勾选框，只要还有一个没被
勾选，"安装"按钮就保持禁用；`dom_access` 还会有第二个界面。这里刻意
**没有"输入以确认"**这种设计：那是用于不可逆的破坏性操作的模式，让用户
习惯于打字敲过去，只会摧毁勾选框本应承载的那个信号。

关于更新：如果权限不变或收窄，会静默地应用；如果权限**扩大**了，更新会
被暂存而不会安装，旧版本会继续运行，直到用户审阅了这个差异为止。拒绝
更新不会有任何代价。
