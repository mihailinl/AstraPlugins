# 发布插件

将源码变成已签名、可分发的包所需的一切，用户可以通过侧载把它安装到 Astra。

## `.astraplugin` 包

`.astraplugin` 是一个具有特定布局的 **ZIP 归档**。守护进程会验证它，（可选地）校验签名，把它解压到自己的插件目录，并以凭据启动 `entry.command`。

```
<plugin-id>-<version>.astraplugin
├── plugin.toml                # 清单
├── bin/                       # 编译后的二进制（仅 Rust）
│   └── my_plugin.exe
├── dist/                      # 打包后的 JS（仅 TypeScript）
│   └── index.js
├── src/                       # Python 源码（仅 Python）
│   ├── plugin.py
│   └── __init__.py
├── requirements.txt           # Python 依赖（仅 Python）
├── requirements.lock          # 由 uv 锁定的 Python 依赖（仅 Python）
├── ui/                        # 自定义 UI 文件（可选）
├── locales/                   # i18n JSON 文件（可选）
├── icon.png | icon.svg        # 可选的品牌图标
├── README.md                  # 可选
├── LICENSE                    # 可选
├── SIGNATURE                  # Ed25519 签名（若包已签名）
└── PUBKEY                     # Ed25519 公钥（若包已签名）
```

当 `astra-plugin build` 产出归档时，它会：

1. 执行语言特定的构建步骤。
2. 把编译出的产物复制到预期目录。
3. 重写 `entry.command`，使其指向包内路径（仅 Rust —— Python/TS 在包内的路径是稳定的）。
4. 如果 `plugin.toml` 旁边存在 `ui/`、`locales/`、图标与文档，则把它们一并加入。
5. 如果 `~/.astra/plugin-keys/private.key` 存在，则用 Ed25519 签名每个条目，并把 `SIGNATURE` 和 `PUBKEY` 添加到归档中。

## 签名

### 生成密钥对

```bash
astra-plugin keygen
```

输出：

- `~/.astra/plugin-keys/private.key` —— base64 编码的 Ed25519 种子。**请保密。** 任何拿到此文件的人都能为您的插件签署新版本，并且用户会信任它们。
- `~/.astra/plugin-keys/public.key` —— 可以安全地公开。

添加 `--force` 以覆盖现有的密钥对（适用于轮换密钥 —— 但会使您已建立的信任关系失效）。

### 构建期间签名

没有单独的签名命令：一旦存在密钥对，`astra-plugin build` 就会自动签名。归档包含：

- `SIGNATURE` —— 对归档内所有其他文件的签名清单。
- `PUBKEY` —— 所用的公钥。用户可以在安装前将其与可信来源（您的网站、您的密钥固定策略）对比。

若要发布 **未签名** 的构建产物，可删除私钥，或在不拥有私钥的机器上构建。

### 签名验证

签名验证在侧载时由守护进程完成。守护进程在插件 UI 中展示包的 `PUBKEY`，用户可以在点击"安装"前对比指纹。

## 分发

### 直接下载

通过您的网站、GitHub Releases 或任何文件托管服务提供 `.astraplugin` 文件。用户下载后将文件拖入 Astra 的插件页面。

### Git + 发布产物

典型的发布流程：

1. 提升 `plugin.toml` 中的 `plugin.version`。
2. 提交、打标签（`git tag v0.2.0`）、推送。
3. `astra-plugin validate` → `astra-plugin build -o dist/plugin-0.2.0.astraplugin`。
4. 把 `.astraplugin` 上传到该标签对应的 GitHub Release。

对 CI 友好，因为 `astra-plugin` 是一个单独的二进制。

### 注册表

计划中会有一个中心化的插件注册表。在它上线之前，通过直接 URL 分享插件。

## 侧载

守护进程提供两个 RPC 来安装 `.astraplugin`：

- `SideloadPlugin(bytes)` —— 通过 gRPC 接收包。Astra UI 的文件选择器会使用它。
- `ImportPluginFile(path)` —— 指示守护进程从磁盘读取文件。当用户把文件拖入 UI 时使用。

两者都会（如存在）验证签名、校验清单、解压到 `~/.astra/plugins/<id>/` 并启动进程。

卸载插件会停止进程、删除解压目录并清除插件状态。

## 升级策略

- 每次发布都提升 `plugin.version`。
- 守护进程记录已安装的插件版本，当新包具有更高 SemVer 时会显示"有可用更新"标记。
- 有破坏性配置变更？使用带默认值的新字段，而不要重命名现有字段 —— 守护进程在升级时会保留旧配置。

## 本地化

在包内提供 `locales/` 目录：

```
locales/
├── en.json
├── ru.json
├── uk.json
├── de.json
├── es.json
├── zh-CN.json
└── ja.json
```

每个 SDK 都有一个 `I18n` 助手来读取这些文件，并在遇到未知键时优雅回退。清单负责翻译字段标签（`ActionType.MyAction`、`FieldLabel.X`）—— 请把代码中的 ID 保持稳定，而把显示文本放进 JSON 文件。

## 发布前检查清单

- [ ] `astra-plugin validate` 无错误通过。
- [ ] `astra-plugin build` 成功完成并产出大小合理的归档。
- [ ] `plugin.toml` 包含 `description`、`author` 与 `license`。
- [ ] 若存在 `[config]` schema，则每个字段都有合理的默认值。
- [ ] 已在干净的守护进程实例中通过侧载测试该包。
- [ ] `PUBKEY` 指纹在用户可验证的某处有文档。
- [ ] `locales/` 覆盖插件向用户展示的所有字符串。
- [ ] `README.md` 说明插件的功能和任何运行时要求。
- [ ] 您有办法在需要撤销已泄露的发布版本时联系到用户。
