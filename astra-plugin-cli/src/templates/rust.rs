//! Rust plugin project templates.
//!
//! # The bar
//!
//! §3.1 of the production plan: **one dependency, about twelve lines.** That is
//! not a slogan, it is the acceptance test — `astra-plugin new p` writes a
//! `Cargo.toml` with a single `[dependencies]` entry and a `main.rs` of twelve
//! non-blank lines, and it builds.
//!
//! Everything the scaffold needs and does not name itself comes through
//! `astra_plugin_sdk::prelude` — `tokio`, `serde`, `serde_json`, `anyhow`,
//! `async_trait`, `schemars`. The macros expand to `::astra_plugin_sdk::…`
//! paths, so nothing here compiles by accident off a dependency the author
//! could delete.
//!
//! # Why `#[astra::plugin]` and not a hand-written trait impl
//!
//! The old scaffold wrote `impl PluginCapability` directly, with a `list_tools`
//! that returned a hand-typed JSON Schema string next to a `call_tool` that
//! matched on the tool name. Two places to edit for one change, and the schema
//! could disagree with what the handler actually parsed with nothing to notice.
//! `#[tool]` derives the schema from the argument type, so they cannot.

/// The scaffolded `Cargo.toml`. One dependency.
pub fn generate_cargo_toml(name: &str) -> String {
    let crate_name = name.replace('-', "_");
    format!(
        r#"[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2024"

[dependencies]
# One dependency, on purpose. The SDK re-exports everything the generated code
# names — tokio, serde, serde_json, anyhow, async-trait, schemars — and
# `#[astra::plugin]` expands to `::astra_plugin_sdk::…` paths, so adding those
# crates back here changes nothing and removing this line breaks everything.
#
# 0.6 is the first release whose HostClient attaches `x-session-token`; 0.5 and
# earlier get `unauthenticated` from the daemon on every host call, so do not
# relax this bound.
astra-plugin-sdk = "0.6"

# Taking structured tool arguments? Mark the argument struct `#[astra::args]`:
#
#   #[astra::args]
#   struct Roll {{
#       /// How many dice to roll
#       #[serde(default)]
#       count: u32,
#   }}
#
#   #[tool] async fn roll(&self, a: Roll) -> Result<String, ToolError> {{ .. }}
#
# It is `#[derive(Deserialize, JsonSchema)]` pointed at the SDK's copies of both
# crates, and the doc comments become the schema the model reads. Settings get
# `#[astra::config]`, which is the same plus `#[serde(default)]` — the daemon's
# first config payload to a freshly installed plugin is `{{}}`.
#
# Writing `#[derive(Deserialize)]` here instead does not work and says so: serde's
# derive needs `serde` in the crate graph, which is the one line this file exists
# not to have. Adding serde yourself is still supported — do that and
# `use serde::Deserialize;` shadows the prelude's name.
#
# Developing against an unreleased SDK? Swap the line above for one of these:
#   astra-plugin-sdk = {{ git = "https://github.com/mihailinl/AstraPlugins", branch = "main" }}
#   astra-plugin-sdk = {{ path = "../AstraPlugins/astra-plugin-sdk" }}
"#
    )
}

/// One generated member of the plugin's `impl` block, plus the manifest
/// capability that the SDK will infer from it.
///
/// The pairing is the point: `DeclaredCapabilities::CAPS` is derived from the
/// hooks that are really present, so a scaffold cannot declare a capability its
/// code does not serve — which is exactly the drift `astra-plugin check`
/// compares a built binary against `plugin.toml` to catch.
struct Member {
    code: String,
    /// The capability `#[astra::plugin]` infers from this member.
    implies: Option<&'static str>,
}

impl Member {
    fn new(implies: Option<&'static str>, code: &str) -> Self {
        Self {
            code: code.to_string(),
            implies,
        }
    }
}

