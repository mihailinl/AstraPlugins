> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/spec/registry-index.md)。如与英文版有出入，以英文版为准。

# 已签名的注册表文档 —— 规范性规格说明

**状态：** 对文档格式和验证规则是规范性的。**尚未生效：** 这里描述
的签名链已经规定好，两端都已实现，但**尚未锚定**——在把本文件中的
任何一句话当作安全保证来依赖之前，请先阅读 §0.1。

四份文档，三种 schema，一种签名构造：

| 文档 | schema 字符串 | 由谁签名 | 本仓库中的拷贝 |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **无签名**——它是编译进 Astra 的密钥的一份抄本 | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | 一个 **root** 密钥 | 和目录一起发布 |
| `index.json` | `astra.registry.index/1` | `trust.json` 委托的一个 **index** 密钥 | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | 同一个 index 密钥 | `astra-registry/registry/v1/revocations.json` |

要求用语遵循 RFC 2119。

---

## 0. 这条链回答什么，不回答什么

它回答的是：*这份目录是不是 Astra 注册表发布的那一份，它是不是最新
的，其中是否有什么已被撤回？* 这是唯一能让一条缓存记录安全地用于安
装的东西，因为这条记录固定的是一个构件摘要，而摘要不会过期。

它**不**回答*插件是谁构建的*。那是 GitHub 的构建证明，在摄入
(ingest)时由注册表 bot 检查（§7），从来不是由守护进程检查。守护进
程持有的是注册表对作者的一次*断言*，在首次安装时被固定下来（TOFU）,
并绑定到下载 URL——见 §7.3。UI 文案必须说"和之前是同一个作者"，绝不
能说"已验证的构建"。

### 0.1 这条链目前尚未锚定——请先读这一段

* `astra-registry/registry/v1/root.json` 携带
  `"status": "provisioned"` 和两个 Ed25519 密钥。
  `astra-registry/SECURITY.md` §4 中的那套仪式
  （`tools/keygen-root.sh`）已于 2026-08-11 离线执行完毕。
* `astra-daemon` 的 `PRODUCTION_ROOT_KEYS` 列出了同样的两个。注册表
  这份拷贝是公开的，好让第三方不需要反汇编二进制文件就能读到它们，
  也好让两边一旦不一致就能被察觉；私钥的那一半从未出现在联网的机器
  上过。
* **一个根密钥并不会给目录签名。** 它给 `trust.json` 签名，而后者委
  托给一个索引签名密钥。**那份文档现在已经签好了。**
  `registry/v1/trust.json` 能在 `astra-root-2026a` 下通过验证，委托
  给索引签名密钥 `astra-index-2026a`，并指名了 bot 在构建证明中会
  接受的唯一那个可复用工作流提交
  （`e3329df252a46d747676cb540ae4b986af68a3ad`，也就是标签
  `plugin-release/v1` 所指向的那个）。注册表自己的
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` 会把
  这三个事实全部打印出来。所以 `E_TRUST_UNPROVISIONED` 在摄入时已
  经不会再触发了。
* 因此，今天的状态是：`trust.json` 能通过验证，一个索引密钥也已经
  被委托，但**还没有任何东西用它给目录签过名**。每一份目录仍然被归
  类为 `UNSIGNED`，但这次密钥仪式换掉了它携带的理由 —— 从
  `NoTrustAnchor` 变成了 **`NoSignatures`**。守护进程的
  `classify_signature` 把两者分得很清楚：`NoTrustAnchor` 意味着没有任何
  经过验证的 `trust.json` 到达这个构建，因此根本没有密钥可以用来校验签名，
  而目录本身很可能是签过名的；`NoSignatures` 意味着信任锚就在那里，而目录
  自己一个签名也没有。发生变化的是缺失的到底是哪一环：现在的缺口在被委托
  的密钥和索引之间，而不再是在根密钥和委托之间。
* `registry/v1/index.json` 和 `registry/v1/revocations.json` 提交
  时携带的是 `"signatures": []`——"未签名"被明明白白地说了出来，而
  不是让一个缺失的成员和一个被剥离的成员无法区分。
* 由此产生、绝不能被含糊带过的后果：一份未签名的目录永远无法把一条
  记录升级为"完全可信可安装"的状态，而且由于
  `verify_revocations_document` 是严格的（§6.4），**一份未签名的撤
  回列表会被拒绝，所以失效强制机制同样没有生效**——在成功获取过一
  份签名有效的列表之前，状态始终是
  `RevocationFreshness::NotEnforced`。

下面描述的一切都是格式和算法本身，等剩下的那一环落地时，这些内容
不会有任何变化。根仪式已经执行过了，委托也已经签好了；剩下的就是让
一个签名出现在某份已发布 `index.json` 的 `signatures` 数组里，到那
一刻，这条链才开始在用户的机器上产生实际分量。

## 1. 信封(envelope)

每一份已签名文档都有相同的外层形态：

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **只有 `signed` 是经过认证的。** 它之外的任何东西都不能被当作事实
  来读取——`$comment` 不行，`key_id` 字符串不行，签名列表自身的形态
  也不行。
* `sig` 是原始的 **64 字节 Ed25519 签名**的 base64 编码。index 的
  schema 固定了它的拼写形式：`^[A-Za-z0-9+/]{86}==$`。
* `key_id` 只是一个用于日志记录和密钥选择的**提示**。校验器**必须**
  用每一个受信任的密钥去尝试每一个给出的签名，并且**必须**报告实际
  验证成功的那个密钥的 `key_id`，而不是文档自己声称的那个。一份关于
  谁签署了它说了谎的文档，只要真的有一个受信任的密钥签过它，依然会
  通过验证；而只是点名了正确的密钥，永远无法让它通过验证。
* 一个空的 `signatures` 数组意味着未签名。这不是一种错误形态；这是
  举行仪式之前的状态，也是任何一份手写本地目录的状态。

## 2. 签名输入

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` 是该文档的 schema 字符串：`astra.registry.trust/1`、
  `astra.registry.index/1`，或 `astra.registry.revocations/1`。
