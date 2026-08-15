> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/1-orientation/security.md)。如与英文版有出入，以英文版为准。

# 安全模型

在你发布任何东西之前，在你安装任何东西之前，请先读这一页。

## 一句话概括

**插件是一个以你完整用户账户权限运行的原生进程。** 它可以读取你的文件、
打开套接字、启动程序。Astra 中没有任何东西会在操作系统层面对它进行沙箱化、
隔离或限制。

这不是本页在轻描淡写的一个漏洞 —— 这就是现状的设计本身。隔离是生产计划中
的**第 7 阶段**，之所以在那里被指名，是为了表明这是一个决定而不是遗漏，
而且它**尚未实现**。将来可能的候选方案：Linux 上的 Landlock + seccomp、
Windows 上的低完整性令牌或 AppContainer、rlimits。在那之前，"已签名"和
"已上架"都无法说明这个进程能对你的机器做什么。

在任何 Astra 可能暗示相反含义的地方，它都*必须*把这句话明说出来 ——
安装同意页面和溯源(provenance)面板都带有一个固定不变的说明区块，声明
构建证明并不证明代码是安全的。守护进程在拒绝一次未验证的安装时，给出的
消息里已经这么说了："插件是以你的完整权限运行的原生进程，所以一个未经
验证的插件可能会接管你的机器"（`astra-daemon/src/plugins/manager.rs`）。
应用自身的界面长什么样，是 Astra 需要去记录的事，不属于本仓库的范畴；
本页描述的是守护进程、CLI 和各种格式。

## 每种机制实际回答的问题

四个层次，四个不同的问题。把它们混为一谈，正是"它是签名的"变成"它是
安全的"的原因。

| 层次 | 机制 | 由谁验证 | 回答什么 |
|---|---|---|---|
| 1. 构建溯源 | GitHub 构件证明（Sigstore 无密钥模式、OIDC） | 注册表 bot，在 CI 中 | "这些字节来自仓库 R 中提交 C 处的工作流 W" |
| 2. 分发信任 | 在一份已签名索引中，对构件摘要的 Ed25519 反签名 | 守护进程，离线完成 | "Astra 确实上架了正是这些字节，且未被撤回" |
| 3. 身份连续性 | 对 `github:owner/repo` 的 TOFU（首次使用即信任）锁定 | 守护进程，离线完成 | "这次更新和安装时是同一个作者" |
| 4. 运行时授权 | 每次 host RPC 调用时的 `[permissions]` + `require_permission` | 守护进程，每次调用时 | "这个插件可以请求 Astra 做什么" |

它们都没有回答"这段代码是否安全"这个问题。这个问题没有机械化的答案，
一个暗示自己能回答的系统，比一个坦承自己回答不了的系统更糟糕。

## 两件今天成立、且不会被淡化的事实

### 信任链已经规范化并实现，但恰好短了一环

根密钥(root key)已经存在，它们之下的委托关系现在也存在了。**不存在的
是目录本身的签名**，所以在用户的机器上什么都验证不了。具体来说
（[`spec/registry-index.md` §0.1](../spec/registry-index.md)）：

- 注册表的 `root.json` 携带 `"status": "provisioned"`，以及两个在
  2026-08-11 通过一次离线仪式生成的 Ed25519 密钥；
- 守护进程的 `PRODUCTION_ROOT_KEYS` 列出了同样的两个 —— 这个文件之所以
  存在，是为了让第三方无需反汇编二进制文件就能读到这些密钥，也是为了让
  两边一旦不一致就能被察觉；
- 根密钥并不直接给目录签名：它给 `trust.json` 签名，而后者委托给一个
  索引签名密钥。**那份文档现在已经签好了。** `registry/v1/trust.json`
  能在 `astra-root-2026a` 下通过验证，委托给 `astra-index-2026a`，并且
  指名了注册表 bot 在构建证明中会接受的唯一那个可复用工作流提交。注册表
  自己的 `node tools/sign-trust.mjs --verify registry/v1/trust.json`
  会把这一切都打印出来。所以摄入端(ingest)的拦截 `E_TRUST_UNPROVISIONED`
  已经不再触发了；
