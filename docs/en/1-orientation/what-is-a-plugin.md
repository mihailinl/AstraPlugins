# What a plugin is

A plugin is a **separate program** that the Astra daemon starts, and that talks
to the daemon over gRPC on localhost. It is not a library, it is not loaded into
Astra's address space, and it is not a script Astra interprets. Astra spawns it
the way a shell would, with arguments on the command line, and stops it by
asking it to shut down and then killing the process group if it does not.

That single fact decides most of the rest:

- **You can write it in anything** that speaks gRPC. Three SDKs ship here —
  Rust, Python, TypeScript — and they are at
  [full parity](../reference/parity.md): all 35 hooks in all three.
- **It has your privileges, not fewer.** See [the security model](security.md).
- **It survives its own bugs badly and Astra's not at all.** A panic in a
  handler is caught and returned as an error rather than killing the process
  (`astra-plugin-sdk/src/panics.rs`); a crash of the whole process is noticed by
  the daemon's health check within 15 s.

## The two directions

Everything a plugin does is one of two things, and they are separate systems
with separate names in `plugin.toml`.

| | Direction | Manifest section | Answers |
|---|---|---|---|
| **Capabilities** | daemon → plugin | `[capabilities]` | What the plugin implements and Astra may call *into* |
| **Permissions** | plugin → daemon | `[permissions]` | Which host RPCs the plugin may call *out* to |

They used to be one word for both, which is how `dom_access` — the most
dangerous thing in the system — came to be something a plugin granted itself by
declaring it. They are two words now. Declaring
`[capabilities] event_handlers = true` does not let you subscribe to events;
`[permissions] subscribe_events` does, and only after the user consents.

`[permissions]` is **default-deny**: with no section at all, a plugin may call
`Register`, `PluginLog`, `GetPluginSelfConfig` and `GetDaemonInfo` and nothing
else ([`spec/permissions.md` §2](../spec/permissions.md)).

## The ten capabilities

Every key is a boolean, defaults to `false`, and obliges you to serve some
hooks. The right-hand column is the *required* ones; the optional ones are in
[the parity table](../reference/parity.md).

| `[capabilities]` key | Your plugin becomes | Hooks you must serve |
|---|---|---|
| `tools` | a set of functions the model can call | `ListTools`, `CallTool` |
| `tts` | a text-to-speech provider in the Voice settings | `TtsSynthesize`, `TtsListVoices` |
| `stt` | a speech-to-text provider | `SttProcess`, `SttGetLanguages` |
| `ai_provider` | a model backend | `AiComplete` |
| `actions` | steps in the command editor | `ExecuteAction`, `GetPluginActionTypes` |
| `triggers` | trigger types commands can listen for | `GetPluginTriggerTypes`, `FireTrigger` |
| `ui_contributions` | panels, pages and overlays in the Astra window | `GetUiContributions` |
| `event_handlers` | a subscriber to daemon events | `SubscribeEvents` |
| `client` | a chat front-end of its own | `SendChatMessage` |
| `dom_access` | code running inside the Astra window | none — it is a rendering decision, not a hook |

Source: [`reference/manifest.md`](../reference/manifest.md), generated from the
crate the daemon parses your manifest with. `ui_panels` is not a capability and
never was — three shipped examples declared it, serde dropped the unknown key,
and the only symptom was `astra-plugin check` reporting no capabilities at all.
`[capabilities]` refuses unknown keys for exactly that reason.

## What a manifest looks like

The smallest useful one — a plugin with tools, no permissions, nothing else:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat."
author = "You"
license = "MIT"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
```

One that fires a trigger has to ask for the permission, and the `reason` is what
the user reads when Astra asks them to consent:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice, and fire a trigger when one comes up."
author = "You"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

Every section and key: [`reference/manifest.md`](../reference/manifest.md).

## What a plugin cannot do

- **It cannot grant itself a permission — once it is installed.** The
  `[permissions]` block is a request. For a plugin installed from the registry
  or imported as a file, the granted set is resolved by the daemon from where
  the plugin came from and stored where the plugin cannot write it — the
  manifest lives in the plugin's own directory, which the plugin can edit.
  **A sideloaded plugin is the exception**: at that tier the manifest *is* the
  consent record and there is no ceiling, so it can widen its own permissions by
  editing its own file. See
  [the security model](security.md#where-a-plugin-came-from-decides-its-ceiling).
- **It cannot reach Astra's `ChatService` directly.** The session token a plugin
  gets at registration is scoped to `PluginHostService`. Driving an AI turn goes
  through `SendChatMessage`, which is gated on the `send_chat_message`
  permission and is a high-risk one.
- **It cannot depend on an unrouted hook.** A hook can exist in the proto and in
  all three SDKs and have no daemon call site: `TtsSynthesizeStream` is one
  today. Implementing it is free; relying on being called is not supported until
  the [parity table](../reference/parity.md) says `live`.
- **It cannot be installed on a platform it has no bundle for.** See
  [platforms](platforms.md).

## Next

[Architecture](architecture.md) if you want to know how the process is started
and authenticated, or go straight to
[Getting started](../2-tutorial/getting-started.md).
