> **本文档为翻译版本。** 权威来源是 [docs/en](../en/publishing.md)。如与英文版有出入，以英文版为准。

# 发布插件

**一页讲完：从空目录到用户可以安装的插件。** 每一条命令都按顺序列在这里，并附带
它产生的输出。如果关于发布你只打算读一页，就读这一页；更深入的页面会在相关处
链接，但完成本页并不需要读它们中的任何一个。

---

## 哪怕别的都不看，也请看这一部分

向 Astra 发布一个插件意味着**一件具体的事**：你在自己的 GitHub 仓库里给一次
发布打上标签(tag),GitHub 的 CI 构建这个包并出具证明(attest),然后你向注册表
发送一次上架申请 —— 仅此一次，永远只有这一次。

以下这些**不是**发布，而且每一种都有人真的试过：

| 不是发布的方式 | 为什么行不通 |
|---|---|
| 把源码推送到 GitHub | 注册表从不读取你的源码树。它读取的是附加在某个 release 上的 `.astraplugin` 文件，而这个文件并不存在 |
| 把一个 `.zip`，或者你在自己笔记本上构建出的包发给别人 | 这些字节没有构建证明，不管插件本身写得多好，注册表都会拒绝 |
| 开一个 issue，请维护者替你构建 | 除了你自己仓库的 CI，没有人会构建你的插件。不存在别的构建者 |
| 绕开上架表单，在注册表上开一个描述你插件的 issue | 只有表单会打上 `listing` 标签，也只有这个标签会启动摄入。空白 issue 在那边现在已经关掉了，没有标签的申请得到的是一条点名该标签的回复而不是沉默 —— 但回复不等于上架。参见[提交](#8-一次性提交仅此一次) |

**为什么必须如此，用两句话说清楚。** 注册表用用户即将下载的那份确切文件的
SHA-256 来固定你的插件，并读取 GitHub 的构建证明 —— 一个由工作流自身的 OIDC
身份签发的 Sigstore 签名 —— 它声明了正是这些字节，出自那个工作流、那个 commit、
那个仓库。你在自己笔记本上构建后交给别人的文件，这两样都没有，所以在用户机器上
Astra 没有可以核对的东西，注册表也没有可以固定的东西。

这些都不是在断言你的代码是安全的。参见本页末尾的
[信任由什么建立](#信任由什么建立)。

---

## 开始之前

<!-- doctest: cli -->
```bash
astra-plugin --version
```

如果什么都没打印出来，先停在这里，去做 **[安装 CLI](install-cli.md)**。那只是
一行 `cargo install`，但需要 Rust 工具链，而且目前还没有预编译二进制文件 ——
那一页把这一点讲得很清楚，也告诉你该装什么。

> **请使用 `0.2.1` 或更新版本。** `0.2.0` 写出的发布工作流会在你推送第一个标签
> 的那一刻就被 GitHub 拒绝，所以 `0.2.0` 的构建无法完成本页的流程。如果
> `--version` 显示 `0.2.0`，请先重新运行
> [安装 CLI](install-cli.md) 中的 `cargo install` 命令，再继续往下走。

你还需要一个**公开的** GitHub 仓库。构建证明会发布到一个公开的透明日志
(transparency log)中；在私有仓库上需要 GitHub Enterprise，发布工作流会明确
告诉你这一点，而不是悄悄产出没有证明的包。

---

## 1 · 生成脚手架

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

`--lang python` 和 `--lang typescript` 会为另外两个 SDK 生成脚手架；`--template`
决定你从哪个模板起步(`tool`、`tts`、`stt`、`stt-streaming`、`ai-provider`、
`ui`、`action-trigger`、`client`、`blank`)。编写插件本身的内容在
[快速上手](2-tutorial/getting-started.md) 和 [各 SDK 页面](4-sdk/rust.md)。

**在继续之前，先填好 `plugin.toml` 里的两个字段。** 脚手架生成时 `author` 是
空的，`description` 是通用文案，而这两者都会显示在你的商店卡片上：

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

脚手架生成的 `icon.svg` 只是占位图；替换方式见
[申请上架 §你的上架条目会是什么样子](5-publish/get-listed.md#你的上架条目会是什么样子)。

## 2 · 证明它能跑起来

<!-- doctest: cli -->
```bash
astra-plugin test .
```

这是一套一致性(conformance)测试，会把你的插件当作**真实进程**运行，并让它与一个
模拟守护进程对话 —— 而不是针对你测试文件里的某个类型运行。截取结论部分：

<!-- doctest: output from="astra-plugin test ." -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

要在真正运行中的 Astra 里驱动它，用 `astra-plugin dev .` —— 那就是
[侧载(sideload)](5-publish/sideload.md)，是开发时的循环手段，**不是**把插件
交给别人的方式。

## 3 · 设置发布工作流

你不需要自己写任何 YAML。一条命令搞定：

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

这个 commit SHA 不是装饰。它就是已发布的可复用工作流 `plugin-release/v1`
所指向的目标，也是注册表经根签名的 `trust.json` 所允许的 SHA 之一 —— 由任何
其他工作流产出的构建都会被以 `E_WORKFLOW_NOT_ALLOWED` 拒绝。想推进这个固定值，
随时可以重新运行 `init-ci`；它会保留你已设置的输入值。

**在继续之前，检查它打印出的 SHA。** 它必须是
`e3329df252a46d747676cb540ae4b986af68a3ad`。如果是
`dc1a044876926e9cf1170f034e2eab533ec07641`，说明你用的是 CLI `0.2.0`：那是
*标签对象(tag object)*的 SHA，而 `uses: …@<sha>` 需要的是 commit，所以你的第
一次 `git push --tags` 会在任何 job 启动之前就以 `invalid value workflow reference`
失败。重新运行 [安装 CLI](install-cli.md) 中的 `cargo install` 命令，然后再次
运行 `astra-plugin init-ci` —— 它会重写固定值并保留你的输入。它不会就地修复
文件，所以已存在的 `release.yml` 在你重新运行之前会一直带着错误的 SHA。这正是
让一位真实作者的第一次发布失败的那个 bug。

关于生成文件的内容，以及它的三项权限各自为何必要的详细说明，见
[用 CI 发布](5-publish/release-with-ci.md)。

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` 会应用一切可以机械修复的内容。`--resolve-pin` 会向 GitHub 询问你的
工作流固定值是否仍是最新的；它默认关闭，这样 `dev` 和 CI 运行一次检查都不需要
联网。

## 4 · 推送它，公开地

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

这一步没有任何特别之处 —— 就是一个普通仓库。但请注意它*不是*什么：推送它并
不是发布这个插件，而止步于此正是促成本页出现的那两次真实提交出错的地方。真正
让它成为已发布插件的，是下一步的标签(tag)。

## 5 · 打标签 —— 这才是发布

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

`astra-plugin version` 会在一次编辑中同时重写 `plugin.toml` **以及**项目中
其他所有清单文件 —— `Cargo.toml`、`package.json`、`pyproject.toml` —— 所以
它们不会互相矛盾。除非你传入 `--allow-downgrade`，否则它会拒绝一个排序低于
当前版本的版本号，因为 Astra 拒绝安装降级版本，那样的发布将无法被安装。

**标签就是整个发布流程。** 推送它会触发你的 `release.yml`，它会调用那个被
固定住的可复用工作流，而后者会运行三个 job —— 一个 `plan` job，把你的清单
当作数据来读取，绝不运行你的代码；一个 `build` 矩阵，运行你的代码，但不持有
任何写入令牌；以及一个 `publish` job，它自己重新推导每一个摘要，并对自己
哈希过的内容出具证明。这种拆分正是安全属性所在，详见
[用 CI 发布 §3](5-publish/release-with-ci.md#3-ci-做了什么)。

完成后，你的 GitHub Release 会带有：

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

只有当所有资产都已附加后，这个 Release 才会变为可见。Rust 插件每个平台一个
文件；TypeScript 和 Python 是单一的 `noarch` 文件。

**如果工作流根本没有运行**，常见原因是 `on: push: tags:` 与 `tag-prefix:`
互相矛盾 —— 一个比前缀更窄的 glob 永远不会触发。其余的失败模式见
[用 CI 发布 §常见问题](5-publish/release-with-ci.md#常见问题)。

## 6 · 自己核实这次发布

任何人都可以做到，无需信任 Astra 或注册表：

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

当包本身有问题时，`astra-plugin verify` 以 **1** 退出；当 CLI 无法给出答案
时（比如文件缺失），以 **2** 退出。归档格式以及校验器必须拒绝的内容见
[`spec/bundle-v2.md`](spec/bundle-v2.md)。

## 7 · 对上架申请做预检

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

它会运行所有能在本地执行的注册表检查，然后 —— 这是更重要的一半 —— 指名
那些只有注册表才能运行的检查项，让你知道还有什么尚未得到验证：

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that you have admin or maintain on the repository
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

## 8 · 一次性提交，仅此一次

<!-- doctest: cli -->
```bash
astra-plugin publish
```

它会在你的浏览器中打开一个**已预填内容的 issue**，位于注册表仓库上。它不上传
任何东西，也不持有任何凭证 —— 没有 `astra-plugin login`，你的 shell 历史里
不会留下 token，也没有需要对接的密钥环(keyring)。`--print-url` 会打印链接，
而不是打开浏览器：

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **请使用那条链接。** 其中的 `template=plugin-listing.yml` 承担着关键作用：
> 这个 issue 模板声明了 `labels: ["listing", "needs-triage"]`，而注册表的
> bot 只会对带有 `listing` 标签的 issue 进入提交处理路径。别的东西都不会打上
> 这个标签 —— bot 自己也不会，而且这是刻意的：在那个仓库里，这个标签是一枚
> 权限令牌，而不是一个分类。
>
> 以前这会静悄悄地失败。一位真实作者的两份申请到达时不带任何标签，分诊返回
> `mode: "none"`，检查、发布、评论这几步全部被跳过，**他什么都没得到，连一个
> 拒绝的回应都没有** —— 这正是这一页存在的原因。现在两边都堵上了：注册表关掉了
> 空白 issue，所以表单是唯一的入口；而万一还是有没带标签的申请进来，它会收到
> 一条评论，点名那个标签，以及在同一个 issue 上启动验证所需的那一次点击。
> 但还是请用这条链接：它是那条不需要任何人介入就能开始摄入的路径。

这次提交只携带**两个事实**：你的源码仓库(`you/dice-roller`)和发布标签
(`v0.1.0`),外加两项确认 —— 你拥有或维护着该仓库，以及你已经读过政策。其余
的一切都从已获证明的包中读取，因为包里的每一样东西都在证明范围内，因而其
可信度严格高于任何填进表单里的内容。

## 9 · 接下来会发生什么

详细内容以及每一个原因代码，见
[申请上架 §提交之后会发生什么](5-publish/get-listed.md#3-提交之后会发生什么)。
简版如下：

| 结果 | 含义 | 涉及谁 |
|---|---|---|
| **已发布(Published)** | 已提交，会出现在下一次索引构建中的目录里 | 不涉及任何人 |
| **延迟(Delayed)** | 一切都通过了；会在指定时间自动发布 | 不涉及任何人 |
| **保留(Held)** | 这是注册表无权自动做出的决定 | 由一位维护者在 **48 小时**内处理 |
| **拒绝(Refused)** | 某项检查失败了 | 由你：修复它，并在 issue 上评论 `/recheck` |

**首次上架总是会被保留给人来判断** —— 这是恰好需要人工介入的三种事件之一，
另外两种是新申请的高风险权限，以及仓库变更。48 小时是这三种情况共同公布的
SLA。

保留状态由维护者在你的 issue 上评论 `/approve` 来解除，这会从头重新运行
所有检查，而不是信任任何缓存的结果。你不需要输入那条命令，等待期间也不需要
做任何事。参见
[保留状态如何被解除](5-publish/get-listed.md#保留状态如何被解除)。

无论结果如何，bot 都会在你的 issue 上评论结果和原因 —— 而且现在，即使它*不会*
开工，也就是第 8 步描述的那种失败，它同样会评论。如果一小时后仍然没有任何评论，
检查 `listing` 标签。如果没有，请维护者加上：打标签会触发与新提交相同的事件，
所以验证会在同一个 issue 上开始，你不需要重新输入任何东西。

## 10 · 此后的每一次发布

什么都不用做。打标签，剩下的交给 CI；注册表会注意到这次发布并重新生成索引。

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

如果几分钟后注册表还没有注意到：

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

这是给**已经上架**的插件用的手动 ping。不加 `--notify` 的话，`publish` 会
改为打开一个首次上架申请，而这不是你在第二次发布时想要的结果。

---

## 信任由什么建立

`astra-plugin build` 链接到这里，所以在这条链接改变之前，答案就放在这个锚点上。

**不是你手上的任何密钥。** `astra-plugin keygen` 和 `astra-plugin sign` 产出
的是一个可选的第二重身份因子 —— 对防范 GitHub 账号被盗很有用，因为这个密钥
存放在被盗的 GitHub 会话触及不到的地方。Astra 并不会拿它去校验你的密钥：
守护进程校验的是 ZIP 内的 `SIGNATURE`/`PUBKEY` 对，比对的是一个*固定的 Astra
发布者密钥*，所以用你自己的密钥签过名的包，其不受信任的程度和未签名的包
完全一样。这个命令，以及它写入的格式条目，都正在被逐步淘汰。

**Astra 真正依据的**，是一条对整份文件的 SHA-256 进行反签名(countersign)的
注册表记录，以及 —— 在摄入(ingest)时由注册表 bot 校验，而不是由守护进程校验
的 —— GitHub 的构建证明，说明是哪个工作流、在哪个 commit、在哪个仓库产出
了这些字节。

**如今这条信任链锚定到了多远。** 根密钥双方都存在：
`astra-registry/registry/v1/root.json` 携带 `"status": "provisioned"` 和
两个 Ed25519 密钥，守护进程内编译进的 `PRODUCTION_ROOT_KEYS` 也是同样的两个。
`registry/v1/trust.json` 现在由 `astra-root-2026a` 签名，并委托给一个索引
签名密钥 `astra-index-2026a` —— 这已用注册表自己的
`node tools/sign-trust.mjs --verify registry/v1/trust.json` 验证过，该命令
同时也会打印出 bot 在证明中会接受的唯一一个可复用工作流 SHA
(`e3329df252a46d747676cb540ae4b986af68a3ad`，即 `plugin-release/v1` 所指向
的那个 commit)。**仍然缺失的一环是目录本身的签名：**`registry/v1/index.json`
和 `revocations.json` 携带的都是 `"signatures": []`，因此默认的 Astra 构建
没有任何东西可以核对，会把所有目录都归类为未签名。这里没有对任何尚未落地的
保证做出承诺；参见 [安全模型](1-orientation/security.md) 与
[`spec/registry-index.md` §0.1](spec/registry-index.md)。

**这一切都没有说代码是安全的。** 插件是一个拥有你完整用户权限的原生进程，
没有沙箱。上架不是安全审查 —— 没有人会去读你的代码，注册表自己的政策也是
这么说的。

---

## 插件到达一台机器的另外两种方式

两者都面向开发者，两者都有代价，而且**都不是发布**：

- [安装本地 `.astraplugin` 文件](5-publish/local-install.md) —— 一个通过
  带外方式送达的包。不管清单里申请了什么，四种权限都会被直接拒绝。
- [侧载(sideload)一个源码目录](5-publish/sideload.md) —— 开发时的循环手段。
  需要开发者模式，会以你的完整用户账户运行未签名代码，且永远不会自动启动。

## 另请参阅

- [安装 CLI](install-cli.md) —— 本页所有命令的出处
- [用 CI 发布](5-publish/release-with-ci.md) —— 完整的工作流细节
- [申请上架](5-publish/get-listed.md) —— 提交流程及其后续
- [版本管理](versioning.md) —— 数字的含义，以及一次弃用会持续多久
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)
