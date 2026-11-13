// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! **A trigger fired while handling a daemon call names the call that caused
//! it.**
//!
//! The bug this answers: a plugin action runs inside a command run that a user
//! started by typing in a chat. The plugin fires a trigger, which starts a
//! second command run — and today that second run has no idea what caused it,
//! so its output is filed into a freshly auto-created conversation the user
//! never sees. With two chats doing this at once, nothing on the wire even
//! distinguishes them.
//!
//! The mechanism is a per-invocation lease: the daemon mints an opaque token
//! when it calls into a plugin and carries it as gRPC call metadata under
//! `spec/wire.yaml`'s `x-astra-cause`; the SDK echoes it on `FireTrigger`; the
//! daemon redeems it and recovers the cause.
//!
//! These tests run the whole chain over real sockets — capability server,
//! runner, scoped context, detached task, host client, mock daemon — because
//! every link in it is invisible when it breaks. A lease that never reaches the
//! wire produces a working plugin whose output goes to the wrong place, with no
//! error anywhere.
//!
//! **Nothing here asks the daemon to do anything.** No daemon in the field
//! sends a lease yet, so in production every one of these fires is a root
//! event, which is exactly what `a_plugin_that_was_never_leased_fires_a_root_event`
//! pins.

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::testing::WireHarness;
use astra_plugin_sdk::wire::X_ASTRA_CAUSE;

/// Fires `on_roll_value` the way the shipped reference plugin does: clone the
/// host out of the context, `tokio::spawn`, fire from the detached task, return
/// before it has run.
///
/// That idiom is the reason Rust cannot use a task-local for this — a
/// `tokio::task_local!` does not cross `spawn` — and therefore the reason the
/// cause rides inside the `Arc<dyn Host>` instead.
struct Roller;

#[async_trait::async_trait]
impl PluginCapability for Roller {
    type Config = NoConfig;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef::new("roll_dice", "Roll dice")]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        _name: &str,
        _args: &str,
    ) -> Result<String, ToolError> {
        let host = ctx.host().clone();
        tokio::spawn(async move {
            // Yield first: without it a passing test would not distinguish
            // "the cause survived the spawn" from "the future ran inline".
            tokio::task::yield_now().await;
            let _ = host.fire_trigger("on_roll_value", r#"{"value":"2"}"#).await;
        });
        Ok("1d5: [2] = 2".into())
    }
}

async fn roll(harness: &WireHarness, cause: Option<&str>) {
    let mut request = harness.request(astra_plugin_sdk::proto::PluginCallToolRequest {
        tool_name: "roll_dice".into(),
        arguments_json: "{}".into(),
        invocation: None,
        attachments: Vec::new(),
    });
    if let Some(cause) = cause {
        request
            .metadata_mut()
            .insert(X_ASTRA_CAUSE, cause.parse().unwrap());
    }
    harness.client().call_tool(request).await.unwrap();
}

/// The fire is detached, so it lands after the RPC has answered.
async fn wait_for_fires(harness: &WireHarness, n: usize) {
    for _ in 0..200 {
        if harness.fired_triggers().len() >= n {
            return;
        }
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
    }
    panic!(
        "expected {n} fired trigger(s), saw {}",
        harness.fired_triggers().len()
    );
}

/// End to end: the lease the daemon put on `CallTool` comes back out on
/// `FireTrigger`, having crossed a `tokio::spawn` in between.
#[tokio::test]
async fn a_lease_on_a_call_comes_back_on_the_trigger_it_caused() {
    let harness = WireHarness::start(Roller).await.unwrap();

    roll(&harness, Some("lease-abc")).await;
    wait_for_fires(&harness, 1).await;

    let fired = harness.fired_triggers();
    assert_eq!(fired[0].trigger_type, "on_roll_value");
    assert_eq!(
        fired[0].caused_by.as_deref(),
        Some("lease-abc"),
        "the lease did not survive the trip; the daemon would file this fire as a root event \
         and its output would land in a conversation nobody is looking at"
    );
}

