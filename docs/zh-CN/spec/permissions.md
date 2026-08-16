> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/spec/permissions.md)。如与英文版有出入，以英文版为准。

# 权限 —— 规范性规格说明

**状态：** 规范性的。词汇表、关卡、上限、四条来源路径以及哈希，全部
都已实现并强制执行；凡是已经规定但尚未强制执行的地方，本文档会在对
应的行里说明。

要求用语遵循 RFC 2119。

`plugin.toml` 中存在两个正交的段，把它们搞混正是这套词汇表被创造出来
要修复的那个 bug：

| 段 | 方向 | 问题 |
|---|---|---|
| `[capabilities]` | 守护进程 → 插件 | *我实现了什么，Astra 可以调入其中？* |
| `[permissions]` | 插件 → 守护进程 | *我可以调出到什么，我可能被交给哪些界面(surface)？* |

它们曾经共用一个词来表达两件事，而那个词指的是第一件事——这正是
`dom_access` 曾经沦为一个插件只需声明就能自我授予的能力的由来。

---

## 1. 词汇表

八个 id，一个封闭的集合（`astra-plugin-manifest/src/permissions.rs`，
`PERMISSION_NAMES`，由测试固定到枚举上）。注册表会根据这份列表校验
上架条目的 id，Astra 本地化的标签表也以此为键，所以一个只在某处添加、
没有在其他地方同步添加的 id，渲染出来会是空白的一行。

| id | 限制的调用 | 授予什么 | 高风险 |
|---|---|---|---|
| `fire_trigger` | `PluginHostService.FireTrigger` | 运行用户已保存的自动化流程 | |
| `subscribe_events` | `SubscribeEvents` | 接收守护进程事件，**限定在已声明的类型内**（§1.1） | |
| `set_variable` | `SetVariable` | 写入守护进程的变量上下文，限定在调用插件的命名空间内 | |
| `send_chat_message` | `SendChatMessage` | 驱动一次 AI 对话轮次——花费用户的 token，用他们助手的声音说话 | ● |
| `push_to_ui` | `PushToUi` | 向 Astra 窗口推送一个事件 | ● |
| `set_theme_contribution` | `SetThemeContribution` | 重新设置整个应用的样式 | ● |
| `dom_access` | *没有 RPC*——一个**界面层(surface)** | 在 Astra 窗口内运行插件自己的脚本，能访问用户的对话以及每一个其他插件的界面 | ● |
| `client` | *没有 RPC*——一个**界面层(surface)** | 作为一个客户端前端：有自己的聊天界面，有自己的会话 | ● |

**带 ● 标记的五项是高风险的**（`HIGH_RISK_PERMISSIONS`），每一项都会
得到自己的同意勾选框。计划文档 §4.3 详细列出了四个勾选框，遗漏了
`push_to_ui`；§5.6 列出了五个。实现采用的是**并集**，因为这个分歧出
现在 UI 段落和安全章节之间，多一个勾选框的代价只是多一次点击，少一
个的代价却是丢掉那个属性本身。

**`dom_access` 和 `client` 不限制任何 RPC**，这恰恰是为什么它们需要
第二个强制执行点：它们是在*界面层*被分发出去的地方（§4.2）被强制执
行的，而不是在某次调用得到响应的地方。

### 1.1 权限参数

`[permissions]` 中的一个条目是一个对象，不是一个布尔值：

```toml
[permissions]
fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
subscribe_events = { types = ["command_completed"], reason = "Reacts when a command finishes" }
set_variable     = { scopes = ["plugin"] }
```

| 成员 | 类型 | 含义 |
|---|---|---|
| `reason` | string，≤ 140 字符 | 作者自己的话（§6） |
| `types` | array of string | **仅 `subscribe_events`。** 事件类型白名单 |
| `scopes` | array of string | **仅 `set_variable`。** `plugin` / `session` / `persistent`。**保留字段**——守护进程今天已经按插件 id 对每个插件的写入做了命名空间隔离，所以这个字段目前还没有任何收窄作用。它之所以被解析，是为了让声明它的清单文件可以发布，并且在任何地方都得到相同的哈希 |

