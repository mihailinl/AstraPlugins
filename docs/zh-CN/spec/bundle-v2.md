> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/spec/bundle-v2.md)。如与英文版有出入，以英文版为准。

# `.astraplugin` 包格式，版本 2 —— 规范性规格说明

**状态：** 规范性的。本文档定义的是字节内容本身。它的编写方式，让一个
从未见过本仓库的第三方，仅凭这份文档就能实现一个校验器，并且对
[`testdata/bundles/`](../../../testdata/bundles/README.md) 中的每一个
文件都得出和我们一样的判定。

**Schema 字符串：** `astra.bundle/2`
**文件扩展名：** `.astraplugin`
**媒体类型：** 未注册；以 `application/octet-stream` 提供服务。

要求用语 —— **MUST**、**MUST NOT**、**SHOULD**、**MAY** —— 遵循
RFC 2119。"拒绝"（Reject）的意思是：整体拒绝这个包，不解压，也不回退
到任何更早的格式。这个格式里没有"部分接受"这回事。

---

## 0. 这个格式是什么，不是什么

一个 v2 包是一个 ZIP 归档，其**第一个条目是一份清单，指名并计算了每一
个其他条目的摘要**。这就是整个想法的核心。它换来了一样 v1 包（一个内含
`plugin.toml` 的普通 ZIP）换不来的东西：读取者在还没有信任归档自身
结构的任何一部分之前，就能知道这个归档*被允许*包含什么，落到磁盘上的
每一个文件都会被拿去和那份清单核对。

这个格式刻意**不做**的三件事，写在这里，是为了不让读者仅凭摘要的存在
就推断出这些东西：

* **它不携带自身的真实性(authenticity)证明。** v2 包内部没有任何东西
  能证明是谁产出了它。真实性来自文件之外：一份针对
  `sha256(整个文件)` 的 GitHub 构建证明，以及一份固定了同一个数字的
  已签名注册表索引（[`registry-index.md`](registry-index.md)）。旧式
  的 ZIP 内 `SIGNATURE`/`PUBKEY` 对（§11）*不是*例外——它正在被淘汰，
  从来都不是信任信号。
* **它对插件在运行时可以做什么，只字未提。** 那是
  [`permissions.md`](permissions.md) 的范畴。
* **它不是沙箱边界。** 一个已安装的插件是一个以用户完整权限运行的原生
  进程。校验一个包只能告诉你这些字节就是作者发布的那些字节；它不会
  约束这些字节运行起来之后会做什么。

## 1. 一致性，以及哪份实现是规范性的

有三个程序会读取这个格式：

| | 实现 | 角色 |
|---|---|---|
| **CLI** | `astra-plugin-cli/src/bundle.rs`（`BundleBuilder`、`Bundle::open`） | 写出包；`astra-plugin verify` 把它读回来 |
| **daemon** | `Astra/astra-rs/astra-daemon/src/plugins/bundle.rs`（`inspect`、`BundleManifest::check_structure`）+ `ops/install_plugin.rs`（`extract_archive`） | 决定一个陌生人的字节是否会被解压到用户的磁盘上 |
| **registry** | `astra-registry/bot/lib/bundle.mjs`（`inspectBundle`） | 决定一次上架是否被公开 |

**这份文档是规范性的；三个实现都不是。** 当某个实现和这份文本产生
分歧时，是那个实现有 bug。当两个实现彼此产生分歧时，这种分歧会作为一
个有名字的差异记录在 `testdata/bundles/vectors.json` 中，并在 §14 复
现——那里的 `verdict` 字段才是正确答案，`expect` 字段是每个程序今天
实际的行为。

对第四份实现的启示：**去实现 §13，而不是照搬这三个程序中的任何一
个。** 一个精确复刻守护进程的校验器会继承分歧 F2；一个精确复刻注册表
的会继承 F3。

## 2. 容器

* 一个包**必须**是一个能被常规读取器读取的 ZIP 归档：从偏移量 0 开始
  的本地文件头、一个中央目录（central directory）、一条中央目录结束
  记录。
* **条目零不得使用 ZIP64。** 一个本地头中声明了 ZIP64 大小哨兵值
  `0xFFFFFFFF` 的 `MANIFEST.json` 会被拒绝（§4）。其他条目没有声明
  的 ZIP64 限制；一个大到那种程度的清单文件已经不是清单文件了。
* 条目**只能是文件**。目录条目会被拒绝（§6.5）：目录是由路径隐含出来
  的，无法携带摘要。
* **条目零必须是 `MANIFEST.json`，以存储方式（压缩方法 0）保存。**
  其他每一个条目**可以**使用方法 0（存储）或方法 8（deflate）。CLI
  会把清单文件之外的所有内容用级别 6 的 deflate 打包；
  `testdata/bundles/` 中的向量则全程使用存储方式。两者都是符合规范的。
* 顺序：`MANIFEST.json` 在最前；旧式的 `SIGNATURE`/`PUBKEY` 对（如果
  存在）在最后，且按这个顺序（§11）；其余的位于中间。生产者*应该*
  按路径的字节字典序写出中间部分——CLI 就是这么做的，因为它的条目
  保存在一个 `BTreeMap` 中——但校验器**不得**要求这一点。*清单文件*
  的 `files` 数组是排过序的，这一要求是强制的（§7.4）；归档本身的
  顺序则不是。
