> **本文档为翻译版本。** 权威来源是 [docs/en](../en/music-provider-plugins.md)。如与英文版有出入，以英文版为准。

# 音乐服务插件

音乐服务插件在其 `plugin.toml` 的 `[capabilities]` 部分声明
`music_provider = true`。这样它就成为 Astra 的 **媒体会话** 来源：音乐小组件、
Dynamic Island 以及助手的媒体工具（`get_now_playing`、`control_media`、
`play_music`、`get_music_queue`）可以触达它所对接的服务——Spotify 的 Web API、
桌面播放器的本地 API、通往浏览器的桥接——并能在服务 **内部** 为歌曲点赞、
读取其播放队列、搜索其曲库并在那里开始播放。

插件不需要为此绘制任何界面，Astra 自己的播放器会负责。

## Astra 会替插件做的事

插件周边的一切都由守护进程的媒体中枢负责：

- **配对。** 当服务在本机播放时，操作系统通常已经有同一播放的媒体会话
  （Spotify 应用、某个浏览器标签页）。中枢会把两者配对，一首歌就是一个会话：
  系统会话获得你的点赞按钮和队列，不会重复显示。什么是 **听得到的** 仍以
  操作系统为准，你的标题、封面和进度从不覆盖它。
- **远程会话。** 你报告为 **不在** 本设备上播放的会话（手机、音箱）会单独
  显示，并标记为远程。它绝不会被当作“这台电脑”，灵动岛会忽略它。
- **路由。** 对已配对的会话，播放/暂停/下一首/跳转走操作系统，任何应用都适用；
  点赞、取消点赞、随机、循环、音量、队列和开始播放则交给你。
- **边界与安全。** 封面由守护进程下载（仅限 https，且绝不访问本机所在网络）；
  链接只能是 https 或已知的应用协议；字符串和列表会被截断；模型从你这里读到的
  一切都会被标记为不可信文本。

因此插件只需报告每个服务正在播放什么，并一次执行一个操作。

## 创建提供方

<!-- doctest: cli -->
```bash
astra-plugin new my-music --lang python --template blank --capabilities music_provider --output ./my-music
```

`--lang` 也可以是 `rust` 或 `typescript`。没有专门的音乐模板：该能力通过
`--capabilities` 引入，脚手架中的 `music_control` 在你实现之前一律回答
`not_configured`。`astra-plugin test` 会用一个任何插件都不会报告的会话和条目
探测这些钩子。对于插件从未发布过的会话键，SDK 会在你的钩子运行之前回答
`not_found`，所以探测不会暂停或点赞你自己播放器上的任何内容。`MusicSearch`
例外：它发送真实的查询，已登录的插件会从真实服务中作答 (搜索不会改变任何东西)。

请设置 `min_astra_version`：`[capabilities]` 是封闭集合，早于引入
`music_provider` 的 Astra 会拒绝整个清单。

## 报告：每次都发布完整集合

报告采用推送方式。每个 SDK 都持有一个发布器——Python 和 TypeScript 中是
`self.music`，Rust 中是你从 `music_publisher` 返回的 `MusicPublisher`——并以此
为守护进程的长连接流 `MusicSubscribe` 供数：立即发送最新快照，每次发布时再发，
并每隔 `music_snapshot_heartbeat_secs`（15 秒）重发一次，以便发现沉默的插件。
早于 `music_session_stale_secs`（45 秒）的快照将不再被信任。

**每次发布都是完整集合。** 你遗漏的会话即视为已结束。

<!-- doctest: illustrative reason="needs a running service account; shows the publish call shape only" -->
```python
self.music.publish(
    [MusicService("spotify", "Spotify", can_search=True, can_play=True)],
    [MusicSession(
        session_key="spotify",
        service_id="spotify",
        this_device=True,
        device_name="DESKTOP-1",
        exclusive_app_hints=["spotify", "spotify.exe"],
        status="playing",
        title="Believer",
        artist="Imagine Dragons",
        artwork_url="https://i.scdn.co/image/…",
        position_seconds=42.0,
        duration_seconds=204.0,
        liked=True,
        controls=["play", "pause", "next", "previous", "seek", "like", "unlike", "queue", "play_into"],
    )],
)
```