**`subscribe_events.types` 是一份由守护进程按每个事件强制执行的白名
单，空白名单意味着什么都不允许。** 有三种状态，而中间那种正是关键
所在：

* 权限缺失 → 完全没有流；
* 权限存在，但 `types` 为空 → **什么都不允许**；守护进程会拒绝这次订
  阅，并给出指明修复方法的消息，而不是返回一个永远沉默的流；
* `types` 已列出 → 恰好是那些
  `AstraEvent::event_type_str()` 值。

那种直觉的读法——"没有过滤器就意味着接收一切"——正是这项权限存在
的目的所要堵上的那个漏洞：一个没有过滤的订阅者会收到
`speech_recognized`，也就是用户说的每一个字。

### 1.2 未知的 id 会被保留，而不是被拒绝

一份清单文件如果指名了一个这个构建版本从未听说过的 id，会被**接
受**。原因有两个，指向同一个方向：

1. **向前兼容。** 新的 id 会随新版本的 Astra 一起出现。一个拒绝未知
   id 的守护进程，会让每一次新增都成为对每一个更旧守护进程的一次
   "标志日"（flag day）。
2. **哈希。** `permissions_hash`（§5）是由三份实现针对这些字节计算
   出来的。丢弃一个读取者不认识的键，会让其中两份对"到底签的是什
   么"产生分歧。

一个未知的 id 是**不起作用的**——默认拒绝意味着它永远不会授予任何东
西——而这不是悄无声息发生的。同意页面会通过它的
`permission.unrecognised` 标签把它渲染出来，而不是把它丢弃，所以用
户会被告知这个插件申请了某样这个版本的 Astra 不认识的东西。
`Permissions::unknown()` 的存在是为了让工具能够逐项列出它们；**
`astra-plugin check` 今天并不会这么做**——它只报告存在一个
`[permissions]` 段，到此为止。

（相比之下，`[capabilities]` 是 `deny_unknown_fields` 的：那是一个
封闭的布尔值集合，一个拼写错误读起来会和 `false` 一模一样。）

## 2. 默认拒绝，以及不需要任何权限的四个 RPC

**一个缺失的 `[permissions]` 段，意味着除了始终被允许的集合之外，不
会授予任何 host RPC。** 一个缺失的段不是"未指定"；它是一个完整的答
案，而这个答案是"不"。

始终被允许的集合有四个，并且被写成了一张表
（`host_service.rs` 中的 `HOST_RPC_PERMISSIONS`），两个金丝雀测试
(canary)会拿每一个 RPC 去和它核对，所以一个没有被限制的新 RPC 会
表现为一次测试失败，而不是一次悄无声息的遗漏：

| RPC | 权限 |
|---|---|
| `Register` | — |
| `PluginLog` | — |
| `GetPluginSelfConfig` | — |
| `GetDaemonInfo` | — |
| `SubscribeEvents` | `subscribe_events` |
| `SendChatMessage` | `send_chat_message` |
| `FireTrigger` | `fire_trigger` |
| `SetVariable` | `set_variable` |
| `SetThemeContribution` | `set_theme_contribution` |
| `PushToUi` | `push_to_ui` |

`GetDaemonInfo` 是在计划文档三项清单之外新增的一项，这是一个决定，
而不是遗漏：它返回的 `version`、`state`、`grpc_port` 和 `language`，
全都是 `PluginRegisterResponse` 早已交给调用方的信息，所以它不会泄
露任何新东西。为它发明一个权限 id，只会在用户面前放一个什么都保护
不了的勾选框，而什么都保护不了的勾选框，正是用户学会随手勾选各种框
的原因。

**`client_session_token` 会发给每一个插件。** 这个令牌是*认证*（谁
在调用），而不是*授权*（他们可以做什么）。对非 `client` 插件扣留它，
会拒绝掉 `PluginLog`、`GetPluginSelfConfig`、`SubscribeEvents` 和
`FireTrigger`——也就是始终被允许的那个集合——并破坏每一个插件以及
仓库内的两个 sidecar。`client` 这道关卡应该存在于上限和特定的界面
层上，而不是存在于令牌本身上。

## 3. 声明是提出申请；授予是另一个对象

