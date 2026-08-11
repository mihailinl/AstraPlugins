//! Golden inputs: audio the daemon really sends, chat events the firehose
//! really carries, and config payloads that really arrive.
//!
//! Everything here is **deterministic** — same bytes on every run, on every
//! machine, with no clock and no RNG. A fixture that varies is a test that
//! fails on someone else's laptop and nowhere else.

use crate::capability::SttOptions;
use crate::proto;

/// The sample rate the daemon's voice pipeline captures at, and therefore the
/// only rate an STT plugin is ever handed.
pub const SAMPLE_RATE: u32 = 16_000;

/// Samples in one captured batch: 100 ms at [`SAMPLE_RATE`].
///
/// The daemon batches the microphone at 1600 samples, which is why the
/// wake-word seed dump is ~80 chunks and not ~8.
pub const SAMPLES_PER_CHUNK: usize = 1_600;

/// Bytes in one chunk. The wire format is f32 little-endian PCM — 4 bytes a
/// sample — and a plugin that assumes i16 halves every duration it computes.
pub const BYTES_PER_CHUNK: usize = SAMPLES_PER_CHUNK * 4;

/// How long the wake-word seed buffer is, in captured chunks.
///
/// The daemon holds a rolling pre-roll so the utterance that *contains* the
/// wake word is transcribed rather than the tail after it, and dumps the whole
/// thing into the STT session the instant the word fires. ~8 s at 100 ms a
/// chunk. This is the burst that has to survive the trip.
pub const WAKE_SEED_CHUNKS: usize = 80;

/// One chunk of f32-LE PCM: a 440 Hz sine at `amplitude`, phase-continuous
/// from sample index `start`.
///
/// Deterministic and shaped like real audio — a plugin that computes a mean
/// amplitude (mock-stt does) gets a number that is stable and not zero.
pub fn pcm_chunk(start: usize, amplitude: f32) -> Vec<u8> {
    let mut out = Vec::with_capacity(BYTES_PER_CHUNK);
    for i in 0..SAMPLES_PER_CHUNK {
        let t = (start + i) as f32 / SAMPLE_RATE as f32;
        let v = amplitude * (std::f32::consts::TAU * 440.0 * t).sin();
        out.extend_from_slice(&v.to_le_bytes());
    }
    out
}

/// `chunks` chunks of continuous 440 Hz PCM.
pub fn pcm(chunks: usize) -> Vec<Vec<u8>> {
    (0..chunks)
        .map(|c| pcm_chunk(c * SAMPLES_PER_CHUNK, 0.25))
        .collect()
}

/// One second of speech-shaped audio: ten chunks. The ordinary case.
pub fn utterance() -> Vec<Vec<u8>> {
    pcm(10)
}

/// The wake-word seed dump: [`WAKE_SEED_CHUNKS`] chunks delivered back to back,
/// as fast as the transport will take them, before any live audio arrives.
///
/// This is the burst that exposed the 32-vs-500 channel mismatch: the daemon
/// pushed the whole pre-roll into a channel the SDK had sized at 32, and every
/// utterance reached the recognizer truncated to its first fraction.
pub fn wake_seed_burst() -> Vec<Vec<u8>> {
    pcm(WAKE_SEED_CHUNKS)
}

/// Exactly [`crate::limits::STT_AUDIO_CHANNEL_CAPACITY`] chunks — the largest
/// burst the contract says a plugin must absorb without the daemon's writer
/// blocking.
///
/// The count is read from the generated limit, never typed out: the number
/// lives in `spec/limits.yaml`, and a fixture with its own copy of it is
/// exactly the drift the spec exists to prevent.
pub fn channel_saturating_burst() -> Vec<Vec<u8>> {
    pcm(crate::limits::STT_AUDIO_CHANNEL_CAPACITY as usize)
}

/// The per-utterance decoding hints the daemon puts on the first chunk:
/// a language and the configured wake-word spellings as decoding bias.
pub fn stt_options() -> SttOptions {
    SttOptions {
        language: "en".into(),
        initial_prompt: "Astra, hey Astra".into(),
    }
}

// ── the chat firehose ────────────────────────────────────────────────────────

fn evt(seq: u64, event: proto::conversation_event_msg::Event) -> proto::ConversationEventMsg {
    proto::ConversationEventMsg {
        seq,
        timestamp: None,
        source_id: "test".into(),
        event: Some(event),
    }
}

/// One complete assistant turn as it arrives on `SubscribeChatEvents`: user
/// message, assistant start, two text deltas, a tool call and its result,
/// assistant complete.
///
/// Seqs are monotonic and start at 1, which is what a plugin that dedups by
/// seq needs in order to be testable at all.
pub fn firehose_events() -> Vec<proto::FirehoseEventMsg> {
    use proto::conversation_event_msg::Event as E;
    let conversation_id = "conv-1".to_string();
    let message_id = "msg-1".to_string();

    let events = vec![
        evt(
            1,
            E::UserMessage(proto::UserMessageEvt {
                message_id: "user-1".into(),
                content: "roll 2d20".into(),
                ..Default::default()
            }),
        ),
        evt(
            2,
            E::AssistantStart(proto::AssistantStartEvt {
                message_id: message_id.clone(),
            }),
        ),
        evt(
            3,
            E::AssistantTextDelta(proto::AssistantTextDeltaEvt {
                message_id: message_id.clone(),
                delta: "Rolling".into(),
            }),
        ),
        evt(
            4,
            E::ToolCallStart(proto::ToolCallStartEvt {
                message_id: message_id.clone(),
                call_id: "call-1".into(),
                name: "roll_dice".into(),
                arguments: r#"{"count":2,"sides":20}"#.into(),
            }),
        ),
        evt(
            5,
            E::ToolCallResult(proto::ToolCallResultEvt {
                call_id: "call-1".into(),
                output: "Rolled 2d20: [7, 20] = 27".into(),
                status: "completed".into(),
            }),
        ),
        evt(
            6,
            E::AssistantTextDelta(proto::AssistantTextDeltaEvt {
                message_id: message_id.clone(),
                delta: " — 27.".into(),
            }),
        ),
        evt(
            7,
            E::AssistantComplete(proto::AssistantCompleteEvt {
                message_id: message_id.clone(),
            }),
        ),
    ];

    events
        .into_iter()
        .map(|event| proto::FirehoseEventMsg {
            conversation_id: conversation_id.clone(),
            event: Some(event),
        })
        .collect()
}

