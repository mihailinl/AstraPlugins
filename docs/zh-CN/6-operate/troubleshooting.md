> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/6-operate/troubleshooting.md)。如与英文版有出入，以英文版为准。

# 故障排查

按 CLI 和守护进程实际打印出的字符串来索引。如果你面前正好有一个错误，
就在本页搜索它的一个片段。

## 从这里开始

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

十五项检查，每一项都以它所回答的问题的形式表述出来。它知道你正在运行
哪个 CLI、它解析出了哪个配置目录、守护进程是否可达、你有哪些工具链、
你的清单文件能否解析、入口点是否存在、你的权限是否覆盖了你的能力、你
的 `[platform]` 段是否正确，以及你的发布工作流是否已固定版本。每一个
失败都带有一行 `fix:`。在一个你还没构建过的项目里，它会在其中一项上
以非零状态退出 —— "Will the daemon find something to start? … does
not exist" —— 这是对的：因为还没有任何东西产出过这个二进制文件。

## 项目无法解析出它的 SDK

**`error: failed to select a version for the requirement astra-plugin-sdk = "^0.6"`**
**`ERROR: No matching distribution found for astra-plugin-sdk<0.6,>=0.5`**
**`error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)`**

三种语言，同一种形态的错误 —— 但原因已经不再是 SDK 不存在。
`astra-plugin new` 为 Rust 固定 `astra-plugin-sdk` `0.6`，为 Python 固定
`>=0.5,<0.6`，为 TypeScript 固定 `^0.5.0`，而公共注册表上分别是 crates.io
**0.6.0**、PyPI **0.5.0**、npm **0.5.0**。这些固定值在一个全新的、什么都没配置
的项目里都能解析出来。所以如果你这边解析不出来，原因就在你的机器和注册表之间：

- **过期的索引、锁文件，或没有同步的镜像。** 解析器读到的是发布之前的注册表
  缓存视图，或者是同样过期的公司代理。`cargo update -p astra-plugin-sdk`；
  `pip install --upgrade --no-cache-dir -r requirements.txt`；npm 则删掉
  `node_modules` 和锁文件后重新安装。`cargo --offline` 和 `npm --offline`
  本来就会产生这个错误。
- **有人放宽了下限。** 被改成 `0.5`(Rust)或 `0.4`(Python、TypeScript)的
  固定值，要的是任何注册表在那个约束下都不提供的东西。请把脚手架原本的固定值
  改回去，而不是继续放宽：0.6 是第一个 `HostClient` 会附带 `x-session-token`
  的 Rust 发行版，所以对更旧的 SDK，这个错误会被换成每一次 host 调用上的
  `unauthenticated` —— 见下面一节。

`doctor` 和 `check` 都不会提到这些，因为它们读取的都是 `plugin.toml`，而版本
固定值存在于该语言自己的构建文件中。

## 插件无法启动

**`Could not read /…/astra/daemon.token. Astra does not look like it is running — start the app first.`**
就是字面意思。`dev`、`logs` 以及安装都需要一个正在运行的 Astra；
`new`、`build`、`check`、`test`、`sign` 和 `publish` 则不需要。如果
Astra*确实*在运行，那就是它解析出的配置目录和 CLI 解析出的不一样 ——
把 `doctor` 打印出的路径和 Astra 设置里显示的路径对比一下。

