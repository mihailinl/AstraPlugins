//! Dice Roller's reference test suite — what a plugin's tests should look
//! like.
//!
//! Copy the shape, not the assertions. There are two levels and they are not
//! interchangeable:
//!
//! * **Level 1** ([`Harness`]) runs the hooks in process against a
//!   [`RecordingHost`]. Fast, no daemon, no socket. This is where a plugin's
//!   *logic* is tested, and where nearly all of a plugin's tests belong.
//! * **Level 2** ([`WireHarness`]) starts the plugin the way the daemon starts
//!   it — bind, register, `on_start`, serve — and drives it with a real gRPC
//!   client. Slower, and it catches an entire class of defect level 1 is
//!   structurally blind to: a hook the service never routes, a missing session
//!   token, a message that does not encode.
//!
//! The plugin is pulled in with `#[path]` rather than built as a library,
//! because a plugin is a binary: this is the same `src/main.rs` Astra runs.

#[allow(dead_code, unused_imports)]
#[path = "../src/main.rs"]
mod plugin;

use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::testing::{Harness, MockDaemon, WireHarness};
use plugin::{DiceRoller, RollArgs};

/// The plugin as a user with default settings has it.
fn dice() -> Harness<DiceRoller> {
    Harness::new(DiceRoller::default()).with_config(json!({ "default_sides": 6 }))
}

// ── level 1 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn rolls_the_dice_it_was_asked_for() {
    let h = dice().start().await.unwrap();

    let out = h
        .call_tool("roll_dice", json!({ "count": 3, "sides": 20 }))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d20: "), "{out}");

    // Three dice, three values in 1..=20 — the roll is seeded from the clock,
    // so the *shape* is what can be asserted, and it is what matters.
    let values = &out[out.find('[').unwrap() + 1..out.find(']').unwrap()];
    let values: Vec<u32> = values.split(", ").map(|v| v.parse().unwrap()).collect();
    assert_eq!(values.len(), 3);
    assert!(values.iter().all(|v| (1..=20).contains(v)), "{values:?}");
}

#[tokio::test]
async fn an_unconfigured_roll_uses_the_configured_default() {
    let h = dice().with_config(json!({ "default_sides": 4 })).start().await.unwrap();
    let out = h.call_tool("roll_dice", json!({})).await.unwrap();
    assert!(out.starts_with("Rolled 1d4: "), "{out}");
}

/// A fresh install sends `{}`. `#[astra::args]` puts `#[serde(default)]` on the
/// container and `Default for DiceConfig` supplies 6, so the plugin runs on the
/// documented default rather than on zero sides.
#[tokio::test]
async fn a_fresh_install_gets_the_documented_default() {
    let h = Harness::new(DiceRoller::default())
        .with_config_json("{}")
        .start()
        .await
        .unwrap();
    let out = h.call_tool("roll_dice", json!({})).await.unwrap();
    assert!(out.starts_with("Rolled 1d6: "), "{out}");
}

/// Arguments the model can get wrong come back as `BAD_ARGUMENTS`, which is the
/// one kind it can act on: retry with different arguments.
#[tokio::test]
async fn a_one_sided_die_is_bad_arguments_and_not_a_crash() {
    let h = dice().start().await.unwrap();
    let err = h
        .call_tool("roll_dice", json!({ "count": 1, "sides": 1 }))
        .await
        .unwrap_err();
    assert!(matches!(err, ToolError::BadArguments(_)), "{err:?}");

    let err = h.call_tool_json("roll_dice", "{ not json").await.unwrap_err();
    assert!(matches!(err, ToolError::BadArguments(_)), "{err:?}");

    let err = h.call_tool("no_such_tool", json!({})).await.unwrap_err();
    assert!(matches!(err, ToolError::NotFound(_)), "{err:?}");
}

/// The trigger is fired from a spawned task, so the assertion waits for it
/// rather than assuming the tool call outlived it.
#[tokio::test]
async fn every_die_fires_on_roll_value() {
    let h = dice().start().await.unwrap();
    h.call_tool("roll_dice", json!({ "count": 4, "sides": 6 }))
        .await
        .unwrap();

    let fired = h.wait_for_triggers("on_roll_value", 4).await;
    assert_eq!(fired.len(), 4);
    for t in &fired {
        let payload: serde_json::Value = serde_json::from_str(&t.payload_json).unwrap();
        assert_eq!(payload["roll"], "1d6");
        assert!(payload["value"].is_string(), "{payload}");
    }
}

/// `[permissions]` is default-deny. `plugin.toml` declares `fire_trigger` — but
/// a user can revoke it, and a plugin that dies on the denial is a plugin that
/// dies on someone else's machine.
#[tokio::test]
async fn a_denied_fire_trigger_is_logged_and_the_roll_still_answers() {
    let h = dice().start().await.unwrap();
    h.host().deny("fire_trigger");

    let out = h.call_tool("roll_dice", json!({ "count": 1 })).await.unwrap();
    assert!(out.starts_with("Rolled 1d6: "), "the roll is still the answer");

    // dice-roller logs the failure rather than losing it silently, which is
    // what the `try_lock` this replaced used to do.
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(1);
    let warning = loop {
        if let Some(l) = h.logs().into_iter().find(|l| l.level == "warn") {
            break l;
        }
        assert!(std::time::Instant::now() < deadline, "no warning was logged");
        tokio::time::sleep(std::time::Duration::from_millis(5)).await;
    };
    assert!(warning.message.contains("on_roll_value"), "{warning:?}");
}