* **校验器要从自己的常量中提供 `domain`，绝不能从它正在读取的文件的
  `schema` 成员中获取。** 否则，一份针对 `trust.json` 的签名，只需
  编辑一个字符串，就能被重放成一份针对 `index.json` 的签名——而任何
  能让一份目录被签名的人，都能借此发布一份*空的*撤回列表，把整套机
  制关掉。
* `0x00` 的作用是防止一个 domain 恰好是另一个 domain 的前缀时产生
  冲突。
* Ed25519 验证**应该**是严格模式（`ed25519_dalek::verify_strict`，
  或等价实现）：拒绝小阶(small-order)公钥，以及一个宽松的校验器会
  接受的可延展编码(malleable encoding)。
* 这个签名是针对 SHA-256 摘要计算的，作为一条普通消息传给 Ed25519。
  不要启用任何"预哈希"模式；Ed25519 内部会自己做哈希，而这个构造给
  它喂的是 32 字节。

这一点的两端都存在，并且通过测试保证一致：
`astra-registry/bot/lib/sign.mjs`（`signingDigest`、
`signEnvelope`、`verifyEnvelope`）和
`astra-daemon/src/plugins/trust.rs`（`signing_digest`、
`verify_envelope`）。`astra-registry/bot/fixtures/index/` 保存着一
份由 JavaScript 签名器产出、由 Rust 校验器逐字节核对的文档，所以两
边不可能在不让构建变红的情况下产生偏差。

## 3. 规范化（JCS 档案）

`JCS(signed)` 是 RFC 8785 规范化 JSON，附带一处刻意的收窄。

* **对象的键按 UTF-16 代码单元排序**（RFC 8785 §3.2.3）。这正是
  JavaScript 默认的 `Array.prototype.sort()` 所做的事，Rust 那一侧
  也是明确写出来的（`a.encode_utf16().cmp(b.encode_utf16())`），而
  不是假设按字节顺序排列。对于全 ASCII 的键，这两种顺序是一致的；
  超出 BMP 范围时就不一致了。
