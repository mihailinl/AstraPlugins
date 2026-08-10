# Mock STT

A speech-to-text provider that never transcribes anything. It is a wiring test.

## What it does

Registers as an STT provider and, for every utterance, returns a deterministic
sentence describing the audio it was handed:

```
mock transcript: 64000 bytes, 16000 samples @ 16000 Hz, mean amp 0.0731
```

No model, no download, no GPU, no delay. If that line appears in your
conversation after you speak, the whole STT path — capture, endpointing,
transport, the plugin protocol, the result coming back into the chat — is
working, and any remaining problem is in the model, not the plumbing.

It advertises three languages (`en`, `ru`, `uk`) so the language selector has
something to show. They make no difference to the output.

## What it needs

Nothing. No audio device, no network, no model, no configuration. It is the
lightest possible thing that can occupy the STT slot.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `stt` | The plugin appears as a speech-to-text provider and receives captured microphone audio | It has to be handed the audio to describe it |

While it is the selected STT provider, your microphone audio is streamed to this
plugin. It reads at most the first 1024 samples to compute a mean amplitude,
keeps nothing, writes nothing and sends nothing anywhere.

## Configuration

None.

## Build it yourself

```bash
cd examples/mock-stt
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — 59 lines. This is the minimum viable STT plugin; start here
  before writing a real one.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