* 时间戳没有任何含义。CLI 会给每个条目盖上 `1980-01-01T00:00:00`（
  DOS 时间戳能表达的最早日期），这样相同输入的两次构建会产出相同的
  字节。校验器**不得**读取时间戳。

## 3. 两种摘要

这个格式中恰好存在两种摘要构造方式。两者都是 SHA-256，都渲染为
**64 个小写十六进制字符**，且都不会以不区分大小写的方式进行比较。

### 3.1 构件摘要(Artifact digest)

```
artifact_digest = SHA256(the entire .astraplugin file, byte for byte)
```

没有规范化，没有遍历条目，没有排除项。这是一个恰好出现在三个地方的数
字，而且在这三个地方都是同一个数字：

1. GitHub 构建证明的主体(subject)，
2. 已签名注册表索引中的 `artifacts.<platform>.sha256`，
3. 守护进程在打开归档之前所流式读取并哈希的内容。

它被裸露地写出（不带 `sha256:` 前缀），因为它出现的每一个地方本身
都已经是有类型的。

### 3.2 清单摘要(Manifest digest)——以及为什么要做域分离(domain-separated)

```
manifest_digest = SHA256( "astra.bundle/2" ‖ 0x00 ‖ MANIFEST.json bytes )
```

前缀是 14 个 ASCII 字节 `astra.bundle/2`，后跟一个 `0x00` 字节——总共
15 字节——紧接着是条目零*存储时*的字节内容，完全按照它在归档中的样子，
不重新序列化，不做空白规范化，也不做尾随换行调整。

**为什么要有这个前缀。** 没有它，这个构造就是 `SHA256(某些字节)`——
这恰好和同一份文档中每一个 `files[].sha256` 的形态一模一样。这两者
会变成流经同一批记录、却无法区分的 64 位十六进制字符串，一个从某个
上下文中取出的值会在另一个上下文中"验证通过"。这个前缀让清单摘要成为
了对同一批字节的一个不同函数。

**具体示例**（向量 `ok-minimal`，可用
`testdata/bundles/handcheck.sh ok-minimal` 复现，它只用到 `dd`、
`od`、`printf`、`cat` 和 `sha256sum`）：

```
sha256(manifest bytes)                    2e16024e4557332a2a404a89a94b124807e0b4741046e29fc3f6b94ea1b69682
sha256("astra.bundle/2\0" ‖ manifest)     8e88f82cc6dbb9c253e3a4409a03f763668ca1a46439f994e2a45a6da23ccaf4
sha256(whole file)                        ac3d49a2fc2b7408d5b3c805ec91541510c272547a16e3bc7a30f269ba801aed
```

一个在应该产出第二个值的地方产出了第一个值的实现，忘记了这个前缀。
`vectors.json` 为每一个向量都记录了这两个数字（`manifest_sha256` 和
`manifest_digest`），所以这只是一行检查的事，而且这两者在任何真实的
清单文件上都**永远不会**相等。

### 3.3 已退役的构造方式，以及让它退役的那次碰撞

在 v2 之前，一个包是靠一个针对以下内容的 ZIP 内 `SIGNATURE` 来认证的

```
legacy_digest = SHA256( name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ … )
```

按 ZIP 索引顺序，跳过 `SIGNATURE` 和 `PUBKEY` 本身。没有分隔符，没有
长度前缀，没有条目计数，没有域分隔符(domain separator)。那种构造方式
是**有歧义的**，而这种歧义就存在于本仓库中，以两个被冻结的文件的形式：

| 向量 | 归档持有的内容 | 贡献的部分 |
|---|---|---|
| `collision-a-bc` | 条目 `a`，内容 `bc` | `a` ‖ `bc` = `abc` |
| `collision-ab-c` | 条目 `ab`，内容 `c` | `ab` ‖ `c` = `abc` |

这两个归档携带**逐字节完全相同的 `MANIFEST.json`**，因此拥有相同的
`manifest_digest`；它们的构件摘要不同；而它们的旧式摘要却是同一个
数字：

```
legacy_concat_sha256   0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   (both)
```

一个 `SIGNATURE` 同时认证了两个归档，使用那种方案的校验器无法分辨自
己手里拿的到底是哪一个。

在 v2 下它们被区分开了，而这需要网罗性检查**两个方向都做**才能实现
（§7.1）：在 `collision-ab-c` 中，`ab` 是一个没有任何清单行覆盖的
归档条目，*同时*，`a` 是一个没有任何归档条目满足的清单行。一个只检查
"listed ⇒ present" 的校验器会接受它。

`legacy_concat_sha256` 被记录在 `vectors.json` 中，仅用于这一个目的。
本项目中的任何东西都不应该为了其他任何目的去计算它。

## 4. 条目零，逐字节说明

一个合规的读取器**必须**能够从文件的前缀部分获取 `MANIFEST.json`，
不解压任何东西，也不读取中央目录。这正是让读取器能在信任任何攻击者
控制的结构之前，就了解归档被允许包含什么的那个特性。三份实现都恰好
是这么做的（CLI 和守护进程中的 `manifest_from_local_header`，注册表
中的 `manifestBytesFromLocalHeader`）。

读取偏移量 0 处的本地文件头。所有多字节字段都是小端序(little-endian)。