* **没有无意义的空白。** 采用紧凑形式。
* **字符串**按 RFC 8785 §3.2.2.2 的要求转义：转义 `"`、`\` 以及 C0
  控制字符（存在简写形式的用简写），`/` 和所有非 ASCII 字符保持为
  字面的 UTF-8。
* **数字必须是 ±(2^53 − 1) 范围内的整数**——也就是 JavaScript 的
  `Number.MAX_SAFE_INTEGER`。两份实现都**拒绝**其他任何情况，而不
  是去实现 §3.2.2 那套浮点数规范化。注册表只发出整数
  （`serial`、`size`、`protocol`），而一份把 §3.2.2*几乎*做对了的
  实现，会产出一种在一边能验证通过、在另一边却不能的签名。`1.0` 和
  `1` 是同一个 JSON 数字，两者都会被序列化为 `1`。
* **重复的对象键必须在解析时被拒绝**，而不是被消解掉（RFC 8785
  §3.1）。`{"a":1,"a":2}` 意味着两件事，而一份已签名的文档必须只意
  味着一件事。文档之后的多余字节出于同样的理由被拒绝。
* 值为 `undefined` 的成员并不存在；JSON 里没有这种东西。（注册表的
  序列化器会把它们丢弃；一个 JSON 解析器也从来不会产出这种值。）

仓库中提交的那份美化打印过的文件，是由*同一个*序列化器
（`stableStringify`）以相同的键序生成的，所以一个审阅者在读一份 diff
时，读到的（除了空白差异）就是将要被签名的那些字节。

## 4. 密钥、委托与轮换

### 4.1 Root

* Ed25519。公钥那一半**编译进 Astra**，是原始 32 字节的 base64 编
  码。
* **两个槽位**，在一次离线仪式中生成：一个是 `Active`，另一个是
  `Reserve`，在必须替换根密钥之前从不使用。两者从第一天起就一起出
  货，所以替换根密钥只是一次签名，而不是一个"标志日"。
* 一个根密钥**只给 `trust.json` 签名，别的什么都不签**。根签名永远
  不会出现在 `index.json`、`revocations.json`，或者某个包上。
* `root.json` 是一份抄本，不是一个权威来源：它是刻意未签名的——一份
  自签名的根文档，证明不了任何编译进去的密钥本身还没证明的东西。它
  存在的意义，是让这两份拷贝可以被互相比对。每个条目的
  `fingerprint_sha256` 是对原始 32 字节公钥计算的 SHA-256，小写十六
  进制表示；这和 `tools/keygen-root.sh` 打印出的值、以及守护进程在
  一次根签名验证通过时记录进日志的值是同一个。
* 存在专供测试用的根密钥（`astra-registry/tools/testkeys/`，私钥那
  一半是刻意提交进仓库的，`key_id` 带有
  `TEST-ONLY-DO-NOT-TRUST-` 前缀）。守护进程只有在**调试构建**下、
  且开启了非默认的 `insecure-test-trust-roots` feature 时才能编译
  进它们；在发布构建中请求这个 feature 会导致 `compile_error!`。

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

验证规则：

* `serial` **不得**为 0——0 是校验器一侧"目前还没接受过任何东西"的
  哨兵值，所以一份已发布的文档不能声称自己是 0。
* `schema` **必须**等于 `astra.registry.trust/1`。之所以要在检查签
  名之前先检查这个，纯粹是为了让一份归档错位的文档报出"schema 错误"
  而不是"没有根签过这个"；这不会改变最终结果，因为摘要的 domain 是
  校验器自己的常量。
* 未知的成员会被**保留并忽略**。一个更新的注册表新增一个字段，绝不
  能把一个更旧的守护进程弄崩；原始的、已验证的 `signed` 内容能原样
  经历一次往返，所以不会有任何东西被悄悄丢弃再重新签名。
* 一条 `index_keys` 记录如果带有无法解析的密钥或无法解析的时间窗
  口，会被**带一条警告跳过**，而不是致命错误：一行坏数据不应该赔上
  一份本可以被另一个密钥验证通过的目录。一个无法解析的 `not_before`
  会被当作*尚未生效*处理，一个无法解析的 `not_after` 会被当作*已过
  期*处理——对单行数据是安全失败(fail closed)，对整份文档则是安全
  放行(fail open)。
* `reusable_workflow_shas` 是**注册表 bot**强制执行的（§7）已解析
  可复用工作流 commit SHA 白名单。守护进程会携带它，但不会使用它。
  修改它需要一次根密钥仪式，这正是把它放在这里的全部意义。

**轮换。** 每季度轮换一次，出现可疑情况时立即轮换。一次有计划的轮
换会发布一份 `trust.json`，其中即将退出和即将启用的密钥拥有**重叠
30 天的窗口期**，所以在换岗期间，`index_keys_valid_at(now)` 返回两
个密钥是正常状态，而不是异常。

### 4.3 由哪个时钟来判定密钥窗口

存在两种时钟读数：这台机器自己的，以及产出这份文档那次抓取的 HTTP
`Date`。

* **新鲜度**（§5）的判定用的是 `now = server_date ?? local`——在一
  次抓取的有效期内，相信注册表给出的读数。这不会给攻击者带来任何他
  们原本没有的能力（他们本来就可以给一台自己无法控制其时钟的机器提
  供一份过期文档），却能拯救更常见得多的情形：一台时钟不准的笔记本
  电脑被告知自己的目录已经过期了。
* **密钥有效窗口**的判定用的是 `window_now = max(local, server)`
  ——网络可以把"现在"往*前*拉，但**永远**不能把它往*后*推。
  `not_after` 是唯一能让一个被攻陷的索引密钥退役的机制；如果按网络
  提供的某个瞬间来判定它，就等于让窃取者也能通过给出一个旧的 `Date`
  来永远自选那一天。取较晚的那个读数，能让一个被盗且已退役的密钥，
  无论攻击者控制的是哪一种读数，都变得*更加*过期。
* 超过 **2 小时**（`CLOCK_SKEW_TOLERANCE_HOURS`）的不一致，本身就
  是一个信号：这时的判定结果是 `CLOCK_SKEW`，而不是关于文档本身的
  某种断言。这个阈值足够小，能让一颗没电的 CMOS 电池立刻触发它；也
  足够大，不会被普通的、没有 NTP 校时的时钟漂移触发。
* 任何从时钟写入的**持久性**数据（最近一次抓取的时间戳、下限值）都
  会先被夹紧(clamp)到本地时钟。否则，一次带着
  `Date: Fri, 01 Jan 2100 …` 的响应，就会把一个守护进程对"现在"的
  认知永久移到 2100 年——这是任何一个能应答一次抓取的人都能写入的、
  持久性的拒绝服务攻击。

## 5. `index.json`

### 5.1 形态

`signed` 的内容是：

| 成员 | 类型 | 规则 |
|---|---|---|
| `schema` | 常量 `astra.registry.index/1` | 必需 |
| `serial` | integer ≥ 0 | 必需，单调递增（§5.4） |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | 在**签名时**盖上，在提交进仓库的树里不存在 |
| `expires_at` | 同上 | `issued_at + 30 天` |
| `plugins` | array | 每一个上架插件对应一条记录，按 `id` 排序 |

时间戳是 RFC 3339 UTC 格式，**精确到秒，没有毫秒，没有偏移量**。同
一个瞬间的两种拼写方式，是两份不同的已签名文档。

一条插件记录携带 `id`、`name`、`version`、`description`、
`license`、`capabilities`、`repository_url`、`source`、`icon_url`、
`downloads`、`stars`、`updated_at`、`download_url`、
`platform_downloads` 和 `releases[]`。完整的 JSON Schema 是
`astra-registry/schema/index-v1.json`；它是
`additionalProperties: false` 的，是字段列表的权威来源。

有两条规则值得重新强调，因为校验器依赖它们：

* **`releases[]` 是权威的那一半**，按 semver 优先级由新到旧排列。
  每个 release 都有 `version`、`published_at`、`release`
  （`{kind: "github_release", repo, tag}` 或
  `{kind: "direct", base_url}`）和 `artifacts`（平台键 →
  `{url, filename, sha256, size}`）。
* **扁平字段是 `releases[0]` 的一个投影**，在同一次生成器运行中计
  算出来，所以不可能和它产生分歧。`version`、`platform_downloads`
  和 `download_url` 之所以存在，是因为正在出货的守护进程读取的恰好
  就是它们。

平台键：`linux-x64`、`windows-x64`、`noarch`，外加保留的
`linux-arm64`、`windows-arm64`、`macos-x64`、`macos-arm64`。一个
`noarch` 构件会被写在**每一个受支持的平台键**下面，所以任何客户端
都不需要专门知道这个词
（`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`）。

`downloads` 和 `stars` 永远是 `0`。这个注册表什么都不计数。

**Staging 条目**——一个发布记录在纸面上存在、但还没有构件摘要的上
架条目——会被标记为 `staging: true`，**从 `platform_downloads` 和
`download_url` 中被省略**，并且从结构上就是无法安装的：没有摘要，
就没有安装。

### 5.2 构件摘要，以及 URL 可以指向哪里

`artifacts.<key>.sha256` 是整个 `.astraplugin` 文件的 `sha256`——和
构建证明的主体、以及守护进程所哈希的是同一个数字
（[`bundle-v2.md` §3.1](bundle-v2.md#31-构件摘要artifact-digest)）。`size`
是那个文件的长度；schema 把它的上限定在 256 MiB。

每一个构件 URL **必须**是 `https://`，并且**必须**位于其自身
`release` 对象所隐含的前缀之下：

