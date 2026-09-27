> **本文档为翻译版本。** 权威来源是 [docs/en](../en/publishing.md)。如与英文版有出入，以英文版为准。

# 发布插件

**一页讲完：从空目录到用户可以安装的插件。** 每一条命令都按顺序列在这里，并附带
它产生的输出。如果关于发布你只打算读一页，就读这一页；更深入的页面会在相关处
链接，但完成本页并不需要读它们中的任何一个。

---

## 哪怕别的都不看，也请看这一部分

向 Astra 发布一个插件意味着**一件具体的事**：你在自己的 GitHub 仓库里给一次
发布打上标签(tag),GitHub 的 CI 构建这个包并出具证明(attest),然后你在面板里
提交一次 —— 仅此一次，永远只有这一次。

以下这些**不是**发布，而且每一种都有人真的试过：

| 不是发布的方式 | 为什么行不通 |
|---|---|
| 把源码推送到 GitHub | 注册表从不读取你的源码树。它读取的是附加在某个 release 上的 `.astraplugin` 文件，而这个文件并不存在 |
| 把一个 `.zip`，或者你在自己笔记本上构建出的包发给别人 | 这些字节没有构建证明，不管插件本身写得多好，注册表都会拒绝 |
| 请维护者替你构建 | 除了你自己仓库的 CI，没有人会构建你的插件。不存在别的构建者 |
| 在面板的提交页面以外的任何地方向注册表描述你的插件 | 注册表只处理在面板里登录后、为绑定到你账户的仓库所做的提交。没有别的入口。参见[提交](#8--一次性提交仅此一次) |

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

如果什么都没打印出来，先停在这里，去做 **[安装 CLI](install-cli.md)**。现在
已经有预编译二进制文件了 —— 下载一个 Linux 或 Windows 的归档文件，用
`SHA256SUMS.txt` 核对一下，完全不涉及工具链。从源码构建依然有效，也是
macOS 和 ARM Linux 上唯一的路。`cargo install astra-plugin-cli` 根本不是
一条路 —— 那一页说明了原因。

> **不要从版本号去判断你这个构建是否健康。** 在提交 `5b8ab22` 之前构建的 CLI
> 会写出一个发布工作流，你推送第一个标签的那一刻它就会被 GitHub 拒绝。这个修复
> 进入 `master` 的时间*早于*版本号提升到 `0.2.1`，所以一个构建可以既带着它又
> 显示 `0.2.0`，而且不存在缺少它的 `0.2.1`。今天从 `master` 安装，无论数字是
> 多少你都会拿到修复。真正能定论的是 `init-ci` 打印出的 SHA，本页会在
> [第 3 步](#3--设置发布工作流)运行它。

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

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
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

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned c3f342469d186ef48458992930bf1b7c583c78d4 (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

这个 commit SHA 不是装饰。它就是已发布的可复用工作流 `plugin-release/v1`
所指向的目标，也是注册表经根签名的 `trust.json` 所允许的 SHA 之一 —— 由任何
其他工作流产出的构建都会被以 `E_WORKFLOW_NOT_ALLOWED` 拒绝。想推进这个固定值，
随时可以重新运行 `init-ci`；它会保留你已设置的输入值。

**在继续之前，检查它打印出的 SHA。** 它必须是 `plugin-release/v1` 今天所指向
的那个 commit，而能回答这一点的只有远端：`git ls-remote
https://github.com/mihailinl/AstraPlugins.git refs/tags/plugin-release/v1
'refs/tags/plugin-release/v1^{}'` —— 两个 refspec 都要问，远端若回了 peel 过的
`^{}` 那一行，就以那一行为准；这正是 `init-ci` 自己问的那一对。如果你的固定值
对不上，就重新运行 [安装 CLI](install-cli.md) 中的 `cargo install` 命令，然后
再次运行 `astra-plugin init-ci` —— 它会重写固定值并保留你的输入。它不会就地修复
文件，所以已存在的 `release.yml` 在你重新运行之前会一直带着过期的 SHA。剩下的
都是历史，而且是有日期的：`plugin-release/v1` 在 2026-08-11 到 2026-08-19 之间
是一个附注标签，早于提交 `5b8ab22` 的 CLI 会在 GitHub 需要 commit 的地方固定住
它的标签对象 `dc1a044876926e9cf1170f034e2eab533ec07641`，那正是让一位真实作者的
第一次发布在任何 job 启动之前就以 `invalid value workflow reference` 失败的那个
bug；今天这个标签是轻量标签，所以再也没有构建会报告那个 SHA 了。

关于生成文件的内容，以及它的三项权限各自为何必要的详细说明，见
[用 CI 发布](5-publish/release-with-ci.md)。

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  REGISTRY WARN: B_UNBOUND predicted once this listing needs a binding: there is no .well-known/astra-plugin-owner at the repository root (working tree). From the registry's cutover every first listing needs one, and every listing after the binding deadline; a release without it is refused B_UNBOUND. Mint a token in the panel and run `astra-plugin init-ci --binding <token>` — https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository
  NOT CHECKED: B_BINDING_UNUSABLE, B_OWNER_CHANGED, B_REPOSITORY_RECYCLED, E_WORKFLOW_NOT_ALLOWED — only the registry can answer these, from the plugins service, GitHub and trust.json
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` 会应用一切可以机械修复的内容。`--resolve-pin` 会向 GitHub 询问你的
工作流固定值是否仍是最新的；它默认关闭，这样 `dev` 和 CI 运行一次检查都不需要
联网。

## 4 · 推送它，公开地 —— 带上所有权文件

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin init-ci --binding <token>
git add .well-known && git commit -m "Bind this repository to my Minice account" && git push
astra-plugin check --strict
```

前三行没有任何特别之处 —— 这就是一个普通的仓库。但要注意它*不是*什么：推送
这个仓库并不是发布插件，而停在这一步，正是促成本页的两次真实提交出错的地方。
让它成为一个已发布插件的，是下一步的标签。

**绑定行就是所有权证明，而且不是可选的。** 在推送和 `init-ci` 之间，用将来
负责发布的 Minice 账户登录 https://astra.minice.ai/plugins，为
`you/dice-roller` 铸造一个绑定令牌 —— 面板会在 GitHub 上查找这个仓库，所以
它必须先推送上去。`init-ci --binding` 会把令牌写成仓库根目录下
`.well-known/astra-plugin-owner` 的第一行；提交到默认分支后，注册表就靠它
知道是哪个账户代表这个仓库发言 —— 这正是构建证明唯一说不出来的事。漏掉它，
你的首次提交就会以 `B_UNBOUND` 被拒绝。

等你在下一步打好标签后，`astra-plugin check --tag v0.1.0` 会像注册表一样，从
标签的提交把这一行读回来。令牌是公开的，不认证任何发布，所以绝不要合并一行
不是你自己铸造的绑定行。它记录了什么、能用多久、重命名会对它造成什么，见
[上架 —— 绑定你的仓库](5-publish/get-listed.md#绑定你的仓库)。

## 5 · 打标签 —— 这才是发布

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
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
[用 CI 发布 §3](5-publish/release-with-ci.md#3--ci-做了什么)。

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

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
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

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

在这份清单中，绑定判定是由你自己的工作决定的，你已经在
[第 4 步](#4--推送它公开地--带上所有权文件)完成了它。剩下的都取决于
你已经给工作流构建出来的那次发布打上了标签。

## 8 · 一次性提交，仅此一次

**在运行它之前**，像注册表那样从你的标签把绑定行读回来。这是本页上唯一一项
你在其他一切都做对的情况下仍可能不通过的检查：

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
astra-plugin publish
```

`publish` 会在浏览器里打开面板的**提交页面**，仓库和标签都已填好。它不上传
任何东西，也不持有任何凭证 —— 没有 `astra-plugin login`，shell 历史里没有
token，也没有需要对接的密钥环。在你以仓库绑定的 Minice 账户登录并亲自提交
之前，这个页面不会提交任何东西。`--print-url` 会打印链接而不是打开浏览器：

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

提交只携带**两项事实**：你的源仓库(`you/dice-roller`)和发布标签
(`v0.1.0`)。其余一切都从已证明的包中读取，因为包里的一切都被证明所覆盖，
因此比任何填进表单的东西都严格地更有价值。

## 9 · 接下来会发生什么

细节，包括每一个代码：[上架 §提交之后会发生什么](5-publish/get-listed.md#3--提交之后会发生什么)。
简短版本：面板会显示提交的状态，同样的节点也会以通知的形式送达你 —— 发到你
Minice 账户经过验证的电子邮箱和面板，只有在你关联了 Telegram 时才会发到
Telegram。

| 结果 | 含义 | 谁参与 |
|---|---|---|
| **已发布** | 已提交，随后进入签名目录 | 没有人 |
| **已延迟** | 全部通过；它会在面板显示的时间自行发布 | 没有人 |
| **已保留** | 一个注册表无权自动做出的决定 | 一位审核员，在面板里 |
| **已拒绝** | 某项检查失败 | 你：修好它，然后按代码的提示在面板里重新检查，或者重新打标签 |

**首次上架总是会为人工审核而保留** —— 这是需要人来处理的恰好三件事之一，
另外两件是新请求的高风险权限，以及仓库或绑定的变化。审核员在面板里批准或
拒绝；等待期间你什么都不用做。任何批准都不会缩短延迟，规则由注册表的
`docs/POLICY.md` 公布。

## 10 · 此后的每一次发布

什么都不用做。打一个标签，其余交给 CI；注册表会自行发现已上架插件的新标签，
面板会显示它的状态。

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

没有需要提交的东西，也没有需要通知的东西。一次没有出现的发布，会在面板中你
插件的页面上显示出来，带有它的状态和原因。

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
同时也会打印出 bot 在证明中会接受的可复用工作流 SHA —— 自 2026-08-19 标签移动
以来共有两个：`plugin-release/v1` 现在指向的那个 commit，以及它之前指向的那个。
从 2026-09-20 起，客户端拿到的目录已用这个密钥签名；提交在注册表 `main`
上的副本 `registry/v1/index.json` 和 `revocations.json` 是有意携带
`"signatures": []` 的，没有任何客户端读取它们。**仍然缺失的一环是 Pages 上
一份已签名的撤回列表**，所以失效机制尚未被强制执行。这里没有对任何尚未落地的
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