| offset | size | 字段 | 要求 |
|---|---|---|---|
| 0 | 4 | 签名 | 必须是 `0x04034B50`，否则拒绝：不是 ZIP |
| 6 | 2 | 通用标志位 | 第 0 位（加密）必须为 0；第 3 位（数据描述符）必须为 0 |
| 8 | 2 | 压缩方法 | 必须是 0（存储） |
| 18 | 4 | 压缩后大小 | 不得为 `0xFFFFFFFF`（ZIP64 哨兵值）；必须 ≤ 4 MiB |
| 26 | 2 | 文件名长度 `n` | — |
| 28 | 2 | 附加字段长度 `e` | — |
| 30 | `n` | 文件名 | 必须恰好是 13 字节的 `MANIFEST.json` |
| 30+`n`+`e` | size | 清单文件的字节内容 | — |

**按照实现的顺序去检查问题：** 首先检查*名字*，其他一切之后再说。一个
条目零是别的文件的归档，会撞上那个文件碰巧不满足的某个头部检查，而
报告*那个*错误会让读取者去追查一个自己根本没有的清单文件的问题。

由此产生的拒绝情形，及其对应向量：

* 条目零不是 `MANIFEST.json` → `manifest-not-first`。
* 条目零被压缩了 → `manifest-compressed`。
* 大小超出了文件末尾 → 被截断的包。

**一个在某处包含了 `MANIFEST.json` 的包，绝不能被当作 v2 之前的包来
读取。** 如果清单文件存在但不是条目零，答案是拒绝，绝不会回退到更弱
的规则。否则，只要移动一个条目就足以关闭逐文件哈希这个 v2 唯一新增
的特性了。（`manifest-not-first` 的存在就是为了让每一份实现都守住这
一点。）

### 4.1 中央目录必须一致

条目零存在两次：一次在偏移量 0 的本地头中，一次作为 ZIP 读取器会用到
的中央目录记录。ZIP 格式中没有任何东西强制这两者描述相同的字节——
中央目录是最后才被附加上去的。

一份校验器**必须**通过*两条*路径都读取这份清单文件并进行比较：

* CLI 和注册表比较两段字节字符串/它们的摘要；
* 守护进程通过自己的 ZIP 读取器读取条目 0，并把这些字节和它从偏移量
  0 提取出的字节进行比较。

向量：`header-disagree`。这是这里最具 v2 特色的一种攻击。如果不加检
查，注册表会哈希、展示并反签名一份任何守护进程都永远不会强制执行的
清单文件。

**两者一致时，被摘要计算的是哪些字节：** 偏移量 0 处的那些字节。当两
者不一致时，这个包会被拒绝，所以这个问题根本不会出现。

## 5. `MANIFEST.json`

UTF-8 的 JSON，一个对象。CLI 会以带尾随换行的美化打印方式写出它；摘要
是针对实际写出的字节计算的，所以格式是生产者的选择，校验器在计算哈希
前**不得**重新序列化。

完整示例——向量 `ok-minimal`，即哈希出 `2e16024e…` 的那些确切字节：

```json
{
  "schema": "astra.bundle/2",
  "plugin_id": "vector-plugin",
  "version": "1.0.0",
  "platform": {
    "os": "linux",
    "arch": "x86_64"
  },
  "protocol": 1,
  "min_astra_version": "",
  "capabilities": [
    "tools"
  ],
  "permissions": {},
  "permissions_hash": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
  "entry": {
    "command": "./bin/fixture",
    "args": []
  },
  "files": [
    {
      "path": "bin/fixture",
      "sha256": "0f7ceb62618162c2ac6765ac683e65dc81ad19add148ada1e7186d186847caba",
      "size": 33,
      "mode": "0755"
    },
    {
      "path": "plugin.toml",
      "sha256": "da1141bb5c5390f1c8a646a0e0b0be1f26cdc0862ccb850dd86e0cd0238f3117",
      "size": 218,
      "mode": "0644"
    }
  ]
}
```

### 5.1 字段

| 字段 | 类型 | 生产者 | 校验器 |
|---|---|---|---|
| `schema` | string | 必须是 `"astra.bundle/2"` | 必须精确比较；任何其他值 → 直接拒绝，绝不猜测 |
| `plugin_id` | string | 插件 id，与 `plugin.toml` 一致 | §9 |
| `version` | string | semver | 由注册表和守护进程与上架条目进行比对 |
| `platform` | `{os, arch}` | 见 §5.2 | 宿主兼容性检查属于安装器的职责，不属于本格式 |
| `protocol` | integer ≥ 0 | 该插件所使用的传输协议 | 范围检查属于宿主的职责 |
| `min_astra_version` | string | semver，或表示无要求的 `""` | — |
| `capabilities` | array of string | 守护进程的能力词汇表 | — |
| `permissions` | object | `plugin.toml` 的 `[permissions]` 段，原样保留 | §10 |
| `permissions_hash` | string | 针对 §10 规范字节计算的 `"sha256:" ‖ hex` | §10 |
| `entry` | `{command, args}` | §8 | §8 |
| `files` | array | §7 | §7 |

**生产者必须发出上面的每一个字段。** 校验器**必须**拒绝一份缺少
`schema`、`plugin_id`、`version`、`platform`、`entry` 或 `files` 的
清单文件。

*一处分歧，明说而不是藏起来：* 守护进程会在 `protocol`、
`min_astra_version`、`capabilities`、`permissions` 和
`permissions_hash` 缺失时给出默认值（`#[serde(default)]`）；CLI 的
读取器则要求它们必须存在。因此一份省略了其中之一的清单文件，是可以
安装的，却无法被 `astra-plugin verify` 校验。请不要产出这样的清单
文件。