/// The state every daemon in the field is in, and the one this must never make
/// worse: no lease on the call, nothing invented to fill it.
///
/// An empty header would be worse than none — the daemon would have to tell
/// "the SDK sent a lease it could not resolve" apart from "the SDK sent no
/// lease", and only one of those is a bug.
#[tokio::test]
async fn a_plugin_that_was_never_leased_fires_a_root_event() {
    let harness = WireHarness::start(Roller).await.unwrap();

    roll(&harness, None).await;
    wait_for_fires(&harness, 1).await;

    assert_eq!(harness.fired_triggers()[0].caused_by, None);
}

/// Two chats rolling at once is the scenario the whole design exists for. The
/// cause lives in the context the runner built for each call, so two calls in
/// flight cannot collect each other's — there is no ambient slot to race over.
#[tokio::test]
async fn concurrent_calls_do_not_collect_each_others_cause() {
    let harness = WireHarness::start(Roller).await.unwrap();

    let (a, b) = tokio::join!(roll(&harness, Some("chat-a")), roll(&harness, Some("chat-b")));
    let _ = (a, b);
    wait_for_fires(&harness, 2).await;

    let mut seen: Vec<Option<String>> = harness
        .fired_triggers()
        .iter()
        .map(|t| t.caused_by.clone())
        .collect();
    seen.sort();
    assert_eq!(
        seen,
        vec![Some("chat-a".to_string()), Some("chat-b".to_string())]
    );
}

