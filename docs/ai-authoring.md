# AI-assisted plugin authoring

This is the entry point for a coding agent given a user's plain-language plugin
idea from Astra's Plugins → Dev tab. Read the repository's [AGENTS.md](../AGENTS.md)
first. This page is a route through the documentation, not a second plugin
protocol or a substitute for the SDK and CLI.

## 1. Understand the result

Restate the requested behaviour as a few observable checks. Decide which
capabilities the plugin needs; one plugin may combine several. Do not make the
user translate their idea into hook names. Ask only when different answers would
change the result: what data or service to use, which action should happen, an
author or licence, access to a required account, or a project path when no writable workspace is available.
Propose a display name and id for the user to accept. Never invent credentials
or claim an external account is connected. The CLI scaffold may write
`license = "MIT"` by default; do not treat that as the user's decision.
Confirm the author and licence with the owner before publication; do not invent either or accept the scaffold’s MIT default on the user’s behalf. For an explicitly authorized local test without publication, leave an unknown author empty and omit the licence field while undecided. This does not require a licence decision before running the local fixture.

Choose settings before drawing a page. If the user only needs to choose a model
file, enter an API key or change a threshold, use [config fields](en/3-reference/config-fields.md)
so Astra renders the controls. If the plugin needs its own content or workflow
inside the Astra window, read the [UI authoring guide](ui-authoring.md).

## 2. Read only the relevant contract

Begin with [getting started](en/2-tutorial/getting-started.md), the
[manifest reference](en/reference/manifest.md), the guide for the chosen
[Rust](en/4-sdk/rust.md), [Python](en/4-sdk/python.md) or
[TypeScript](en/4-sdk/typescript.md) SDK, and the matching row below. Use
[hook parity](en/reference/parity.md) or [the protocol](en/reference/protocol.md)
for an exact signature only when the SDK guide does not answer it.
An example demonstrates a pattern; check its README and current status before
reusing it. Do not copy a manifest instead of running the CLI scaffold. Keep the manifest’s description in English, and make locales/en.json listing.name/listing.description exactly match plugin.name/plugin.description. Put translated listing text in the appropriate locale file and UI labels in localized keys. After changing metadata, run `astra-plugin locale sync --path .`, then `astra-plugin check . --strict`; see [localisation](en/3-reference/localisation.md) for E8/E11 rules.

| User's need | Capability | Read | Starting example |
|---|---|---|---|
| Give the assistant callable functions | `tools` | [hooks](en/reference/parity.md) | [dice-roller](../examples/dice-roller/) |
| Speak text | `tts` | [provider config fields](en/3-reference/config-fields.md) | [tone-tts](../examples/tone-tts/) |
| Transcribe speech | `stt` | [provider config fields](en/3-reference/config-fields.md) | [mock-stt](../examples/mock-stt/), [echo-stt](../examples/echo-stt/) for streaming |
| Detect a wake word | `wakeword` | [wake word contract](en/wakeword-plugins.md) | No maintained example yet; scaffold as the guide shows, then replay phrase and non-phrase audio |
| Provide an AI completion backend | `ai_provider` | [hook parity](en/reference/parity.md) | Scaffold with `--template ai-provider` |
| Connect another chat surface | `client` | [SDK host calls](en/4-sdk/rust.md) | [telegram-client](../examples/telegram-client/) |
| Add an automation step | `actions` | [hooks](en/reference/parity.md) | [dice-roller](../examples/dice-roller/) |
| Start an automation | `triggers` | [permissions](en/3-reference/permissions.md) | [dice-roller](../examples/dice-roller/) |
| Add an Astra page, panel or overlay | `ui_contributions` | [UI authoring](ui-authoring.md) | Scaffold with `--template ui` |
| Add a user-placed desktop widget | `ui_contributions` | [Desktop widgets](en/4-sdk/desktop-widgets.md) | Scaffold with `--template desktop-widget` |
| React to daemon events | `event_handlers` | [event hooks](en/reference/parity.md), [permissions](en/3-reference/permissions.md) | [Rust SDK events](en/4-sdk/rust.md) |
| Run code in Astra's window | `dom_access` | [UI authoring](ui-authoring.md), [permissions](en/3-reference/permissions.md) | [companion](../examples/companion/) |

The capabilities list is defined by the installed Astra build, not by this
table. A public branch can be ahead of or behind that build. Compare its
manifest and hooks with the build information in the copied assignment.
If a needed capability or hook is absent from the public docs, obtain the
matching checkout or the build's offline instructions before implementing it.
Do not guess based on another capability. For unreleased desktop widgets, use the supplied matching CLI and SDK artifacts rather than assuming a registry version contains the feature. The [widget guide](en/4-sdk/desktop-widgets.md) provides local dependency setup, exact modules in all SDKs and compiled Kit props; runtime source is not needed for authoring. In particular, a local development
build may expose wake-word support before this page is published.

## 3. Build and prove it

1. Run `astra-plugin new <id> --lang <language> --template <closest-template>`
   with `--output <new-path>` if the user chose a location. The output path
   must not exist yet; the CLI creates it. The [CLI reference](en/reference/cli.md)
   lists templates; add other capabilities in the generated manifest.
2. Implement through an SDK. For a desktop widget, use the complete descriptor examples and retain the scaffold initialization. Define stable formats/surfaces, explicit size bounds and `repeatable` as needed. Use `astra.widget` instance config/data, preserve other config keys on replacement, validate finite bounded numbers, and subscribe to context/data changes. Own settings are opened by the host editor and edit its Save/Cancel draft; they do not write instance data. Preview uses sample data and disabled actions. Surface opening returns a token and receives parameters via `context.params`. Declare only permissions the code uses and write
   their reasons for the person who will see the install consent.
3. Add focused tests for the plugin's behaviour, including the unhappy path.
   Run `astra-plugin check . --strict` and `astra-plugin test .`; fix failures.
4. If you made a page, panel, desktop widget or overlay, load it through `astra-plugin dev .`
   and inspect it in the running Astra window. Verify the states in the
   [UI authoring guide](ui-authoring.md). A green build cannot prove layout.
5. Produce `astra-plugin build .` output. The recipient should not need your SDK source checkout; Python still requires its declared interpreter and installed runtime dependencies. Do not accept a guessed author/license from scaffold defaults; an explicitly local test may leave author empty and licence omitted until the owner decides before publication. Report which checks actually ran, remaining limitations, and the absolute
   path to the plugin folder. The user loads that folder in Plugins → Dev.

If the repository cannot be reached, say which source you could read. Ask for
a clone or use the offline instructions from Astra's Dev tab. Never claim to
have checked a page, SDK, CLI or screen you could not access.
