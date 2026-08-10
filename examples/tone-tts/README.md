# Tone TTS

A text-to-speech provider that speaks in beeps. It is a wiring test.

## What it does

Registers as a TTS provider. Given text, it emits one 120 ms sine tone per word,
separated by 60 ms of silence, as a 24 kHz mono WAV the daemon decodes through
its normal audio path. Three "voices" differ only in pitch: 220 Hz, 440 Hz and
880 Hz. Speed changes the tone and gap lengths; pitch is ignored.

You will not enjoy listening to it. What it gives you is a TTS provider with no
model, no download and no latency, so that when speech does not come out of your
speakers you can tell in one attempt whether the problem is the voice model or
everything else.

It also demonstrates the data-driven Voice settings hook: `tts_config_fields`
returns two fields (an envelope slider and a debug-log toggle), the daemon
projects them into the provider descriptor, and Astra's Voice page renders them
with its generic field component. No per-plugin frontend code exists for this
plugin — that is the point of the hook.

## What it needs

Nothing. Audio playback is Astra's job, not the plugin's; this plugin only
produces WAV bytes.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `tts` | The plugin appears as a text-to-speech provider and receives the text to be spoken | It has to be given the text to count the words |

While it is the selected TTS provider, **text Astra is about to speak is sent to
this plugin** — assistant replies, and anything else you have Astra read aloud.
This plugin counts the words and discards the text. It writes nothing and sends
nothing anywhere. A TTS provider that did phone home would look identical from
outside, which is worth remembering when the provider is not this one.

## Configuration

Two fields, rendered on Astra's Voice page from the plugin's own declaration:

| Setting | Default | Meaning |
|---|---|---|
| Envelope shape | `1.0` | 0–1 in steps of 0.05. Strength of the half-sine envelope on each word |
| Log each synthesis call | off | One info-level log line per synthesis |

## Build it yourself

```bash
cd examples/tone-tts
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — 146 lines: voice list, config fields, and a WAV writer over
  `hound`. The minimum viable TTS plugin.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