/// The compatibility promise behind `Host::fire_trigger_caused_by` being a
/// DEFAULTED trait method: this impl is in another crate and overrides only the
/// methods that existed before leases did. It has to keep compiling, and its
/// fires have to keep arriving.
///
/// A plugin author's own test double is exactly this shape. Requiring the new
/// method would break every one of them at compile time, in a wave whose whole
/// premise is that it changes nothing.
#[tokio::test]
async fn a_host_written_before_leases_existed_still_compiles_and_fires() {
    struct AncientHost;

    #[async_trait::async_trait]
    impl Host for AncientHost {
        fn plugin_id(&self) -> &str {
            "ancient"
        }
        async fn fire_trigger(&self, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn log(&self, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn get_config(&self) -> anyhow::Result<String> {
            Ok("{}".into())
        }
        async fn get_daemon_info(
            &self,
        ) -> anyhow::Result<astra_plugin_sdk::proto::PluginDaemonInfoResponse> {
            Ok(Default::default())
        }
        async fn get_ai_settings(
            &self,
        ) -> anyhow::Result<astra_plugin_sdk::proto::PluginAiSettings> {
            Ok(Default::default())
        }
        async fn set_variable(&self, _: &str, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn push_to_ui(&self, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn send_chat_message(
            &self,
            _: &str,
            _: &str,
            _: bool,
        ) -> anyhow::Result<astra_plugin_sdk::ChatStream> {
            Ok(Box::pin(tokio_stream::empty()))
        }
        async fn set_theme_contribution(
            &self,
            _: astra_plugin_sdk::proto::PluginThemeContribution,
        ) -> anyhow::Result<()> {
            Ok(())
        }
    }

    let ctx = PluginContext::new("test", Arc::new(AncientHost));
    ctx.host().fire_trigger("on_roll_value", "{}").await.unwrap();
    ctx.host()
        .fire_trigger_caused_by("on_roll_value", "{}", Some("lease-abc"))
        .await
        .expect("the default drops the cause rather than failing the fire");
}

// ── the lease and the invocation are two different facts on one call ─────────
//
// They arrive by different routes and must not be able to stand in for each
// other: the lease is gRPC METADATA (`x-astra-cause`) and says *what run* is
// calling; the invocation is a field in the request BODY and says *which
// conversation* that run belongs to. A call can carry either, both or neither.
//
// The SDK reads them at two different moments for a mechanical reason —
// `scoped()` runs while the request is still a `tonic::Request` and can only
// see metadata; the invocation is not readable until `into_inner()`. A test
// that exercised only one of them would not notice the second read being
// dropped, or overwriting the first.

/// Records what `ctx.invocation()` said, so a test can assert on it after the
/// RPC has answered.
#[derive(Clone, Default)]
struct SeenInvocation(Arc<std::sync::Mutex<Vec<Option<String>>>>);

struct Reporter(SeenInvocation);

#[astra_plugin_sdk::async_trait]
impl PluginCapability for Reporter {
    type Config = NoConfig;

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        _name: &str,
        _args: &str,
    ) -> Result<String, ToolError> {
        self.0
             .0
            .lock()
            .unwrap()
            .push(ctx.invocation().and_then(|i| i.conversation()).map(str::to_string));
        // Fire as well, so one call can be asked both questions.
        let host = ctx.host().clone();
        tokio::spawn(async move {
            tokio::task::yield_now().await;
            let _ = host.fire_trigger("on_roll_value", "{}").await;
        });
        Ok("ok".into())
    }
}

#[tokio::test]
async fn a_lease_and_an_invocation_on_one_call_are_read_back_independently() {
    let seen = SeenInvocation::default();
    let harness = WireHarness::start(Reporter(seen.clone())).await.unwrap();

    let mut request = harness.request(astra_plugin_sdk::proto::PluginCallToolRequest {
        tool_name: "roll_dice".into(),
        arguments_json: "{}".into(),
        invocation: Some(astra_plugin_sdk::proto::PluginInvocation {
            conversation_id: "conv-7".into(),
        }),
        attachments: Vec::new(),
    });
    request
        .metadata_mut()
        .insert(X_ASTRA_CAUSE, "lease-xyz".parse().unwrap());
    harness.client().call_tool(request).await.unwrap();
    wait_for_fires(&harness, 1).await;

    assert_eq!(
        seen.0.lock().unwrap().as_slice(),
        [Some("conv-7".to_string())],
        "the body's conversation must reach the handler's context"
    );
    assert_eq!(
        harness.fired_triggers()[0].caused_by.as_deref(),
        Some("lease-xyz"),
        "and attaching the invocation must not have cost the metadata lease"
    );
}

#[tokio::test]
async fn an_invocation_with_no_lease_still_reaches_the_handler() {
    // The case the review caught: a run that HAS a conversation but no lease —
    // the two are independent, so neither implies the other.
    let seen = SeenInvocation::default();
    let harness = WireHarness::start(Reporter(seen.clone())).await.unwrap();

    harness
        .call_tool_from("roll_dice", "{}", Some("conv-8"))
        .await
        .unwrap();

    assert_eq!(seen.0.lock().unwrap().as_slice(), [Some("conv-8".to_string())]);
}

#[tokio::test]
async fn an_empty_conversation_id_is_no_conversation_at_all() {
    // `""` is how a daemon spells "not from a conversation" in a message it
    // still sends. Handing a plugin `Some("")` would give it an id that can
    // never resolve, and it must be indistinguishable from an absent message.
    let seen = SeenInvocation::default();
    let harness = WireHarness::start(Reporter(seen.clone())).await.unwrap();

    harness.call_tool_from("roll_dice", "{}", None).await.unwrap();
    harness.call_tool("roll_dice", "{}").await.unwrap();

    assert_eq!(
        seen.0.lock().unwrap().as_slice(),
        [None, None],
        "an empty invocation and an absent one are the same answer"
    );
}

// ── speech and identity, from inside a leased call ──────────────────────────
//
// `Speak`, `StopSpeaking` and `GetUserIdentity` are DEFAULTED `Host` methods,
// and the host a handler holds is the scoped one (`CausalHost`) wrapping the
// real client. A wrapper that forgot one would compile, and the handler would
// get "this Host does not implement Speak" while the client underneath speaks
// perfectly well — so these run the whole chain: leased `CallTool`, scoped
// context, wrapper, client, session token, mock daemon.

use astra_plugin_sdk::proto::{PluginErrorCode, PluginSpeechOutcome};

/// `announce` says its argument string and reports what Astra answered and
/// who is using it; `hush` stops its own speech.
struct Announcer;

#[async_trait::async_trait]
impl PluginCapability for Announcer {
    type Config = NoConfig;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![
            ToolDef::new("announce", "Say something aloud"),
            ToolDef::new("hush", "Stop saying it"),
        ]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        name: &str,
        args: &str,
    ) -> Result<String, ToolError> {
        if name == "hush" {
            ctx.host().stop_speaking().await?;
            return Ok("hushed".into());
        }
        let said = ctx.host().speak(args).await?;
        let who = ctx.host().get_user_identity().await?;
        let outcome = match said.outcome() {
            PluginSpeechOutcome::Spoken => "spoken",
            PluginSpeechOutcome::Stopped => "stopped",
            PluginSpeechOutcome::NotSpoken => "not_spoken",
            _ => "unspecified",
        };
        let why = said.error.unwrap_or_default();
        let rate_limited = why.code() == PluginErrorCode::PluginErrorRateLimited;
        Ok(format!(
            "{outcome}|rate_limited={rate_limited}|wait={}|{}|{}|{}",
            why.retry_after_ms, who.install_id, who.authorized, who.account_id
        ))
    }
}

async fn announce(harness: &WireHarness, tool: &str, text: &str) -> astra_plugin_sdk::proto::PluginCallToolResponse {
    let mut request = harness.request(astra_plugin_sdk::proto::PluginCallToolRequest {
        tool_name: tool.into(),
        arguments_json: text.into(),
        invocation: None,
        attachments: Vec::new(),
    });
    request
        .metadata_mut()
        .insert(X_ASTRA_CAUSE, "lease-speak".parse().unwrap());
    harness
        .client()
        .call_tool(request)
        .await
        .expect("CallTool answered")
        .into_inner()
}

/// The words reach the daemon through the scoped host, with the session
/// token, and the identity round-trips field for field. Speaking is not a
/// fire, so nothing about it spends or carries the lease.
#[tokio::test]
async fn speech_and_identity_from_a_leased_call_reach_the_daemon() {
    let harness = WireHarness::start(Announcer).await.unwrap();

    let resp = announce(&harness, "announce", "The kettle has boiled.").await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(
        resp.result,
        "spoken|rate_limited=false|wait=0|mock-install-pseudonym|true|mock-account-pseudonym"
    );
    assert_eq!(harness.daemon().spoken(), vec!["The kettle has boiled.".to_string()]);
    assert!(
        harness.daemon().unauthenticated_calls().is_empty(),
        "a host call went out without the session token: {:?}",
        harness.daemon().unauthenticated_calls()
    );
    assert!(harness.fired_triggers().is_empty());
}

/// `NotSpoken` is an ANSWER, not an error: the handler gets the outcome and
/// the daemon's `PluginError` — the code and the wait — and decides.
#[tokio::test]
async fn a_not_spoken_answer_reaches_the_handler_with_its_code_and_wait() {
    let harness = WireHarness::start(Announcer).await.unwrap();
    harness
        .daemon()
        .set_speak_response(astra_plugin_sdk::proto::PluginSpeakResponse {
            outcome: PluginSpeechOutcome::NotSpoken as i32,
            error: Some(astra_plugin_sdk::proto::PluginError {
                code: PluginErrorCode::PluginErrorRateLimited as i32,
                message: "this plugin has used its speaking time".into(),
                retry_after_ms: 1500,
                ..Default::default()
            }),
        });
    harness.daemon().set_user_identity(astra_plugin_sdk::proto::PluginUserIdentity {
        install_id: "install-x".into(),
        signed_in: true,
        authorized: false,
        account_id: String::new(),
    });

    let resp = announce(&harness, "announce", "Again.").await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "not_spoken|rate_limited=true|wait=1500|install-x|false|");
    // What the plugin asked to say is still on the record.
    assert_eq!(harness.daemon().spoken(), vec!["Again.".to_string()]);
}

/// `speak` gates both rpcs, as it does in the daemon: revoke it and Speak and
/// StopSpeaking are both refused, as `Unauthorized`, which a handler's `?`
/// passes on with its kind intact.
#[tokio::test]
async fn without_the_speak_grant_neither_speak_nor_stop_speaking_is_allowed() {
    let harness = WireHarness::start(Announcer).await.unwrap();
    harness.daemon().revoke("speak");

    for tool in ["announce", "hush"] {
        let resp = announce(&harness, tool, "x").await;
        assert!(!resp.success, "{tool} must be refused without `speak`");
        assert_eq!(
            resp.error_detail.expect("a coded refusal").code(),
            PluginErrorCode::PluginErrorUnauthorized,
            "{tool}"
        );
    }
    assert!(harness.daemon().spoken().is_empty());
}

// ── a settings request, from inside a leased call ───────────────────────────
//
// `RequestSettingsChange` is a DEFAULTED `Host` method like `Speak`, so the
// same whole chain runs for it: leased `CallTool`, scoped context, wrapper,
// client, session token, mock daemon.

use astra_plugin_sdk::proto::{PluginSettingChange, PluginSettingsChangeOutcome};

/// `tune` asks for `ai.model` = its argument string and reports what Astra
/// answered: `outcome|code|refused_path|retry_after_ms`.
struct Tuner;

#[async_trait::async_trait]
impl PluginCapability for Tuner {
    type Config = NoConfig;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef::new("tune", "Ask for a model")]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        _name: &str,
        args: &str,
    ) -> Result<String, ToolError> {
        let asked = ctx
            .host()
            .request_settings_change(
                &[PluginSettingChange::new("ai.model", args)],
                "tuned for this model",
            )
            .await?;
        let outcome = match asked.outcome() {
            PluginSettingsChangeOutcome::Applied => "applied",
            PluginSettingsChangeOutcome::Unchanged => "unchanged",
            PluginSettingsChangeOutcome::Declined => "declined",
            PluginSettingsChangeOutcome::TimedOut => "timed_out",
            PluginSettingsChangeOutcome::Refused => "refused",
            _ => "unspecified",
        };
        let wait = asked.error.map(|e| e.retry_after_ms).unwrap_or_default();
        Ok(format!(
            "{outcome}|{}|{}|{wait}",
            asked.code, asked.refused_path
        ))
    }
}

