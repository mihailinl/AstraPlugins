> **本文档为翻译版本。** 权威来源是 [docs/en](../en/migration-0.6.md)。如与英文版有出入，以英文版为准。

# 将插件迁移到 0.6 系列 SDK

面向已经有一个可用的 0.5 时代插件的人。内容按你会遇到问题的顺序排列：**在你
改动任何一行代码之前，运行时就会出问题的部分**，然后是编译期会出问题的部分，
然后是能编译但行为不同的部分，最后是只会产生警告的部分。

发布列车是 `sdk-v0.6.0`：Rust crate 升到 0.6.0，Python 和 TypeScript 包升到
0.5.0。数字为何不同，参见 [versioning.md](versioning.md)。

下面每一段代码都是本仓库中真实存在的代码 —— 九个 Rust 示例是在提交
`134f6d1` 中被移植到 0.6 的，所以每处对比的两侧都存在于 git 历史中，均从
那里引用。

---

## 0. 为什么你不能继续留在原地

这不是一次"多了个漂亮新 API"的发布。**在你什么都还没改动之前，0.5 插件对
当前的守护进程来说就已经是坏的了**：

> 0.5 版的 `HostClient` 不会发送 `x-session-token`，守护进程会对除
> `Register` 之外的每一个 host RPC 都回答 `unauthenticated`。

于是 `fire_trigger`、`set_variable`、`log`、`push_to_ui` 等等，会在一台不属于
你的机器上于运行时失败，用户看到的消息只会被解读为"这个插件坏了"。而注册
(Registration)本身仍然会成功，这正是令人困惑的地方：插件看起来启动了，
实际上什么都没做。

这就是 0.6 存在的全部理由，也是为什么创作 API 的改动被允许放在同一次发布中
进行的理由。

---

## 1. 捷径（Rust）：改一行，就能编译通过

如果你需要今天就让插件跑起来，把真正的迁移留到下周，那就改一下 import：

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

差异就是这么多。`compat` 就是 0.5 的 trait、0.5 的结果类型，以及 0.5 版的
`HostClient`/`DaemonClient` 形态，通过一个 blanket impl 转发到 0.6 的
trait 上。已经在真实的 0.5 版 dice-roller（255 行，除了那一行 import 之外
没有任何改动）上验证过：

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

（每碰到一个被弃用的条目就有一条警告 —— 这里是 11 条，外加一条
`unused_mut`，因为旧的 `let mut h = host.lock().await` 已经不再需要了。）

它能编译通过，工具能正常响应，之前存进 `set_host` 里的 host 依然能连接到
守护进程。SDK 自己的测试套件也证实了这一点：七个*针对 0.5 trait* 编写的
测试，通过 0.6 的测试工具运行，位于
`astra-plugin-sdk/src/capability.rs`（`mod compat::tests`）中。

在你依赖它之前，有三件事需要了解：

- **`compat::*` 取代 `prelude::*`，而不是在它之上追加。** 如果两个都
  import，作用域里就会有两个名叫 `PluginCapability` 的 trait，`impl
  PluginCapability for MyPlugin` 就会变成有歧义（E0659），而不是弃用警告。
- **它会在 0.8 中消失** —— 按 [versioning.md](versioning.md) 的规定，是
  两个 minor 版本之后。
- **0.5 中原本就没有的钩子，现在依然没有。** `ai_complete`、
  `tts_activate`、`stt_load` / `stt_unload` / `stt_load_state` 会通过垫片
  (shim)返回 `UNIMPLEMENTED`，协议会将其解读为*钩子不存在*。要实现它们，
  你就必须迁移到新 trait。

`compat::*` 同时也重新导出了 0.6 的名字 —— `PluginContext`、`ToolError`、
`Host`、`Daemon`、`Config`、`NoConfig` —— 所以你可以把各个钩子逐个迁移到
新签名，而不用再次改动那行 import。等最后一个钩子迁移完成，把
`compat::*` 换回 `prelude::*`，警告就都消失了。

本文档接下来的内容，就是这次迁移本身。

---

## 2. 编译期会出问题的地方（Rust）

以下是把未经修改的 0.5 版 dice-roller 针对 0.6 构建时得到的真实错误 ——
共 15 个，分五类。

### 2.1 `Config` 成为必须的关联类型

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

