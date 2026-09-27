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
仓库、发给某人的一个 `.zip`、你在自己笔记本上构建出的包，或者一条请
维护者帮忙构建的消息。注册表只会上架 CI 出具过证明的发布资产，
其他一概不行。

下面的每一步，要么是 `astra-plugin`，要么是你自己仓库里的一次提交，要么是
以你的 Minice 账户登录的 https://astra.minice.ai/plugins 面板。如果你还没有
这个 CLI，请先[安装它](../install-cli.md) —— 已经有预编译二进制文件了。

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
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**其中有一项你要提前解决，而且必须解决。** 绑定判定读取的是
[绑定你的仓库](#绑定你的仓库) 写入的那一行。在打标签之前提交它，检查就有
东西可找；漏掉它，你得到的第一个答复就是 `B_UNBOUND`。

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

## 绑定你的仓库

**上架属于一个 Minice 账户。** 每一次首次上架，以及已有绑定的上架的每一次
发布，都会对照一个**绑定**来读取：你仓库根目录下
`.well-known/astra-plugin-owner` 里的一行，由 CLI 根据你在面板里铸造的令牌
写入，铸造时要以将来负责发布的那个 Minice 账户登录。这是本页唯一不是命令的
一步，而跳过它，是一次正确、诚实的首次提交被拒绝的最常见原因。

**1 · 铸造一个令牌。** 用将来拥有这个上架的 Minice 账户登录
https://astra.minice.ai/plugins —— 它需要 `astraUser`，拥有 Astra 就会有 ——
然后为这个仓库铸造一个绑定令牌。

**2 · 写入这一行。** 在仓库里的任何位置运行：

<!-- doctest: cli -->
```bash
astra-plugin init-ci --binding <token>
```

它会把 `astra-binding: <token>` 写成仓库根目录下
`.well-known/astra-plugin-owner` 的**第一行**，删除之前任何写法的绑定行，保留
你的登录名行，并且不联网：

<!-- doctest: output from="astra-plugin init-ci --binding k3Vq9ZtW2xLr8NfBcY5pHd" unrun="rewrites .well-known/astra-plugin-owner in a git repository; re-run it at the root of your own" -->
```
  Rewrote: .well-known/astra-plugin-owner
    line 1   astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd
    kept     1 other line(s), byte for byte

  This token is public once you push it. It records one Minice account's consent
  to publish from this repository, and it authenticates no release: never merge a
  binding line you did not mint yourself. What that means, and what a rename or a
  transfer does to it:
    https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository

  Next: commit this file on your default branch, then tag. Before you push the tag,
    astra-plugin check --tag <tag>
  reads the line back from the tagged commit, as the registry will.
```

**3 · 提交到默认分支，然后打标签。** 推送标签之前，按照注册表的方式把这一行
读回来 —— 从标签的提交读，而不是从你的工作区读：

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
```

格式错误的行会在这里失败，报 `B_BINDING_MALFORMED`，这时修正它还不需要任何
代价。缺少这一行则是一条预测 `B_UNBOUND` 的警告。只有注册表才能给出的四个
回答，每次都会被列为未检查。

**4 · 在面板里提交。** `astra-plugin publish` 会打开面板的
提交页面，仓库和标签都已填好，例如
https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0 ——
在你登录并亲自提交之前，这个页面不会提交任何东西。

**令牌是什么，不是什么。** 绑定令牌是**公开的**：它就放在公开仓库的一个文件
里。它记录的是**一个账户同意**从这个仓库发布，它**不认证任何发布** —— 一个
没有被任何东西延迟的发布，会在账户得知之前就发布出去。所以**绝不要合并一行
不是你自己铸造的绑定行**：添加或修改这一行的拉取请求，是在要你把上架交给别人
的账户。

**这一行必须在哪里。** 在仓库根目录，无论你的插件在哪个目录；在发布标签指向的
那个提交里；并且在文件的前 4096 字节之内。一行覆盖仓库里的所有插件。之后把它
从默认分支删掉，不会结束任何已经绑定的东西。

**铸造的令牌能用多久。** 铸造的令牌在铸造 30 天后过期，除非有一个仍在进行的
提交指明了它，或者在应用这条规则时它那一行位于仓库的默认分支上 —— 每次作出
过期决定之前都会重新检验这条规则。所以，很久以后才打标签、而默认分支上没有
这一行的作者需要重新铸造，而在应用这条规则时那一行仍在该分支上的作者则不需要。
提交之后又删掉的一行，不会让令牌继续有效。

**登录。** 注册表根据账户最近一次经过验证的登录来判断它是否有资格发布，这次
登录的有效期是 12 小时。只要账户在这段时间内没有登录，已绑定仓库的发布就会
等待；面板会说明这一点，一条 `notice.sign_in` 通知会请你登录。在你登录之前，
什么都不会发布。

**通知发到哪里。** 发到 Minice 账户经过验证的电子邮箱，以及面板。Telegram 是
可选的额外渠道，你可以关联它；没有任何东西要求它。

**重命名或转移会让已安装的副本搁浅。** Astra 通过插件的仓库
`github:owner/name` 来识别已安装的插件。重命名仓库或把它转给另一个所有者，
每一个已安装的副本都会停止接收更新，直到从新名字重新安装为止。没有任何东西
能改变这一点。

**对于已经上架的插件。** 未绑定的上架处于 `grandfathered` 状态：它会像今天
一样继续发布，直到绑定截止日期和注册表切换两者中较晚的那个。截止日期在第三方
绑定开放之前确定，并由注册表公布。在那之后，未绑定的上架变为 `frozen`：已安装
的副本继续工作，它也仍然可以安装，但在带有绑定行的发布被发布之前，它不会再有
新的发布被发布 —— 一个已绑定的发布就能让它解冻，没有任何惩罚。第一个带有
绑定行的发布会被扣留一次，交给人工审核，即 `R_FIRST_BINDING`。并且从切换起，
`grandfathered` 上架的延迟发布或需审核发布会一直等到该上架完成绑定。

**预检。** `astra-plugin check` 会拒绝注册表拒绝的 id —— 保留的 id，或者不符合
注册表 id 模式的 id —— 以及格式错误的绑定行。`astra-plugin dev` 和
`astra-plugin build` 两者都不拒绝：注册表的规则决定的是什么能上架，而不是你
可以运行什么。

## 2 · 在面板里提交

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

它会在浏览器里打开面板的**提交页面**，仓库和标签都已填好。**它不上传任何
东西，也不持有任何凭证** —— 没有 `astra-plugin login`，shell 历史里没有
token，也没有需要对接的密钥环。这个页面根据链接自行填写，但不会提交任何
东西：提交的是你，要以该仓库绑定的 Minice 账户登录后提交。`--print-url` 则
改为打印链接：

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

没有绑定行的仓库会在链接上方得到提示，并告诉你去哪里阅读如何绑定；没有这个
标签的检出会得到一行提示，说明标签必须已经推送。两者都是提醒，不是错误：
注册表从 GitHub 读取标签的提交和发布，所以重要的是你推送了什么。

提交只携带**两项事实**：

| 字段 | 为什么是输入而不是读取 |
|---|---|
| 源仓库(`you/dice-roller`) | 包本身无法担保自己是从哪里分发的 |
| 发布标签(`v0.1.0`) | 同上 |

**其余一切都从已证明的包中读取** —— id、版本、显示名称、摘要、许可证、能力、
权限、平台、摘要值、大小。这不是为了方便：包里的一切都被证明所覆盖，因此比
任何填进表单的东西都严格地更可信。它还消除了一整类拒绝，因为不存在可以和
`plugin.toml` 不一致的表单。

## 3 · 提交之后会发生什么

面板会显示你的提交所处的状态以及附带的每一条原因，同样的节点也会以通知的
形式送达你：发到 Minice 账户经过验证的电子邮箱和面板，只有在你关联了
Telegram 时才会发到 Telegram —— 没有任何东西要求 Telegram。下面的规则是
注册表的，发布在它的 `docs/POLICY.md` 中；代码是面板显示的代码，上线时使用
英文标题。

### 一次提交会经历的状态

| 状态 | 含义 |
|---|---|
| `received` | 面板接受了你的提交，还没有任何东西读取它 |
| `checking` | 注册表的 bot 正在读取发布，并从头验证每一个资产 |
| `held` | 机器能决定的都已通过，有一个决定属于人 —— 见下文 |
| `approved` | 一位审核员批准了这次保留；在没有其他等待项时发布 |
| `delayed` | 全部通过；它会在面板显示的时间自行发布 |
| `published` | 已提交到注册表 |
| `served` | 已进入 Astra 安装所用的签名目录 |
| `refused` | 某项检查失败。面板会给出代码，并说明重新检查(Recheck)能否解决，还是需要新的标签 |
| `stopped` | 你在它发布之前停止了它，它不会发布 |

当以下条件全部成立时，一次发布会在没有任何人参与的情况下自行发布：它来自该
插件已上架的那个仓库，并绑定到同一个账户；bot 的每项检查都是绿色；版本严格
更新；它没有请求之前没有的高风险权限；并且它完全没有请求任何新的权限或能力。
只去掉最后一个条件，它仍会自行发布，只是要经过一段延迟。

**首次上架从来不属于这种情况。** 它会为人工审核保留一次，永远只有这一次，
所以“我的第一个插件多久能上架”的答案是 *在审核员读过它之后*，面板会显示它
正在等待。

### 当答案是一个代码时

拒绝不是对你插件的判决；它是一个有名字、可修复的状况，面板会告诉你它通过
两种方式中的哪一种解决。**重新检查(Recheck)** 是面板里的一个按钮，它会针对
同一个标签从头重新运行每项检查 —— 用于已打标签的字节之外的修正，比如你忘了
附上的发布资产。**新的标签** 是改变这些字节之内任何东西的唯一办法，因为证明
覆盖的正是这些字节。绑定相关的代码：

| 代码 | 含义 | 修复 |
|---|---|---|
| `B_UNBOUND` | 打标签的提交里没有绑定行，而这个上架需要一行 | 绑定仓库并重新打标签：[绑定你的仓库](#绑定你的仓库) |
| `B_BINDING_MALFORMED` | 有两行绑定行，或者某一行本意是绑定行却不合格(`Astra-Binding:`、过短的令牌) | `astra-plugin init-ci --binding <token>` 会用恰好一行重写该文件；重新打标签。`astra-plugin check --tag` 会在你推送之前显示这一点 |
| `B_BINDING_UNUSABLE` | 这一行上的令牌没有绑定任何这次发布能用的东西：已撤销、已过期、为另一个仓库铸造，或其账户不能发布 | 在面板里为这个仓库铸造一个新令牌并重新打标签；面板会说明下面两种情况中哪一种适用于你 |
| `B_BINDING_INVALID` | 只对你和审核员显示：问题在令牌本身 —— 未知、已撤销、已过期，或为另一个仓库铸造 | 为这个仓库铸造一个新的 |
| `B_ACCOUNT_INELIGIBLE` | 只对你和审核员显示：令牌背后的账户不能发布，例如因为它不再持有 `astraUser` | 修好账户，然后重新检查 |
| `B_OWNER_CHANGED` | 仓库现在属于另一个所有者，而不是这个上架登记时的所有者 | 转移就是作者变更。它要等审核员处理；已安装的副本会一直保留旧名字，直到重新安装 |
| `B_REPOSITORY_RECYCLED` | 这个仓库名现在属于另一个仓库，而不是已上架的那个 | 永久性的：重新检查、新标签或批准都无法解除。只有审核员能重置该上架的身份 |

以及作者最常遇到的发布代码：

| 代码 | 含义 | 修复 |
|---|---|---|
| `E_ATTESTATION_MISSING` | 包没有构建证明 | 你上传了一个自己构建的包。让 CI 来构建它：[用 CI 发布](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | 发布里没有 `.astraplugin` 资产 | 工作流没有运行，或者运行了但失败了。查看 Actions 标签页，附上资产，然后重新检查 |
| `E_RELEASE_NOT_FOUND` | 那个仓库没有带这个标签的发布 | 草稿发布除了你之外对所有人都不可见，而私有仓库看起来和不存在的仓库一模一样。发布它，然后重新检查 |
| `E_WORKFLOW_NOT_ALLOWED` | 构建运行了一个本注册表不允许的工作流 | 按提交 SHA 固定 Astra 的可复用工作流 —— `astra-plugin init-ci` 会这样做 —— 然后重新打标签 |
| `E_ASSET_URL_FOREIGN` | 某个资产 URL 不在你自己仓库的发布之下 | 每个下载 URL 都必须位于 `https://github.com/<owner>/<repo>/releases/download/<tag>/` 之下 |
| `E_INPUT_REPO` / `E_INPUT_TAG` | 仓库或标签的形式不符合预期 | 写 `you/dice-roller`，不是 URL；写 `v0.2.0`，不是提交 SHA，也不是分支 |

完整的列表，连同每个代码的标题和修复方法，是注册表中的 `docs/BOT-CHECKS.md`。

有两种等待看起来像卡住的提交，其实不是：

| 代码 | 含义 |
|---|---|
| `W_ELIGIBILITY_UNREADABLE` | 注册表根据你账户最近一次经过验证的登录来判断它是否有资格发布，这次登录的有效期是 12 小时。登录面板，发布就会继续；一条 `notice.sign_in` 通知也会这样告诉你 |
| `W_REGISTRY_UNACKNOWLEDGED` | 注册表的 bot 发生了变化，正在等待运维人员的确认。你的发布没有任何问题，也不需要你做任何事 |

### 需要人来处理的三件事

恰好三件，而且除非修改注册表已公布的策略，这个列表不会增加：

| 事件 | 代码 | 原因 |
|---|---|---|
| **一个插件的首次上架**，或者已上架插件第一次带绑定行的发布 | `R_FIRST_LISTING`、`R_FIRST_BINDING` | 一次，永远只有这一次。此时还没有任何东西被固定，所以之后没有任何东西可以拿来对照 |
| **新请求的高风险权限** | `R_NEW_HIGH_RISK` | 用户会被要求同意它；在那之前，应该有人读过它是用来做什么的 |
| **仓库、其身份或其绑定发生了变化** | `R_IDENTITY_CHANGED`、`R_BINDING_CHANGED` | 每一份已安装的副本都固定指向旧仓库。在有人另有说明之前，变化就是作者变更 |

这里的高风险是四个名字：`client`、`dom_access`、`send_chat_message`、
`set_theme_contribution` —— 在 `[capabilities]` 和 `[permissions]` 中同样
匹配，因为你在哪个部分声明它们并不重要。`push_to_ui` 会有一个同意勾选框，但
不需要审核：它只在你的插件已经拥有的面板内部绘制。

某项检查也可能单独把一个决定交给人 —— 一个和已上架插件只差一处编辑的名字，
或者一个和它冲突的显示名称。那会以 `R_CHECK_HELD` 的形式到来，不属于这三件。

审核员在面板里批准或拒绝，拒绝会附带原因，并送达你。等待期间你什么都不用做；
面板会显示这次保留。

### 什么时候一次发布会转而等待

有些发布通过了所有检查，仍然不会立即发布：

| 情形 | 代码 |
|---|---|
| 插件持有**任何**高风险权限，无论这次发布是否改变了它 | `P_DELAY_HIGH_RISK` |
| 发布请求了上一次没有的权限或能力，且在非高风险集合之内 | `P_DELAY_WIDENED` |
| 以上任一情形，且来自一位在本注册表中有干净发布记录的作者 | `P_TRUSTED_AUTHOR` |

面板会给出确切的发布时间，时间一到，整个检查会针对那时的字节从头重新运行。
**任何批准都不会缩短延迟。** 延迟只换来一件事，注册表也不声称更多：一个时间
窗口，让一个账户被盗用的作者能够看到一个不是自己做的发布，并停止它。延迟的
长度见注册表的 `docs/POLICY.md`。

仍处于 `grandfathered` 状态的上架 —— 在绑定出现之前上架、至今尚未绑定 ——
还有一种等待：从切换起，它的延迟发布或需审核发布会一直等到该上架完成绑定。

### 停止、撤回、申诉、举报

- **停止。** 在一次发布发布之前，你可以在面板里停止它，它就不会发布。
- **撤回(yank)。** 发布之后，你可以在面板里撤回某个版本。撤回永远不能恢复
  —— 请改为发布一个新版本 —— 并且它会像关于上架的其他所有决定一样，附带一条
  决定记录保存下来。在你的上架尚未绑定期间，请在面板里请审核员替你撤回。
- **申诉。** 你认为有误的、关于你上架的决定，在面板里申诉，答复也记录在那里。
- **评分** 只有星级：没有文字，没有回复，没有名字。
- **举报** 别人的插件请通过 https://astra.minice.ai/plugins 进行，而不是通过
  GitHub。Astra、守护进程、注册表或签名链中的安全问题请发到
  security@minice.ai —— 见
  [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#security)。

## 4 · 此后的每一次发布

什么都不用做。打一个标签，其余交给 CI：注册表会自行发现已上架插件的新标签，
验证它，面板会显示它的状态。没有需要提交的东西，也没有需要通知的东西。一次
没有出现的发布，会在面板中你插件的页面上显示出来，带有它的状态和原因。

**每一次发布都会检查绑定，而不只是第一次。** 每一次都会对照它所打标签的提交
里的绑定行以及该上架的身份记录来读取，所以一个绑定行发生了变化、或者转给了
另一个所有者的仓库，会等待人工处理而不是直接发布 —— 正是这一点，让被盗的
令牌或被转移的仓库成为一件有人能看到的事。

## 上架并不意味着什么

上架不是一次安全审查。没有人会去读你的代码，注册表自己的政策也明确
这么说：一项权限决定的是守护进程会*为*插件做什么，而完全不涉及插件的
进程能对这台机器做什么。这里没有沙箱。参见
[安全模型](../1-orientation/security.md)。

## 今天的实际状态

有一件事，读者在按照本页操作之前应该知道。

**签名链已经贯穿到了目录(catalogue)本身，但还没有贯穿到撤回列表。** 具体来说，每一部分都是可以核实的：

- 根密钥两边都存在 —— `registry/v1/root.json` 携带
  `"status": "provisioned"`，以及两个 Ed25519 密钥，守护进程内编译进
  的 `PRODUCTION_ROOT_KEYS` 也是同样的两个；
- `registry/v1/trust.json` **现在已经**由 `astra-root-2026a` **签
  名**，并委托给一个索引签名密钥 `astra-index-2026a`。注册表自己的
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` 会确认
  这一点，并打印出 bot 在证明中会接受的那些可复用工作流 SHA 值 ——
  自 2026-08-19 标签移动以来共有两个：`plugin-release/v1` 现在指向的那个
  commit，以及它之前指向的那个。所以过去会拦住每一次摄入
  的 `E_TRUST_UNPROVISIONED`，现在已经不会再触发了；
- **客户端拿到的目录是已签名的。** 从 2026-09-20 起，注册表的签名器用
  `astra-index-2026a` 给 `index.json` 签名并把它部署到 Pages。提交在
  `main` 上的副本 `registry/v1/index.json` 和 `revocations.json` 是有意
  携带 `"signatures": []` 的，没有任何客户端读取它们。Pages 提供的撤回
  列表仍然是那份已提交的未签名列表，所以失效强制机制尚未生效。

参见 [`spec/registry-index.md` §0.1](../spec/registry-index.md) 和
[安全模型](../1-orientation/security.md)。

这对你意味着什么：本页描述的提交路径今天已经端到端可用 —— 你的
提交会被读取，各项检查会运行，面板会显示答复，一次上架会被提交。
仍然悬而未决的，是 Pages 上那份已签名的撤回列表，有了它，注册表才能从
已经装上的副本中撤回某个版本。等它落地之后，本页的内容不会有任何变化。

## 另请参阅

- [`spec/registry-index.md`](../spec/registry-index.md) —— 索引、失效列表，以及验证算法
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) —— bot 会从你的归档中读取什么
- [版本管理](../versioning.md) —— 数字的含义，以及一次弃用会持续多久