**`plugin.toml` 中的任何内容都不是一次授予。** 一个 `[permissions]`
块是作者的*申请*。**被授予的集合**是一个独立的对象，由守护进程按来
源路径解析，并存放在插件无法触及的地方——
`<base_dir>/registry/records/<id>.json`，是插件目录树的兄弟节点，
绝不是它的子节点，用守护进程持有的密钥做了 MAC 保护。

强制执行读取的是这个被授予的集合，绝不读取清单文件——每一个受限制
的 RPC 顶部那次调用的形态（下面是从 `host_service.rs` 摘出的说明性
片段，不是可运行的示例）：

```rust
let (plugin_id, grants) =
    self.require_permission(&request, Permission::FireTrigger, "FireTrigger").await?;
```

一个能通过编辑自己清单文件来扩大自己授权的插件，意味着这套权限系统
不过是一句注释。在 Phase 4 之前，这曾经是字面意义上的事实：
`[capabilities] dom_access = true`——插件自己目录下某个文件里的一
行——会被直接照搬到渲染器所遵循的那个 UI 贡献上，把插件的脚本直接
加载进 Astra 窗口本身。

**为什么这条记录不在插件的目录里。** 插件是以用户的身份运行的，
`current_dir` 被设置为它的安装目录。0600 模式防的是其他用户，防不
了这个当事者本身。一份当事者能写入的记录，会让一个恶意插件给自己
授予 `dom_access`、覆写 TOFU 锁定、为了逃避基于摘要的失效检测而重写
`artifact_sha256`、并重写各文件的哈希值以让启动时的重新检查通过。

### 3.1 能力桥接

`dom_access` 和 `client` 既是 `[capabilities]` 布尔值，**也**是权限
id。在这个拆分出现之前编写的每一个插件，都在旧的位置说明自己想要
什么——包括 `companion`、`doom` 和 `bad-apple`，它们没有一个完整声
明了 `[permissions]` 段。

所以一个 `[capabilities] dom_access = true` 位，会像一个
`[permissions]` 条目一样被当作**一次申请**来读取，并从同一张表
（`declared_permissions()`）得到完全相同的答案。这座桥接刻意*不是*
"能力位授予对应权限"这种设计：它把这个位放在申请所在的位置，这样
"这可以吗？"这个问题就只有一个答案，而不是两个。

对作者的后果是：**一个通过注册表发布的插件必须声明
`[permissions] dom_access`**，因为一次注册表安装是从它的信任记录中
授权的，而那份信任记录是根据包的 `MANIFEST.json` 中 `[permissions]`
块写入的——正是那个条目，才是同意页面渲染出来、用户去勾选的那个。

## 4. 被授予的集合来自哪里

### 4.1 四条来源路径

`decide_grants()` 就是把这张表写成的一个纯函数。

| 路径 | 被授予的集合 |
|---|---|
| **内置 sidecar**（`builtin_stt`、`builtin_vox`） | 紧邻那个 sidecar 的 `build_manifest()` 定义的、**代码中声明**的集合。没有信任记录，不读磁盘——一个 sidecar *按设计*就没有记录，所以一条会去寻找记录的代码路径，就会变成一条可能因此失败的代码路径 |
| **注册表安装** | 安装时写下的信任记录：包的 `MANIFEST.permissions`，经过同意检查后，受该层级上限的约束 |
| **`ImportPluginFile`**（一个来自带外渠道的 `.astraplugin`） | 一条 `tier: "local-unverified"` 的信任记录——清单文件声明的集合，**受第 2 层级上限约束** |
| **侧载(Sideload)**（一个源码目录，开发者模式） | 一条 `tier: "sideloaded"` 的信任记录——清单文件声明的集合，**没有上限** |

有四种分支不在那张表里，但同样具有规范性：

| 状态 | 授予什么 |
|---|---|
| `Untrusted`——本该有一条记录，但它无法被信任 | **什么都不授予** |
| `TamperDetected`——某个文件已经不再匹配为它记录下的摘要 | **什么都不授予** |
| `Revoked`——一份已签名的撤回列表覆盖了它 | **什么都不授予** |
| `Unrecorded`——在信任记录存在之前就已安装，完全没有记录 | 清单文件声明的集合，**受第 2 层级上限约束** |