**未知的成员必须被接受并忽略。** 未来某次 v2 的新增内容（比如一个
`changelog_url`）绝不能让每一个携带它的包在更旧的宿主上变得无法安
装。没有 schema 版本提升就不能改变的，是上面这些字段的*含义*——而
`schema` 会被精确比较，正是这一点约束了这个边界。

### 5.2 `platform`

```json
{"os": "linux",   "arch": "x86_64"}     → registry platform key  linux-x64
{"os": "windows", "arch": "x86_64"}     → registry platform key  windows-x64
{"os": "any",     "arch": "any"}        → registry platform key  noarch
```

某个轴上的 `any` 意味着"无要求"：当
`(os == "any" || os == host_os) && (arch == "any" || arch == host_arch)`
时，一个包和某个宿主是兼容的。`noarch` 是每一个 TypeScript 和
Python 插件出货的方式——源码或字节码，由宿主已经具备的运行时来运
行——注册表会为一个 `noarch` 包在每一个受支持的平台键下都写入相同的
URL 和摘要，所以任何客户端都不需要专门学习这个词。向量：
`ok-noarch-runtime`。

今天没有其他 `{os, arch}` 组合能指名一个目标。`linux-arm64`、
`windows-arm64`、`macos-x64` 和 `macos-arm64` 是注册表 schema 中保留
的平台键；Astra 没有为它们提供守护进程。

## 6. 条目名称

每一个归档条目名称都会被检查。这些规则之所以存在，是因为一个条目名称
会变成别人文件系统上的一个路径，而读取它的不只是解压工具本身。

在以下任何条件成立时，一个条目名称会被**拒绝**：

1. **为空**。
2. 包含**反斜杠** `\`。ZIP 路径只使用 `/`；反斜杠在 Windows 上是路径
   分隔符，在其他地方是一个字面的文件名字符。
3. 是**绝对路径**——以 `/` 开头。
4. 包含 **`:`**。在 NTFS 上，`bin/fixture:stream` 会作为一个备用数据
   流悄无声息地写*进* `bin/fixture` 内部。向量：`path-ads`。
5. 包含**控制字符**（U+0000–U+001F，U+007F）。
6. 存在**空的路径分量**（`a//b`），或者某个分量等于 **`.`** 或
   **`..`**。向量：`path-traversal`（`../escape`）。
7. 存在以**点或空格结尾**的分量。Win32 会悄悄地把两者都去掉，所以
   `bin/fixture.` 和 `bin/fixture` 会变成两个条目、一个文件。向量：
   `path-trailing-dot`。
8. 某个分量的**主干**（第一个 `.` 之前的文本，不区分大小写比较）是一
   个保留的 MS-DOS 设备名：`con`、`prn`、`aux`、`nul`、`com1`–
   `com9`、`lpt1`–`lpt9`。`CON.txt` 同样也是控制台。

此外：

9. **重复的名称会被拒绝**，无论是精确重复还是**不区分大小写**的重复：
   `plugin.toml` 和 `Plugin.TOML` 对 ZIP 读取器来说是两个条目，但在
   NTFS 和 APFS 上是一个文件，其中第二个会在第一个*已经被哈希之后*把
   它覆盖掉。向量：`duplicate-entry`、`duplicate-entry-case`（参见分
   歧 F1）。
10. **目录条目会被拒绝**（§2）。如果一个条目的名字以 `/` 结尾，或者
    它的外部属性给出的 Unix 模式满足 `mode & 0o170000 == 0o040000`，
    它就是一个目录。两者都要检查：前者是 ZIP 写入器惯常发出的形式，
    后者是一个恶意写入器可能改为发出的形式。
11. **符号链接条目会被拒绝**：一个外部属性给出的 Unix 模式满足
    `mode & 0o170000 == 0o120000` 的条目。这里的逃逸点在链接的*目
    标*上，而这正是条目的*内容*——上面所有的路径规则检查的都是名字，
    没有一条能看到这个内容。向量：`symlink-entry`。

这些规则适用于**每一个**条目，包括 `MANIFEST.json`、`SIGNATURE` 和
`PUBKEY`。

## 7. `files` —— 归档要与之核对的清单

`files` 是一个对象数组：

| 成员 | 类型 | 规则 |
|---|---|---|
| `path` | string | 一个归档条目名称；遵循 §6 |
| `sha256` | string | **恰好 64 个小写十六进制字符**，不带前缀 |
| `size` | integer ≥ 0 | 未压缩字节长度 |
| `mode` | string | 四位八进制数字，例如 `"0755"`——是一个*字符串*，因为 JSON 没有八进制字面量，十进制的 `755` 是另一个模式 |

* 包含任何大写十六进制数字的 `sha256` 会被**拒绝**，而不是被折叠成小
  写。这里的摘要是按字符串比较的，所以一个大写的摘要永远不会匹配任何
  东西，表现出来的会是一个损坏的文件，而不是一份格式错误的清单。向
  量：`uppercase-digest`。
* `mode` **必须**能被解析为八进制数。守护进程的解析器会接受一个前导
  的 `0o`；生产者**不得**发出它。`"0788"` 会被拒绝——8 不是一个八进
  制数字。
* 同一个 `path` **不得**出现两次。
* 一个保留名称（`MANIFEST.json`、`SIGNATURE`、`PUBKEY`）**不得**出
  现：清单文件无法列出自己的摘要，而旧式的那对密钥是针对被列出的文
  件计算的。

### 7.1 两个方向的网罗性

