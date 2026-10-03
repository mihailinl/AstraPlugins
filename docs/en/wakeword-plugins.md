# Wake word plugins

A wake word plugin declares `wakeword = true` in the `[capabilities]` section of
its `plugin.toml`. Astra lists installed plugins with that capability under
**Voice → Wake Word**. The choice and its settings disappear when the plugin is
uninstalled. The plugin does not need a separate page or a UI contribution.

## Start a new detector

Use the current CLI and a fresh output directory:

<!-- doctest: cli -->
```bash
astra-plugin new my-wakeword --lang rust --template blank --capabilities wakeword --output ./my-wakeword
```

`--lang` may also be `python` or `typescript`. There is no wakeword
template yet. The Rust blank scaffold includes an unrelated `hello` tool
and its test: replace both. Keep `wakeword = true` as the only capability
unless the plugin actually serves other features. Use `astra-plugin check`
to catch a mismatch between the manifest and compiled binary.

The daemon sends the three calls below through `CallFromUi`, even for a
wakeword-only plugin. This is a transport reuse; it does not require
`ui_contributions`, an iframe, or `push_to_ui`. Generic hook tables list
`CallFromUi` under UI because that is its original use.

For Rust, implement the SDK's `handle_ui_call(&self, ctx: &PluginContext,
method: &str, params_json: &str) -> Result<String, ToolError>` hook, or use
`#[ui_call]` methods (with `#[ui_call(name = "process-audio")]` and
`#[ui_call(name = "reset-audio")]` for the hyphenated names); each
`#[ui_call]` method needs a `///` doc comment, or the macro refuses to
compile it. Set `#[astra::plugin(capabilities = "wakeword")]` on the impl
block (the scaffold above already does): automatic `#[ui_call]` inference
otherwise declares `ui_contributions`, which disagrees with the manifest.
Route `status`, `reset-audio`, and `process-audio` to one detector instance
whose frame buffer is retained between calls. Return JSON strings with the
response shapes below.
In Python, use the SDK's `@ui_call` handlers; in TypeScript, use
`ui: { contributions: [], onCall: { ... } }` with the three method names.
These handlers do not create a visible UI page.
See the [Rust](4-sdk/rust.md), [Python](4-sdk/python.md), and
[TypeScript](4-sdk/typescript.md) SDK guides for the surrounding entry point,
configuration access, and lifecycle.

The plugin supplies its settings through the existing `[config]` JSON Schema.
Astra shows the fields in Voice only while that plugin is selected and saves
them through `UpdatePluginConfig`. String, number, boolean and enum properties
are supported. A string with `"format": "password"` uses a password field;
`"format": "file"` (or `"x-astra-field-type": "file_picker"`) offers a local
file picker. `"x-astra-field-type": "slider"` and `"textarea"` choose those
controls for numeric and string properties. The plugin reads the configured
path; Astra does not prescribe a keyword-model format.

Protocol 1 uses the authenticated `CallFromUi` request/response channel for
three methods. This is an internal daemon call; no iframe or page is created.

| Method | Request JSON | Response JSON |
|---|---|---|
| `status` | `{}` | `{"ready": true}` or `{"ready": false, "message": "…"}` |
| `process-audio` | `{"pcm_base64": "…"}` | `{"detected": false}` or `{"detected": true}` |
| `reset-audio` | `{}` | `{}` |

`pcm_base64` contains 16 kHz mono, signed 16-bit little-endian PCM. Astra
sends 100 ms (1600 samples) per call. The plugin must retain samples between
calls if its detector has a different frame length. `reset-audio` discards
that retained audio and the model's partial detection state when Astra resets
the wake gate. Decode Base64, reject malformed or odd-length PCM, convert each
little-endian byte pair to an `i16`, then feed the samples to the detector in
order. Do not treat each 100 ms batch as a complete utterance. Each call has a
two-second deadline; the audio loop uses a bounded queue and never waits for
the plugin.
`astra-plugin test` calls all three methods and checks their JSON response
shapes, including an all-zero audio batch while the plugin may be unconfigured.
That test does not verify that the chosen keyword is detected. Before delivery,
load a valid model and check `status.ready = true`; replay several recorded
utterances of the wake phrase across multiple 100 ms calls; and replay silence,
background noise, and ordinary speech as negative cases. Verify that
`reset-audio` clears a partial phrase and that detection works after reset.
Then install or sideload the plugin, select it in **Voice → Wake Word**, and
confirm that Astra starts listening and wakes on the phrase. An unconfigured
model should report `ready: false` with a useful message.

Astra checks `status.ready` before starting listening. If the selected plugin
is missing, stopped or not ready, listening fails closed rather than silently
turning into continuous transcription. Runtime selection uses
`voice.wake_word_mode = "plugin__<id>"`, replacing hyphens in the plugin ID with
underscores, as STT and TTS plugin provider IDs do.
Report `ready: true` only after the detector and its configured model can
process audio; the presence of a file path alone is insufficient.