* `github_release` → `https://github.com/<repo>/releases/download/<tag>/`，
* `direct` → 该 release 的 `base_url`，

并且**必须**以声明的 `filename` 结尾。这是在
`astra-registry/tools/validate.mjs` 中强制执行的，而不是靠 schema
的一个 pattern 来做，因为一个只能描述 GitHub 情形的 pattern，会让自
托管的情形根本无法表达。`direct` 是为自托管和 staging 目录而存在
的；政策把它排除在公开目录之外。

### 5.3 确定性——审计者所依赖的那个特性

`index.json` 的 `signed` 成员是由 `tools/build-index.mjs` 从
`plugins/**` 生成的，并且**不读取任何时钟**：相同的源 + 相同的
serial → 相同的字节。键按 UTF-16 代码单元排序，插件按 id 排序，
release 按 semver 排序。如果提交进仓库的文件哪怕有一个字节不同，
`--check` 就会失败，而 CI 会运行它。

`issued_at`/`expires_at` 是由 `bot/sign-index.mjs` 在签名时添加的，
而不是由生成器添加的，原因有两个：它们是*发布*本身的属性，而且一个
会读时钟的生成器是无法被复现的。正是这一点让 §8 的审计成为可能——第
三方能够从 git 树重新构建出目录内容，并把它和被签名的内容进行比对。