设 `Listed` 为 `files[].path` 的集合，`Present` 为归档条目名称集合
减去上面三个保留名称。校验器**必须**强制执行：

```
Present ⊆ Listed     (no archive entry that the manifest does not list)
Listed ⊆ Present     (no listed file that the archive does not contain)
```

两者始终都要。只做一个是个漏洞：

* 只检查 `Listed ⊆ Present`，会让攻击者能够**添加**一个解压工具会
  写出、却没有任何东西会去哈希的条目——向量 `extra-file`
  （`bin/backdoor`）；
* 只检查 `Present ⊆ Listed`，会让攻击者能够**删除**一个条目，同时还
  声称这个包完好无损——向量 `missing-file`。

正是这个合取式，把那对碰撞（§3.3）区分开来。

### 7.2 内容摘要

对于 `Present` 中的每一个条目：该条目**未压缩内容**的 SHA-256**必
须**等于其 `files` 行中的 `sha256`。向量：`content-digest-mismatch`
——正确的文件集合，正确的长度，错误的字节内容。这正是用来撞上一个
被调包的二进制文件的检查。

*何时*执行这个检查是一个实现选择，但有一条硬性约束：被哈希的字节
**必须**是落到磁盘上的字节。因此守护进程是在解压*过程中*进行哈希，
而不是在解压前的那一遍扫描中——参见分歧 F2，这是刻意为之，不是一个
漏洞。

### 7.3 大小

每一个条目的 `size` **必须**等于清单文件中的对应值。两项独立的检查
都是适当的，守护进程两者都做：在做任何事情之前，先看中央目录中声明
的大小（这是攻击者可控的，所以这只是一个廉价的测谎手段，不是真正的
检查），以及流式传输过程中的字节计数。声明的大小是流式解压的边界。
向量：`size-mismatch`。

### 7.4 权限模式

当一个归档条目携带 Unix 模式时，`mode & 0o777` **必须**等于清单文件
中的 `mode & 0o777`。当它不携带模式时（一个在 Windows 上写出的归
档），这项比较会被跳过；模式缺失不是缺陷，模式不匹配才是。清单文件
中的模式是解压工具实际应用的那个。向量：`mode-mismatch`（参见分歧
F3）。

生产者会做规范化处理：CLI 对任何可执行的东西（被解析出的入口二进制
文件、磁盘上的可执行位，或者 `[bundle] executables` 中列出的路径）
写入 `0755`，其他一律写入 `0644`。它刻意不去复制磁盘上任意的模式：
否则在一个不同 umask 下的检出(checkout)，会在内容没有任何变化的情况
下改变包的字节内容。

### 7.5 已排序

`files` **必须**按 `path` 严格升序排序。比较方式是按**原始字节**
（不是按 Unicode 排序规则，也不区分大小写）。守护进程强制严格递增
（`w[0].path >= w[1].path` → 拒绝），这同时也捕获了重复的情形。校验
器被允许对这个数组做二分查找；一个未排序的数组会让这种查找悄悄地
出错。向量：`unsorted-files`。

## 8. `entry.command`

`entry.command` 是清单文件中唯一会变成一次 `execve` 的字段。它**必
须**是以下两者之一：

* 一个**宿主运行时**，与封闭列表 `python`、`python3`、`node`、
  `bun`、`deno` 精确匹配；或者