- **但 `registry/v1/index.json` 依然携带 `"signatures": []`**，
  `revocations.json` 也是如此。目录上没有签名，被委托的密钥就没有可以
  校验的东西，每个目录依然会被归类为 `UNSIGNED` —— 但理由是
  **`NoSignatures`** 而不是 `NoTrustAnchor`：信任锚到位了，签名没有。
  `NoTrustAnchor` 是更早、更糟的情况，意思是根本没有任何经过验证的
  `trust.json` 到达这个构建；
- 而由于撤回列表(withdrawal list)是被严格校验的，一份未签名的撤回列表
  会被拒绝，所以**失效强制机制也同样没有生效**。

因此，一次默认构建依然会安全失败(fail closed)。这里没有对你今天已经
拥有的保证做出任何承诺；这套机制真正开始对用户产生分量，是从一份已签名的
索引存在的那一刻起，而不是更早。

### 本地签名密钥不赋予任何信任

`astra-plugin keygen` 和 `astra-plugin sign` 确实存在。它们是一个可选的
第二重因子 —— 用来纵深防御 GitHub 账号被接管的情形，其价值在于这个密钥
存放在一个被盗的 GitHub 会话触及不到的地方。

它们**不是**让 Astra 决定安装一个插件的依据，用你自己的密钥签过名的包，
其不受信任的程度和一个未签名的包完全一样。守护进程校验的是 ZIP 内的
`SIGNATURE`/`PUBKEY` 对，比对的是一个*固定的 Astra 发布者密钥*，而不是
压缩包内自带的那个密钥。`astra-plugin build` 每次运行都会这么说：

<!-- doctest: output from="astra-plugin build ." -->
```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
```

`astra-plugin sign` 在成功时也会这么说，而且是故意不藏在 `--help` 里的：

<!-- doctest: output from="astra-plugin sign <bundle>" -->
```
This signature is an optional second factor, not a trust signal.

Astra does not verify it against your key — the daemon checks the in-ZIP pair against a
pinned Astra publisher key, so a bundle signed with your own key is untrusted by
construction, exactly as an unsigned one is.
```

ZIP 内的这对签名是一个正在被淘汰的格式特性；这个命令以及它写入的条目，
都已经在被移除的计划之列。

不存在 `astra-plugin login`，以后也不会有：发布携带的是一个仓库和一个
标签，所以没有需要存储的凭证，也就没有可以泄露的凭证。

## 权限门(permission gate)做的事