**守护进程在启动时就把这个进程回收了。** 预算是
`plugin_start_timeout_secs` = **20 秒**，到第一行输出为止。一个在
模块作用域就导入了庞大 ML 技术栈的 Python 插件有可能超出这个时间；
请把导入延迟到真正需要它的那个钩子内部。`astra-plugin test` 会测量
这个时间并打印出具体数字：

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
```

**插件启动后立刻就死了。** 先看看 `astra-plugin logs -f`；如果那里
完全空空如也，说明这个进程是在 SDK 安装好它自己的日志机制之前就失败
了。手动运行这个二进制文件 —— `astra-plugin dev --standalone` 会这样
做，并且告诉你用那种方式做不到什么。

**`HealthCheck` 出错会把插件标记为已死亡。** 它每 15 秒运行一次，而且
没有经过守护进程的可选钩子辅助函数路由：*任何*错误，包括
`UNIMPLEMENTED`，都意味着已死亡。如果你重写了 `health_check`，请确保
它绝不会抛出异常。

## Host 调用返回 `permission_denied`

这条消息会点名是哪个权限，以及被授予的权限集合是从哪里来的。按可能性
从高到低排列，有三个原因：

1. **你没有声明它。** `[permissions]` 是默认拒绝的。声明
   `[capabilities] event_handlers = true` 换不来 `SubscribeEvents`；
   `[permissions] subscribe_events` 才可以。
2. **用户没有授予它**，或者安装路径给它设了上限。一个
   [本地导入的文件](../5-publish/local-install.md) 会直接拒绝
   `send_chat_message`、`set_theme_contribution`、`dom_access` 和
   `client`。
3. **你处于登出状态，或者应用被锁定了。** Astra 在这两种状态下都会
   拒绝插件的 RPC 调用，CLI 也会这样说明："Astra refuses plugin RPCs
   while signed out or locked — sign in and unlock the app, then try
   again."

`astra-plugin doctor` 不需要运行任何东西就能回答第 1 种情况：

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Host 调用返回 `unauthenticated`

除 `Register` 之外的每一次 `PluginHostService` 调用，都必须在
`x-session-token` 中携带会话令牌。全部三个 SDK 都会附带它 —— **Rust
从 0.6 起，Python 和 TypeScript 从 0.5 起**。对更旧的 SDK，每一次
host 调用都会以这种方式失败，这也是为什么脚手架的依赖下限不会设得
更低。

`astra-plugin test` 会端到端地断言这一点：

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`
```

## 侧载(sideload)被拒绝

**`Sideloading is disabled.`** `safety.allow_unsigned_plugins` 是
关闭的。在打开它之前，请先阅读
[打开它要付出什么代价](../5-publish/sideload.md)。

**`Refusing sideload marker in …: this daemon never authorised a sideload of …`**
有人手动放置了一个 `sideload.json`。自从守护进程开始自己保存它所授权
过的记录之后，这种方式就一直不管用了。请使用 `astra-plugin dev`。

## 安装被拒绝

在注册表这条路径上，每一次验证失败都是一次**没有覆盖(override)余地
的硬性拦截**，而且每一种都会点名到底是下面两件事中的哪一件发生了。

| 你看到的 | 意味着什么 |
|---|---|
| 下载的文件和注册表所签署的内容不一致 | `DIGEST_MISMATCH` —— 下载内容已被丢弃。请报告这个问题 |
| Astra 无法验证插件目录(catalogue)的签名 | `SIGNATURE_INVALID` —— 商店会被禁用，而不是退回到使用未经验证的数据 |
| 这次更新来自和你安装时不同的仓库 | `IDENTITY_CHANGED` —— 永远没有覆盖(override)选项。只有卸载才能清除这个锁定 |
| 该插件已被撤回 | `REVOKED` —— 附带公告和一键卸载。文件从不会被静默删除 |
| 这个包是给另一个平台用的 | `PLATFORM_UNSUPPORTED` |
| 这个插件需要更新版本的 Astra | `PROTOCOL_UNSUPPORTED` |
| 网络问题，或者你的系统时钟不准 | 可重试，并且措辞会体现这一点。这些绝不应该看起来像是一次验证失败 |

对本地文件出现 **`nothing here vouches for these bytes`**：请改为
从 Plugins 页面安装，或阅读[本地安装](../5-publish/local-install.md)
了解导入它要付出什么代价。

今天，信任链恰好锚定得**短了一环**：根密钥已经存在，委托了索引签名
密钥的、经根签名的 `trust.json` 现在也已经存在，但
`registry/v1/index.json` 和 `revocations.json` 依然携带
`"signatures": []`。目录上没有签名，被委托的密钥就没有什么可以核对
的，所以一个目录会被归类为未签名，失效机制也不会被强制执行。参见
[`spec/registry-index.md` §0.1](../spec/registry-index.md)。

## 一次工具调用以模型无法自行解决的方式失败

请使用正确的代码；那才是模型会去读的东西。

| 代码 | 什么时候用它 |
|---|---|
| `BAD_ARGUMENTS` | 换一组参数重试有可能成功的时候 |
| `NOT_CONFIGURED` | 缺少某项设置的时候 —— **并且设置 `config_field`**，正是它把这个错误变成了指向那个具体输入项的链接 |
| `UNAUTHORIZED` | 某个值确实存在，但被拒绝了。这和 `NOT_CONFIGURED` 不同 |
| `RATE_LIMITED` | 当上游给出了重试时间时，附带 `retry_after_ms` |
| `UNAVAILABLE` / `TIMEOUT` | 临时性的。稍后再发起同样的调用可能会成功 |
| `INTERNAL` | 一个 bug。模型对此无能为力 |

`UNIMPLEMENTED` **不是**一个错误：它意味着"这个钩子不存在"，守护进程
也是这样理解它的。因为你的 TTS 崩溃了就返回它，会让守护进程相信你根本
没有 TTS。完整的分类见
[`reference/errors.md`](../reference/errors.md)。

## `astra-plugin check` 报错

**`config.schema is not valid JSON`** 或者
**`should have "type": "object" at root`** —— 设置表单就是从这份
schema 生成出来的。

**`[capabilities]` 中出现未知的键会让整个清单文件失败。** 这个段是
唯一一个未知键会被拒绝的地方，因为其中每个键都是一个可选开启的布尔值，
否则一个拼写错误看起来会和 `false` 一模一样。`ui_panels` 就是典型
案例：正确名字是 `ui_contributions`，有三个已发布的示例因为这个错误，
好几个月里都什么能力也没声明成功。

**`[permissions]` 中未知的 id 会被保留并发出警告**，而不是被拒绝 ——
新的 id 会随新版本的 Astra 一起出现，而 permissions 这个段是由三种
实现逐字节哈希的，所以丢弃一个键会让它们对"到底签的是什么"产生分歧。

`astra-plugin check --fix` 会应用它能证明的修正，其余的会报告出来。

## CLI 没有打印出任何有用的信息

`RUST_LOG` 现在是能用的 —— 它从 0.1 版本起就有文档，但在安装订阅者
(subscriber)之前一直不起作用：

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

跟踪日志会输出到 **stderr**，所以 stdout 上的 `--json` 依然保持为
一份干净的单一文档。

## 退出码

| | |
|---|---|
| `0` | 成功 |
| `1` | 插件或包有问题 |
| `2` | CLI 无法运行这项检查 —— 比如文件缺失、工具链缺失 |

这个区分是有实际意义的：一个把"这个包坏了"和"我根本没法查看"一视同仁
的发布工作流，注定会误报其中的一种情况。

## 还是卡住了

- [日志](logs.md) —— 各操作系统下它们的位置
- [性能](performance.md) —— 各种超时以及它们背后的数字
- [示例](../7-examples/README.md) —— 十一个可运行的插件，其中好几个
  正好行使了你正在调试的那条路径