* **一个清单文件中列出的文件的路径。** 在去掉开头的 `./` 并把 `\`
  转换成 `/` 之后进行比较。其结果**必须**出现在 `files[].path` 中。

会被直接拒绝的情形：

* （去除首尾空白后）为空；
* 是绝对路径（`/usr/bin/sh`，或者类似 `C:\…` 的 Windows 盘符前缀）；
* 包含 `..` 分量——向量 `entry-command-escape`
  （`../../../bin/sh`）；
* 指名了一个清单文件没有列出的文件——向量 `entry-command-shell`
  （`sh`）。

**关于 shell。** 注册表会按名字拒绝各种 shell —— `sh`、`bash`、
`zsh`、`fish`、`dash`、`csh`、`ksh`、`cmd`、`cmd.exe`、
`powershell`、`powershell.exe`、`pwsh`、`pwsh.exe` —— 并给出一个独
立的错误码，因为 `entry.command: "sh"` 会把不受约束的 `args` 变成
任意代码。CLI 和守护进程通过"运行时或已列出文件"这条规则达成了相同
的判定（shell 两者都不是）。一份符合规范的校验器只需要这条通用规则；
单独点名各种 shell 换来的是更好的错误信息，而不是不同的结果。

`entry.args` 是一个字符串数组，默认为 `[]`。这个格式对它的内容不做
任何约束；宿主不会去解释它。

**不要把这里"加固"成"必须是一个已列出的文件"。** 那会让整个目录中
脚本语言的那一半直接下线——每一个 TypeScript 和 Python 插件都是通
过一个宿主运行时来运行的。向量 `ok-noarch-runtime`
（`entry.command: "node"`，`platform: any/any`）的存在，正是为了
捕获这个错误，而且它是一个*接受*向量。

## 9. `plugin.toml` 和 `plugin.id`

每一个包**必须**包含一个 `plugin.toml` 条目，像其他任何文件一样被
列在 `files` 中。它是宿主解析的插件清单文件；其完整字段参考见
[清单参考手册](../reference/manifest.md)。

有两条规则之所以属于*这份*文档，是因为一个包可能因为它们而被拒绝：

* `MANIFEST.plugin_id` 和 `MANIFEST.version` **必须**与安装器所请求
  的内容、以及提供这个包的那个上架条目一致。没有这一点，一个注册表
  条目 `foo` 就可能提供一个清单文件写着 `bar` 的归档，而 `bar` 却会
  被安装上。
* **`plugin.id` 会成为一个路径分量**——`<plugins_dir>/<id>/`——这是
  宿主创建、写入、并递归删除的一个目录。因此它会被校验：
  * 非空，且每一个字符都是 `[a-z0-9-]`（小写 ASCII 字母、数字、连
    字符）；
  * **不得**以点或空格结尾（这已经被字符集排除了；之所以作为单独的
    规则保留下来，是为了让日后放宽字符集时，这个漏洞不会被悄悄地重
    新引入）；
  * **不得**是 §6.8 主干规则下的一个保留 MS-DOS 设备名。

  向量：`plugin-id-traversal`、`plugin-id-con`（参见分歧 F4）。
  `con` 在 Linux 上可以安装，在 Windows 上不可能，而只运行东西的
  Linux CI 对此毫无察觉。

## 10. `permissions` 和 `permissions_hash`

`MANIFEST.permissions` 是插件 `[permissions]` 段的原样拷贝：一个把
权限 id 映射到一个请求对象（`{reason?, types?, scopes?}`）的对象。
它的词汇表和含义见 [`permissions.md`](permissions.md)；这一节只定义
字节内容和哈希本身。

```
canonical_bytes  = RFC 8785 (JCS) serialisation of the permissions object
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( canonical_bytes ) )
```

规则：

* **`null` 和 `{}` 是相同的值**——一个什么都不申请的插件——两者都会
  被规范化为 `{}`。一个省略了该成员的生产者和一个写出空对象的生产者
  **必须**产出相同的哈希。那个哈希是
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
  = `sha256("{}")`，它出现在大多数向量中。
* `sha256:` 前缀是**值的一部分**，这一点和 `files[].sha256` 不同。
  它携带自己的算法名，是因为这个数字要跨越仓库边界进行比较——打包工具
  写下它，注册表在摄入(ingest)时重新推导它，宿主在信任它之前也重新
  推导它。
* 空的成员会被**省略**，而不是以空值的形式发出：一个没有 reason、没
  有 types、没有 scopes 的请求是 `{}`，绝不是
  `{"reason":""}`。同一个声明的两种规范拼写方式，正是这个哈希要防止
  的那种偏差。
* 实践中的 JCS：对象的键按 UTF-16 代码单元排序，没有无意义的空白，
  字符串按 RFC 8785 §3.2.2.2 的要求转义。这份文档中的值只有字符串、
  字符串数组和对象——没有数字——所以 JCS 那个微妙的一半（§3.2.2 的
  数字规范化）在这里不会出现。

具体示例（向量 `ok-permissions`，所有实现都必须遵循的值）：

```
{"fire_trigger":{"reason":"Fires the on_dice_roll trigger you configure"},"subscribe_events":{"reason":"Watches for command_completed"}}
→ sha256:63dde3632926bc9fb348e0973dbce01d07476a1569cede023edde451b04a6a85
```

以及一个带参数的、规范化后的例子：

```
{"set_variable":{"scopes":["plugin"]},"subscribe_events":{"reason":"Watches for command_completed","types":["command_completed","tool_started"]}}
```

校验器**必须**根据 `MANIFEST.permissions` 重新计算这个哈希，并拒绝
一份和自身 `permissions_hash` 不一致的清单文件。向量：
`permissions-hash-mismatch`——`permissions` 块申请了
`fire_trigger`，而 `permissions_hash` 却是 `{}` 的哈希，也就是说两
者描述的是不同的插件。今天由谁来检查这一点，见分歧 F5。

## 11. 旧式的 `SIGNATURE` / `PUBKEY` 对

一个 v2 之前的包可以携带两个额外条目：`SIGNATURE`（针对 §3.3 那个拼
接摘要的 64 字节 Ed25519 签名的 base64 编码）和 `PUBKEY`（32 字节原
始公钥的 base64 编码）。它们正在**被淘汰**，在它们还存在的期间：

* 它们**从不**列在 `files` 中（它们是针对被列出的文件计算的）；
* 如果其中之一存在，**两者都必须存在**，并且**必须**是归档中的最后
  两个条目，先 `SIGNATURE` 后 `PUBKEY`。它们之后如果还有任何东西，
  就会超出签名所覆盖的范围。向量：`ok-legacy-signed`（一个接受向
  量——这对密钥是被容忍的，不是必需的）。
* **它们不是信任信号。** 一个随附在自己认证的归档里的密钥，无法证明
  是谁写下了它，而它们所覆盖的摘要正是那个有歧义的摘要。校验器**不
  得**把它们的存在、有效性或缺失当作任何东西的证据。注册表会发出一
  个警告（`W_LEGACY_SIGNATURE_ENTRY`）然后继续处理。

退役日期在双方各自只命名一次，这样两边就不会产生偏差：CLI 的
`LEGACY_PAIR_SUNSET`（`astra-plugin 0.5.0 / Astra 0.4.0`）和守护进程
的 `LEGACY_SIGNATURE_SUNSET`（`Astra 0.4.0 (astra-plugin 0.5.0)`）。
`astra-plugin build` 已经不再写出它们；只有 `astra-plugin sign` 还
会这么做，它会和守护进程的读取器一起在退役期到来时消失。

## 12. 限制

来自 [`spec/limits.yaml`](../../../spec/limits.yaml)，这些数字被声明
的唯一地方：

| 限制 | 值 | 适用对象 |
|---|---|---|
| `max_archive_entries` | 10 000 | ZIP 条目数量，包括 `MANIFEST.json` |
| `max_extract_bytes` | 524 288 000（500 MiB） | 未压缩字节总量 |
| 清单文件上限 | 4 MiB | 仅 `MANIFEST.json` 本身 |

一个超出其中任意一项的包**必须**被拒绝。条目数量上限要在为每个条目
分配一条记录**之前**应用，字节数上限则既要应用于清单文件声明的总
和，也要应用于流式传输过程中实际到达的字节——那些声明出来的数字，
只是归档自身的断言。

CLI 会拒绝*构建*超出这些限制的内容，这样作者能在自己的机器上就发
现，而不是等到用户安装失败时才发现。

## 13. 验证算法

这是可以实现出来的形式。一个校验器持有一个文件，以及可选的、来自某
个上架条目的期望值 `(plugin_id, version, platform_key)`。每一步失败
时都是一次**拒绝**。

**A. 文件。**
1. `artifact_digest = SHA256(file)`。如果提供了一个期望的摘要且不
   匹配，就在这里停止；下面的一切都失去了意义。

**B. 条目零，从偏移量 0 开始。**（§4）
2. 解析本地文件头。Name = `MANIFEST.json`；flags 的第 0 位和第 3 位
   均为 0；method 为 0；size 不是 ZIP64 哨兵值且 ≤ 4 MiB；切出清单
   文件的字节内容。
3. `manifest_digest = SHA256("astra.bundle/2" ‖ 0x00 ‖ manifest_bytes)`。
4. 把清单文件解析为 JSON。`schema == "astra.bundle/2"`，精确匹配。

**C. 中央目录。**（§2、§4.1、§12）
5. 正常打开这个归档。条目数量 ≤ 10 000。
6. 中央目录中的条目 0 是 `MANIFEST.json`，存储方式，其字节内容和
   第 2 步得到的字节内容相同。

**D. 结构，在读取任何内容之前。**（§6、§7、§12）
7. 按顺序遍历各条目。对每一个：应用 §6（名称规则，不能是目录，不能
   是符号链接，不能有精确重复或折叠大小写后的重复）。
8. 构建 `Present`（条目名称减去三个保留名称）。检查
   `Present ⊆ Listed` 和 `Listed ⊆ Present`。
9. 对 `files` 中的每一行：64 位小写十六进制的 `sha256`，可解析的
   四位八进制 `mode`，`path` 不重复，`path` 不是保留名称；数组按
   `path` 的字节值严格升序排列。
10. 对 `Present` 中的每一个条目：声明的 `size` 匹配，并且——如果归档
    携带模式——`mode & 0o777` 也匹配。
11. `files[].size` 的总和 ≤ 500 MiB。
12. 如果 `SIGNATURE` 或 `PUBKEY` 存在：两者都存在，且按这个顺序是
    归档中的最后两个条目。
13. `entry.command` 是一个已列出的文件或一个宿主运行时（§8）。

**E. 内容。**（§7.2）
14. 对 `Present` 中的每一个条目，以流式方式、按声明的大小为界：未
    压缩内容的 SHA-256 等于清单文件中的值。如果校验器同时也在解压，
    就哈希它写出的字节，而不是再读一遍。

**F. 这个格式要求的、单靠结构性读取无法完成的交叉检查。**
15. `permissions_hash` 等于根据 `MANIFEST.permissions` 重新计算出的
    结果（§10）。
16. `plugin.toml` 能被解析，且 `plugin.id` 遵循 §9。如果有提供上架
    条目，`plugin_id` / `version` / `platform` 要与之一致。

步骤 A–E 只需要这个文件。步骤 F 需要文件和上架条目两者。

## 14. 黄金向量

`testdata/bundles/` 保存着 27 个被冻结的 `.astraplugin` 文件、
`vectors.json`（判定结果、层次、两种摘要，以及每个实现今天的行为）
和 `SHA256SUMS`。两个消费方都保存着 vendor 依赖的拷贝
（`Astra/astra-rs/astra-daemon/testdata/bundles/`、
`astra-registry/tests/vectors/`），由 `tools/vendor-testdata.sh`
刷新。每个测试套件在读取任何一个向量之前，都会先针对 `SHA256SUMS`
校验自己的那份拷贝。

**没有任何一个测试套件会重新生成自己的测试夹具(fixture)。** 一个用
今天的代码构建出自己输入的测试套件，只是在断言今天的代码和它自己
一致。

### 接受（5 个）

| 向量 | 证明了什么 |
|---|---|
| `ok-minimal` | 对照组。每一次拒绝都必须是对*某样东西*的拒绝 |
| `ok-noarch-runtime` | `platform: any/any` + `entry.command: "node"`——每一个 TypeScript 和 Python 插件是如何出货的（§5.2、§8） |
| `ok-permissions` | 一个哈希正确、非空的权限映射——强制三个 JCS 实现达成一致（§10） |
| `ok-legacy-signed` | 正在退役的那对密钥，位于最后两个条目，顺序正确（§11） |
| `collision-a-bc` | 碰撞对中诚实的那一半（§3.3） |

### 拒绝（22 个）

| 向量 | 拒绝它的规则 |
|---|---|
| `collision-ab-c` | §7.1，**两个**方向 |
| `extra-file` | §7.1 `Present ⊆ Listed` |
| `missing-file` | §7.1 `Listed ⊆ Present` |
| `duplicate-entry` | §6.9 精确重复 |
| `duplicate-entry-case` | §6.9 折叠大小写后的重复（F1） |
| `symlink-entry` | §6.11 |
| `content-digest-mismatch` | §7.2（F2） |
| `size-mismatch` | §7.3 |
| `mode-mismatch` | §7.4（F3） |
| `uppercase-digest` | §7 `sha256` 字符集 |
| `unsorted-files` | §7.5 |
| `manifest-not-first` | §4 |
| `manifest-compressed` | §4 |
| `header-disagree` | §4.1 |
| `path-traversal` | §6.6（以及 §7.1：该条目未被列出） |
| `path-ads` | §6.4（以及 §7.1） |
| `path-trailing-dot` | §6.7（以及 §7.1） |
| `entry-command-shell` | §8 |
| `entry-command-escape` | §8 |
| `plugin-id-traversal` | §9（F4） |
| `plugin-id-con` | §9（F4） |
| `permissions-hash-mismatch` | §10（F5） |

关于三个 `path-*` 向量的说明：每一个都把自己那个恶意条目藏在
`MANIFEST.files` 之*外*，所以一个只实现了 §7.1 的校验器也会把这三个
全部拒绝。但它仍然应该实现 §6——一旦有朝一日某份清单文件真的列出了
这样一个路径，网罗性检查就无话可说了，只有名称规则才管用。

### 14.1 自检数值

对任何实现来说，最快的第一项检查，是确认每个向量的两种摘要都与
`vectors.json` 中的 `artifact_sha256` 和 `manifest_digest` 匹配。这
些数字不是来自这三个程序中的任何一个：`testdata/bundles/handcheck.sh`
会用 `dd`、`od`、`printf`、`cat` 和 `sha256sum` 重新独立推导出它们。
27 个构件摘要和 25 个清单摘要都匹配——两处跳过的是
`manifest-not-first` 和 `manifest-compressed`，它们的条目零按构造
本身就不是一份以存储方式保存的清单文件。一个共享的 bug 可以让三个
程序彼此一致；它没办法让它们和 coreutils 保持一致。

## 15. 已知的分歧

这些记录在 `vectors.json` 的 `divergence` 下，每一项都被三个测试套
件全部断言——这是一个带有测试的行为缺陷，测试会在修复后变色，而不是
注释里的一个 TODO。**每一行中，这份文档的判定都是正确答案。**

| | 向量 | 谁没有跟上 | 为什么会这样 |
|---|---|---|---|
| **F1** | `duplicate-entry-case` | 只有守护进程会在查找重复项之前折叠大小写 | CLI 和注册表使用的是精确匹配的集合。两者都应该折叠大小写。 |
| **F2** | `content-digest-mismatch` | 守护进程的解压前扫描接受了它 | **这是设计使然。** 守护进程是在解压*过程中*哈希内容的，所以被哈希的字节就是被写出的字节。这不是一个漏洞；这是同一项检查在不同时刻进行。 |
| **F3** | `mode-mismatch` | 注册表 bot 完全不比较模式（只发警告） | 模式是由安装器应用的，不是由注册表应用的，所以它把这项检查降了级。§7.4 说的是要比较。 |
| **F4** | `plugin-id-*` | CLI 在 `verify` 和 `check` 中都不校验这个 | 守护进程的 `PluginManifest::validate` 和注册表的 `invalidId` 都会拒绝。作者自己的机器也应该这样做。 |
| **F5** | `permissions-hash-mismatch` | 只有 CLI 的包读取器不重新计算这个哈希 | 守护进程会阻止安装（`PERMISSIONS_HASH_MISMATCH`），注册表会拒绝上架（`E_PERMISSIONS_HASH_MISMATCH`）。 |

如果你解决了其中一项，请删除对应的 `divergence` 块，并把那个实现的
`expect` 设为判定结果——测试套件会在你做到的那一刻告诉你。

## 16. 一个已验证的包能告诉你什么，不能告诉你什么

**能告诉你的：** 这些字节正是列出它们的那份清单所描述的确切字节，归
档中的每一个文件都在两个方向上都得到了说明，没有任何东西会被解压到
安装目录之外，而你手上的摘要，正是任何人对着这份文件重新计算时会得
到的摘要。

**不能告诉你的：** 是谁写下了它（那是构建证明和已签名索引的职
责——[`registry-index.md`](registry-index.md)）、它是否目前已被撤
回（那是撤回列表的职责）、它在运行时可以调用什么
([`permissions.md`](permissions.md))，或者这个进程一旦启动能对这台
机器做什么。插件是以用户的身份、用用户的权限运行的。这个格式中的任
何部分都不会改变这一点，Astra UI 中的任何部分也不得暗示它改变了这
一点。

---

*编写本文档时核实过的来源，全部是在本文档落地的那次提交上读取的：
`astra-plugin-cli/src/bundle.rs`；
`Astra/astra-rs/astra-daemon/src/plugins/bundle.rs`；
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`
（`permissions_hash`、`jcs`）；
`Astra/astra-rs/astra-plugin-manifest/src/manifest.rs`（`validate`、
`is_reserved_device_name`）；`astra-registry/bot/lib/bundle.mjs`；
`astra-registry/tools/lib/canonical.mjs`；`spec/limits.yaml`；
`testdata/bundles/{README.md,vectors.json}` 以及各个向量本身的字
节。*
