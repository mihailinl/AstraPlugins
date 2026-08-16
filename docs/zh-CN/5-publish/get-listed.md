> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/5-publish/get-listed.md)。如与英文版有出入，以英文版为准。

# 申请上架

**一个插件只会被上架一次，永远只有这一次。** 此后，发布就是零接触的：
打标签，让 CI 构建并出具证明，注册表会自动接收它。

前提条件：在一个**公开**仓库上，[由 CI 构建的一次发布](release-with-ci.md),
带有已附加且已出具证明的 `.astraplugin` 资产。打标签就能满足这个前提
条件 —— 可复用工作流位于 `mihailinl/AstraPlugins` 的默认分支上，并以
`plugin-release/v1` 的形式发布，所以推送一个标签就会触发构建和出具
证明。本页的一切都假定你已经完成了这一步；如果还没有，请先完成
[用 CI 发布](release-with-ci.md)，或者阅读一页讲完整个流程的
[发布插件](../publishing.md)。

**下面这些都不能替代它**，因为每一种都有人真的试过：一个包含你源码的
仓库、发给某人的一个 `.zip`、你在自己笔记本上构建出的包，或者一个请
维护者帮忙构建的 issue。注册表只会上架 CI 出具过证明的发布资产，
其他一概不行。

以下几乎每一条命令都是 `astra-plugin`；唯一的例外是
[第 2 步](#2--证明你控制着这个仓库)，那只是在你自己仓库里的一个文件加
一次 `git commit`。如果你还没有这个 CLI，请先
[安装它](../install-cli.md) —— 现在已经有预编译二进制文件了。

## 1 · 预检

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

它会运行所有能在本地执行的注册表检查，然后 —— 这是更重要的一半 ——
**指名那些只有注册表才能运行的检查**，让你知道还有什么尚未得到验证：

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that `.well-known/astra-plugin-owner` on your default branch names the account opening the listing request
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**其中有一项你可以提前解决，而且应该这么做。** 所有权那一行已经点名了
这个文件，而提交它就是
[第 2 步](#2--证明你控制着这个仓库)。在提交之前先做好这件事，检查就会
一次通过；跳过它，你得到的第一个答复就会是拒绝。

### 你的上架条目会是什么样子

决定这一点的是两个文件，而且都是你已经和 `plugin.toml` 放在一起的
文件。清单文件里的任何地方都没有写出它们的名字 —— 打包工具是靠文件名
本身把它们拾取出来的，注册表则从它刚刚验证过的包里把它们读回来。你
从来不需要输入任何 URL，任何人也无法替你输入。

**图标** —— 你插件卡片上显示的图片。以下任意一种：

<!-- doctest: illustrative reason="the accepted filenames, not a command; spec/icon-formats.yaml is the list both the packer and the registry read" -->
```
icon.png    icon.webp    icon.svg    icon.jpg    icon.ico
```

`astra-plugin new` 会生成一个占位用的 `icon.svg` 脚手架，让你有东西
可以替换。请把它画成正方形；它显示时大约只有 64 像素，所以需要的是
一个鲜明的轮廓，而不是精细的细节，而且因为商店会跟随用户的主题，图标
在浅色和深色背景下都应该能看清。带透明背景的 PNG 是常见的答案。

如果你使用 SVG，请保持它是静态的：不要有 `<script>`，不要有 `on*`
事件处理器，不要有 `<foreignObject>`，也不要引用你机器之外的任何东西。
带有这些内容的图标会被丢弃，你的插件会以没有图片的方式上架。这不会
让你的发布失败 —— 一个装饰性文件不应该成为软件发布的关卡 —— 但你会
收到相应的警告，而且没有人能看到你的图标。

**`README.md`** —— 你插件的详情页，在有人点击卡片时展示。这是一个人在
决定是否安装你的插件时会读的内容，因此它比那一行摘要更有价值。

它会以 GitHub 风味的 markdown 渲染，包括表格。截图也能正常显示，一段
只由图片组成的段落会变成一行图库(gallery)：

<!-- doctest: illustrative reason="markdown an author writes in their own README; there is nothing here for a runner to execute" -->
```markdown
![The command editor, mid-roll](docs/editor.png)
![The trigger firing on a natural 20](docs/trigger.png)
```

有三条规则，注册表在推导你的上架条目时都会应用：

- **用相对路径链接图片**，并把它们提交到你的仓库中。它们会被重写为
  指向你发布所构建的那个确切 commit，所以在有人批准了这次上架之后，
  图片不可能再发生变化。
- **托管在 GitHub 之外的任何地方的图片都会被丢弃**，替换为它们的
  alt 文本，包括构建徽章(build badge)在内。这更像是一条隐私规则，而
  不是安全规则：渲染出的 README 中每一张远程图片，都是用户机器在尚未
  安装任何东西之前发出的一次请求。
- **原始 HTML 会被剥除。** 布局请用 markdown 来完成。

过长的 README 会在 16 KB 处、按行边界截断，并附带一个指向 GitHub 上
完整内容的链接。

## 2 · 证明你控制着这个仓库

**请在开这个 issue 之前先做这件事。** 只需要一个文件、一次提交，而
跳过它正是一次正确、诚实的首次提交最常被拒绝的原因。

注册表必须回答一个本页其他任何地方都没有回答的问题：**申请这次上架
的人，是否真的控制着即将被上架的这个仓库？** 证明本身已经证明了这个
包确实来自那个仓库，而且上架条目也固定在那个仓库上 —— 但这两个事实
都没有说明*你*是谁。没有这一步，一个陌生人就可能把别人的插件拿去上架，
从而变成了那个插件更新到达 Astra 用户手中所经过的身份。

把这个文件提交到你仓库的**默认分支**：

<!-- doctest: illustrative reason="the path and content of a file the author writes in their own repository; there is nothing here for a runner to execute" -->
```
path      .well-known/astra-plugin-owner
content   your GitHub login, one per line
```

创建它只需要一条命令，在你插件仓库的根目录运行：

<!-- doctest: illustrative reason="git commands against the author's own repository — the runner has no such repository, and `cli` blocks must contain an astra-plugin command" -->
```bash
mkdir -p .well-known
echo 'your-github-login' > .well-known/astra-plugin-owner
git add .well-known/astra-plugin-owner
git commit -m "Declare the Astra registry owner for this repository"
git push
```

**这能证明什么：** 一个能写入你默认分支的人，断言这个 GitHub 登录名
代表这个仓库 —— 这是在 bot 检查的那一刻实时读取的，所以从文件里删掉
一个登录名，那个人就无法再开新的上架申请、也无法通过 `/recheck`。但它
**够不到**已经上架的插件：[此后的每一次发布](#5--此后的每一次发布)都是
针对发布该 release 的账号来证明的，而上架条目无论如何都仍然钉在这个仓库上。
**这不能证明什么：** 完全不能证明你代码的任何事情，因为根本没有人会
去读它；这不是一个签名，也不是一次安全审查。

### 格式，精确地说

一行一个登录名。`#` 之后的一切都是注释，开头可以有 `@`，前后的空白
会被去掉，比较时不区分大小写。只会读取前 4 KB。所以下面这个文件是有效
的，列出了一位所有者：

<!-- doctest: illustrative reason="the contents of a file in the author's repository, not a command" -->
```
# owners of this repository
@Rel0d1x   # primary
```

请列出所有可以代表这个仓库提交或重新提交申请的人。对于一个属于某个
组织的仓库，通常不止一个名字。

### 确认注册表能读到它

bot 会通过 GitHub 的 contents API、以未认证方式，从默认分支读取这个
文件。你可以发出和它完全一样的请求：

<!-- doctest: illustrative reason="gh against the author's own repository; `cli` blocks must contain an astra-plugin command, and this one is deliberately shell-only" -->
```bash
gh api repos/you/dice-roller/contents/.well-known/astra-plugin-owner \
  --header 'Accept: application/vnd.github.raw+json'
```

它应该会把你的登录名原样打印出来。如果它打印出 `Not Found (HTTP
404)`，说明这个文件不在 bot 查找的位置 —— 常见的原因是它在默认分支
以外的分支上、还没有提交或推送，或者目录名写成了没有开头那个点的
`well-known`。

### 为什么这是一个步骤，而不是一个后备方案

注册表会尝试三种方式来确立控制权，而这个文件正是对普通作者行得通的
那一种。这不是偏好，而是结构性的，另外两种方式都曾在真实提交中被
观察到失败：

| 方式 | 为什么它不能替你回答 |
|---|---|
| **协作者权限** —— 询问 GitHub 谁拥有 `admin` 或 `maintain` | GitHub 只会对已经拥有该仓库 admin 可见性的调用者回答这个端点。注册表的 token 属于注册表本身，所以对*你的*仓库，它得到的是 `403` —— 这意味着"我不会告诉你"，而不是"不是"，因而会被当作完全没有回答处理 |
| **发布的作者** —— 发布这次 release 的账号 | [用 CI 发布](release-with-ci.md) 中的发布工作流创建了这个 GitHub Release，所以它的作者是 `github-actions[bot]`，而不是一个人。恰恰是遵循了这份文档化流程，才让这种方式失效 |
| **`.well-known/astra-plugin-owner`** | 不需要对注册表可见任何东西，也不需要安装任何东西。它能给出回答 |

第一种方式返回的 `403` 不会算在你头上，单凭它自己也永远不会导致拒绝。
拒绝只会在三种方式全都没有给出回答时发生，而这正是这个文件不存在时
会发生的情况。

## 3 · 提交

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

它会在你的浏览器中打开一个在注册表上预填好内容的 issue。**它不上传
任何东西，也不持有任何凭证** —— 没有 `astra-plugin login`，你的 shell
历史里不会留下 token，也没有需要对接的密钥环(keyring)。`--print-url`
会改为打印出链接：

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

这段输出是在一个没有自己 git 标签的目录里录下来的。如果你在自己的检出里、
在还没拉到该标签之前运行它，段落上方会多出一行 ——
`Note: this checkout has no tag v0.1.0.` 这是提醒，不是错误：注册表是从
GitHub 读取这次发布的，所以真正重要的是标签已经推送、并且 CI 已经把
产物附加上去了。

> **那个 URL 里的 `template=plugin-listing.yml` 是至关重要的。**
> 这个模板声明了 `labels: ["listing", "needs-triage"]`，而注册表的 bot
> 只会对带有 `listing` 标签的 issue 进入提交处理路径。别的东西都不会打上
> 这个标签 —— bot 自己也不会，而且这是刻意的：在那里它是一枚权限令牌，
> 而不是一个分类；一个见到像表单的东西就盖章的 bot，等于把这项豁免交给了
> 任何会复制表单的人。
>
> 已经有两次真实的上架申请正是以这种方式石沉大海：它们到达时不带标签，分诊
> 返回 `mode: "none"`，检查、发布、评论几个步骤全部被跳过，作者**什么都没
> 得到，连一个拒绝的回应都没有**。现在两边都已经修好了。注册表关掉了空白
> issue，所以 *New issue* 页面只提供表单；而万一还是有没带标签的申请进来，
> 它会收到一条评论，准确说明缺了什么，外加那一次点击 —— 由维护者加上
> `listing` —— 就能在同一个 issue 上启动验证，什么都不用重打。而从这条链接
> 打开，可以把这一切都跳过。

这次提交携带**两个事实**：

| 字段 | 为什么是输入的而不是读取的 |
|---|---|
| 源码仓库（`you/dice-roller`） | 包本身无法证明自己是从哪里提供的 |
| 发布标签（`v0.1.0`） | 同上 |

外加三项确认，全部必填：你已经把 `.well-known/astra-plugin-owner` 提交到
默认分支并且里面写着你的登录名、你拥有或维护着该仓库，以及你已经读过政策。

**其余的一切都从已获证明的包中读取** —— id、版本、显示名称、摘要、
许可证、能力(capability)、权限、平台、摘要值(digest)、文件大小。这
不只是图个方便：包里的每一样东西都在证明的覆盖范围内，这使它比任何
填进表单里的内容都要严格地更可信。这也消除了整整一类拒绝的可能性，
因为根本不存在一个能和 `plugin.toml` 产生分歧的表单。

## 4 · 提交之后会发生什么

这一节正是两位真实的作者需要、却没能得到的内容。它描述的是
`astra-registry/docs/POLICY.md` 和 `docs/BOT-CHECKS.md` 所定义的注册表
流程；这两份文档要么是从 bot 自己的代码（`bot/lib/policy.mjs`、
`bot/lib/codes.mjs`）生成的，要么是针对它做过校验的，所以这里的数字
不可能悄悄偏离那些维护着它们的代码。

### 整个流程

1. **你的 issue 会被打上 `listing` 和 `needs-triage` 标签** —— 由
   issue 模板自动完成。这一步决定了接下来是否会发生任何事；参见 §3
   中的警告。
2. **bot 会对它进行分诊**，读取你提供的两个事实，以未认证方式从
   GitHub 获取这次发布，并针对这些字节运行 `docs/BOT-CHECKS.md` 中的
   每一项检查：证明本身以及是哪个工作流产出了它、资产的 URL 是否位于
   你自己仓库的发布命名空间下、你是否控制着这个仓库
   （[第 2 步](#2--证明你控制着这个仓库)）、归档的结构、清单文件、
   许可证、版本排序，以及声明与实际调用之间的 host RPC 扫描。
3. **bot 会在你的 issue 上评论**结果、原因，以及 —— 如果有的话 ——
   确切的发布时间。无论结果如何，你都会被告知。

如果一小时内都没有任何评论，检查一下这个 issue 的标签。没有
`listing` 标签，就意味着第 1 步没有发生，后续的一切都没有运行。

### 四种结果

| 结果 | 含义 | 涉及谁 |
|---|---|---|
| **已发布（Published）** | 已提交，会出现在下一次索引构建中的目录里 | 不涉及任何人 |
| **延迟（Delayed）** | 一切都通过了；会在指定时间自动发布 | 不涉及任何人 |
| **保留（Held）** | 这是注册表无权自动做出的决定 | 由一位维护者在 48 小时内处理 |
| **拒绝（Refused）** | 某项检查失败了。政策根本没机会表态 | 由你：修复它，并评论 `/recheck` |

当以下条件全部成立时，一次发布会在没有任何人介入的情况下自动发布：它
来自这个插件已经上架所对应的那个仓库、bot 的每一项检查都通过、版本号
严格更新、没有申请任何它之前没有的高风险权限，而且完全没有申请任何新
的权限或能力。只有最后一条不满足，它依然会在延迟之后自动发布。

**首次上架永远不属于上述情况之一。** 按定义它一定会被保留给人来判断 ——
见下文 —— 所以"我的第一个插件要多久才能上架"这个问题的答案是*bot 评论
之后最多 48 小时*，而不是*几分钟*。

### 保留状态如何被解除

不需要你做任何事。一位维护者会在你的 issue 上评论 **`/approve`**，
随后整个摄入(ingest)过程会针对当时那一刻的字节内容，从头重新运行
一遍 —— 一次批准只是一个"某人在这个时间点说了 yes"的标记，不携带任何
缓存下来的判定结果，所以批准某样东西并不会跳过任何一项检查。
**`/reject <reason>`** 是另一半，它必须带上理由，而这个理由会被发布
给你。这两条命令都会针对注册表仓库进行权限检查：发出评论的人需要在
那个仓库拥有 `admin` 或 `maintain` 权限，这一点会在命令被读取的那一刻
通过 GitHub 的 API 重新证明，而不是信任事件负载(payload)里自带的信息；
其他任何人发出的命令都会得到回应，而不是被忽略。

你不需要输入这两条命令中的任何一条，等待期间也不需要做任何事。它们
之所以被记录在这里，只是为了让"保留给维护者处理"指名的是一套机制，
而不是一片沉默。

*一条附加说明，之所以要说出来，是因为本页的原则就是把这些都说清楚：*
这条维护者命令的路径，和本页是同时落地到注册表中的。如果你的保留发生
在它之前，结果是一样的，SLA 也是一样的 —— 依然由维护者来决定 —— 只是
这个决定可能是手动记录的，而不是通过命令记录的。

### 拒绝是什么样子

bot 会附带一个固定的代码，以及该怎么处理它。一次拒绝不是对你插件的
最终判决；它是一个有名字的、可以修复的状态。作者们最常遇到的几种：

| 代码 | 含义 | 修复方法 |
|---|---|---|
| `E_ATTESTATION_MISSING` | 这个包没有构建证明 | 你上传的是自己构建的包。让 CI 来构建它：[用 CI 发布](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | 这次发布没有携带任何 `.astraplugin` 资产 | 工作流没有运行，或者运行了但失败了。检查你仓库的 Actions 标签页 |
| `E_RELEASE_NOT_FOUND` | 那个仓库没有带着那个标签的发布 | 一个草稿发布(draft release)除了你自己之外任何人都看不到，一个私有仓库看起来和一个不存在的仓库完全一样 |
| `E_WORKFLOW_NOT_ALLOWED` | 构建运行的工作流不是这个注册表所允许的 | 用 commit SHA 把 Astra 的可复用工作流固定住。`astra-plugin init-ci` 会替你完成这件事 |
| `E_ASSET_URL_FOREIGN` | 某个资产的 URL 不在你自己仓库的 releases 之下 | 每一个下载 URL 都必须位于 `https://github.com/<owner>/<repo>/releases/download/<tag>/` 之下 |
| `E_OWNERSHIP_UNPROVEN` | 没有任何东西证明你控制着这个仓库 | 你几乎肯定是跳过了[第 2 步](#2--证明你控制着这个仓库)。在默认分支上提交一个包含你 GitHub 登录名的 `.well-known/astra-plugin-owner` 文件，然后评论 `/recheck` —— 不需要新的发布，也不需要新的标签 |
| `E_INPUT_REPO` / `E_INPUT_TAG` | 仓库或标签的格式不符合预期 | 应该是 `you/dice-roller`，不是一个 URL；应该是 `v0.2.0`，不是一个 commit SHA 或分支名 |

修复之后，在同一个 issue 上评论 **`/recheck`**。所有检查会针对当时
那一刻的字节内容，从头重新运行一遍；不会恢复任何进度，也不会信任任何
排队中的结果。每种失败的确切措辞的完整清单，在注册表的
`docs/BOT-CHECKS.md` 中。

bot 自身的退出码是：`0` 已上架 · `1` 拒绝 · `3` 保留给维护者 · `2`
bot 自身出了故障。最后一种被刻意区分开来："你的插件有问题"和"我们的
工具有问题"绝不能对一个陌生人呈现为同一条评论。

### 需要人来处理的三件事

恰好三件，而且这份清单不会在注册表已发布的政策没有变化的情况下增长：

| 事件 | 原因 |
|---|---|
| **一个插件的首次上架** | 一次性的，永远只有这一次。此时还没有任何东西被固定下来，所以之后没有什么可以拿来对照检查 |
| **新申请的一项高风险权限** | 用户将被要求对此表示同意；应该先有人读过它是用来做什么的 |
| **仓库或身份发生了变化** | 每一份已安装的副本都携带着对旧仓库的锁定。除非有人明确说明否则一次仓库变更就等同于一次作者变更 |

这里的"高风险"指的是四个具体的名字：`client`、`dom_access`、
`send_chat_message`、`set_theme_contribution` —— 无论它们是在
`[capabilities]` 还是 `[permissions]` 中声明的，都同样适用，因为你在
哪个段声明它们并不是重点。`push_to_ui` 会有一个同意勾选框，但不会触发
审查：它只是在你插件已经拥有的一个面板内部绘制内容。

某项检查也可能单独把一个判断交给人来处理 —— 比如一个名字和某个已上架
插件只差一次编辑、一个和现有条目冲突的显示名称。这种情况会以
`R_CHECK_HELD` 的形式出现，不属于上述三件事之一，但适用同样的 SLA。

对上述情况，**SLA 是 48 小时**，从 bot 发表评论的那一刻算起。只有一位
维护者，这正是这份清单只有三项的原因。注册表公开的是一旦超时会发生
什么，而不只是一个承诺：超过 96 小时，维护者必须要么把积压的队列公开
处理掉，要么在一次经过审查的提交中，把触发这件事的事件类型从阻塞集合
中移出去，而那次提交也会同时修改做出这个承诺的那段文字。

### 什么时候一次发布会转而等待

有些发布通过了一切检查，却依然不会立即发布：

| 情况 | 代码 | 延迟 |
|---|---|---|
| 该插件持有**任意**一种高风险权限，无论这次发布是否改变了它 | `P_DELAY_HIGH_RISK` | 24 小时 |
| 这次发布在非高风险的集合中，申请了上一版没有的权限或能力 | `P_DELAY_WIDENED` | 24 小时 |
| 上述任意一种情况，但作者在这个注册表中已有 **5 次干净的**发布记录 | `P_TRUSTED_AUTHOR` | 6 小时 |

bot 会给出确切的发布时间，一旦倒计时结束，整个摄入过程会针对届时的
字节内容从头重新运行一遍。这个延迟只买来一件事，注册表也不会声称
更多：一个作者的 GitHub 账号如果被人接管，在这个窗口期内，本人能够
看到一次自己并未发起的发布，并有机会站出来说明情况。

## 5 · 此后的每一次发布

什么都不用做。打标签，剩下的交给 CI；注册表会注意到这次发布并重新
生成索引。

如果它还没有注意到：

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

这是给**已经上架**的插件用的手动 ping。不这样做的话，`publish` 会
打开一个首次上架申请。

**在这条路径上，所有权是另一个问题。** 一次 ping —— 以及它背后的 cron
兜底 —— 是针对*发布*该 release 的账号来证明的，既不是针对敲下 ping 的
人，也不是针对 `.well-known/astra-plugin-owner`。因此编辑那个文件并不会
改变谁能为一个已经上架的插件发布新版本。真正约束它的是：一次 ping 只能
指向注册表**已经钉住**的那个仓库；换仓库就不再是例行公事，会重新回到
人来处理。

## 上架并不意味着什么

上架不是一次安全审查。没有人会去读你的代码，注册表自己的政策也明确
这么说：一项权限决定的是守护进程会*为*插件做什么，而完全不涉及插件的
进程能对这台机器做什么。这里没有沙箱。参见
[安全模型](../1-orientation/security.md)。

## 今天的实际状态

有一件事，读者在按照本页操作之前应该知道。

**签名链已经锚定到了委托(delegation)这一层，但还没有贯穿到目录
(catalogue)本身。** 具体来说，每一部分都是可以核实的：

- 根密钥两边都存在 —— `registry/v1/root.json` 携带
  `"status": "provisioned"`，以及两个 Ed25519 密钥，守护进程内编译进
  的 `PRODUCTION_ROOT_KEYS` 也是同样的两个；
- `registry/v1/trust.json` **现在已经**由 `astra-root-2026a` **签
  名**，并委托给一个索引签名密钥 `astra-index-2026a`。注册表自己的
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` 会确认
  这一点，并打印出 bot 在证明中会接受的唯一那个可复用工作流 SHA
  值，`e3329df252a46d747676cb540ae4b986af68a3ad` —— 即
  `plugin-release/v1` 所指向的那个 commit。所以过去会拦住每一次摄入
  的 `E_TRUST_UNPROVISIONED`，现在已经不会再触发了；
- **目录本身仍然是未签名的。** `registry/v1/index.json` 和
  `revocations.json` 携带的都是 `"signatures": []`，所以默认的
  Astra 构建没有签名可以核对，会把所有目录都归类为未签名，并安全
  失败(fail closed)。出于同样的原因，失效强制机制也没有生效。

参见 [`spec/registry-index.md` §0.1](../spec/registry-index.md) 和
[安全模型](../1-orientation/security.md)。

这对你意味着什么：本页描述的提交路径今天已经端到端可用 —— 你的
issue 会被读取，各项检查会运行，bot 会给出回应，一次上架会被提交。
仍然悬而未决的，是让 Astra 能够*从*注册表所发布的内容中*安装*插件所
需要的那个签名。等它落地之后，本页的内容不会有任何变化。

## 另请参阅

- [`spec/registry-index.md`](../spec/registry-index.md) —— 索引、失效列表，以及验证算法
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) —— bot 会从你的归档中读取什么
- [版本管理](../versioning.md) —— 数字的含义，以及一次弃用会持续多久