/// The schema the model is shown is generated from the type the handler parses.
#[tokio::test]
async fn the_tool_schemas_are_the_argument_types() {
    let h = dice().start().await.unwrap();

    let names: Vec<String> = h.tools().await.into_iter().map(|t| t.name).collect();
    assert_eq!(names, ["roll_dice", "coin_flip"]);

    let roll = h.schema("roll_dice").await;
    roll.assert_is_a_parameters_object();
    assert_eq!(roll.properties(), ["count", "sides"]);
    assert_eq!(
        roll.description_of("sides").as_deref(),
        Some("Sides per die. Omitted means \"whatever the user configured\"."),
    );
    h.assert_schema_matches::<RollArgs>("roll_dice").await;
}

/// The action path is the command editor's, and it takes dice notation rather
/// than JSON arguments.
#[tokio::test]
async fn the_action_parses_dice_notation() {
    let h = dice().start().await.unwrap();

    let types = h.action_types().await;
    assert_eq!(types.len(), 1);
    assert_eq!(types[0].r#type, "roll_dice");
    assert!(
        types[0].fields.iter().any(|f| f.id == "dice_notation"),
        "the command editor needs the field to render",
    );

    let out = h
        .execute_action("roll_dice", json!({ "dice_notation": "2d10" }))
        .await
        .unwrap();
    assert!(out.starts_with("2d10: "), "{out}");

    // Nonsense notation falls back rather than failing the command.
    let out = h
        .execute_action("roll_dice", json!({ "dice_notation": "nonsense" }))
        .await
        .unwrap();
    assert!(out.starts_with("1d6: "), "{out}");

    let err = h.execute_action("nope", json!({})).await.unwrap_err();
    assert!(matches!(err, ActionError::NotFound(_)), "{err:?}");
}

/// Every config payload the daemon can produce. The plugin has to be serving
/// afterwards — which is the whole assertion.
#[tokio::test]
async fn survives_every_config_the_daemon_can_send() {
    let h = dice().start().await.unwrap();
    h.fuzz_config().await;

    h.config_changed(json!({ "default_sides": 6 })).await;
    assert!(
        h.call_tool("roll_dice", json!({})).await.unwrap().starts_with("Rolled 1d6: "),
    );
    assert!(h.health().await.0);
}

// ── level 2 ──────────────────────────────────────────────────────────────────

/// The whole plugin, over its own gRPC server, against a daemon that enforces
/// the session token — and the trigger arriving at the daemon at the end is the
/// half no in-process test can see.
#[tokio::test]
async fn the_daemon_can_start_it_call_it_and_receive_its_triggers() {
    let daemon = MockDaemon::start().await.unwrap();
    daemon.set_config_json(r#"{"default_sides":6}"#);

    let w = WireHarness::start_on(
        daemon,
        DiceRoller::default(),
        "dice-roller",
        // What `plugin.toml` declares. The daemon passes it on argv; the plugin
        // cannot read the manifest itself.
        &["tools", "actions", "triggers"],
    )
    .await
    .unwrap();

    let reg = w.daemon().registration().unwrap();
    assert_eq!(reg.plugin_id, "dice-roller");
    assert_eq!(reg.capabilities, ["tools", "actions", "triggers"]);

    let tools: Vec<String> = w.list_tools().await.unwrap().into_iter().map(|t| t.name).collect();
    assert_eq!(tools, ["roll_dice", "coin_flip"]);

    let resp = w.call_tool("roll_dice", r#"{"count":2,"sides":6}"#).await.unwrap();
    assert!(resp.success, "{}", resp.error);

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    while w.fired_triggers().len() < 2 {
        assert!(
            std::time::Instant::now() < deadline,
            "the triggers never reached the daemon: {:?}",
            w.fired_triggers()
        );
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
    }
    assert!(w.fired_triggers().iter().all(|t| t.trigger_type == "on_roll_value"));

    assert!(w.health().await.unwrap().healthy);
    w.shutdown().await.unwrap();
}

/// The daemon revoked `fire_trigger`. The tool still answers — with the roll,
/// because dice-roller treats a failed trigger as a warning and not as a
/// failure of the call.
#[tokio::test]
async fn a_revoked_permission_does_not_take_the_tool_down_with_it() {
    let daemon = MockDaemon::start().await.unwrap();
    daemon.set_config_json(r#"{"default_sides":6}"#);
    daemon.revoke("fire_trigger");

    let w = WireHarness::start_on(daemon, DiceRoller::default(), "dice-roller", &["tools"])
        .await
        .unwrap();

    let resp = w.call_tool("roll_dice", r#"{"count":1,"sides":6}"#).await.unwrap();
    assert!(resp.success, "{}", resp.error);
    assert!(w.fired_triggers().is_empty());

    w.shutdown().await.unwrap();
}
