//! What each harness level is for, demonstrated on one plugin.
//!
//! Read this as the argument for having two levels. Every test below is
//! labelled with the level it needs, and the level-2 ones say what level 1
//! cannot see and why. A harness that has never caught anything is decoration;
//! each of these corresponds to a defect this project actually shipped.

use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicU32, Ordering};

use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::testing::{Harness, MockDaemon, WireHarness, fixtures};
use astra_plugin_sdk::wire::SESSION_TOKEN_HEADER;

// ── the plugin under test ────────────────────────────────────────────────────

#[astra::args]
struct RollArgs {
    /// How many dice to roll (1-100).
    #[serde(default = "one")]
    count: u32,
    /// Sides per die. Omitted means "whatever the user configured".
    sides: Option<u32>,
}

fn one() -> u32 {
    1
}

#[astra::config]
#[derive(Default)]
struct DiceConfig {
    /// Sides per die when a roll does not say.
    default_sides: u32,
}

#[derive(Default)]
struct Dice {
    config: Config<DiceConfig>,
    rolls: AtomicU32,
}

#[astra::plugin]
impl Dice {
    /// Roll dice and return the total.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: RollArgs) -> Result<String, ToolError> {
        let sides = a.sides.unwrap_or(self.config.load().default_sides).max(2);
        let count = a.count.clamp(1, 100);
        self.rolls.fetch_add(count, Ordering::Relaxed);
        // Deterministic: this is a harness demo, not a dice game.
        let total = count * sides;
        ctx.host()
            .fire_trigger("on_roll_value", &json!({ "sum": total }).to_string())
            .await?;
        Ok(format!("Rolled {count}d{sides} = {total}"))
    }

    /// Panics, on purpose. Every plugin has one of these; the author has not
    /// found it yet.
    #[tool]
    async fn bad_unwrap(&self) -> Result<String, ToolError> {
        let none: Option<&str> = None;
        // The bug is the point: this is the `unwrap` every plugin has and its
        // author has not found yet.
        #[allow(clippy::unnecessary_literal_unwrap)]
        Ok(none.expect("this tool has a bug").to_string())
    }

    #[hook]
    async fn on_config(&self, _ctx: &PluginContext, config: DiceConfig) {
        self.config.store(config);
    }

    #[hook]
    async fn health_check(&self) -> (bool, String) {
        (true, format!("ok — {} rolls", self.rolls.load(Ordering::Relaxed)))
    }
}

fn dice() -> Harness<Dice> {
    Harness::new(Dice::default()).with_config(json!({ "default_sides": 6 }))
}

// ── level 1: the logic ───────────────────────────────────────────────────────