### 5.4 Serial

* **单调递增**，从默认分支上的
  `git rev-list --count HEAD -- plugins` 推导而来。绝不从文件中读
  取再自增：同一分钟内的两次合并都会读到 *N*，都会写入 *N+1*，第二
  次会悄悄撤销第一次的增量。commit 数量是历史本身的一个属性，所以
  并发的合并在结构上就会得到不同的值。限定路径意味着一次文档提交不
  会推动目录的版本号。
* 一个校验器会为每个目录 URL 保留一个**serial 下限**，任何低于它的
  都会被拒绝。这个下限是 `max(in-memory, on-disk)`，存在于守护进程
  拥有并做过 MAC 保护的状态中（`astra.registry.state/1`），**而不
  是**在索引缓存里：缓存是一种随时可能被删除的便利手段，而这个下限
  是一项必须能够在攻击者恰好会执行的那种删除动作中存活下来的安全决
  策。它是*在代码中*单调递增的，所以损坏那份状态文件只会重置文件本
  身，不会重置正在运行的进程。

三份文档，三条 serial 规则，它们之间的差异是刻意为之的：

| 文档 | 何时被接受 | 原因 |
|---|---|---|
| `trust.json` | **严格大于**当前持有的值 | 它只会在密钥轮换时改变，所以"相同 serial、不同字节"除了是一次回滚攻击，不可能是别的 |
| `index.json` | **不低于**下限 | 常规的重新发布 |
| `revocations.json` | 磁盘上的值**大于等于**；**严格大于**的 serial 会替换整个集合，小于等于的 serial 只能**新增**条目 | 这份列表按计划会被重新签名以维持在它 7 天的窗口内；如果拒绝相等的 serial，会导致每一个平静的星期都拦住安装。"相同 serial、更少条目"是一次重放攻击，而只允许新增能击败它 |

状态文件上的 MAC 是一根**绊线，而不是一道边界**：它的密钥和它所认
证的文件位于同一个 0700 目录中，所以一个能读那个目录的攻击者就能伪
造它。它把门槛从"编辑一个文件"提高到了"找到并使用那个密钥"。真正的
边界是那个目录本身——它是 `plugins/` 的兄弟节点，绝不是它的子节点，
所以这些决定的对象，不会同时也是它们的作者。

### 5.5 新鲜度，以及那个最重要的不对称性

| 文档 | TTL | 陈旧的代价 |
|---|---|---|
| `index.json` | **30 天**（`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`） | 一条**横幅提示**。浏览界面会说这份目录已经过期。**已缓存、由摘要固定的记录依然可以安装。** |
| `revocations.json` | **7 天**（`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`） | 对新安装的**硬性拦截** |

这种不对称性就是整个新鲜度策略，它是从每份文档的用途中推导出来的。
一条目录记录是一个*摘要*，摘要不会过期：一个冻结注册表、让你继续持
有一条你早已验证过的记录的攻击者，什么都得不到。撤回列表则相反——
在那里"继续"意味着"继续安装某个我们可能已经撤回的东西"——所以那一
份才是拦截的对象：

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

注意最后一句话。陈旧从来不会让一个已经在运行的插件停下来。

一个合规客户端会发出的判定代码，按严重程度从高到低排列
（`IndexVerdict::code`）：

| 代码 | 含义 |
|---|---|
| `SIGNATURE_INVALID` | 提供了签名，但没有一个是由受信任的密钥做出的。**唯一意味着篡改的代码。** 得出这个结论不涉及任何时钟，所以任何时钟都无法为它开脱。 |
| `SIGNATURE_KEY_EXPIRED` | 一个被委托的密钥签署了它，但超出了它的有效窗口，判定时手头握有一个服务器 `Date`（所以时钟偏差不是一个借口） |
| `CLOCK_SKEW` | 这台机器的时钟和文档的时间戳不可能同时都是对的，而签名验证通过了——所以嫌疑落在时钟上 |
| `CATALOG_STALE` | 已经超过 `expires_at` |
| `FRESHNESS_UNKNOWN` | 既没有 `issued_at` 也没有 `expires_at`——一份手写的本地目录 |
| `UNSIGNED` | 没有签名，或者没有信任锚点可以用来校验它们 |

`SIGNATURE_INVALID` 和 `SIGNATURE_KEY_EXPIRED` 是**拒绝**：这份文
档根本不会被读取，也不会为它提供任何缓存回退方案。`UNSIGNED` 不是
一次拒绝——它是这个世界举行仪式之前的状态，也是每一份本地目录的状
态——但它永远无法把一条记录升级为完全可信的状态。

一份文档**是从哪里取来的，从来都不是一项输入**。一份目录之所以被
信任，是因为一个被委托的密钥给它签了名；`plugins.registry_url` 只
是普通的配置项，目录本来就被预期会更换主机。守护进程的验证路径中不
包含任何主机名检查，也绝不能长出这样一个检查。