如果你的插件没有任何设置，只需要一行：

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

如果有设置，就声明这个类型并实现 `on_config` —— SDK 会替你解析守护进程
发来的 JSON。bad-apple 的改动前（`examples/bad-apple/src/main.rs`，
`134f6d1^` 时刻）：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

改动后（`examples/bad-apple/src/main.rs`）：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

二十行变两行，而且类型错误的字段现在会被报告，而不是被悄悄跳过。

> **使用 `#[serde(default)]`（或者会自动添加它的 `#[astra::config]`）。**
> 守护进程发给一个刚安装好的插件的第一份配置负载是 `{}`。带有必填字段的
> 配置类型会拒绝它，`on_config` 就一次都不会被调用，你的插件会用
> `Config::default()` 去处理每一次调用 —— 一个空的 API key，一个空字符串
> 的触发器名字。SDK 会对这种情况大声发出警告，但那不一定是你正盯着看的
> 那个日志面板。

`Config<T>` 就是用来存放它的无锁存储：`self.config.load()` 是一次原子
读取，工具调用中途发生的配置重写不会阻塞它。

### 2.2 处理函数需要接收 `&PluginContext`

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

在 `&self` 之后加上 `ctx: &PluginContext`（或 `_ctx`）。它携带
`plugin_id`、`language`、`active_triggers`、`host` 和 `daemon`；克隆它的
代价很低；它永远不会是 `None`。mock-stt 的前后对比：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS 同时把原本四个参数合并成了一个 `TtsRequest` —— tone-tts 从
`(&self, text, voice_id, speed, _pitch)` 变成了
`(&self, _ctx, req: TtsRequest)`，读取 `req.text`、`req.voice_id`、
`req.speed`。

在参数无法到达的地方 —— 一个被 spawn 出来的任务、一个 `Drop`、来自别人
crate 的回调 —— `astra_plugin_sdk::ctx()` 会返回同一个上下文。

### 2.3 `set_host` 和 `set_daemon_client` 已被移除

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

删掉这个钩子、删掉这个字段，改用 `ctx.host()`。这一处值得认真处理，而不是
简单地走垫片(shim)敷衍过去，因为 0.5 的原有形态里本身就有一个缺陷。
dice-roller 的改动前（`examples/dice-roller/src/main.rs`，`134f6d1^`
时刻）：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

当第二次工具调用持有那个锁时，`try_lock` 会返回 `None`，插件会打印
"host client not available yet"，然后**什么都没触发**。改动后：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

`Arc<dyn Host>` 没有锁可失去。这同样适用于客户端类型的插件：对于拥有
`client` 能力的插件，`ctx.daemon()` 在其整个生命周期内都是 `Some`，所以
所有"daemon client not ready"的分支都可以去掉了。telegram-client 去掉了
它的 `SharedDaemon` 字段和这个检查：