/// **Level 1.** The shape §3.1 promises: build, configure, start, call, assert.
#[tokio::test]
async fn level_1_runs_a_tool_and_records_what_it_told_the_daemon() {
    let h = dice().start().await.unwrap();

    let out = h.call_tool("roll_dice", json!({ "count": 2 })).await.unwrap();
    assert_eq!(out, "Rolled 2d6 = 12");

    let fired = h.fired_triggers();
    assert_eq!(fired.len(), 1, "{fired:?}");
    assert_eq!(fired[0].trigger_type, "on_roll_value");
    assert_eq!(fired[0].payload_json, r#"{"sum":12}"#);
}

/// **Level 1.** Config reaches the plugin typed, through the same
/// `on_config_changed` the daemon calls.
#[tokio::test]
async fn level_1_config_is_delivered_and_can_be_replaced() {
    let h = dice().with_config(json!({ "default_sides": 20 })).start().await.unwrap();
    assert_eq!(h.call_tool("roll_dice", json!({})).await.unwrap(), "Rolled 1d20 = 20");

    h.config_changed(json!({ "default_sides": 4 })).await;
    assert_eq!(h.call_tool("roll_dice", json!({})).await.unwrap(), "Rolled 1d4 = 4");
}

/// **Level 1.** The failure an author meets first: `[permissions]` is
/// default-deny, so the first host RPC they did not declare is refused. The
/// injected error is built the way the real client builds it, so the handler's
/// `?` recovers the same kind.
#[tokio::test]
async fn level_1_injects_the_denial_a_user_would_have_met() {
    let h = dice().start().await.unwrap();
    h.host().deny("fire_trigger");

    let err = h.call_tool("roll_dice", json!({})).await.unwrap_err();
    assert!(
        matches!(err, ToolError::Unauthorized(ref m) if m.contains("fire_trigger")),
        "a denied host call must not arrive as `Internal`: {err:?}",
    );
    assert!(h.fired_triggers().is_empty());

    // …and the plugin recovers when the grant is added.
    h.host().clear_failures();
    assert!(h.call_tool("roll_dice", json!({})).await.is_ok());
}

/// **Level 1.** The schema the model is shown is the one the handler parses.
///
/// A hand-written `list_tools` next to a handler that parses something else is
/// how a model ends up calling a tool with fields that do nothing.
#[tokio::test]
async fn level_1_the_declared_schema_is_the_one_the_handler_parses() {
    let h = dice().start().await.unwrap();

    let schema = h.schema("roll_dice").await;
    schema.assert_is_a_parameters_object();
    assert_eq!(schema.properties(), ["count", "sides"]);
    assert_eq!(
        schema.description_of("count").as_deref(),
        Some("How many dice to roll (1-100)."),
        "the doc comment is what the model reads",
    );
    h.assert_schema_matches::<RollArgs>("roll_dice").await;
}

/// **Level 1.** Every config payload the daemon can produce, including the two
/// that are not JSON. The plugin must still be serving afterwards.
#[tokio::test]
async fn level_1_survives_every_config_the_daemon_can_send() {
    let h = dice().start().await.unwrap();
    let accepted = h.fuzz_config().await;

    assert!(
        accepted.iter().any(|(p, _)| *p == "{}"),
        "a fresh install sends `{{}}` and it has to parse: {accepted:?}",
    );
    // Still alive, still answering, and back on a known config.
    h.config_changed(json!({ "default_sides": 6 })).await;
    assert_eq!(h.call_tool("roll_dice", json!({})).await.unwrap(), "Rolled 1d6 = 6");
    assert!(h.health().await.0);
}

/// **Level 1.** The firehose fixture, including the event whose oneof is empty
/// — a daemon newer than this SDK. It must be ignored, not fatal.
#[tokio::test]
async fn level_1_replays_the_chat_firehose() {
    let h = dice().start().await.unwrap();
    h.conversation_events(fixtures::firehose_events()).await;
    h.conversation_events(fixtures::firehose_error_turn()).await;
    assert!(h.health().await.0);
}

// ── level 2: the wire ────────────────────────────────────────────────────────

/// **Level 2 — and level 1 structurally cannot.**
///
/// Level 1 calls `plugin.call_tool(..)`. Level 2 makes a `CallTool` RPC, which
/// means the tonic-generated descriptor, the capability server, the
/// interceptor, and `CapabilityServiceImpl`'s routing from that method to that
/// hook. Break any of those and level 1 still passes.
#[tokio::test]
async fn level_2_drives_the_plugin_through_its_own_grpc_server() {
    let w = WireHarness::start(Dice::default()).await.unwrap();

    let tools = w.list_tools().await.unwrap();
    let names: Vec<&str> = tools.iter().map(|t| t.name.as_str()).collect();
    assert!(names.contains(&"roll_dice"), "{names:?}");

    let resp = w.call_tool("roll_dice", r#"{"count":3,"sides":6}"#).await.unwrap();
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "Rolled 3d6 = 18");

    w.shutdown().await.unwrap();
}

/// **Level 2.** Registration is a thing that only happens on the wire: the
/// capability list, the protocol version and the SDK name are on the `Register`
/// message and nowhere else. A level-1 harness never sends one.
#[tokio::test]
async fn level_2_registers_with_the_capabilities_the_daemon_stated() {
    let daemon = MockDaemon::start().await.unwrap();
    let w = WireHarness::start_on(daemon, Dice::default(), "dice-roller", &["tools", "triggers"])
        .await
        .unwrap();

    let reg = w.daemon().registration().expect("the plugin registered");
    assert_eq!(reg.plugin_id, "dice-roller");
    assert_eq!(reg.capabilities, ["tools", "triggers"]);
    assert_eq!(reg.protocol_version, astra_plugin_sdk::PROTOCOL_VERSION);
    assert!(!reg.sdk_version.is_empty());
    assert!(reg.port > 0, "the daemon has to be told a port it can dial");

    w.shutdown().await.unwrap();
}

/// **Level 2 — and level 1 structurally cannot.**
///
/// Every host RPC but `Register` needs `x-session-token`. No SDK sent it before
/// 0.6, in any language, so `fire_trigger` / `log` / `set_variable` all failed
/// `unauthenticated` on a real daemon while every unit test passed. Nothing
/// short of a server that checks the header can notice.
#[tokio::test]
async fn level_2_host_calls_carry_the_session_token() {
    let w = WireHarness::start(Dice::default()).await.unwrap();

    let resp = w.call_tool("roll_dice", r#"{"count":1,"sides":6}"#).await.unwrap();
    assert!(resp.success, "{}", resp.error);

    let fired = w.fired_triggers();
    assert_eq!(fired.len(), 1, "the trigger reached the daemon: {fired:?}");
    assert_eq!(fired[0].trigger_type, "on_roll_value");

    w.shutdown().await.unwrap();
}

/// **Level 2 — and level 1 structurally cannot.**
///
/// The plugin's own capability server listens on loopback, which separates it
/// from nothing: any process running as this user can dial the port. The guard
/// is the spawn token, and whether tonic really runs the interceptor for this
/// service is a fact about the wire.
#[tokio::test]
async fn level_2_a_caller_without_the_spawn_token_is_refused() {
    let w = WireHarness::start(Dice::default()).await.unwrap();

    let err = w
        .client()
        .list_tools(w.unauthenticated_request(
            astra_plugin_sdk::proto::Empty {},
        ))
        .await
        .expect_err("an untokened local process must not reach the plugin's tools");
    assert_eq!(err.code(), tonic::Code::Unauthenticated, "{err}");

    // The daemon's own client, which has the token, still works.
    assert!(!w.list_tools().await.unwrap().is_empty());

    w.shutdown().await.unwrap();
}

/// **Level 2.** A permission the manifest did not ask for is denied by the
/// daemon, and the plugin has to answer with something the model can read
/// rather than falling over.
#[tokio::test]
async fn level_2_a_revoked_permission_comes_back_as_a_coded_tool_error() {
    let daemon = MockDaemon::start().await.unwrap();
    daemon.revoke("fire_trigger");
    let w = WireHarness::start_on(daemon, Dice::default(), "dice-roller", &["tools"])
        .await
        .unwrap();

    let resp = w.call_tool("roll_dice", r#"{"count":1,"sides":6}"#).await.unwrap();
    assert!(!resp.success);
    assert!(
        resp.error.starts_with("UNAUTHORIZED: "),
        "a denial must keep its code through the `string error` field: {}",
        resp.error
    );
    assert_eq!(
        resp.error_detail.as_ref().map(|d| d.code),
        Some(astra_plugin_sdk::proto::PluginErrorCode::PluginErrorUnauthorized as i32),
    );

    w.shutdown().await.unwrap();
}

/// **Level 2 — and level 1 structurally cannot.**
///
/// The 500-slot audio channel. It bounds two channels in series (the daemon's
/// and the SDK's) and the smaller one is the real capacity — which is how a
/// 32-slot SDK channel silently capped a 500-slot daemon one and truncated
/// every utterance to its first fraction.
///
/// The condition is reproduced exactly: the plugin does not read a byte until
/// the whole wake-seed burst has been *sent*, so the only thing that can absorb
/// it is the channel. Size that channel below the burst and the send never
/// completes, the gate never opens, and this test times out — which is the
/// failure the bug deserved and never got.
#[tokio::test]
async fn level_2_absorbs_the_wake_seed_burst_the_spec_sizes_the_channel_for() {
    struct Deferred {
        /// Opened by the client once every chunk is on the wire.
        gate: Arc<tokio::sync::Notify>,
    }

    #[async_trait]
    impl PluginCapability for Deferred {
        type Config = NoConfig;

        async fn stt_transcribe_stream(
            &self,
            _ctx: &PluginContext,
            mut audio: tokio::sync::mpsc::Receiver<Vec<u8>>,
            events: tokio::sync::mpsc::Sender<SttEvent>,
            _sample_rate: u32,
            _options: SttOptions,
        ) -> anyhow::Result<()> {
            // Not one byte until the burst has been delivered.
            self.gate.notified().await;
            let (mut chunks, mut bytes) = (0usize, 0usize);
            while let Some(chunk) = audio.recv().await {
                chunks += 1;
                bytes += chunk.len();
            }
            let _ = events
                .send(SttEvent::transcript(format!("{chunks} chunks, {bytes} bytes")))
                .await;
            Ok(())
        }
    }

    let gate = Arc::new(tokio::sync::Notify::new());
    let w = WireHarness::start(Deferred { gate: gate.clone() }).await.unwrap();

    let burst = fixtures::channel_saturating_burst();
    let expected_bytes: usize = burst.iter().map(|c| c.len()).sum();
    let expected_chunks = burst.len();

    // The stream is built here rather than through `WireHarness::stt_process`
    // because the *timing* is the test: the gate opens after the last chunk has
    // been handed to the transport, and nowhere else. A plugin whose channel is
    // too small stalls the transport before that point, so the gate never
    // opens, so nothing is ever read — which is a hang, and the 20 s timeout
    // below turns it into a failure.
    let sample_rate = fixtures::SAMPLE_RATE;
    let options = fixtures::stt_options();
    let sender_gate = gate.clone();
    let outbound = async_stream_of(burst, sample_rate, options, move || {
        sender_gate.notify_one()
    });

    let events = tokio::time::timeout(std::time::Duration::from_secs(20), async {
        use tokio_stream::StreamExt;
        let mut stream = w
            .client()
            .stt_process(w.request(outbound))
            .await
            .unwrap()
            .into_inner();
        let mut events = Vec::new();
        while let Some(ev) = stream.next().await {
            events.push(ev.unwrap());
        }
        events
    })
    .await
    .expect(
        "the wake-seed burst did not reach the plugin within 20s — the audio \
         channel is smaller than spec/limits.yaml says it is",
    );

    assert_eq!(
        events.len(),
        1,
        "one final transcript, not a partial per chunk: {events:?}"
    );
    assert_eq!(
        events[0].text,
        format!("{expected_chunks} chunks, {expected_bytes} bytes"),
        "every chunk of the burst has to arrive, in full",
    );

    w.shutdown().await.unwrap();
}

/// The client half of the burst: every chunk, then `is_last`, then `sent()` —
/// which only runs once the transport has taken the last chunk.
fn async_stream_of(
    chunks: Vec<Vec<u8>>,
    sample_rate: u32,
    options: SttOptions,
    sent: impl FnOnce() + Send + 'static,
) -> impl tokio_stream::Stream<Item = astra_plugin_sdk::proto::PluginAudioChunk> + Send + 'static {
    use astra_plugin_sdk::proto::PluginAudioChunk;
    async_stream::stream! {
        let mut first = true;
        for data in chunks {
            yield PluginAudioChunk {
                data,
                is_last: false,
                sample_rate,
                options: first.then(|| options.clone()),
            };
            first = false;
        }
        yield PluginAudioChunk { data: Vec::new(), is_last: true, sample_rate, options: None };
        sent();
    }
}

/// **Level 2.** `on_start` returning `Err` **aborts startup**: the plugin never
/// begins serving and the process exits non-zero. The harness has to report
/// that as a failure to start rather than hanging on a client connect, because
/// a plugin the daemon believes is healthy and that answers every call with the
/// same failure is the outcome this rule exists to prevent.
#[tokio::test]
async fn level_2_a_plugin_that_cannot_start_does_not_serve() {
    struct NeedsAKey;
    #[async_trait]
    impl PluginCapability for NeedsAKey {
        type Config = NoConfig;
        async fn on_start(&self, _ctx: &PluginContext) -> anyhow::Result<()> {
            anyhow::bail!("no API key configured")
        }
    }

    let err = WireHarness::start(NeedsAKey)
        .await
        .expect_err("a plugin whose on_start failed must not come up");
    let text = format!("{err:#}");
    assert!(text.contains("no API key configured"), "{text}");
}

// ── 5.10: panic containment ──────────────────────────────────────────────────

/// **Level 1.** A panicking handler is still a panicking handler in process —
/// the harness calls the hook directly, so it propagates. This is the level
/// that finds the bug; the next one proves it is survivable.
#[tokio::test]
#[should_panic(expected = "this tool has a bug")]
async fn level_1_a_panicking_tool_panics_the_test() {
    let h = dice().start().await.unwrap();
    let _ = h.call_tool("bad_unwrap", json!({})).await;
}

/// **Level 2.** §5.10's acceptance: a panicking tool returns an error, and the
/// process survives to answer the next call.
///
/// Before this the panic unwound out of the tonic handler; the daemon saw a
/// dropped connection with no message in it, and under `panic = "abort"` — an
/// ordinary release profile — the whole plugin went down and took every other
/// capability with it.
#[tokio::test]
async fn level_2_a_panicking_tool_returns_an_error_and_the_plugin_keeps_serving() {
    let w = WireHarness::start(Dice::default()).await.unwrap();

    let resp = w.call_tool("bad_unwrap", "{}").await.expect(
        "a panicking tool must answer, not drop the connection",
    );
    assert!(!resp.success);
    assert!(resp.error.starts_with("INTERNAL: "), "{}", resp.error);
    assert!(resp.error.contains("call_tool panicked"), "{}", resp.error);
    assert!(resp.error.contains("this tool has a bug"), "{}", resp.error);

    // The point of the whole exercise: everything else still works.
    let resp = w.call_tool("roll_dice", r#"{"count":1,"sides":6}"#).await.unwrap();
    assert!(resp.success, "{}", resp.error);
    assert!(w.health().await.unwrap().healthy);

    w.shutdown().await.unwrap();
}

/// **Level 2.** A panic in a lifecycle hook is contained too — the daemon gets
/// a status naming the hook instead of a dead socket. `INTERNAL`, never
/// `UNIMPLEMENTED`: the daemon reads that as "the hook is absent" and would
/// stop calling it for the life of the process.
#[tokio::test]
async fn level_2_a_panicking_lifecycle_hook_is_a_status_not_a_dead_socket() {
    struct Fragile;
    #[async_trait]
    impl PluginCapability for Fragile {
        type Config = NoConfig;
        async fn on_active_triggers(&self, _ctx: &PluginContext, _types: Vec<String>) {
            panic!("index out of bounds in on_active_triggers");
        }
    }

    let w = WireHarness::start(Fragile).await.unwrap();
    let err = w
        .active_triggers(&["on_roll_value"])
        .await
        .expect_err("the hook panicked, so the call failed");
    assert_eq!(err.code(), tonic::Code::Internal, "{err}");
    assert!(err.message().contains("on_active_triggers"), "{err}");

    assert!(w.health().await.unwrap().healthy, "the process is still up");
    w.shutdown().await.unwrap();
}

/// **Level 2 — and level 1 structurally cannot.**
///
/// `SttProcess` is server-streaming, and a streaming hook that fails has
/// nowhere to put the failure except the stream. The runner used to spawn the
/// plugin task, `warn!` its `Err` and close the stream normally, so a plugin
/// that declares `stt` and implements no `stt_transcribe` answered `SttProcess`
/// with **OK and zero events** — while Python and TypeScript answered
/// `UNIMPLEMENTED` to the same plugin.
///
/// That is not a cosmetic disagreement. Phase 1 fixed `Unimplemented` to mean
/// *the hook is absent*, and this was the one language that could not say it.
/// The field symptom was a working microphone, a moving waveform, no text ever,
/// and nothing in the daemon log.
#[tokio::test]
async fn level_2_an_stt_hook_that_is_not_implemented_says_unimplemented() {
    struct HalfStt;
    #[async_trait]
    impl PluginCapability for HalfStt {
        type Config = NoConfig;
        // Declares `stt` and answers the cheap half of it — but never
        // implements `stt_transcribe`, so the SDK's own default runs.
        async fn stt_languages(&self) -> Vec<String> {
            vec!["en".into()]
        }
    }

    let daemon = MockDaemon::start().await.unwrap();
    let w = WireHarness::start_on(daemon, HalfStt, "half-stt", &["stt"])
        .await
        .unwrap();

    // The half that *is* implemented still answers.
    assert_eq!(
        w.client()
            .stt_get_languages(w.request(astra_plugin_sdk::proto::Empty {}))
            .await
            .unwrap()
            .into_inner()
            .languages,
        ["en"],
    );

    let err = w
        .stt_process(
            fixtures::utterance(),
            fixtures::SAMPLE_RATE,
            fixtures::stt_options(),
        )
        .await
        .expect_err("a plugin with no stt_transcribe must not answer OK with zero events");
    assert_eq!(err.code(), tonic::Code::Unimplemented, "{err}");
    assert!(err.message().contains("stt_transcribe"), "{err}");

    w.shutdown().await.unwrap();
}

/// **Level 2, about the harness itself.**
///
/// [`MockDaemon`]'s session-token gate is the single assertion that makes
/// `level_2_host_calls_carry_the_session_token` mean anything: that test
/// detects a missing token *solely* by this daemon rejecting the call. Relax
/// the gate — while debugging, or in a refactor that drops the early return —
/// and the test keeps its name, keeps passing, and stops testing anything.
///
/// So the gate gets its own test, from the outside, on the wire. TypeScript's
/// mock has had one since 5.6; this is the same test.
#[tokio::test]
async fn the_mock_daemons_own_session_gate_refuses_an_untokened_caller() {
    use astra_plugin_sdk::proto::plugin_host_service_client::PluginHostServiceClient;

    let daemon = MockDaemon::start().await.unwrap();
    let mut client = PluginHostServiceClient::connect(format!("http://{}", daemon.addr()))
        .await
        .expect("the mock daemon is listening");

    let log = || astra_plugin_sdk::proto::PluginLogRequest {
        plugin_id: "impostor".into(),
        level: "info".into(),
        message: "let me in".into(),
    };

    // No token at all.
    let err = client
        .plugin_log(tonic::Request::new(log()))
        .await
        .expect_err("MockDaemon must refuse a host call with no session token");
    assert_eq!(err.code(), tonic::Code::Unauthenticated, "{err}");

    // A token, but the wrong one.
    let mut wrong = tonic::Request::new(log());
    wrong
        .metadata_mut()
        .insert(SESSION_TOKEN_HEADER, "not-the-token".parse().unwrap());
    let err = client
        .plugin_log(wrong)
        .await
        .expect_err("MockDaemon must refuse a host call with the wrong session token");
    assert_eq!(err.code(), tonic::Code::Unauthenticated, "{err}");

    // The token it actually issued gets through — otherwise the gate could be
    // "reject everything", which would fail the real tests for the wrong reason.
    let mut right = tonic::Request::new(log());
    right
        .metadata_mut()
        .insert(SESSION_TOKEN_HEADER, daemon.session_token().parse().unwrap());
    client.plugin_log(right).await.expect("the issued token works");

    // And every refusal is on the record, so `astra-plugin test` can assert on
    // it without re-deriving what a rejection looks like.
    assert_eq!(
        daemon.recorded().unauthenticated_calls(),
        ["log", "log"],
        "both refusals are recorded, the accepted call is not",
    );
}

/// **Level 1.** The daemon's event payload, decoded by the SDK's own types.
///
/// The JSON below is what the daemon's `plugins::event_view::for_plugin`
/// produces for this variant — a NARROWING, written key by key, not
/// `serde_json::to_string(&AstraEvent)`. The keys are `command_id`,
/// `command_name`, `trigger_type`, `run_id` and `fired_by`.
///
/// **`trigger_text` is gone from the event itself**, not merely unread: it was
/// the phrase the user typed or spoke, delivered to every plugin that asked to
/// hear that commands run, and the daemon removed the field. A plugin still
/// declaring it would read `""` forever, which is the same "looks like an
/// answer" failure `variables` had before it.
///
/// The two reader-dependent values are asserted here as the daemon sends them
/// to a plugin that did NOT fire this command: `command_name` is `""` (a
/// command's name is the user's own writing) and `fired_by` is absent.
#[tokio::test]
async fn a_daemon_event_decodes_from_the_daemons_own_key_names() {
    #[derive(Default)]
    struct Listener {
        seen: Mutex<Vec<String>>,
    }

    #[async_trait]
    impl PluginCapability for Listener {
        type Config = NoConfig;
        fn subscribed_events(&self) -> Vec<String> {
            vec!["command_triggered".into()]
        }
        async fn on_command_triggered(
            &self,
            _ctx: &PluginContext,
            event: astra_plugin_sdk::events::CommandTriggeredEvent,
        ) {
            self.seen.lock().unwrap().push(format!(
                "{}/{}/{}/{}/{:?}",
                event.command_id,
                event.command_name,
                event.trigger_type,
                event.run_id,
                event.fired_by
            ));
        }
    }

    let h = Harness::new(Listener::default()).start().await.unwrap();
    h.event(
        "command_triggered",
        r#"{"type":"command_triggered","command_id":"cmd-1","command_name":"","trigger_type":"text","run_id":"5f0a1c62-0000-0000-0000-000000000001","fired_by":null}"#,
    )
    .await;

    assert_eq!(
        *h.plugin().seen.lock().unwrap(),
        ["cmd-1//text/5f0a1c62-0000-0000-0000-000000000001/None"],
    );
}