`Untrusted` 依然可以手动启动，而当它这样启动时，运行时不带任何授
权：「用户要求了」并不是关于字节内容的证据。`Unrecorded` 之所以是
受限而不是被拒绝，是因为对这些插件什么都不授予，会在升级时破坏正
常工作的安装，而用户又没有办法自行修复；而不加上限地把清单内容授
予它们，则会让其中任何一个都能通过编辑自己目录下的一个文件来自我
授予 `dom_access`。第 2 层级的上限，正是"从某处来，但什么都没证
明"这句话的确切形状。

一个没有可信记录的 `Verified` 插件会得到**什么都没有**：`Verified`
*意味着*存在一条可信的记录，对于这种不可能出现的组合，答案不是退
回去信任清单文件。

每一次拒绝都会点名它的来源（`GrantSource::describe`）——只说"被拒绝
了"、却不说"而这就是那个对此什么都没说的来源"，正是让一套权限系统
被推倒重来的失败模式。

### 4.2 两道关卡，不是一道

一项权限只有在**两者都**成立时才会被兑现：

1. **授权(grant)**——一次由同意页面产生、由信任记录持有的、按每次
   安装给出的答案；
2. **上限(ceiling)**——一条任何记录都无法买通突破的、按来源而定的
   规则。

`require_permission` 会针对限制某项权限的六个 host RPC——
`SubscribeEvents`、`SendChatMessage`、`FireTrigger`、`SetVariable`、
`SetThemeContribution`、`PushToUi`——去询问第一道关卡。剩下的四个
（`Register`、`GetPluginSelfConfig`、`PluginLog`、`GetDaemonInfo`）
在 `HOST_RPC_PERMISSIONS` 中携带的是 `None`，永远被允许；§2 中有对
应的表格和推理过程。`ceiling_admits` 会在任何一个*界面层*被分发出去
的地方——`PluginStatusMsg`、UI 贡献响应、活跃主题响应——去询问第二道
关卡，这样渲染器就永远不会收到一个它可能会去兑现的值。一个在授权
映射表中找不到的插件会被拒绝："对它什么都没解析出来"不能成为把系统
中风险最高的界面层交给它的理由。

## 5. 层级上限

| 层级 | 来源 | 上限 |
|---|---|---|
| **1 · 注册表** | 按照安装算法验证过的 | **一切**，取决于用户同意。验证失败时没有覆盖(override)的余地 |
| **2 · 本地文件**（`ImportPluginFile`） | 通过带外方式收到的 `.astraplugin` | `send_chat_message`、`set_theme_contribution`、`dom_access` 和 `client` 会被**直接拒绝，而不只是给出警告** |
| **3 · 侧载(Sideload)** | 用户用文件对话框指向的一个源码目录，开发者模式开启 | **没有上限**——而且**永远不会自动启动**：开发者模式在加载时是必需的，重启后会保持停止状态，直到用户再次启动它 |

侧载所属的层级，会以 `provenance.tier.sideloaded`（"从一个文件夹加
载"）的形式呈现给用户，出现在溯源面板中。计划文档还要求，只要
`dom_access` 处于生效状态，就在卡片和窗口边框上显示一个永久的、无
法关闭的"DEVELOPER — unverified code from a local directory"徽章；
**这个徽章今天在 UI 中并不存在**，本文档也没有声称它存在。

**第 2 层级的晋升机制尚未实现。** 计划文档描述的是，当一个被导入文
件的摘要出现在一份全新的索引中、且版本下限也满足时，把它晋升到第
1 层级；但今天 `import_plugin_file` 完全不会把任何已验证的发布传入
安装路径，所以一个被导入的包，无论索引对它的摘要说了什么，都**始
终**是 `local-unverified`。不要告诉作者说，发布出去会追溯性地解除
他们邮件发给别人的那个文件的上限。

