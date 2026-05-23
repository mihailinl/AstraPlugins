//! Test TTS plugin. For each word in the input text it emits a short sine tone
//! at the voice's base frequency, separated by silence. The output is a WAV
//! blob the daemon can decode through its normal `AudioFormat::Wav` path.

use astra_plugin_sdk::prelude::*;
use tracing::info;

const SAMPLE_RATE: u32 = 24_000;
const WORD_MS: u32 = 120;
const GAP_MS: u32 = 60;

struct ToneTts;

impl ToneTts {
    fn voice_freq(voice_id: &str) -> f32 {
        match voice_id {
            "low" => 220.0,
            "high" => 880.0,
            _ => 440.0,
        }
    }

    fn synth_wav(text: &str, voice_id: &str, speed: f32) -> anyhow::Result<Vec<u8>> {
        let freq = Self::voice_freq(voice_id);
        let speed = if speed > 0.1 { speed } else { 1.0 };
        let word_samples = ((WORD_MS as f32 / 1000.0) * SAMPLE_RATE as f32 / speed) as usize;
        let gap_samples = ((GAP_MS as f32 / 1000.0) * SAMPLE_RATE as f32 / speed) as usize;

        let words = text.split_whitespace().count().max(1);
        let total = words * word_samples + (words.saturating_sub(1)) * gap_samples;
        let mut samples: Vec<f32> = Vec::with_capacity(total);

        let dt = 1.0 / SAMPLE_RATE as f32;
        for w in 0..words {
            let phase_base = w as f32 * 0.37;
            for n in 0..word_samples {
                let t = n as f32 * dt;
                let env = (n as f32 / word_samples as f32 * std::f32::consts::PI).sin();
                let s = (2.0 * std::f32::consts::PI * freq * t + phase_base).sin();
                samples.push(0.4 * env * s);
            }
            if w + 1 < words {
                samples.extend(std::iter::repeat(0.0).take(gap_samples));
            }
        }

        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: SAMPLE_RATE,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut buf = std::io::Cursor::new(Vec::<u8>::new());
        {
            let mut writer = hound::WavWriter::new(&mut buf, spec)?;
            for s in &samples {
                let clamped = s.clamp(-1.0, 1.0);
                writer.write_sample((clamped * 32767.0) as i16)?;
            }
            writer.finalize()?;
        }
        Ok(buf.into_inner())
    }
}

#[async_trait]
impl PluginCapability for ToneTts {
    async fn tts_voices(&self) -> Vec<VoiceInfo> {
        vec![
            VoiceInfo {
                id: "default".into(),
                name: "Tone — 440 Hz".into(),
                language: "any".into(),
                gender: "neutral".into(),
                preview_url: String::new(),
            },
            VoiceInfo {
                id: "low".into(),
                name: "Tone — 220 Hz".into(),
                language: "any".into(),
                gender: "neutral".into(),
                preview_url: String::new(),
            },
            VoiceInfo {
                id: "high".into(),
                name: "Tone — 880 Hz".into(),
                language: "any".into(),
                gender: "neutral".into(),
                preview_url: String::new(),
            },
        ]
    }

    async fn tts_synthesize(
        &self,
        text: &str,
        voice_id: &str,
        speed: f32,
        _pitch: f32,
    ) -> anyhow::Result<AudioData> {
        info!(
            "tts_synthesize: voice={}, speed={:.2}, len={}",
            voice_id,
            speed,
            text.len()
        );
        let wav = Self::synth_wav(text, voice_id, speed)?;
        let words = text.split_whitespace().count().max(1) as u32;
        let duration_ms = words * WORD_MS + words.saturating_sub(1) * GAP_MS;
        Ok(AudioData {
            data: wav,
            format: "wav".into(),
            sample_rate: SAMPLE_RATE,
            duration_ms,
        })
    }

    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

#[tokio::main]
async fn main() {
    astra_plugin_sdk::run(ToneTts).await.unwrap();
}
