# Examples

Eleven working plugins. Each one has its own `README.md` written for someone who
wants to *use* it; this file is the index for someone deciding what to read.

Every column below is copied from the example's `plugin.toml` and its own
README, not from memory.

## The index

| Example | Lang | What it demonstrates | `[capabilities]` | `[permissions]` | Needs |
|---|---|---|---|---|---|
| [dice-roller](dice-roller/) | Rust | **Start here.** One dependency, `#[tool]`, `#[action]`, `#[hook]`, and a trigger a user's command can start from. It is also the reference conformance suite (`tests/reference_suite.rs`) | `tools`, `actions`, `triggers` | `fire_trigger` | Nothing |
| [text-utils](text-utils/) | Python | The same three-capability shape in Python: `@tool` from type hints, `@action` with `Field`s, and a clock-driven trigger. Also `locales/` from Python — English, Russian and Ukrainian, a `[config] schema` of `$keys`, and the only **plural family** any example plugin ships | `tools`, `actions`, `triggers` | `fire_trigger` | **Python 3.10+** on the machine running Astra (`runtimes = ["python"]`) |
| [json-tools](json-tools/) | TypeScript | The same shape again in TypeScript: `s.object()` declaring a tool's parameters once, an action that writes a variable, and level-1 + level-2 tests side by side (`test/plugin.test.mjs`) | `tools`, `actions`, `triggers` | `set_variable` (scope `session`) | **Node 18+** (`runtimes = ["node"]`) |
| [tone-tts](tone-tts/) | Rust | A TTS provider with no model: one sine tone per word. Also the data-driven Voice settings hook, `tts_config_fields` | `tts` | none | Nothing |
| [mock-stt](mock-stt/) | Rust | An STT provider that returns a deterministic sentence describing the audio. The lightest thing that can occupy the STT slot | `stt` | none | Nothing |
| [echo-stt](echo-stt/) | Rust | An STT provider that plays your microphone back at you as chunks arrive — a diagnostic for "is the daemon sending me the audio I think it is?" | `stt` | none | An **audio output device**. Linux: ALSA (`libasound2`); to build, `libasound2-dev` and `pkg-config`. **Wear headphones** |
| [web-chat](web-chat/) | Rust | A `client` plugin: its own chat surface on `http://127.0.0.1:9090`, every chat event forwarded over a WebSocket. Multi-client sync, made watchable | `client` | none — `client` is requested by the capability bit | A free TCP port **9090** on loopback, and a browser |
| [telegram-client](telegram-client/) | Rust | The `client` example that actually runs: Telegram in, Astra's reply streamed back over `Host::send_chat_message`, and `I18n` (English + Russian). Its README is also the clearest statement of what a plugin may and may not do to a conversation | `client` | `client`, `send_chat_message` | A **Telegram bot token** and outbound access to `api.telegram.org` |
| [companion](companion/) | Rust | A UI plugin: an animated overlay that lives inside the Astra window, with a translated phrase list that follows Astra's language | `ui_contributions`, `dom_access` | none — `dom_access` is requested by the capability bit | Nothing |
| [bad-apple](bad-apple/) | Rust | A UI plugin with real rendering: four renderers over a pre-extracted 1-bit RLE stream (`ui/frames.bin`, ~3 MB), driven from `plugin.toml` config | `ui_contributions`, `dom_access` | none — `dom_access` is requested by the capability bit | Nothing at run time; frames and audio are in the bundle |
| [doom](doom/) | Rust | The ceiling of what a UI plugin can be: Chocolate Doom compiled to WebAssembly, on Freedoom data, as a page in Astra's navigation | `ui_contributions`, `dom_access` | none — `dom_access` is requested by the capability bit | Nothing beyond Astra, but it is **~15 MB to download and ~36 MB on disk** — by far the largest example here |

Nine are Rust, one Python, one TypeScript. The Rust ones build per platform
(`linux-x64`, `windows-x64`); the Python and TypeScript ones are `noarch`.