第 2 层级的拒绝清单是 `TIER2_REFUSED_PERMISSIONS`——它刻意**不是**
和 `HIGH_RISK_PERMISSIONS` 相同的清单：`push_to_ui` 值得拥有一个勾
选框，但不值得因为它就拒绝一个用户选择导入的文件。这四项是从 §5.5
直接引用的，不是推断出来的。

**第 3 层级不是套了个更好看徽章的第 2 层级。** 这个划分是按*意图*，
而不是按验证状态来区分的。一个用文件对话框指向自己磁盘上某个目录的
用户，给出的信号比一个来自别处的未验证文件要强得多——而
`companion`、`doom` 和 `bad-apple`，也就是这个项目自己的旗舰示例，
全都需要那条被第 2 层级拒绝的 DOM 路径。给第 3 层级设上限，会让
`astra-plugin dev` 变得不可能。

未知的 id 会被每一道上限丢弃（`capped()` 用
`Permission::from_id(id).is_some_and(keep)` 做过滤）：一道放行了自
己无法分类的 id 的上限，会是一道形状恰好和下一个版本吻合的漏洞。

**这条设计原则在任何地方都被坚守着：** *用户的覆盖(override)所能买
到的，唯一只是运行来自一个 Astra 未经审查的源的代码的权利。它永远
不能买到一个已验证插件本该必须申请的权限。*

## 6. 同意

同意页面在**任何下载发生之前**渲染出来，内容来自目录记录的
`permissions`——注册表在摄入(ingest)时从包的 `MANIFEST.json` 复制
过来的。

* 每个 id 都通过**Astra 自己的本地化标签表**渲染出来。作者的
  `reason` 处于从属地位：带引号、纯文本、不超过 140 字符，始终带有
  *"The author says:"*前缀。它绝**不是**标签本身——措辞的修正随
  Astra 一起发布，绝不能被一个上架条目自行编造。
* 每一项高风险权限都会得到**自己的勾选框**；`dom_access` 会得到第
  二个界面。
* 这个答案会作为**一道上限，而不是一次申请**传入安装过程
  （`InstallOptions::consent`）：如果*包*本身申请了任何页面上没有
  展示过的内容，安装会以 `PERMISSIONS_NOT_CONSENTED` 被拒绝。这两
  份清单来自不同的地方——页面渲染的是目录记录，信任记录授权的是包
  自己的清单文件——除此之外没有任何东西能保证它们一致。一个什么都
  不声明、却随附了一个申请 `dom_access` 的包的上架条目，正是那种直
  接瞄准同意界面的"恶意注册表"情形。
* `consent: None`——一元安装、一次导入、一次测试、一次收养——保留的
  是同意机制出现之前的行为：授予包声明的集合，按层级设上限。

**更新。** 一个申请了已安装版本未被授予的权限的新版本，会以
`PERMISSIONS_WIDENED` 被拒绝，变成一个审阅提示；用户明确的批准才是
把它变成一次安装的东西。比较方式是**按权限名比较，绝不是比较整个
请求对象**：一个改进了 `reason` 措辞的作者，并没有扩大任何东西，而
一个把这也算作扩大的更新关卡，只会训练用户去随手点掉这个唯一重要
的对话框。

**撤销会立即生效。** 只要 `granted_permissions` 发生任何变化、同意
被撤回，或者失效发生，守护进程都会关闭服务端的订阅并使会话令牌失
效，所以一个正在运行中的事件流不可能在权限收窄之后继续存活。插件
会通过 `x-astra-teardown-reason` trailer（`grants_changed`、
`consent_declined`、`revoked`、`trust_lost`、`disabled`、
`uninstalled`、`re_registered`）得知具体发生了哪一种——这是一个稳定
的标记，所以 SDK 永远不需要去解析英文文本，才能知道重试是否毫无意义。

### 6.1 写一个好的 `reason`

它会展示给正在做决定的用户。它**必须**不超过 140 字符，并且**应该**：

* 点名**用户能认出来的功能**，而不是 API——是"Fires the
  on_dice_roll trigger you configure"，不是"calls FireTrigger"；
* 如果不是一直如此，**说明是什么时候**——比如"only while a
  recording is in progress"；
