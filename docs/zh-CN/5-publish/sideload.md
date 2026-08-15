> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/5-publish/sideload.md)。如与英文版有出入，以英文版为准。

# 侧载（sideload）—— 一个开发工具

> **这不是插件安装的方式。** 侧载会把 Astra 指向你磁盘上的一个源码
> 目录，并以未签名的方式，用你完整用户账户的权限，把它当作原生进程
> 运行起来。它存在的目的是让你能够开发一个插件。它藏在一个需要显式
> 开启的选项背后，而这个开关会降低这台机器上**每一个**插件的门槛，
> 不只是你的那一个。
>
> 用户从 Astra 内部安装插件。作者通过
> [`init-ci` 加上一个标签](release-with-ci.md) 来发布，然后
> [一次性申请上架](get-listed.md) —— [完整流程一页讲完](../publishing.md)。
>
> 让别人克隆你的仓库然后侧载它，不是发布。这是在请求对方以自己的身份
> 运行未签名的代码，而它能触及到的，也正好只是你能直接联系上的那些人。

永远不要侧载一个你没有写过、也没有审计过的插件。如果有人给你发来一个
目录，并指导你打开开发者模式，那就是在请求你以自己的身份运行他们的
代码。

## 打开它

除非 `safety.allow_unsigned_plugins` 为 true，否则侧载会被拒绝。
守护进程会原原本本地这样说：

<!-- doctest: illustrative reason="the daemon's refusal, quoted from astra-daemon/src/plugins/manager.rs; reproducing it needs a running Astra with the setting off" -->
```
Sideloading is disabled. It runs an unsigned local plugin as native code with
your full privileges. Turn on Settings -> Privacy -> "Allow unsigned plugins"
(`safety.allow_unsigned_plugins`) to sideload (local plugin development only).
```

CLI 会把它转换成同样的指示，并把修复方法单独放在一行
（`astra-plugin-cli/src/daemon.rs`）。这两条消息给出的设置分区名字
不一样 —— 守护进程说的是 Privacy，CLI 说的是 Safety。**设置项的键名
是 `safety.allow_unsigned_plugins`**，这才是你该搜索的东西。

## 使用它

来自 [CLI](../install-cli.md) 的一条命令：

<!-- doctest: cli -->
```bash
astra-plugin dev
astra-plugin dev . --daemon-addr 127.0.0.1:32000
```

`dev` 会按顺序做四件事，遇到第一个失败就停下：

1. `astra-plugin check --strict` —— 它不会把一份本身就已经有问题的
   清单文件交给守护进程；
2. 构建；
3. 通过 `SideloadPlugin` 把**目录**交给守护进程，由守护进程 spawn 这个
   进程、铸造它的认证令牌，并从此掌管它的生命周期；
4. 监视变更、重新构建、停止/启动插件，并持续输出它的日志。

<!-- doctest: output from="astra-plugin dev . with no Astra running" unrun="needs a machine with no Astra daemon listening, which a CI runner cannot promise either way" -->
```
Dev mode: plugin 'dice-roller'
  Directory: /tmp/dice-roller
Checking plugin at /tmp/dice-roller...
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 2.48s
Error: Could not read /home/you/.config/astra/daemon.token. Astra does not look
like it is running — start the app first.
```

**进程的所有权归守护进程，这不是一个风格上的选择。** 插件用守护进程
在 spawn 这个进程时铸造出的一个令牌来向 `PluginHostService` 认证，
守护进程会拒绝任何不携带它自己签发的令牌的 `Register`。一个由 CLI
自行 spawn 出来的插件没有办法拿到这样的令牌 —— 这正是它所取代的那个
自我 spawn 的旧版 dev 循环的问题所在：它启动的进程谁都不联系。

`--standalone` 保留了那种旧的行为，用于它依然有用的场合（确认一个
二进制文件能启动、手动驱动它），并且会提前说明，用那种方式插件是无法
向 Astra 注册的。

`dev --json` 被刻意拒绝：`--json` 承诺的是每次运行对应一份文档，而
`dev` 永远不会结束。`astra-plugin check --json`、
`astra-plugin test --json` 和 `astra-plugin logs --json` 才是它所做
的事情中机器可读的那一半。

## 侧载的确切代价

| | |
|---|---|
| **签名** | 没有。没有任何东西为这段代码背书 |
| **权限** | 你完整的用户账户权限。没有沙箱 —— [第 7 阶段并不存在](../1-orientation/security.md) |
| **这个开关的波及范围** | `allow_unsigned_plugins` 适用于这台机器上的每一个插件，包括你之后再导入的未签名文件 |
| **自动启动** | **绝不会。** 开发者模式在加载时是必需的，重启之后一个被侧载的插件会保持停止状态，直到你再次启动它 |
| **权限上限** | **没有** —— 见下文 |
| **展示给用户的溯源信息** | 溯源面板中的层级为 `sideloaded` —— "从一个文件夹加载" |

### 为什么这里没有权限上限

一个[本地导入的 `.astraplugin`](local-install.md) 会有四种权限被直接
拒绝。一个被侧载的**源码目录**则不会，这个例外是刻意为之，而不是
疏漏：这是 UI 插件的创作循环，`dom_access` 正是 `companion`、
`doom` 和 `bad-apple` 所需要的东西。给第 3 层级设上限，会让这些插件
变得无法开发。

代价在于，第 3 层级被锁在一个需要显式开启的设置背后，永远不会自动
启动，而且是你亲自指向的一个目录 —— 这三个事实，是第 2 层级（一个从
某处送达的文件）都无法宣称的。

计划中还要求，只要 `dom_access` 处于生效状态，就应该在插件卡片和窗口
的边框上显示一个永久的、无法关闭的"DEVELOPER — unverified code from a
local directory"（开发者 —— 来自本地目录的未验证代码）徽章。**这个
徽章今天在 UI 中并不存在**，本页也没有声称它存在。

## 不能用、以后也不会好用的方式

**手动往插件目录里写一个 `sideload.json` 标记文件。** 守护进程会拒绝
一个它没有授权记录的标记：

<!-- doctest: illustrative reason="a daemon log line, quoted from astra-daemon/src/plugins/manager.rs; it is emitted on a machine with a planted marker" -->
```
Refusing sideload marker in <path>: this daemon never authorised a sideload of
'<id>' from <source> (no matching record in <registry path>). A marker file
alone does not authorise running unsigned native code.
```

旧的说明曾告诉作者把标记放进
`~/.config/astra/astra/plugins` —— 这是一个根本不存在的路径，用在一个
早已失效的机制之上，而且完全没有提到 `allow_unsigned_plugins` 这个
前提条件。这些说明已经被删除，而不是被修正。替代方案只有一行：
`astra-plugin dev`。

## 开发完成之后

这条路径不会产出任何别人能够安装的东西。要真正出货：

1. [`astra-plugin init-ci`](release-with-ci.md)，然后打标签 —— CI 会
   构建并出具证明；
2. [`astra-plugin publish`](get-listed.md) —— 一次性的，永远只有这
   一次；
3. 用户从 Astra 内部安装它，摘要值会被固定。

不开发的时候把 `allow_unsigned_plugins` 重新关掉，值得多点这两下。