/// The request reaches the daemon through the scoped host, with the session
/// token, exactly as written — the value as JSON, the reason whole. Asking is
/// not a fire, so nothing about it spends or carries the lease.
#[tokio::test]
async fn a_settings_request_from_a_leased_call_reaches_the_daemon() {
    let harness = WireHarness::start(Tuner).await.unwrap();

    let resp = announce(&harness, "tune", "gpt-4.1").await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "applied|||0");
    let asked = harness.daemon().settings_change_requests();
    assert_eq!(asked.len(), 1);
    assert_eq!(
        asked[0].changes,
        vec![PluginSettingChange::new("ai.model", "gpt-4.1")]
    );
    assert_eq!(asked[0].changes[0].value_json, r#""gpt-4.1""#);
    assert_eq!(asked[0].reason, "tuned for this model");
    assert!(harness.daemon().unauthenticated_calls().is_empty());
    assert!(harness.fired_triggers().is_empty());
}

/// `Refused` is an ANSWER, not an error: the handler gets the code word, the
/// setting it is about and the wait, and decides.
#[tokio::test]
async fn a_refused_settings_request_reaches_the_handler_with_its_code_path_and_wait() {
    let harness = WireHarness::start(Tuner).await.unwrap();
    harness.daemon().set_settings_change_response(
        astra_plugin_sdk::proto::PluginSettingsChangeResponse {
            outcome: PluginSettingsChangeOutcome::Refused as i32,
            refused_path: "ai.model".into(),
            code: "rate_limited".into(),
            error: Some(astra_plugin_sdk::proto::PluginError {
                code: PluginErrorCode::PluginErrorRateLimited as i32,
                message: "this plugin asked too often".into(),
                retry_after_ms: 90_000,
                ..Default::default()
            }),
        },
    );

    let resp = announce(&harness, "tune", "gpt-4.1").await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "refused|rate_limited|ai.model|90000");
    // What the plugin asked for is still on the record.
    assert_eq!(harness.daemon().settings_change_requests().len(), 1);
}

