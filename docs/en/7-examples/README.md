# Examples

Eleven plugins in [`examples/`](../../../examples/), all ported to the current
SDKs and all built in CI. Read one that does what you want to do, then start
from the scaffold rather than from the example — they carry no scaffolding you
would have to delete.

Every entry below is read from that plugin's own `plugin.toml`.

## The ones to read first

| | Language | Capabilities | Permissions | Why this one |
|---|---|---|---|---|
| [`dice-roller`](../../../examples/dice-roller/) | Rust | `tools`, `actions`, `triggers` | `fire_trigger` | The reference plugin. Three capabilities, one permission, and a test suite that shows how each is tested |
| [`json-tools`](../../../examples/json-tools/) | TypeScript | `tools`, `actions`, `triggers` | `set_variable` | The same shape in TypeScript, and the example whose tests reach the wire level |
| [`text-utils`](../../../examples/text-utils/) | Python | `tools`, `actions`, `triggers` | `fire_trigger` | The same shape in Python |

Those three are deliberately the same plugin three ways. If you are choosing a
language, read all three and pick the ecosystem you want to pull libraries from
— every capability is available in every SDK.

## Voice providers

| | Language | Capabilities | Why this one |
|---|---|---|---|
| [`tone-tts`](../../../examples/tone-tts/) | Rust | `tts` | A text-to-speech provider that speaks in beeps. A wiring test, not a voice |
| [`mock-stt`](../../../examples/mock-stt/) | Rust | `stt` | Returns a deterministic transcript describing the audio it got. The bidi stream, minus a recognizer |
| [`echo-stt`](../../../examples/echo-stt/) | Rust | `stt` | Transcribes nothing and plays your microphone back through the plugin process. For hearing what the daemon actually sends you |

`tone-tts` and `mock-stt` are two of the four plugins the conformance job drives
on every CI run, precisely because they exercise hooks nothing else does.

## UI, and `dom_access`

These run code inside the Astra window. They are the reason
[sideloading has no permission ceiling](../5-publish/sideload.md): `dom_access`
cannot be developed any other way.

| | Language | Capabilities | Why this one |
|---|---|---|---|
| [`companion`](../../../examples/companion/) | Rust | `ui_contributions`, `dom_access` | A cat that flies around the window and says things. The smallest complete UI contribution |
| [`bad-apple`](../../../examples/bad-apple/) | Rust | `ui_contributions`, `dom_access` | The *Bad Apple!!* animation in four render modes. Ships its own frame data; see its `SETUP.md` |
| [`doom`](../../../examples/doom/) | Rust | `ui_contributions`, `dom_access` | A Doom page running a WebAssembly engine. The most extreme thing a UI contribution can be |

`companion` is the fourth plugin the conformance job drives, for
`ui_contributions`.

## Clients

A `client` plugin is a chat front-end of its own — its own session, its own
surface. It is a high-risk capability, and it is refused outright to a
[locally imported file](../5-publish/local-install.md).

> **`web-chat` is still ahead of the daemon; `telegram-client` no longer
> is.** The daemon-side half of the client path is not built: every plugin
> is registered as `ClientType::PluginClient`, and the auth interceptor
> rejects that identity on any gRPC path outside `/astra.PluginHostService/`,
> so the `DaemonClient` `web-chat` is written against answers
> `permission_denied` on every call. Read it for the shape of a client
> plugin — the surface, the event flow, the I18n — not as something you can
> run end-to-end today. `telegram-client` was rewritten onto
> `Host::send_chat_message`, which is on the host service and does work;
> what a bridge gives up to get there is the first section of its README.
> See
> [the Rust SDK's `Daemon` section](../4-sdk/rust.md#daemon--present-in-the-sdk-refused-by-the-daemon).

| | Language | Capabilities | Why this one |
|---|---|---|---|
| [`telegram-client`](../../../examples/telegram-client/) | Rust | `client` | Telegram in, Astra's reply streamed back — the one client path that works |
| [`web-chat`](../../../examples/web-chat/) | Rust | `client` | A browser window that talks to Astra. For watching multi-client sync happen |

## Platforms

None of the eleven declares a `[platform]` block, which means the daemon
considers each compatible everywhere — correct for the two interpreted ones,
and something a *published* native plugin should tighten. See
[platforms](../1-orientation/platforms.md).

| Language | What a release builds |
|---|---|
| Rust (nine of them) | `linux-x64` **and** `windows-x64`, one bundle each |
| TypeScript (`json-tools`) | one `noarch` bundle |
| Python (`text-utils`) | one `noarch` bundle |

`doom` and `bad-apple` additionally ship data — a WebAssembly engine, a few
megabytes of frames — and their `SETUP.md` says where it comes from and how to
regenerate it.

## What they are tested by

| Level | What runs | Which examples |
|---|---|---|
| Unit | the SDK's in-process harness, in each example's own tests | `dice-roller`, `mock-stt`, `text-utils`, `json-tools` |
| Build | every example is built on every CI run | all eleven |
| Conformance | `astra-plugin test` starts the real process against a mock daemon and drives every hook its capabilities imply | `dice-roller`, `mock-stt`, `tone-tts`, `companion` |

The conformance set is chosen for coverage of the hook table, not for variety —
tools/actions/triggers, the STT bidi stream, TTS, and UI contributions.
**`ai_provider` has no example and is therefore not covered**, which is worth
saying out loud: a coverage gap nobody names becomes one everybody assumes is
filled.

Python and TypeScript examples are not in the conformance job yet, because their
SDKs are not published and a conformance run that half-installs an SDK reports
on the installation rather than on the plugin. `astra-plugin test` drives a
process and does not care what language wrote it, so they join the job the day
the SDKs publish.

## Running one

<!-- doctest: cli -->
```bash
cd examples/dice-roller
astra-plugin check --strict
astra-plugin test
astra-plugin dev
```

`dev` needs a running Astra and Developer Mode — read
[what that costs](../5-publish/sideload.md) first.