* 避免重复权限自身的标签内容；Astra 已经渲染过了；
* 避免制造紧迫感、威胁，或者给用户下指令。生成器会在任何原样展示
  的地方，拒绝包含双向文字覆盖(bidi override)或零宽连接符的文本，
  同意页面是最不适合搞例外的地方。

一项找不出站得住脚理由的权限，就是一项应该从清单文件中删掉的权
限——没有任何东西会自动检查这一点，阅读上架条目的审阅者是唯一的最
后防线。

## 7. `permissions_hash`

```
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( JCS(permissions) ) )
```

* `JCS` 是 RFC 8785 规范化 JSON——键按 UTF-16 代码单元排序，紧凑输
  出。两个仓库共同实现的这份档案，见
  [`registry-index.md` §3](registry-index.md#3-规范化jcs-档案)。
* **`null` 和 `{}` 是相同的值**，哈希也相同，所以一个省略该成员的
  生产者和一个写出空对象的生产者是一致的：
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`。
* **空的成员会被省略，而不是以空值的形式发出。** `set_variable = {}`
  就是 `{}`，绝不是 `{"reason":""}`。同一个声明的两种规范拼写方式，
  正是这个哈希要防止的那种偏差。
* `sha256:` 前缀是值的一部分，因为它要跨越仓库边界。

三份实现都会计算它，三者也都会被比对：`astra-plugin` 的打包工具把
它写进 `MANIFEST.json`；注册表 bot 在摄入时重新推导它，一旦不一致
就拒绝上架（`E_PERMISSIONS_HASH_MISMATCH`）；守护进程在信任这份清单
文件之前重新推导它，并阻止安装
（`PERMISSIONS_HASH_MISMATCH`）。黄金向量：`ok-permissions`（一个正
确的非空映射）和 `permissions-hash-mismatch`——参见
[`bundle-v2.md` §10](bundle-v2.md#10-permissions-和-permissions_hash)
以及仅存在于 CLI 读取器中的 F5 分歧。

这个哈希同时也被记录在信任记录中，并在发现(discovery)时重新检查，
所以安装后被原地编辑过的 `plugin.toml` 会被检测出来，而不是被照单
全收。

## 8. 权限不是什么

`[permissions]` 回答的是*守护进程会为一个插件做什么*。它不回答*这个
进程能对这台机器做什么*。

插件是一个原生进程，由守护进程启动，以用户的身份、用用户的完整权
限运行。它可以读取用户的文件，打开套接字，而且——在今天——能从磁
盘上读取守护进程自己的令牌。**这里没有沙箱。** 隔离机制（Linux 上
的 Landlock/seccomp，Windows 上的 AppContainer 或低完整性令牌，
rlimits）被划定为未来的工作，明确不在本次发布范围内。

本文档要求每一个消费方都遵守的两个后果：

* **Astra 的 UI 绝不能暗示存在沙箱。** 溯源面板中"不能证明"的那个
  说明区块，以及同意页面的那一句话，正是为此而存在的。
* **一次权限拒绝，只对守护进程自身的权限范围——自动化、聊天轮次、
  主题、窗口——是一道真正的边界。** 对其他一切来说，它是一根绊线，
  而不是一座监狱。

在这一点上诚实，不是拴在结尾处的一句免责声明。一个被描述成沙箱的
权限模型，会让它的用户做出比完全没有这个模型时更糟糕的决定。

---

*编写本文档时核实过的来源：
`Astra/astra-rs/astra-plugin-manifest/src/permissions.rs`；
`Astra/astra-rs/astra-daemon/src/plugins/host_service.rs`
（`HOST_RPC_PERMISSIONS`、`decide_grants`、`ceiling_for`、
`declared_permissions`、`resolve_grants`、`TeardownReason`）；
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs`
（`InstallOptions::consent`、`ceiling_admits`、
`granted_and_admitted`、`UpdateGate`、`block_codes`）；
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`
（`permissions_hash`、`permission_names`、`Tier`、`TrustRecord`）；
`astra-plugin-cli/src/bundle.rs`（`canonical_permissions`、
`permissions_hash`）；`astra-registry/schema/version-v1.json`；
`astra-registry/bot/lib/bundle.mjs`；`testdata/bundles/vectors.json`。*