/// The scaffolded `src/main.rs`.
pub fn generate_main_rs(name: &str, capabilities: &[&str]) -> String {
    let struct_name = name
        .split(['-', '_'])
        .filter(|w| !w.is_empty())
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join("");

    let mut members: Vec<Member> = Vec::new();

    if capabilities.contains(&"tools") {
        members.push(Member::new(
            Some("tools"),
            // The doc comment is the tool's description — the sentence the model
            // reads to decide whether to call it — so it is one line here and
            // the scaffold is exactly §3.1's twelve.
            r#"    /// Say hello. Describe when to use the tool, not how it works.
    #[tool]
    async fn hello(&self) -> Result<String, ToolError> {
        Ok("Hello from the plugin!".into())
    }"#,
        ));
    }

    if capabilities.contains(&"actions") {
        members.push(Member::new(
            Some("actions"),
            r#"    /// Run this action from a command. Shown in the command editor.
    #[action(label = "Do Something")]
    async fn do_something(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("do_something ran").await?;
        Ok("done".into())
    }"#,
        ));
    }

    if capabilities.contains(&"triggers") {
        members.push(Member::new(
            Some("triggers"),
            r#"    /// The trigger types a user can attach a command to. Fire one with
    /// `ctx.host().fire_trigger("something_happened", payload_json)`; check
    /// `ctx.active_triggers().contains(..)` first if the payload is costly.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "something_happened".into(),
            label: "Something happened".into(),
            ..Default::default()
        }]
    }"#,
        ));
    }

    if capabilities.contains(&"tts") {
        members.push(Member::new(
            Some("tts"),
            r#"    #[hook]
    async fn tts_voices(&self) -> Vec<VoiceInfo> {
        vec![VoiceInfo::new("default", "Default Voice")]
    }

    /// Synthesize one utterance. Implement `tts_synthesize_stream` instead if
    /// your engine can emit audio before it has finished — the SDK's default
    /// already forwards streaming calls here as a single chunk.
    ///
    /// This placeholder returns 200 ms of silence at 16 kHz, f32-LE PCM: real
    /// audio in the format the daemon plays, so the plugin passes
    /// `astra-plugin test` and can be heard (as nothing) from the first run.
    /// Replace the body; keep the shape.
    #[hook]
    async fn tts_synthesize(
        &self,
        ctx: &PluginContext,
        req: TtsRequest,
    ) -> anyhow::Result<AudioData> {
        let sample_rate = 16_000;
        let samples = sample_rate / 5; // 200 ms
        let _ = ctx
            .host()
            .log_warn(&format!("TTS placeholder: silence instead of {:?}", req.text))
            .await;
        Ok(AudioData {
            data: vec![0u8; samples as usize * 4],
            format: "pcm".into(),
            sample_rate,
            duration_ms: 200,
        })
    }"#,
        ));
    }

    // `--template stt-streaming` asks for the streaming hook instead of the
    // unary one. Same capability — there is only one STT capability — but the
    // hook an author starts from decides whether their plugin can ever emit a
    // partial result, and bolting `stt_transcribe_stream` onto a finished
    // unary implementation is the retrofit people get subtly wrong.
    if capabilities.contains(&crate::commands::create::STREAMING_MARKER) {
        members.push(Member::new(
            Some("stt"),
            r#"    #[hook]
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into()]
    }

    /// Transcribe while the audio is still arriving. `audio` yields f32-LE PCM
    /// chunks; send `SttEvent::partial`s as you get them and one
    /// `SttEvent::transcript` before returning. A closed channel is
    /// end-of-utterance.
    ///
    /// The channel holds `astra_plugin_sdk::limits::STT_AUDIO_CHANNEL_CAPACITY`
    /// chunks — the daemon dumps its whole wake-word pre-roll into it at once,
    /// so read in a loop and never block on anything slow between reads.
    #[hook]
    async fn stt_transcribe_stream(
        &self,
        _ctx: &PluginContext,
        mut audio: tokio::sync::mpsc::Receiver<Vec<u8>>,
        events: tokio::sync::mpsc::Sender<SttEvent>,
        _sample_rate: u32,
        _options: SttOptions,
    ) -> anyhow::Result<()> {
        let mut samples = 0usize;
        while let Some(chunk) = audio.recv().await {
            samples += chunk.len() / 4;
        }
        let _ = events
            .send(SttEvent::transcript(format!("heard {samples} samples")))
            .await;
        Ok(())
    }"#,
        ));
    } else if capabilities.contains(&"stt") {
        members.push(Member::new(
            Some("stt"),
            r#"    #[hook]
    async fn stt_languages(&self) -> Vec<String> {
        vec!["en".into()]
    }

    /// Transcribe one complete utterance: `audio` is f32-LE PCM. Implement
    /// `stt_transcribe_stream` instead to emit partials while audio flows —
    /// `astra-plugin new --template stt-streaming` starts you there.
    ///
    /// This placeholder describes what it was handed rather than failing: an
    /// utterance that produces no `SttEvent` is a microphone that appears to
    /// work and never yields text, which is the least diagnosable way for an
    /// STT plugin to be broken. Replace the body; keep the one event.
    #[hook]
    async fn stt_transcribe(
        &self,
        _ctx: &PluginContext,
        audio: &[u8],
        sample_rate: u32,
        _options: &SttOptions,
    ) -> anyhow::Result<SttEvent> {
        let samples = audio.len() / 4; // f32-LE
        Ok(SttEvent::transcript(format!(
            "[placeholder] {samples} samples @ {sample_rate} Hz"
        )))
    }"#,
        ));
    }

    if capabilities.contains(&"ai_provider") {
        members.push(Member::new(
            Some("ai_provider"),
            r#"    #[hook]
    async fn ai_models(&self) -> (Vec<AiModelInfo>, String) {
        (vec![AiModelInfo::new("demo-1", "Demo Model")], "demo-1".into())
    }

    /// Stream one completion. Send chunks as they arrive; returning `Ok` ends
    /// the turn and the SDK appends the `Done` chunk for you.
    #[hook]
    async fn ai_complete(
        &self,
        _ctx: &PluginContext,
        _req: AiRequest,
        chunks: tokio::sync::mpsc::Sender<AiChunk>,
    ) -> anyhow::Result<()> {
        chunks.send(AiChunk::text("Hello from the plugin!")).await?;
        Ok(())
    }"#,
        ));
    }

    if capabilities.contains(&"ui_contributions") || capabilities.contains(&"dom_access") {
        members.push(Member::new(
            Some("ui_contributions"),
            r##"    /// The iframes this plugin puts in Astra's UI. `url` is served from the
    /// plugin's own `web/` directory.
    #[hook]
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::page("main", "My Plugin", "web/index.html")]
    }

    /// Called from that iframe by `astra.call("ping", {})`. Push data back
    /// with `ctx.host().push_to_ui(..)`.
    #[ui_call]
    async fn ping(&self) -> Result<String, ToolError> {
        Ok(r#"{"ok":true}"#.into())
    }"##,
        ));
    }

    if capabilities.contains(&"event_handlers") {
        members.push(Member::new(
            Some("event_handlers"),
            r#"    /// Daemon events to subscribe to. Chat events do NOT arrive here — for
    /// those, implement `on_conversation_event` (the `client` capability).
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["state_changed".into()]
    }

    #[hook]
    async fn on_event(&self, ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = ctx.host().log_debug(&format!("event: {event_type}")).await;
    }"#,
        ));
    }

    if capabilities.contains(&"client") {
        members.push(Member::new(
            Some("client"),
            r#"    /// Ask the daemon for a client session, so `ctx.daemon()` is `Some` and
    /// this plugin can drive chat, voice and commands.
    #[hook]
    fn is_client(&self) -> bool {
        true
    }"#,
        ));
    }

    // A plugin with no capability at all still has to expose something, or
    // `#[astra::plugin]` refuses the block — correctly, since a plugin that
    // serves nothing is a bug and not a starting point.
    if members.is_empty() {
        members.push(Member::new(
            Some("tools"),
            r#"    /// Say hello. Replace this with the tool your plugin actually offers.
    #[tool]
    async fn hello(&self) -> Result<String, ToolError> {
        Ok("Hello from the plugin!".into())
    }"#,
        ));
    }

    // `capabilities = "…"` only when the manifest asks for something the
    // generated hooks do not imply — `dom_access`, say, which has no hook at
    // all. Spelling out a list that the macro would have inferred anyway is one
    // more thing that can rot.
    let inferred: std::collections::BTreeSet<&str> =
        members.iter().filter_map(|m| m.implies).collect();
    let requested: std::collections::BTreeSet<&str> = capabilities
        .iter()
        .copied()
        .filter(|c| !c.is_empty())
        .collect();
    let plugin_attr = if requested.is_empty() || requested == inferred {
        "#[astra::plugin]".to_string()
    } else {
        format!(
            "#[astra::plugin(capabilities = \"{}\")]",
            requested.iter().copied().collect::<Vec<_>>().join(", ")
        )
    };

    let body = members
        .iter()
        .map(|m| m.code.as_str())
        .collect::<Vec<_>>()
        .join("\n\n");

    let tests = generate_tests(&struct_name, &inferred);

    format!(
        r#"use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct {struct_name};

{plugin_attr}
impl {struct_name} {{
{body}
}}

astra::main!({struct_name}::default());

{tests}"#
    )
}

