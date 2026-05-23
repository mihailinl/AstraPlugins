//! Echo STT plugin — plays the captured audio back through the plugin
//! process's own output device in REAL TIME, and returns a metadata
//! transcript when the daemon signals end-of-utterance.
//!
//! Implements the SDK's streaming hook `stt_transcribe_stream`: each
//! f32-LE PCM chunk the daemon ships off the mic is played the instant
//! it arrives. The only delay between speaking and hearing the echo is
//! the audio device buffer (~30-50 ms), not the VAD silence-window
//! (~500 ms). The wire-test value is the same as the non-streaming
//! version (proves the daemon ships real audio, in the documented byte
//! layout, at the documented sample rate) — plus it proves that
//! streaming STT actually flows end-to-end.
//!
//! A non-streaming plugin SDK consumer would just override
//! `stt_transcribe` and let the SDK's default `stt_transcribe_stream`
//! buffer everything for them.

use astra_plugin_sdk::prelude::*;
use crossbeam_channel::{unbounded, Sender};
use once_cell::sync::Lazy;
use rodio::buffer::SamplesBuffer;
use rodio::{OutputStream, Sink};
use tokio::sync::mpsc;
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
///
/// We keep ONE long-lived `Sink` per utterance — appending chunks to it
/// gap-lessly plays them as a continuous stream. The sink is rotated on
/// every utterance boundary so a new utterance doesn't queue behind the
/// previous one.
enum AudioCmd {
    Start { sample_rate: u32 },
    Append(PlayJob),
    End,
}

static AUDIO_TX: Lazy<Sender<AudioCmd>> = Lazy::new(|| {
    let (tx, rx) = unbounded::<AudioCmd>();
    std::thread::spawn(move || {
        let (_stream, handle) = match OutputStream::try_default() {
            Ok(p) => p,
            Err(e) => {
                warn!("echo-stt: could not open default audio output: {e}");
                return;
            }
        };
        let mut current_sink: Option<Sink> = None;
        let mut current_rate: u32 = 0;
        while let Ok(cmd) = rx.recv() {
            match cmd {
                AudioCmd::Start { sample_rate } => {
                    current_rate = sample_rate;
                    current_sink = match Sink::try_new(&handle) {
                        Ok(s) => Some(s),
                        Err(e) => {
                            warn!("echo-stt: sink failed: {e}");
                            None
                        }
                    };
                }
                AudioCmd::Append(job) => {
                    if let Some(ref sink) = current_sink {
                        let rate = if job.sample_rate > 0 {
                            job.sample_rate
                        } else {
                            current_rate
                        };
                        sink.append(SamplesBuffer::new(1, rate, job.samples));
                    }
                }
                AudioCmd::End => {
                    if let Some(sink) = current_sink.take() {
                        sink.detach(); // play through, then drop
                    }
                }
            }
        }
    });
    tx
});

fn samples_from_bytes(audio: &[u8]) -> (Vec<i16>, usize) {
    if audio.len() % 4 != 0 {
        warn!(
            "echo-stt: byte count {} is not a multiple of 4 — \
             not f32 PCM as advertised?",
            audio.len()
        );
    }
    let f32_samples: Vec<f32> = audio
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect();
    let count = f32_samples.len();
    let pcm: Vec<i16> = f32_samples
        .iter()
        .map(|&s| (s.clamp(-1.0, 1.0) * 32767.0) as i16)
        .collect();
    (pcm, count)
}

struct EchoStt;

#[async_trait]
impl PluginCapability for EchoStt {
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into(), "ru".into(), "uk".into()]
    }

    /// Non-streaming fallback. Reachable if a caller bypasses the streaming
    /// hook — keep it functional so the plugin still works in that path.
    async fn stt_transcribe(
        &self,
        audio: &[u8],
        sample_rate: u32,
    ) -> anyhow::Result<SttEvent> {
        let (pcm, sample_count) = samples_from_bytes(audio);
        let _ = AUDIO_TX.send(AudioCmd::Start { sample_rate });
        let _ = AUDIO_TX.send(AudioCmd::Append(PlayJob {
            sample_rate,
            samples: pcm,
        }));
        let _ = AUDIO_TX.send(AudioCmd::End);
        let duration_ms = (sample_count as u64 * 1000 / sample_rate.max(1) as u64) as u32;
        let text = format!(
            "echoed {} samples @ {} Hz ({} ms) [non-streaming path]",
            sample_count, sample_rate, duration_ms
        );
        info!("stt_transcribe (fallback): {}", text);
        Ok(SttEvent::transcript(text).with_language("en"))
    }

    /// Streaming hook — the daemon (Wave 4.2k) pushes mic chunks live as
    /// VAD detects speech; each one is queued into the audio thread's
    /// sink and starts playing immediately. End-of-utterance closes the
    /// audio channel; we emit one final event with utterance metadata.
    async fn stt_transcribe_stream(
        &self,
        mut audio_rx: mpsc::Receiver<Vec<u8>>,
        events_tx: mpsc::Sender<SttEvent>,
        sample_rate: u32,
    ) -> anyhow::Result<()> {
        let _ = AUDIO_TX.send(AudioCmd::Start { sample_rate });
        let mut total_samples: usize = 0;
        while let Some(chunk) = audio_rx.recv().await {
            if chunk.is_empty() {
                continue;
            }
            let (pcm, sample_count) = samples_from_bytes(&chunk);
            total_samples += sample_count;
            let _ = AUDIO_TX.send(AudioCmd::Append(PlayJob {
                sample_rate,
                samples: pcm,
            }));
        }
        let _ = AUDIO_TX.send(AudioCmd::End);
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
    let _ = &*AUDIO_TX;
    astra_plugin_sdk::run(EchoStt).await.unwrap();
}