/// Without the grant the request is refused at the gate, as `Unauthorized`,
/// which a handler's `?` passes on with its kind intact — and nothing reaches
/// the card.
#[tokio::test]
async fn without_the_grant_a_settings_request_is_refused_at_the_gate() {
    let harness = WireHarness::start(Tuner).await.unwrap();
    harness.daemon().revoke("request_settings_change");

    let resp = announce(&harness, "tune", "gpt-4.1").await;
    assert!(!resp.success);
    assert_eq!(
        resp.error_detail.expect("a coded refusal").code(),
        PluginErrorCode::PluginErrorUnauthorized
    );
    assert!(harness.daemon().settings_change_requests().is_empty());
}

// ── a command offer, from inside a leased call ──────────────────────────────
//
// `ProposeCommand` is a DEFAULTED `Host` method like `RequestSettingsChange`,
// so the same whole chain runs for it: leased `CallTool`, scoped context,
// wrapper, client, session token, mock daemon.

use astra_plugin_sdk::proto::PluginProposeCommandOutcome;

/// `offer` offers the first command of the `.astra` file in its arguments
/// under the key `morning` and reports what Astra answered:
/// `outcome|enabled|code|retry_after_ms`.
struct Offerer;

#[async_trait::async_trait]
impl PluginCapability for Offerer {
    type Config = NoConfig;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef::new("offer", "Offer a command")]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        _name: &str,
        args: &str,
    ) -> Result<String, ToolError> {
        let commands = astra_plugin_sdk::commands_from_astra_file(args)?;
        let command = serde_json::to_string(&commands[0])?;
        let offered = ctx
            .host()
            .propose_command("morning", &command, "reads you the news")
            .await?;
        let outcome = match offered.outcome() {
            PluginProposeCommandOutcome::Saved => "saved",
            PluginProposeCommandOutcome::Unchanged => "unchanged",
            PluginProposeCommandOutcome::Declined => "declined",
            PluginProposeCommandOutcome::TimedOut => "timed_out",
            PluginProposeCommandOutcome::Refused => "refused",
            _ => "unspecified",
        };
        let wait = offered.error.map(|e| e.retry_after_ms).unwrap_or_default();
        Ok(format!(
            "{outcome}|{}|{}|{wait}",
            offered.enabled, offered.code
        ))
    }
}

