//! Test STT plugin. Ignores the audio content and returns a deterministic
//! description of what it received (byte count, declared sample rate, mean
//! amplitude of the first few f32 samples). Lets you verify the full STT
//! plugin wire without depending on a real speech model.

use astra_plugin_sdk::prelude::*;
use tracing::info;

struct MockStt;

#[async_trait]
impl PluginCapability for MockStt {
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into(), "ru".into(), "uk".into()]
    }

    async fn stt_transcribe(
        &self,
        audio: &[u8],
        sample_rate: u32,
    ) -> anyhow::Result<SttEvent> {
        let bytes = audio.len();
        // Daemon sends f32-LE PCM (4 bytes per sample).
        let sample_count = bytes / 4;
        let mean_amp = if sample_count == 0 {
            0.0_f32
        } else {
            let take = sample_count.min(1024);
            let mut sum = 0.0_f64;
            for i in 0..take {
                let off = i * 4;
                let v = f32::from_le_bytes([
                    audio[off],
                    audio[off + 1],
                    audio[off + 2],
                    audio[off + 3],
                ]);
                sum += v.abs() as f64;
            }
            (sum / take as f64) as f32
        };

        let text = format!(
            "mock transcript: {} bytes, {} samples @ {} Hz, mean amp {:.4}",
            bytes, sample_count, sample_rate, mean_amp
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
    astra_plugin_sdk::run(MockStt).await.unwrap();
}
