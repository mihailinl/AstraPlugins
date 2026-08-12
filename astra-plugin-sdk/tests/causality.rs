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