守护进程只在一个地方强制执行 `[permissions]`：`require_permission`，
作用于 `PluginHostService` 十个 RPC 中的六个。另外四个 —— `Register`、
`GetPluginSelfConfig`、`PluginLog` 和 `GetDaemonInfo` —— **永远被
允许**，完全不做任何权限检查；在守护进程的 `HOST_RPC_PERMISSIONS`
表里它们对应 `(…, None)`，它们的函数体里也没有 `require_permission`
调用。一个 `[permissions]` 段为空的已注册插件，能够到达的就只有这四个，
其他一概不行。这四个为什么是免费的，见
[权限参考](../3-reference/permissions.md#不需要任何权限的四个调用)。
`require_permission` 所读取的那张表 —— 守护进程中的
`HOST_RPC_PERMISSIONS` —— 通过一致性规则 R6 被钉死在
[`spec/hooks.yaml`](../../../spec/hooks.yaml) 上，所以生成出来的
[权限列](../reference/parity.md) 不可能与真正强制执行它的代码产生偏差。

有两道相互独立的关卡，两道都必须通过
（[`spec/permissions.md` §4.2](../spec/permissions.md)）：

1. **授予(grant)** —— 由一次同意页面产生、由一条信任记录持有的、按每次
   安装给出的答案；
2. **上限(ceiling)** —— 一条任何记录都无法买通突破的、按来源而定的规则。

清单文件是一份*申请*。对于第 1、2 层级，被授予的权限集合存放在插件无法
写入的地方，因为一个能够通过编辑自己清单来扩大自己授权的插件，就等于
拥有一套形同虚设的权限系统。

**第 3 层级是例外，而且是刻意如此。** 对于一个侧载(sideload)的源码目录，
守护进程的 `decide_grants` 返回的是 `declared.capped(|_| true)` ——
清单文件本身*就是*同意记录，每次加载时都从插件自己的目录中读取，其上
没有任何上限。因此，一个侧载的插件可以在两次重启之间通过编辑自己的
`plugin.toml` 来扩大自己的权限，直到拥有整个权限词汇表。这也是为什么
开发者模式是一个开发工具，而不是一条安装途径的又一个原因。

有五种权限被列为高风险，各自都有独立的同意勾选框：`send_chat_message`、
`push_to_ui`、`set_theme_contribution`、`dom_access`、`client`。
`dom_access` 还会额外出现第二个界面。更多细节，包括如何写一段值得
让人读下去的 `reason`：见
[权限](../3-reference/permissions.md)。

## 插件的来源决定它的权限上限

| 层级 | 来源 | 上限 |
|---|---|---|
| **1 · 注册表** | 从商店安装，已验证 | 它所申请的一切，取决于用户同意。验证失败时没有覆盖(override)的余地 |
| **2 · 本地文件** | 手动导入的 `.astraplugin` | `send_chat_message`、`set_theme_contribution`、`dom_access` 和 `client` 会被**直接拒绝，而不只是给出警告** |
| **3 · 侧载(sideload)** | 一个源码目录，开发者模式开启 | **没有上限** —— 而且永远不会自动启动 |

第 3 层级刻意不设上限：它是 UI 插件的开发创作循环，如果设了上限就会让
`dom_access` 无法开发。它同时也被锁在一个需要显式开启的设置背后，重启后
永远不会自行启动，并且被
[记录为一个开发工具](../5-publish/sideload.md)，而不是一种安装方式。

无论清单文件怎么说，有四种状态**什么都得不到**：`Untrusted`、
`TamperDetected`、`Revoked`，以及记录无法被信任的 `Verified` 插件。
在信任记录存在之前就已安装的插件（`Unrecorded`）,其清单会被限制在
第 2 层级的上限之内 —— "从某处来，但什么都没证明"正好就是这种情形。

## 没有防御的部分

明确点名，而不是留给读者自己去发现：

| 威胁 | 状态 |
|---|---|
| 插件读取你的文件、密钥、网络 | **没有防御。** 不存在任何隔离机制 —— 第 7 阶段 |
| 插件读取 `daemon.token` 并以客户端身份注册 | **没有防御。** 原因相同 |
| 一个恶意或被攻陷的注册表提供了不同的字节内容 | *在设计上*是有防御的 —— 索引对摘要进行反签名，守护进程会重新哈希 —— **但尚未生效**：根已经就绪（`registry/v1/root.json`，与编译进守护进程的是同样的两个密钥），但它们所签署的目录索引仍然未签名 |
| 一个已被撤回、但已经装上的版本 | 已有规范；今天尚未强制执行，因为一份未签名的撤回列表会被拒绝 |
| 另一个本地进程调用你插件的能力服务端(capability server) | **有防御。** 守护进程在每次调用时都会出示 spawn token，并设置 `ASTRA_PLUGIN_CAPABILITY_AUTH=require`，所以 SDK 会拒绝没有携带它的调用。在一个老到不会发送这个头的守护进程之下，SDK 会停留在 `warn` 状态 —— 错误的令牌会被拒绝，缺失的令牌会被接受 —— 因为除此之外它也别无办法 |
| 插件编辑自己的清单来扩大自己的权限 | **在第 1、2 层级上有防御** —— 授权来自守护进程持有的信任记录，而不是清单本身。**在第 3 层级上没有防御**：对于一个侧载的目录，清单本身就是授权，且没有上限，所以它可以通过编辑自己的文件获得权限词汇表中的一切 |
| 手动伪造的侧载标记 | 有防御。守护进程会拒绝一个不是自己写下的标记 |

## 给用户的一段话

请从 Astra 内部安装。商店路径以摘要固定构件，验证失败是硬性拦截，没有
覆盖(override)的余地。如果有人给你发了一个 `.astraplugin` 文件，导入
它就是你在对那个人做出的一个判断，无论文件申请了什么，四种权限都会被
拒绝。如果有人让你打开开发者模式并把 Astra 指向某个文件夹，他们其实是在
请求你以自己的身份运行未签名的代码。

## 另请参阅

- [`spec/registry-index.md`](../spec/registry-index.md) —— 规范性地说明文档格式和验证算法
- [`spec/permissions.md`](../spec/permissions.md) —— 授权、上限、同意、`permissions_hash`
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) —— `.astraplugin` 内部有什么，校验器必须拒绝什么
- [故障排查](../6-operate/troubleshooting.md) —— 当你遇到某个验证失败时，它分别意味着什么