决定配对的字段：

| 字段 | 含义 |
|---|---|
| `this_device` | 声音可能来自 **这台** 电脑。只有这样的会话才能与系统会话配对 |
| `exclusive_app_hints` | 只播放该服务的应用的系统会话 ID——Spotify 可执行文件、MPRIS 播放器名称。匹配即可配对 |
| `shared_app_hints` | 承载多种内容的宿主，例如浏览器。只有标题和艺人也一致时才会配对 |

提示会以不区分大小写的方式，与系统会话 ID、其最后一段路径或 AppUserModelId
片段、去掉 `.exe` 的该片段以及 MPRIS 播放器名称进行比较——因此 `spotify`
同样能指代 `C:\…\Spotify.exe`、`SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify`
和 `org.mpris.MediaPlayer2.spotify`。

`controls` 从一份固定列表中说明会话接受哪些操作，其余一律被守护进程丢弃：`play`、`pause`、`next`、
`previous`、`seek`、`like`、`unlike`、`shuffle`、`repeat`、`volume`、`queue`
（由你应答 `MusicGetQueue`）以及 `play_into`（由你应答 `MusicPlay`）。

## 应答：四个钩子

| 钩子 | 要求 | 作用 |
|---|---|---|
| `MusicControl` | 必需 | 对一个会话执行一个操作；`value` 对 `seek` 为秒数，对 `volume` 为 `0`–`100`，对 `shuffle` 为 `on`/`off`，对 `repeat` 为 `off`/`track`/`context` |
| `MusicGetQueue` | 可选 | 当前播放条目前后的会话队列，以及 `current_index` |
| `MusicSearch` | 可选 | 曲库搜索；每个条目的 `item_ref` 由你自定，并会回到 `MusicPlay` |
| `MusicPlay` | 可选 | 播放某个条目或与关键词最先匹配的结果——`mode` 为 `now`、`next` 或 `end` |

**你有意的拒绝是一种应答**，而不是错误：用户未登录、服务需要订阅、哪里都没在
播放。抛出或返回 SDK 的拒绝——三个 SDK 中都是 `MusicRefusal`——并附带
`not_supported`、`not_found`、`no_active_device`、`auth`、`premium_required`、
`rate_limited`、`unavailable`、`not_configured` 之一。守护进程会用对方的语言
展示给用户。任何其他错误都会把插件报告为故障。

<!-- doctest: illustrative reason="the service calls are placeholders; shows the refusal shape only" -->
```python
async def music_control(self, request):
    if not self.signed_in:
        raise MusicRefusal(MusicErrorCode.NOT_CONFIGURED, "Connect Spotify in the plugin's settings")
    device = self.devices.get(request.session_key)  # act on THE session named
    if device is None:
        raise MusicRefusal(MusicErrorCode.NOT_FOUND, "That player has gone")
    await device.do(request.action, request.value)
```

## 容易出错的地方

- **按读取到的位置报告，不要提前外推。** 守护进程会从该位置首次报告时起自行
  外推正在播放的会话：未变化而重发的会话 (心跳就是这样) 保留原时间戳，发布新
  位置则重新计时。
- **只要还是同一次播放，就保持会话键不变**（`[A-Za-z0-9._-]{1,64}`）；
  新的键就是新的会话。
- **不要把浏览器标签页报告为独占。** 浏览器播放很多内容，这会把你的点赞按钮
  挂到别人的视频上。
- **不要把登录令牌放进 `[config]`。** Astra 以普通 JSON 保存配置并在插件页面显示；
  请使用操作系统的钥匙串。