/// A turn that ends in an error, which is the branch nobody writes a test for.
pub fn firehose_error_turn() -> Vec<proto::FirehoseEventMsg> {
    use proto::conversation_event_msg::Event as E;
    vec![
        proto::FirehoseEventMsg {
            conversation_id: "conv-2".into(),
            event: Some(evt(
                1,
                E::AssistantStart(proto::AssistantStartEvt {
                    message_id: "msg-2".into(),
                }),
            )),
        },
        proto::FirehoseEventMsg {
            conversation_id: "conv-2".into(),
            event: Some(evt(
                2,
                E::Error(proto::ErrorEvt {
                    message_id: "msg-2".into(),
                    content: "provider returned 429".into(),
                }),
            )),
        },
        // An event whose oneof is empty: a daemon newer than this SDK sending a
        // variant prost cannot name. A plugin must ignore it, not panic.
        proto::FirehoseEventMsg {
            conversation_id: "conv-2".into(),
            event: Some(proto::ConversationEventMsg {
                seq: 3,
                ..Default::default()
            }),
        },
    ]
}

// ── config ───────────────────────────────────────────────────────────────────

/// Config payloads that a plugin has to survive, each with the reason it is in
/// the list.
///
/// Not random: fuzzing a JSON parser tests serde. These are the payloads the
/// *daemon* actually produces, and every one of them has been a live plugin
/// bug — starting with `{}`, which is what a freshly installed plugin is sent
/// and which a config type without `#[serde(default)]` rejects.
pub fn config_fuzz() -> Vec<(&'static str, &'static str)> {
    vec![
        ("{}", "a fresh install: nothing has been configured yet"),
        ("", "the daemon has no stored config at all"),
        ("   ", "whitespace, from a hand-edited settings file"),
        ("null", "a settings row that was written as JSON null"),
        (
            r#"{"unknown_field":1}"#,
            "a setting from a newer version of this plugin",
        ),
        (
            r#"{"nested":{"a":[1,2,{"b":null}]}}"#,
            "arbitrary structure under an unknown key",
        ),
        (
            r#"{"default_sides":"twenty"}"#,
            "the right key with the wrong type — a hand-edited file",
        ),
        (
            r#"{"default_sides":-1}"#,
            "a negative where an unsigned is expected",
        ),
        (
            r#"{"default_sides":1e400}"#,
            "a number no f64 can hold",
        ),
        (
            r#"{"default_sides":6,"api_key":""}"#,
            "present but empty — the NotConfigured case, not a parse failure",
        ),
        (
            r#"{"text":"emoji 🎲 and \"quotes\" and \\ and  "}"#,
            "a string that has to survive JSON escaping",
        ),
        ("[]", "an array where an object belongs"),
        ("\"a string\"", "a scalar where an object belongs"),
        ("{", "truncated: a write that was interrupted"),
        (
            r#"{"a":1,}"#,
            "a trailing comma — legal in JSON5, not in JSON",
        ),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The fixture is bytes, not a description of bytes.
    #[test]
    fn pcm_is_f32_le_at_the_daemons_rate() {
        let chunk = &pcm(1)[0];
        assert_eq!(chunk.len(), BYTES_PER_CHUNK);
        let first = f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        assert_eq!(first, 0.0, "a sine starts at zero");
        // 440 Hz at 16 kHz: a quarter period is ~9.09 samples, so sample 9 is
        // near the peak.
        let peak = f32::from_le_bytes([chunk[36], chunk[37], chunk[38], chunk[39]]);
        assert!(peak > 0.24, "{peak}");
    }

    #[test]
    fn the_same_fixture_twice_is_the_same_bytes() {
        assert_eq!(pcm(3), pcm(3));
    }

    /// The burst is sized from the spec, so raising the limit in
    /// `spec/limits.yaml` widens the test instead of leaving it behind.
    #[test]
    fn the_saturating_burst_is_the_spec_number() {
        assert_eq!(
            channel_saturating_burst().len(),
            crate::limits::STT_AUDIO_CHANNEL_CAPACITY as usize
        );
        assert!(
            WAKE_SEED_CHUNKS < crate::limits::STT_AUDIO_CHANNEL_CAPACITY as usize,
            "the seed dump must fit in the channel with room for live audio — \
             that is what the limit is for"
        );
    }

    #[test]
    fn the_firehose_fixture_is_seq_monotonic() {
        let seqs: Vec<u64> = firehose_events()
            .iter()
            .map(|f| f.event.as_ref().unwrap().seq)
            .collect();
        assert_eq!(seqs, (1..=7).collect::<Vec<_>>());
    }
}
