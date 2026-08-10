# Echo STT

A speech-to-text provider that transcribes nothing and plays your microphone
back to you instead. It is a diagnostic tool.

## What it does

Registers itself as an STT provider. When you select it and speak, it takes each
audio chunk the daemon streams to it and plays it out of the machine's default
audio output **as it arrives**, then returns a transcript that describes the
audio rather than its content — byte count, sample count, sample rate.

That is the entire point. If you are writing a real STT plugin and the
transcription is wrong, the first question is whether the daemon is sending you
the audio you think it is: your voice, at the volume you spoke, at the rate you
expected, without gaps. This plugin answers that question with your ears in
about five seconds.

**Wear headphones.** It plays your microphone through your speakers, which is a
feedback loop.

## What it needs

- An **audio output device**. On Linux that means ALSA (`libasound2`); building
  from source additionally needs `libasound2-dev` and `pkg-config`. If no output
  device can be opened, the plugin logs that and keeps running — you get the
  metadata transcript and no sound.
- Nothing else. No network, no model download, no account.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `stt` | The plugin appears as a speech-to-text provider and receives captured microphone audio | It cannot play back audio it is not given |

While it is the selected STT provider, **your microphone audio is streamed to
this plugin** — that is what selecting an STT provider means, for this one or for
any other. This plugin does not store it, does not write it to disk and does not
send it anywhere; it decodes it to samples and hands it to your sound card.

## Configuration

None.

## Build it yourself

```bash
# Linux build dependencies
sudo apt install libasound2-dev pkg-config

cd examples/echo-stt
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — the whole plugin. The interesting part is the dedicated audio
  thread: `rodio`'s output stream is neither `Sync` nor (on Windows) `Send`, so
  one OS thread owns the stream and a single persistent sink for the plugin's
  lifetime. Rebuilding the sink per utterance re-triggers device setup latency
  on every pause, which is audible as ~100 ms amplitude modulation.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
