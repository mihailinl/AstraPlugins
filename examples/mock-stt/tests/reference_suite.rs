//! mock-stt's reference test suite — what an STT plugin's tests look like.
//!
//! An STT plugin is the hardest kind to test by hand: the input is bytes, the
//! transport is bidirectional streaming, and the failure mode that actually
//! shipped (a truncated utterance) looks exactly like a bad model. So this
//! suite is mostly about audio *arriving whole*.
//!
//! Golden audio comes from `astra_plugin_sdk::testing::fixtures`: f32-LE PCM at
//! 16 kHz in 1600-sample batches, which is what the daemon's capture loop
//! produces, including the wake-word seed burst it dumps in one go.

#[allow(dead_code, unused_imports)]
#[path = "../src/main.rs"]
mod plugin;

use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::testing::{Harness, WireHarness, fixtures};
use plugin::MockStt;

async fn stt() -> astra_plugin_sdk::testing::Running<MockStt> {
    Harness::new(MockStt).start().await.unwrap()
}

// ── level 1 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn reports_the_languages_the_voice_page_offers() {
    assert_eq!(stt().await.stt_languages().await, ["en", "ru", "uk"]);
}

/// The daemon sends f32-LE PCM — four bytes a sample. A plugin that assumes
/// i16 halves every duration it computes and no test of the *text* would say
/// so, which is why the byte and sample counts are asserted directly.
#[tokio::test]
async fn transcribes_one_complete_utterance() {
    let h = stt().await;
    let audio: Vec<u8> = fixtures::utterance().concat();

    let event = h.stt_transcribe(&audio, fixtures::SAMPLE_RATE).await.unwrap();
    assert!(event.is_final, "a complete utterance is a final transcript");
    assert!(event.text.contains(&format!("{} bytes", audio.len())), "{}", event.text);
    assert!(
        event.text.contains(&format!("{} samples", audio.len() / 4)),
        "f32-LE PCM is four bytes a sample: {}",
        event.text,
    );
    assert!(event.text.contains("@ 16000 Hz"), "{}", event.text);
    assert!(
        event.text.contains("lang hint \"en\""),
        "the per-utterance decoding hint is on the first chunk: {}",
        event.text,
    );
}

/// Silence is not an error. The daemon opens a session on every wake, and some
/// of them have nothing in them.
#[tokio::test]
async fn an_empty_utterance_is_a_transcript_and_not_a_failure() {
    let event = stt().await.stt_transcribe(&[], 16_000).await.unwrap();
    assert!(event.text.contains("0 bytes"), "{}", event.text);
}

/// mock-stt implements the one-shot hook only. The SDK's default streaming
/// implementation accumulates every chunk and forwards it, so a non-streaming
/// recognizer answers the streaming path for free — and this is the test that
/// says the accumulation loses nothing.
#[tokio::test]
async fn the_streaming_path_delivers_every_byte_to_a_one_shot_recognizer() {
    let h = stt().await;
    let chunks = fixtures::utterance();
    let total: usize = chunks.iter().map(|c| c.len()).sum();

    let events = h.stt_stream(chunks).await.unwrap();
    assert_eq!(events.len(), 1, "one final transcript: {events:?}");
    assert!(events[0].is_final);
    assert!(
        events[0].text.contains(&format!("{total} bytes")),
        "the whole utterance, not the first chunk: {}",
        events[0].text,
    );
}

/// The wake-word seed dump: ~8 s of pre-roll delivered in one burst the instant
/// the wake word fires. `spec/limits.yaml` sizes the audio channel so this
/// fits; a plugin that receives less than all of it transcribes the tail of an
/// utterance and looks like a bad model.
#[tokio::test]
async fn the_wake_seed_burst_arrives_whole() {
    let h = stt().await;
    let burst = fixtures::wake_seed_burst();
    let total: usize = burst.iter().map(|c| c.len()).sum();

    let events = h.stt_stream(burst).await.unwrap();
    assert!(
        events[0].text.contains(&format!("{total} bytes")),
        "the seed burst was truncated: {}",
        events[0].text,
    );
}

// ── level 2 ──────────────────────────────────────────────────────────────────

/// Over `SttProcess`, which is bidirectional streaming: the audio channel, the
/// inbound forwarder, the sample rate and options riding on the first chunk,
/// and the outbound event stream. None of that exists in process.
#[tokio::test]
async fn the_daemon_can_stream_audio_in_and_read_events_out() {
    let w = WireHarness::start(MockStt).await.unwrap();

    let chunks = fixtures::utterance();
    let total: usize = chunks.iter().map(|c| c.len()).sum();

    let events = w
        .stt_process(chunks, fixtures::SAMPLE_RATE, fixtures::stt_options())
        .await
        .unwrap();

    assert_eq!(events.len(), 1, "{events:?}");
    assert!(events[0].is_final);
    assert!(
        events[0].text.contains(&format!("{total} bytes")),
        "every chunk has to survive the trip: {}",
        events[0].text,
    );
    assert!(events[0].text.contains("lang hint \"en\""), "{}", events[0].text);

    w.shutdown().await.unwrap();
}

/// The same burst, over the wire, where the channel `spec/limits.yaml` sizes
/// actually exists. Sized below the burst, this is where the truncation
/// reappears.
#[tokio::test]
async fn the_wake_seed_burst_survives_the_wire() {
    let w = WireHarness::start(MockStt).await.unwrap();

    let burst = fixtures::wake_seed_burst();
    let total: usize = burst.iter().map(|c| c.len()).sum();

    let events = w
        .stt_process(burst, fixtures::SAMPLE_RATE, fixtures::stt_options())
        .await
        .unwrap();
    assert!(
        events[0].text.contains(&format!("{total} bytes")),
        "the seed burst was truncated on the wire: {}",
        events[0].text,
    );

    w.shutdown().await.unwrap();
}

/// A plugin with no `stt_load` answers `UNIMPLEMENTED`, which the daemon reads
/// as "no model to manage" — the fail-safe. Answering `INTERNAL` here would put
/// the plugin in the daemon's broken list instead.
#[tokio::test]
async fn the_model_lifecycle_hooks_are_absent_not_broken() {
    let w = WireHarness::start(MockStt).await.unwrap();
    let err = w
        .client()
        .stt_get_load_state(w.request(astra_plugin_sdk::proto::Empty {}))
        .await
        .expect_err("mock-stt has no model to load");
    assert_eq!(err.code(), astra_plugin_sdk::tonic::Code::Unimplemented, "{err}");

    let langs = w
        .client()
        .stt_get_languages(w.request(astra_plugin_sdk::proto::Empty {}))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(langs.languages, ["en", "ru", "uk"]);

    w.shutdown().await.unwrap();
}