/// Where the plugin is separated from the test that proves it works.
///
/// `generate_main_rs` emits it, and the twelve-line assertion below counts only
/// what comes before it.
pub const TEST_MODULE_MARKER: &str = "#[cfg(test)]";

/// The one passing test every scaffold ships.
///
/// It is here — at the bottom of `main.rs`, not in `tests/` — for two reasons.
/// A binary crate has no library for an integration test to import, so a
/// `tests/` file would have to reach back in with `#[path = "../src/main.rs"]`
/// and the scaffold would be teaching that trick on line one. And a unit test
/// module sees the plugin's private items, which is what an author's second
/// test is going to want.
///
/// One dependency still: `Harness` and `json!` both arrive through
/// `astra-plugin-sdk`, so `[dev-dependencies]` stays empty.
fn generate_tests(struct_name: &str, inferred: &std::collections::BTreeSet<&str>) -> String {
    // Every scaffold can assert that it starts and is healthy. A scaffold with
    // a tool can assert what the tool answered, which is the assertion an
    // author will actually edit.
    let tool_assertion = if inferred.contains("tools") {
        r#"
        let answer = h.call_tool("hello", json!({})).await.expect("the tool answered");
        assert_eq!(answer, "Hello from the plugin!");
"#
    } else {
        ""
    };

    format!(
        r#"{TEST_MODULE_MARKER}
mod tests {{
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    /// `cargo test`. The harness runs the hooks in process against a recording
    /// host: no daemon, no socket, no Astra installed.
    ///
    /// `h.host().fired_triggers()` / `.logs()` / `.variables()` say what the
    /// plugin told Astra; `h.host().deny("fire_trigger")` stages the refusal a
    /// user's `[permissions]` would produce. For the wire — registration, the
    /// session token, streaming audio — there is
    /// `astra_plugin_sdk::testing::WireHarness`.
    #[tokio::test]
    async fn it_starts_and_answers() {{
        let h = Harness::new({struct_name}::default())
            .with_config(json!({{}}))
            .start()
            .await
            .expect("the plugin started");
{tool_assertion}
        assert!(h.health().await.0);
    }}
}}
"#
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn non_blank(s: &str) -> usize {
        s.lines().filter(|l| !l.trim().is_empty()).count()
    }

    /// §3.1's acceptance bar, as an assertion rather than a hope.
    ///
    /// Twelve lines is not a round number someone liked: it is one `use`, a
    /// two-line struct, a four-line `impl` shell, a three-line handler, its
    /// description, and `astra::main!`. Nothing in that list can be removed
    /// without removing something the plugin *is*.
    #[test]
    fn the_default_scaffold_is_about_twelve_lines() {
        let main_rs = generate_main_rs("dice-roller", &["tools"]);
        // The plugin, not the test module under it — §3.1's bar is about how
        // much a plugin is, and a test is not part of the answer.
        let plugin = main_rs
            .split(TEST_MODULE_MARKER)
            .next()
            .expect("the plugin comes first");
        let n = non_blank(plugin);
        assert_eq!(
            n, 12,
            "the minimum viable plugin drifted to {n} non-blank lines:\n{plugin}"
        );
    }

    /// 5.6: every scaffold ships one passing test, and it is a test that can
    /// fail — it calls the tool and asserts what came back, rather than
    /// asserting that the struct can be constructed.
    #[test]
    fn the_default_scaffold_ships_a_test_that_calls_the_tool() {
        let main_rs = generate_main_rs("dice-roller", &["tools"]);
        assert!(main_rs.contains(TEST_MODULE_MARKER), "{main_rs}");
        assert!(main_rs.contains("#[tokio::test]"), "{main_rs}");
        assert!(main_rs.contains("Harness::new(DiceRoller::default())"), "{main_rs}");
        assert!(
            main_rs.contains(r#"h.call_tool("hello", json!({})).await"#),
            "the scaffolded test has to exercise the scaffolded tool:\n{main_rs}"
        );
    }

    /// A scaffold with no tool still ships a test — it starts the plugin, which
    /// is the assertion that catches a broken `on_start`.
    #[test]
    fn a_scaffold_without_tools_still_ships_a_test() {
        let main_rs = generate_main_rs("speaker", &["tts"]);
        assert!(main_rs.contains("#[tokio::test]"), "{main_rs}");
        assert!(
            !main_rs.contains("call_tool"),
            "a tts scaffold has no `hello` tool to call:\n{main_rs}"
        );
        assert!(main_rs.contains("h.health().await.0"), "{main_rs}");
    }

    /// One dependency. The whole macro layer exists to make this true, so a
    /// second `[dependencies]` line is a regression, not a convenience.
    #[test]
    fn the_default_scaffold_has_exactly_one_dependency() {
        let toml = generate_cargo_toml("dice-roller");
        let deps: Vec<&str> = toml
            .lines()
            .skip_while(|l| l.trim() != "[dependencies]")
            .skip(1)
            .filter(|l| {
                let t = l.trim();
                !t.is_empty() && !t.starts_with('#') && !t.starts_with('[')
            })
            .collect();
        assert_eq!(deps, ["astra-plugin-sdk = \"0.6\""], "{toml}");
    }

    /// The macro infers `tools` from `#[tool]`, so saying so again would be
    /// noise that can disagree with the code.
    #[test]
    fn an_inferable_capability_set_is_not_restated() {
        let main_rs = generate_main_rs("p", &["tools"]);
        assert!(main_rs.contains("\n#[astra::plugin]\n"), "{main_rs}");
    }

    /// …and one the hooks cannot imply is stated, because otherwise the binary
    /// would tell `astra-plugin check` something narrower than `plugin.toml`.
    #[test]
    fn a_capability_no_hook_implies_is_stated_explicitly() {
        let main_rs = generate_main_rs("p", &["tools", "dom_access"]);
        assert!(
            main_rs.contains(r#"#[astra::plugin(capabilities = "dom_access, tools")]"#),
            "{main_rs}"
        );
    }

    #[test]
    fn hyphens_become_a_camel_case_type_name() {
        assert!(generate_main_rs("dice-roller", &["tools"]).contains("struct DiceRoller;"));
        assert!(
            generate_main_rs("dice-roller", &["tools"])
                .contains("astra::main!(DiceRoller::default());")
        );
    }
}