## 6. `revocations.json`

### 6.1 形态

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

由 `tools/build-revocations.mjs` 从
`astra-registry/tools/revocations/` 下的每一个建议(advisory)文件生
成而来；一份建议会为它点名的每一个键都变成一条记录，每一条记录都携
带这份建议的 id、severity、action、reason 和 URL，因为客户端只会展
示其中恰好一条——第一条匹配上的——所以每一条都必须能独立成立。各条
记录按 `(kind, value)` 排序，所以这份文档是确定性的。

### 6.2 kind 词汇表

`astra-daemon/src/plugins/trust.rs` 中的 `RevocationKind` 是权威来
源；注册表的 `KINDS` 表存在的意义，是让注册表不可能发布出一种守护
进程会悄悄忽略掉的 kind——一个未知的 kind，就是一次不会真正发生的
撤回。

| kind | `value` | 匹配对象 |
|---|---|---|
| `digest` | 64 位小写十六进制 | 整个 `.astraplugin` 的 `sha256`，不区分大小写比较 |
| `binary` | 64 位小写十六进制 | 一个**已解析的 `entry.command` 文件**的 `sha256` |
| `id` | 插件 id | 该插件的每一个版本 |
| `id_version` | `<id>@<semver>` | 那一个确切的 release |
| `version_range` | 插件 id + `versions` 窗口 | 见 §6.3 |
| `identity` | `github:owner/repo` 或 `origin:host` | 一个被固定的发布者身份 |
| `publisher_key` | 一个密钥 id | 某条信任记录的 `signer_key_id` |

`action` 是 `block_install`、`disable` 或 `warn` 之一。`warn` 不会
阻止安装；`disable` 还会停止并禁用一份已经安装好的副本。`severity`
（`critical` / `high` / `moderate` / `low`）只是建议性的——没有任何
行为依赖于它。

`reason` 会**原样**展示给用户，出现在一条被守护进程标记为持久性的
通知里，所以生成器会拒绝任何包含双向文字覆盖(bidi override)或零宽
连接符的文本，并把它限制在 300 字符以内。

### 6.3 版本窗口

采用 OSV 的形态和 OSV 的语义：`introduced` 是**包含**的，`fixed`
是**不包含**的，两者都是可选的，`{}` 表示所有版本——这使得
`version_range` 成为 `id` 的一个严格泛化。`introduced == fixed` 什
么都覆盖不到，会在构建时被拒绝。

排序遵循标准的 semver 优先级，所以 `1.0.0-rc.1 < 1.0.0`：一份说"在
1.0.0 中修复"的建议，绝不能让 `1.0.0-rc.1` 逃过撤回。构建元数据会
被忽略（semver §10）。**任何一方都无法解析的版本字符串，都算作在窗
口*之内***——另一种选择是让 `version = "totally-fine"` 溜过一份建
议本可以表达的任何边界，而攻击者会去选择那样的字符串。

### 6.4 验证是严格的，和目录不同

`verify_index_document` 返回一个分级的判定；`verify_revocations_document`
返回 `Err`。没有信任锚点、没有签名、来自一个陌生人的签名，或者来自
一个超出有效窗口的密钥的签名，全都是失败。撤回列表存在的唯一目的
就是用来*拒绝*某样东西，所以一份没有人能归属其来源的文档，只有一种
安全的解读——"这不是一份撤回列表"——把它当作一个空集合返回，正是攻
击者最想要的结果，而这只需要提供任意一个文件就能达到。

一份无法使用的列表，会在再上一层被处理，靠的是那个 7 天的拦截
（§5.5）。正是这一点，而不是一个宽松的解析器，才是防止一次注册表故
障演变成强制机制悄然失效的关键。

一份缓存下来的列表**每次加载时都会被重新验证**，绝不会因为"这个守
护进程自己曾经写过它"就被信任——正是这一点让缓存的副本能够成为安装
级别的输入，也是为什么一次密钥轮换会在退役一份实时列表的同一时刻，
也退役掉缓存的那一份。

### 6.5 侧载缺口，在源头被堵上

一份只按摘要键入的建议，默认会留下一个漏洞：按摘要撤回，而用户可以
先卸载（这会丢掉那份摘要曾经从中读取出来的信任记录），把
`plugin.toml` 和二进制文件复制进一个目录，然后侧载同样的代码。一个
目录没有归档，所以它没有包摘要，也没有签名者。

因此生成器会**拒绝一份每一条记录都只按目录不可能拥有的东西键入的建
议。** 至少要有一条记录属于 `binary`、`id`、`id_version` 或
`version_range` 这几种 kind 之一。`identity` 和 `publisher_key` 明
确不计入这个要求。