> `Some` 说的是这个句柄本身，而不是它能到达哪里。守护进程把每个插件的
> 会话令牌都限定在 `PluginHostService` 范围内，所以目前通过
> `ctx.daemon()` 发出的调用会返回 `permission_denied` —— 参见
> [Rust SDK 页面](4-sdk/rust.md#daemon--sdk-中存在但会被守护进程拒绝)。
> 这一节讲的是迁移的形态，不是今天就能端到端跑通的路径。

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` 已被删除

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

处理函数返回 `Result<String, ToolError>`（`ActionError` 是 `ToolError`
的别名）。对应关系是机械的：

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`，或者在解析处直接用 `?` |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

这个种类信息不是装饰。它决定了 AI 循环能否判断重试是否有意义，而
`NotConfigured { field }` 正是把"工具失败了"变成一个指向那个具体设置项
链接的关键。bad-apple 的改动后：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

注意 `serde_json::to_string` 上的 `?`：`From` 实现覆盖了
`serde_json::Error`、`std::io::Error`、`tonic::Status` 和 `anyhow::Error`，
每一种转换都是在断言失败属于哪一类 —— `call_tool` 内部的
`serde_json::from_str(args)?` 意味着 `BAD_ARGUMENTS`，这是唯一一种模型
可以通过重试来修复的失败。

如果你走垫片(shim)那条路，0.5 的每一种失败都会变成携带同一句话的
`ToolError::Internal`。这是对一个从未说明自己是什么类型的字符串的诚实
解读，而它比你自己花五分钟能说清楚的内容要差得多。

### 2.5 更小的编译期变化

| 内容 | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | 曾是一个钩子 | **已删除。** 守护进程通过 `ASTRA_PLUGIN_CAPABILITIES` 直接给出清单里的 `[capabilities]` |
| `ActiveTriggers::contains` / `update` | `async`、`tokio::RwLock` | 变为同步（`ArcSwap`），`update` 现在叫 `set` |
| `HostClient::new(..)` | 可以构造 | 只能通过 `connect_bootstrap` → `register` → 得到已认证的客户端 |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | 原本可用 | 变成会以一句话报错失败的占位符：请使用 `#[astra::args]`，或在你自己的 `Cargo.toml` 中添加 `serde` |
| `on_shutdown()`、`on_event()`、`on_state_changed()` 以及其他事件钩子 | 没有 `ctx` | 和其他所有钩子一样，第一个参数是 `ctx` |

---

## 3. 运行时会出问题的地方（能编译，但行为不同）

### 3.1 `[permissions]` 默认拒绝一切

这一条会最先在用户的机器上咬你一口，而且它根本不是 SDK 层面的改动 ——
它是 Phase 4。一个没有 `[permissions]` 段的清单，只能调用 `Register`、
`PluginLog` 和 `GetPluginSelfConfig`，**其他什么都不能调用**。
`fire_trigger`、`set_variable`、`push_to_ui`、`send_chat_message`、
`subscribe_events` 和 `set_theme_contribution` 各自都需要一个被声明且被
授予的权限，拒绝会以 `PERMISSION_DENIED` → `ToolError::Unauthorized`
的形式到达。

仅仅声明能力(capability)是不够的。摘自
`examples/dice-roller/plugin.toml`：

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

`reason` 会在安装时展示给用户。请为他们把这句话写清楚。

### 3.2 启动顺序，以及 `on_start`

0.6 修正了顺序：绑定 → 注册 → 构建 ctx → `on_config` →
`on_language_changed` → `on_start` → 开始提供服务。`on_start` 是新增的，
返回 `Err` **会中止启动**：进程会以非零状态退出，而不是留下一个守护进程
以为很健康、却对每次调用都以同样方式失败的插件。

预热和后台任务应该放在这里。echo-stt 把它的音频线程从 `main` 挪到了这里；
telegram-client 把整个 bot 的启动逻辑从 `set_daemon_client` 挪了出来，
这也顺带消除了与 `on_config_changed` 之间的一处竞争：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 悄悄变化的行为

- **`ActiveTriggers` 现在有了写入方。** 在 0.5 中从来没有任何东西会写入
  它，所以 `contains()` 永远返回 false。如果你曾经用它来守护一个代价
  高昂的负载构建，那道守卫过去一直是关闭的，现在打开了 —— 这个负载真的
  会被构建出来。
- **STT 音频通道现在能容纳 500 个数据块，而不是 32 个。** 一个在高负载下
  曾经悄悄丢弃音频的流式识别器，现在不会再丢了。如果你曾经为这种丢弃做过
  补偿，请停止这么做。
- **`source_id()` 不再影响任何东西。** 守护进程已经停止按 source id 过滤；
  每个客户端都能看到每一个事件。0.6 中弃用，0.8 中移除。改为把 id 传给
  `Host::send_chat_message`。
- **能力(capability)来自守护进程**，通过 `ASTRA_PLUGIN_CAPABILITIES`
  传递，而不是通过内省你哪些方法返回了非空向量来判断。一个曾经表明的
  能力与清单不一致的插件，现在表明的就是清单本身的内容 —— 也就是用户
  实际同意的内容。

---

## 4. 只会产生警告的部分

| 警告 | 截止时限 | 应该改用什么 |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | 0.6 的 trait —— 见 §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` —— 见 §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` —— 见 §2.3 |
| `use of deprecated method source_id` | 0.8 | 删掉这个重写 |
| Python `DeprecationWarning: … returned a dict` | 0.7 | 返回对应的数据类 |
| `AiGetModels` / `ai_models()` | 0.8 | 什么都不用做 —— 守护进程从来不会问 |

这张表里的内容目前都还不是错误，也都不会在一个 minor 版本之内就变成
错误：具体的保证内容以及它是如何被强制执行的，见
[versioning.md](versioning.md)。

---

## 5. Python

包版本从 0.4.0 升到 0.5.0。类依然是 `Plugin`，装饰器依然是 `@tool` /
`@action` / `@trigger`，所以大多数文件改动都很小。

**失败现在是有代码的。** `call_tool` 和 `execute_action` 过去会捕获所有
`Exception` 并把它扁平化成 `{"success": False, "error": str(e)}` ——
这就是为什么过去每一种失败看起来都一模一样。现在改为抛出八种错误之一，
SDK 会同时帮你填好旧式的字符串和结构化的 `error_detail`：

摘自 `examples/text-utils/src/plugin.py`：

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` 是那个会变成指向具体设置字段链接的
特殊情况。

还有其他一些需要检查的地方：

- **`stt_transcribe` 多了第三个参数** `options: SttOptions | None`。
  只有两个参数的重写依然能用 —— servicer 会检查一次你的签名，只传入它能
  接受的部分 —— 所以这是可选的，加上 `options=None` 就能拿到守护进程给出
  的语言提示和唤醒词偏置。
- 从能力钩子(capability hooks)中**返回数据类，而不是 dict**。dict 依然
  能用，会发出一个指名应返回哪个类的 `DeprecationWarning`；它们会在 0.7
  中被移除。
- **`HostClient` 不能以未认证状态被构造。**
  `HostClientBootstrap(addr, plugin_id).register(...)` 会返回真正可用的
  实例。
- **`@ui_call` / `@ui_page` 现在会注册。** 它们过去是返回一个会被调用方
  丢弃的 dict 的 `@staticmethod`。
- 用警告来卡住 CI：`python -W error::DeprecationWarning -m pytest`。

## 6. TypeScript

包版本从 0.4.0 升到 0.5.0，发布出去的包名是 `astra-plugin-sdk` —— 而不是
以前在四处地方写着的 `@astra/plugin-sdk`。

- **失败是有代码的**，和其他地方一样是那八种，`code` 是每个类各自的字符串
  字面量，所以 `switch (err.code) { case "NOT_CONFIGURED": … }` 能收窄到
  对应子类，直接访问 `err.configField` 而无需类型转换。
- **`HostClient` 的构造函数是私有的**；`HostClient.register(...)` 是获取
  实例的唯一方式，如果守护进程拒绝，它会抛出 `RegistrationError`。
- **客户端加载的是 SDK 自身生成的 descriptor**，而不是两份手工维护的
  内联 proto 字符串，并且会在连接时检查所有将要调用的方法 —— 不匹配会
  在启动时表现为 `ProtoContractError`，而不是在第一次调用时表现为
  `TypeError`。
- **`UiPanel` 已被弃用**；它是 `UiContribution` 的别名。
- 如果你的 `package.json` 是 0.5.0 之前的版本，请留意新的 `exports`
  映射、`"type": "commonjs"`、`engines: { node: ">=20" }`，以及双重的
  CJS+ESM 输出。

---

## 7. 验证迁移是否成功

你不需要安装 Astra 就能知道移植是否成功。0.6 系列 SDK 自带一套测试工具，
可以让你的处理函数针对一个记录型 host 在进程内运行：

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

这个测试正是垫片(shim)方案被采纳的依据：这里的 `DiceRoller` 就是
**0.5** 版的 dice-roller，除了那一行 import 之外没有任何改动，运行在
0.6 之上。没有守护进程，没有 socket，没有安装 Astra —— `Harness` 会围绕
一个记录型 host 构建出一个 `PluginContext`，所以 `fired_triggers()` 是一个
你可以直接断言的列表。

一份简短的检查清单：

1. 不带 `compat::` 的 import 也能编译通过。
2. 你的 `plugin.toml` 中，对每一个你调用的 host RPC 都有对应的
   `[permissions]` 条目，并且各自都写了给用户看的 `reason`。
3. `on_config` 接收到 `{}` 时不会崩溃 —— 那就是全新安装的情形。
4. 任何你以前在 `set_host` / `set_daemon_client` 里做的事情，现在都在
   `on_start` 中完成，并且当插件确实无法工作时，`on_start` 会返回
   `Err`。
5. 每一处 `ToolResult::err` 都变成了能说明原因的 `ToolError` 变体。
