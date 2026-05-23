//! Echo STT plugin — plays the captured audio back through the plugin
//! process's own output device, and returns a metadata transcript.
//!
//! Wire-validates the full STT plugin path: the daemon's VAD-segmented
//! utterance reaches the plugin as f32 LE PCM @ 16 kHz mono (per the
//! `stt_transcribe` contract), the plugin decodes those bytes correctly,
//! and the daemon receives the final `SttEvent` back over the bidi stream.
//! Hearing your own voice played back proves the daemon captured real
//! audio and the byte layout matches the documented format.

use astra_plugin_sdk::prelude::*;
use crossbeam_channel::{unbounded, Sender};
use once_cell::sync::Lazy;
use rodio::buffer::SamplesBuffer;
use rodio::{OutputStream, Sink};
use tracing::{info, warn};

/// One playback job — a buffer of i16 mono PCM at the given sample rate.
struct PlayJob {
    sample_rate: u32,
    samples: Vec<i16>,
}

/// `rodio::OutputStream` isn't `Sync` (and on Windows the underlying cpal
/// `Stream` isn't `Send` either), so it can't live in a shared static.
/// Instead, a dedicated OS thread owns the stream for the plugin's
/// lifetime and receives playback jobs over a crossbeam channel.
static AUDIO_TX: Lazy<Sender<PlayJob>> = Lazy::new(|| {
    let (tx, rx) = unbounded::<PlayJob>();
    std::thread::spawn(move || {
        let (_stream, handle) = match OutputStream::try_default() {
            Ok(p) => p,
            Err(e) => {
                warn!("echo-stt: could not open default audio output: {e}");
                return;
            }
        };
        // The receive loop also keeps `_stream` alive — dropping the
        // thread tears the audio device down.
        while let Ok(job) = rx.recv() {
            let sink = match Sink::try_new(&handle) {
                Ok(s) => s,
                Err(e) => {
                    warn!("echo-stt: failed to build sink: {e}");
                    continue;
                }
            };
            sink.append(SamplesBuffer::new(1, job.sample_rate, job.samples));
            // Detach: the sink owns its buffer and will play through, then
            // drop. We don't block here so the next utterance queues up
            // immediately without head-of-line blocking the channel.
            sink.detach();
        }
    });
    tx
});

struct EchoStt;

#[async_trait]
impl PluginCapability for EchoStt {
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into(), "ru".into(), "uk".into()]
    }

    async fn stt_transcribe(
        &self,
        audio: &[u8],
        sample_rate: u32,
    ) -> anyhow::Result<SttEvent> {
        // The daemon sends f32 LE PCM (4 bytes per sample) per the
        // `stt_transcribe` contract; sample rate is whatever the daemon
        // captured at — currently 16 kHz, but trust the field.
        let bytes = audio.len();
        if bytes % 4 != 0 {
            warn!(
                "stt_transcribe: byte count {} is not a multiple of 4 — \
                 not f32 PCM as advertised?",
                bytes
            );
        }
        let samples: Vec<f32> = audio
            .chunks_exact(4)
            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect();
        let duration_ms =
            (samples.len() as u64 * 1000 / sample_rate.max(1) as u64) as u32;

        // Convert to i16 so `SamplesBuffer` plays cleanly on every backend
        // (some don't accept f32 directly).
        let pcm: Vec<i16> = samples
            .iter()
            .map(|&s| (s.clamp(-1.0, 1.0) * 32767.0) as i16)
            .collect();

        if let Err(e) = AUDIO_TX.send(PlayJob {
            sample_rate,
            samples: pcm,
        }) {
            warn!("echo-stt: audio thread is gone: {e}");
        }

        let text = format!(
            "echoed {} samples @ {} Hz ({} ms)",
            samples.len(),
            sample_rate,
            duration_ms
        );
        info!("stt_transcribe: {}", text);
        Ok(SttEvent::transcript(text).with_language("en"))
    }

    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

#[tokio::main]
async fn main() {
    // Touch the lazy so the audio thread spins up at startup, not on the
    // first utterance (small but observable warmup if you don't).
    let _ = &*AUDIO_TX;
    astra_plugin_sdk::run(EchoStt).await.unwrap();
}