有五个强制执行点会消费这份列表：安装（计划文档 §5.3-A.4）、更新解
析、导入路径、侧载路径，以及按记录下来的 `artifact_sha256` 对这份
列表和已安装插件做的定期交集检查。

## 7. 来源验证——注册表能检查、而守护进程无法检查的事

### 7.1 摄入时（注册表 bot，`bot/lib/attestation.mjs`）

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`。这能证明那个仓库中的某个工作流构建了这些字节，
   并且 Sigstore 记录下了这一点。
2. **构建证明的主体摘要必须等于该构件的 `sha256`**——这是这个数字
   出现的三个地方中的第三处（`E_ATTESTATION_SUBJECT_MISMATCH`）。
3. 证书的源仓库必须是 `https://github.com/<repo>`
   （`E_ATTESTATION_REPO_MISMATCH`）。
4. **已解析的可复用工作流 commit SHA** 会从证书中被读出来，并且必
   须出现在 `trust.json` 的 `reusable_workflow_shas` 中
   （`E_WORKFLOW_NOT_ALLOWED`）。SHA 缺失是一次失败，而不是一个默
   认值（`E_ATTESTATION_INVALID`）。

第 4 步正是让一个可变的 `@v1` 标签无法被用作供应链的关键：一个标签
可以被重新指向任意一个 commit，而构建证明依然会正确地指名那个仓库
和工作流文件。修改这份白名单需要一次根密钥仪式。

那份白名单现在已经存在了：已签名的 `trust.json` 恰好指名了一个
commit，`e3329df252a46d747676cb540ae4b986af68a3ad`。所以
`E_TRUST_UNPROVISIONED` 已经不会再阻止摄入过程了，第 4 步已经在生
效——由任何其他工作流产出的构建都会被以 `E_WORKFLOW_NOT_ALLOWED`
拒绝。守护进程这一侧依然出于另一个原因保持 fail-closed：目录本身还
没有携带任何签名（§0.1）。

### 7.2 尚未实现：按发布计算的副签名

`PRODUCTION_PLAN` §5.2 规定了一种针对以下内容的、按发布计算的副
签名

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**今天没有任何东西会计算或检查这个。** 这个字符串出现在计划文档中，
但没有出现在这三个仓库中的任何一个里。一条记录的真实性目前来自覆盖
整个目录的那个索引信封签名。请不要按照这一节去实现一个校验器，并期
待能找到这样一个字段。

### 7.3 守护进程转而做的事

守护进程**不**做任何 Sigstore 验证：构建证明是在 bot 的 CI 中检查
的，那里网络、GitHub API 和 `gh` 全都具备。在本地，它做两件事，而正
是这两件事的组合，才把一次注册表密钥的泄露限定在"只能发布新插件"这
个范围内：

* **TOFU 锁定。** 在首次安装时，它会记录下上架条目声明的身份
  （`{kind: "github", repo}` 或 `{kind: "origin", host}`）。一次身
  份不一致的更新，是一次**永远没有覆盖余地的硬性拦截**。
* **URL 与身份的绑定。** 构件 URL 必须位于被固定的仓库的发布命名空
  间之下，在重定向解析完成后按主机名和路径前缀比对。这个身份是记录
  **声明**的那个仓库，而绝不是 URL 隐含的那个仓库——从 URL 推导身
  份，会让这项检查在首次安装时变成同义反复。

剩余风险，之所以要说出来，是因为 UI 不能夸大其词：`identity` 是注
册表断言的一个字符串。一个被攻陷的索引密钥，可以发布一条身份属实、
但溯源信息块是伪造的记录。URL 检查强制字节内容必须来自被固定仓库的
发布命名空间；而一次仓库加注册表的组合攻陷，可以同时打败这两道防
线。

## 8. 审计流程

已发布目录中的一切，都可以由一个没有任何私钥访问权限的第三方来验
证。以下就是这个流程。标记为**tooling**的步骤在 `astra-registry`
中有对应的脚本；标记为**manual**的步骤目前还没有，
`PRODUCTION_PLAN` §5.5 中提到的
`registry/tools/audit-index.sh`**今天并不存在**——这里把它描述为它
将来会自动化实现的那个流程。

**A. 重新生成目录内容。** *(tooling)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

然后把已发布的 `signed` 成员和重新生成的那份进行比对，只忽略
`issued_at` 和 `expires_at`（§5.3）。任何其他差异，都意味着这份目录
和它自己的 git 历史对不上。

*今天这一步会打印出什么*（本文档撰写时验证过）：两次 `--check` 运
行都在 serial 1、0 个签名的状态下报告"和一次全新生成逐字节相同"，
而 `validate.mjs`**会失败**——全部十一个上架条目都是没有构件摘要的
staging 条目，除非传入 `--allow-staging`，否则会被拒绝。对于一份插
件都还没发布过的目录来说，这就是正确答案，也正是其中没有任何东西能
够被安装的原因。