> **`web-chat` cannot run end-to-end today.** It is built on `DaemonClient`,
> and the daemon's half of that path is not in place: every plugin is registered
> as `ClientType::PluginClient`, and the auth interceptor rejects that identity
> on any gRPC path outside `/astra.PluginHostService/` with
> `permission_denied("plugin session tokens are scoped to PluginHostService")`.
> So every `submit_user_message`, `subscribe_chat_events` and `get_settings` in
> it is refused at run time. It compiles, it is in CI, and it is worth reading
> for the shape of a client plugin — it is not a working install.
>
> **`telegram-client` used to be the second half of that sentence and is not any
> more.** It was rewritten onto `PluginHostService.SendChatMessage`, which is on
> the one service a plugin's session token is scoped to, so it installs and
> works. What it had to give up is the interesting part and its README leads
> with it: a plugin cannot list or create conversations, so one bridge holds one
> conversation, not one per Telegram topic.

## Reading the two permission columns

They answer different questions and one does not imply the other.

- **`[capabilities]`** is what the daemon may call **into** the plugin — which
  hooks it serves.
- **`[permissions]`** is what the plugin may call **out** to. It is
  **default-deny**: a manifest with no `[permissions]` section may call
  `Register`, `PluginLog`, `GetPluginSelfConfig` and `GetDaemonInfo`, and
  nothing else. Declaring `triggers = true` is not what lets `fire_trigger`
  through — the `[permissions]` entry is, and its `reason` is what the user
  reads on the install consent sheet.

`dom_access` and `client` are the two exceptions, and only partly. They are in
the permission vocabulary but gate a *surface* rather than a call, and the
daemon reads the capability bit as a permission **request** for them
(`astra-daemon/src/plugins/host_service.rs`, `declared_permissions`). A
sideloaded directory gets what it asks for; an imported `.astraplugin` file has
both refused outright; and a plugin installed from the registry is granted from
its trust record, which is built from the bundle's `[permissions]` block — so a
**published** version of `companion`, `doom`, `bad-apple` or `web-chat` would
have to spell the permission out. As shipped, those four are sideload-and-dev
examples. `telegram-client` is the one that does spell it out, because it needs
a second permission anyway: `send_chat_message` gates a call, not a surface, and
no capability bit asks for it.

One inconsistency worth knowing before you copy it: **`json-tools` calls
`ctx.fireTrigger` at `src/plugin.ts:205` and its `plugin.toml` declares only
`set_variable`.** The call is guarded by `ctx.activeTriggers.has(...)`, so it
only runs once a user has wired a command to the trigger — and then it is
denied. Its `[permissions]` needs a `fire_trigger` line.

## Building and running one

```bash
cd examples/dice-roller
astra-plugin dev .
```

`dev` runs `check --strict`, builds, and asks the running Astra to sideload the
directory, so the daemon owns the process and mints its session token. Editing a
file rebuilds and restarts it, with logs in your terminal. It needs Developer
Mode.

**Hand-writing a `sideload.json` marker does not work.** The daemon refuses any
marker it did not record itself. Older revisions of `doom/SETUP.md` and
`bad-apple/SETUP.md` told you to write one; they were wrong and no longer say
it.

To pack a distributable bundle instead:

```bash
astra-plugin build .              # host platform
astra-plugin build . --all-targets
astra-plugin test .               # the conformance suite, against a real process
```

`dice-roller` also ships a built bundle,
`dice-roller/dice-roller-0.1.1-linux-x64.astraplugin`, so you can try
`astra-plugin verify` without building anything.

## A note on the UI three

`companion`, `bad-apple` and `doom` all ask for `dom_access`, which means their
JavaScript runs **inside the Astra window**, with access to the page: the
conversations on screen and every other plugin's interface. Their READMEs say so
in those words, and the daemon treats it as the highest-risk thing a plugin can
ask for.

More generally: **there is no sandbox.** A plugin is a native process with the
user's full privileges. Nothing in this directory is isolated from your machine,
and none of these examples should be read as a demonstration that it is.

## See also

- [The root README](../README.md) — what a plugin is, and the ten capabilities
- [`docs/en/`](../docs/en/README.md) — the documentation
- [`spec/hooks.yaml`](../spec/hooks.yaml) — the 35 hooks, and which SDK
  implements each
