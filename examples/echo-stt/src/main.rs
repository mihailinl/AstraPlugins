//! Echo STT plugin — plays the captured audio back through the plugin
//! process's own output device in REAL TIME, and returns a metadata
//! transcript when the daemon signals end-of-utterance.
//!
//! Wire-validates the streaming STT path: the daemon ships f32-LE PCM
//! at 16 kHz mono per chunk; this plugin pushes each chunk to a single
//! persistent rodio `Sink` so they play gap-lessly as they arrive. The
//! sink's resampler converts 16 kHz to the device's native rate.

use astra_plugin_sdk::prelude::*;
use crossbeam_channel::{unbounded, Sender};
use once_cell::sync::Lazy;
use rodio::buffer::SamplesBuffer;
use rodio::{OutputStream, Sink};
use tokio::sync::mpsc;
use tracing::{info, warn};

/// One playback job: f32 mono samples in [-1.0, 1.0] at the declared rate.
struct PlayJob {
    sample_rate: u32,
    samples: Vec<f32>,
}

/// `rodio::OutputStream` isn't `Sync` (and on Windows the underlying cpal
/// `Stream` isn't `Send` either), so a dedicated OS thread owns the
/// stream + sink for the plugin's lifetime. Append-only command channel
/// — one persistent `Sink` plays every chunk gap-lessly. Rebuilding the
/// sink per utterance would re-trigger device setup latency on every
/// short pause and was the source of the ~100 ms AM-modulation artifact
/// observed before.
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
        let sink = match Sink::try_new(&handle) {
            Ok(s) => s,
            Err(e) => {
                warn!("echo-stt: failed to build sink: {e}");
                return;
            }
        };
        while let Ok(job) = rx.recv() {
            sink.append(SamplesBuffer::new(
                1u16,
                job.sample_rate,
                job.samples,
            ));
        }
    });
    tx
});

fn samples_from_bytes(audio: &[u8]) -> Vec<f32> {
    if audio.len() % 4 != 0 {
        warn!(
            "echo-stt: byte count {} is not a multiple of 4 — \
             not f32 PCM as advertised?",
            audio.len()
        );
    }
    audio
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

struct EchoStt;

#[async_trait]
impl PluginCapability for EchoStt {
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into(), "ru".into(), "uk".into()]
    }

    /// Non-streaming fallback — kept so the plugin still works if a
    /// caller bypasses the streaming hook.
    async fn stt_transcribe(
        &self,
        audio: &[u8],
        sample_rate: u32,
    ) -> anyhow::Result<SttEvent> {
        let samples = samples_from_bytes(audio);
        let sample_count = samples.len();
        let _ = AUDIO_TX.send(PlayJob {
            sample_rate,
            samples,
        });
        let duration_ms = (sample_count as u64 * 1000 / sample_rate.max(1) as u64) as u32;
        let text = format!(
            "echoed {} samples @ {} Hz ({} ms) [non-streaming]",
            sample_count, sample_rate, duration_ms
        );
        info!("stt_transcribe (fallback): {}", text);
        Ok(SttEvent::transcript(text).with_language("en"))
    }

    /// Streaming hook — daemon pushes mic chunks live. Each one is queued
    /// to the persistent sink. End-of-utterance returns one final
    /// metadata event for the chat.
    async fn stt_transcribe_stream(
        &self,
        mut audio_rx: mpsc::Receiver<Vec<u8>>,
        events_tx: mpsc::Sender<SttEvent>,
        sample_rate: u32,
    ) -> anyhow::Result<()> {
        let mut total_samples: usize = 0;
        while let Some(chunk) = audio_rx.recv().await {
            if chunk.is_empty() {
                continue;
            }
            let samples = samples_from_bytes(&chunk);
            total_samples += samples.len();
            let _ = AUDIO_TX.send(PlayJob {
                sample_rate,
                samples,
            });
        }
        let duration_ms = (total_samples as u64 * 1000 / sample_rate.max(1) as u64) as u32;
        let text = format!(
            "echoed {} samples @ {} Hz ({} ms) [streamed]",
            total_samples, sample_rate, duration_ms
        );
        info!("stt_transcribe_stream: {}", text);
        let _ = events_tx
            .send(SttEvent::transcript(text).with_language("en"))
            .await;
        Ok(())
    }

    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

#[tokio::main]
async fn main() {
    // Touch the lazy so the audio thread + sink spin up at startup, not
    // on the first utterance — the first sink-build is the slowest one
    // and would otherwise add latency to the very first chunk.
    let _ = &*AUDIO_TX;
    astra_plugin_sdk::run(EchoStt).await.unwrap();
}