**B. 检查签名链。** *(tooling)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

然后手动确认 `trust.json` 能在 `registry/v1/root.json` 中某个密钥
下通过验证，且该密钥的指纹和你 Astra 二进制文件记录的日志一致。如
果你愿意，也可以独立地重新计算：`SHA-256(domain ‖ 0x00 ‖
JCS(signed))`，按 §2–§3 做 Ed25519 验证。

*今天这一步会打印出什么：* `FAIL … no trusted key was supplied
(offered: none; trusted: none)`——没有 `trust.json` 可以传入，也没
有 root 可以用来验证它（§0.1）。任何针对当前这棵树报告出别的结果的
校验器，都是在说谎。

**C. 检查 serial 和窗口。** *(manual)* `serial` 必须大于等于你上次
看到的那个值；`expires_at − issued_at` 对目录必须是 30 天，对撤回
列表必须是 7 天；`key_id` 必须是 `trust.json` 所指名的、其窗口包含
`issued_at` 的那个密钥。

**D. 对照公开的透明日志检查每一个构件。** *(manual)* 对索引中的每
一个 release——`<…>` 是从索引记录中读取出来的占位符，所以下面这两
条命令是一个模板，而不是可以直接复制粘贴的：

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` 是**作者的**仓库，来自索引记录中的 `release.repo`。
`--signer-workflow` 是构建它的那个**共享的可复用**工作流——正是
`astra-plugin init-ci` 把调用方固定住的那一个，bot 把它保存为
`astra-registry/bot/ingest.mjs` 中的 `DEFAULT_SIGNER_WORKFLOW`，并
针对 `AstraPlugins/.github/workflows/` 中存在的一个文件进行断言。
请从那个常量中取用确切的字符串，而不是自己重新拼出来；一个位置颠倒
的路径不会匹配任何构建证明，会让每一个诚实的构件看起来都像是没有证
明。

`gh attestation verify` 会为那个构件摘要获取对应的 Sigstore bundle，
并把它拿去和 Sigstore 的信任根做校验，**包括 Rekor 透明日志的包含
证明**。从它的 JSON 输出中，手动断言 bot 在摄入时（§7.1）所断言的
内容：主体摘要等于该文件的摘要，源仓库是索引所指名的那个仓库，以及
被解析出的 signer-workflow commit SHA 存在于 `trust.json` 的
`reusable_workflow_shas` 中。

一条注册表为某个**没有**构建证明、或者其证明指名了不同仓库的构件所
发布的记录，正是这个流程存在的意义所要事后侦测的东西：没有任何东西
能阻止一个被攻陷的注册表密钥去发布一个*新*插件，可审计性就是缓解措
施的全部。

**E. 检查包本身。** *(tooling)* 对下载下来的文件运行
[`bundle-v2.md` §13](bundle-v2.md#13-验证算法)，
并确认它 `MANIFEST.json` 中的 `plugin_id`、`version`、`platform` 和
`permissions_hash` 与索引记录一致。

## 9. 今天已生效内容的汇总

| 属性 | 状态 |
|---|---|
| 文档格式、信封、签名构造、JCS 档案 | 两端都已实现，通过测试夹具交叉测试过 |
| 根密钥 | 已于 2026-08-11 **完成配置**——两端是同样的两个密钥 |
| `trust.json` | 已在 `astra-root-2026a` 下**签名**，委托给 `astra-index-2026a`，并把一个工作流 commit 加入白名单 |
| `index.json` / `revocations.json` 的签名 | 在提交进仓库的树中是空数组——**这正是目前缺失的那一环** |
| 目录判定、serial 下限、新鲜度、时钟处理 | 已在守护进程中实现，并有测试覆盖 |
| 失效词汇表、匹配逻辑、五个强制执行点 | 已实现；**在成功获取过一份签名有效的列表之前不起作用** |
| 摄入时的构建证明检查 | 已实现且正在生效；工作流白名单来自已签名的 `trust.json` |
| 按发布计算的副签名 | 仅在计划文档中规定；**没有实现** |
| `audit-index.sh` | 不存在；§8 是手动流程 |

---

*编写本文档时核实过的来源：
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`；
`astra-registry/tools/lib/canonical.mjs`；
`astra-registry/tools/lib/revocations.mjs`；
`astra-registry/tools/build-index.mjs`；
`astra-registry/bot/lib/sign.mjs`；
`astra-registry/bot/sign-index.mjs`；
`astra-registry/bot/lib/attestation.mjs`；
`astra-registry/registry/v1/{root,index,revocations}.json`；
`astra-registry/SECURITY.md`；
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`；
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`；
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs`
（`refresh_revocations`）。*