const MORNING_FILE: &str = r#"{"format":"astra-commands","version":1,"commands":[
    {"name":"Good morning","triggers":[{"type":"text","phrases":["good morning"]}],
     "actions":[],"enabled":true,"source_id":"6f1c2a9e"}]}"#;

/// The offer reaches the daemon through the scoped host, with the session
/// token, exactly as the plugin built it — the file's local members gone, the
/// rest whole. Offering is not a fire, so nothing about it spends or carries
/// the lease.
#[tokio::test]
async fn a_command_offer_from_a_leased_call_reaches_the_daemon() {
    let harness = WireHarness::start(Offerer).await.unwrap();

    let resp = announce(&harness, "offer", MORNING_FILE).await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "saved|true||0");
    let offered = harness.daemon().command_offers();
    assert_eq!(offered.len(), 1);
    assert_eq!(offered[0].key, "morning");
    assert_eq!(offered[0].reason, "reads you the news");
    let sent: serde_json::Value = serde_json::from_str(&offered[0].command_json).unwrap();
    assert_eq!(
        sent,
        serde_json::json!({
            "name": "Good morning",
            "triggers": [{"type": "text", "phrases": ["good morning"]}],
            "actions": [],
        })
    );
    assert!(harness.daemon().unauthenticated_calls().is_empty());
    assert!(harness.fired_triggers().is_empty());
}

/// `Refused` is an ANSWER, not an error: the handler gets the code word and
/// the wait, and decides.
#[tokio::test]
async fn a_refused_command_offer_reaches_the_handler_with_its_code_and_wait() {
    let harness = WireHarness::start(Offerer).await.unwrap();
    harness.daemon().set_command_offer_response(
        astra_plugin_sdk::proto::PluginProposeCommandResponse {
            outcome: PluginProposeCommandOutcome::Refused as i32,
            code: "rate_limited".into(),
            error: Some(astra_plugin_sdk::proto::PluginError {
                code: PluginErrorCode::PluginErrorRateLimited as i32,
                message: "too many command offers".into(),
                retry_after_ms: 120_000,
                ..Default::default()
            }),
            ..Default::default()
        },
    );

    let resp = announce(&harness, "offer", MORNING_FILE).await;
    assert!(resp.success, "{}", resp.error);
    assert_eq!(resp.result, "refused|false|rate_limited|120000");
    // What the plugin offered is still on the record.
    assert_eq!(harness.daemon().command_offers().len(), 1);
}

/// Without the grant the offer is refused at the gate, as `Unauthorized`,
/// which a handler's `?` passes on with its kind intact — and nothing reaches
/// the card.
#[tokio::test]
async fn without_the_grant_a_command_offer_is_refused_at_the_gate() {
    let harness = WireHarness::start(Offerer).await.unwrap();
    harness.daemon().revoke("propose_command");

    let resp = announce(&harness, "offer", MORNING_FILE).await;
    assert!(!resp.success);
    assert_eq!(
        resp.error_detail.expect("a coded refusal").code(),
        PluginErrorCode::PluginErrorUnauthorized
    );
    assert!(harness.daemon().command_offers().is_empty());
}
