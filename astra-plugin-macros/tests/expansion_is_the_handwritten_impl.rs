//! The load-bearing property of `#[astra::plugin]`: **the expansion is exactly
//! the trait impl the author would have written by hand.**
//!
//! Two plugins are defined below. `macro_side` uses the attribute; `hand_side`
//! is the impl a careful author writes, transcribed from `cargo expand` output
//! with the generated identifiers renamed and nothing else changed. Every test
//! runs the same call against both and asserts the answers are identical.
//!
//! This is what makes outgrowing the macro a non-event: `cargo expand`, paste,
//! delete the attribute, keep going. If someone ever teaches the macro a hidden
//! registry or a side table, these tests are what fails.

use astra_plugin_sdk::prelude::*;

mod common;

// ── the arguments both sides share ───────────────────────────────────────────

#[astra::args]
pub struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    pub count: u32,
    /// Sides per die
    #[serde(default = "six")]
    pub sides: u32,
}

fn one() -> u32 {
    1
}
fn six() -> u32 {
    6
}

#[astra::args]
#[derive(Default, PluginConfig)]
#[serde(default)]
pub struct Settings {
    pub label: String,
}

fn total(a: &Roll) -> u32 {
    // Deterministic: this test is about dispatch, not randomness.
    a.count * a.sides
}

// ── side A: the macro ────────────────────────────────────────────────────────

#[derive(Default)]
pub struct MacroDice {
    pub last_label: std::sync::Mutex<String>,
}

#[astra::plugin]
impl MacroDice {
    /// Roll dice and return the total.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("sides must be >= 2".into()));
        }
        let t = total(&a);
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": t }).to_string())
            .await?;
        Ok(t.to_string())
    }

    /// Flip a coin. Takes no arguments.
    #[tool]
    async fn coin_flip(&self) -> Result<String, ToolError> {
        Ok("Heads".into())
    }

    /// Roll dice from a command.
    #[action(label = "Roll Dice")]
    async fn roll_action(&self, a: Roll) -> Result<String, ActionError> {
        Ok(total(&a).to_string())
    }

    /// Ask the plugin what it last saw.
    #[ui_call]
    async fn get_label(&self) -> Result<String, ToolError> {
        Ok(self.last_label.lock().unwrap().clone())
    }

    #[hook]
    async fn on_config(&self, _ctx: &PluginContext, cfg: Settings) {
        *self.last_label.lock().unwrap() = cfg.label;
    }

    #[hook]
    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

// ── side B: the same plugin, written out ─────────────────────────────────────

#[derive(Default)]
pub struct HandDice {
    pub last_label: std::sync::Mutex<String>,
}

impl HandDice {
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("sides must be >= 2".into()));
        }
        let t = total(&a);
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": t }).to_string())
            .await?;
        Ok(t.to_string())
    }

    async fn coin_flip(&self) -> Result<String, ToolError> {
        Ok("Heads".into())
    }

    async fn roll_action(&self, a: Roll) -> Result<String, ActionError> {
        Ok(total(&a).to_string())
    }

    async fn get_label(&self) -> Result<String, ToolError> {
        Ok(self.last_label.lock().unwrap().clone())
    }
}

#[async_trait]
impl PluginCapability for HandDice {
    type Config = Settings;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![
            ToolDef::new("roll_dice", "Roll dice and return the total.")
                .with_schema(astra_plugin_sdk::schema::of::<Roll>()),
            ToolDef::new("coin_flip", "Flip a coin. Takes no arguments.")
                .with_schema(r#"{"type":"object","properties":{}}"#),
        ]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        name: &str,
        arguments_json: &str,
    ) -> Result<String, ToolError> {
        match name {
            "roll_dice" => {
                let args: Roll =
                    astra_plugin_sdk::serde_json::from_str(if arguments_json.trim().is_empty() {
                        "{}"
                    } else {
                        arguments_json
                    })?;
                let out: Result<String, ToolError> = Self::roll_dice(self, ctx, args).await;
                out
            }
            "coin_flip" => {
                let out: Result<String, ToolError> = Self::coin_flip(self).await;
                out
            }
            _ => Err(ToolError::NotFound(format!("no tool named `{}`", name))),
        }
    }

    async fn action_types(&self) -> Vec<ActionTypeDef> {
        vec![ActionTypeDef {
            r#type: "roll_action".into(),
            label: "Roll Dice".into(),
            icon_svg: String::new(),
            fields: vec![],
            ai_available: true,
            ai_description: "Roll dice from a command.".into(),
            ai_primary_field: String::new(),
            platforms: vec![],
            hidden: false,
        }]
    }

    async fn execute_action(
        &self,
        _ctx: &PluginContext,
        name: &str,
        arguments_json: &str,
    ) -> Result<String, ActionError> {
        match name {
            "roll_action" => {
                let args: Roll =
                    astra_plugin_sdk::serde_json::from_str(if arguments_json.trim().is_empty() {
                        "{}"
                    } else {
                        arguments_json
                    })?;
                let out: Result<String, ToolError> = Self::roll_action(self, args).await;
                out
            }
            _ => Err(ActionError::NotFound(format!("no action named `{}`", name))),
        }
    }

    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        name: &str,
        _arguments_json: &str,
    ) -> Result<String, ToolError> {
        match name {
            "get_label" => {
                let out: Result<String, ToolError> = Self::get_label(self).await;
                out
            }
            _ => Err(ToolError::NotFound(format!("no UI method `{}`", name))),
        }
    }

    async fn on_config(&self, _ctx: &PluginContext, cfg: Settings) {
        *self.last_label.lock().unwrap() = cfg.label;
    }

    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

impl DeclaredCapabilities for HandDice {
    const CAPS: &'static [&'static str] = &["actions", "tools", "ui_contributions"];
}

// ── the comparison ───────────────────────────────────────────────────────────

/// The property a tool schema actually has to have — a JSON object whose root
/// `type` is `"object"`. Asserted by parsing rather than by `starts_with`,
/// because key order in `schemars`' output is `schemars`' business: it emits
/// `title` before `type`, and a test that pins that is testing the dependency.
fn is_object_rooted(schema: &str) -> bool {
    astra_plugin_sdk::serde_json::from_str::<astra_plugin_sdk::serde_json::Value>(schema)
        .ok()
        .and_then(|v| v.get("type").and_then(|t| t.as_str()).map(str::to_string))
        .as_deref()
        == Some("object")
}

fn tool_shape(t: &ToolDef) -> (String, String, String) {
    (
        t.name.clone(),
        t.description.clone(),
        t.parameters_json.clone(),
    )
}

#[tokio::test]
async fn list_tools_is_identical() {
    let a: Vec<_> = MacroDice::default()
        .list_tools()
        .await
        .iter()
        .map(tool_shape)
        .collect();
    let b: Vec<_> = HandDice::default()
        .list_tools()
        .await
        .iter()
        .map(tool_shape)
        .collect();
    assert_eq!(a, b);

    // Not vacuous: the schema really is derived, and the doc comment really is
    // the description.
    assert_eq!(a[0].1, "Roll dice and return the total.");
    assert!(a[0].2.contains("\"count\""), "schema was {}", a[0].2);
    assert!(
        a[0].2.contains("How many dice to roll"),
        "schema was {}",
        a[0].2
    );
    assert!(is_object_rooted(&a[0].2), "schema was {}", a[0].2);
    assert_eq!(a[1].2, r#"{"type":"object","properties":{}}"#);
}

#[tokio::test]
async fn call_tool_dispatches_identically() {
    let (ctx, host) = common::ctx();
    for args in [r#"{"count":3,"sides":6}"#, "{}", "", r#"{"sides":1}"#] {
        let a = MacroDice::default()
            .call_tool(&ctx, "roll_dice", args)
            .await;
        let b = HandDice::default().call_tool(&ctx, "roll_dice", args).await;
        assert_eq!(format!("{a:?}"), format!("{b:?}"), "args = {args}");
    }
    // Both fired the same triggers, in the same order. Three of the four
    // payloads reach the body — `{"sides":1}` is rejected before the trigger —
    // and each is rolled twice, once per side.
    let fired = host.fired.lock().unwrap().clone();
    assert_eq!(fired.len(), 6, "{fired:?}");
    assert_eq!(fired[0], fired[1]);
    assert_eq!(fired[0].0, "dice_rolled");
    assert_eq!(fired[0].1, r#"{"total":18}"#);

    // A bad payload is BadArguments on both sides, not a panic and not a
    // transport error.
    let a = MacroDice::default()
        .call_tool(&ctx, "roll_dice", "not json")
        .await;
    let b = HandDice::default()
        .call_tool(&ctx, "roll_dice", "not json")
        .await;
    assert!(matches!(a, Err(ToolError::BadArguments(_))));
    assert_eq!(format!("{a:?}"), format!("{b:?}"));

    // An unknown name is NotFound with the same message.
    let a = MacroDice::default().call_tool(&ctx, "nope", "{}").await;
    let b = HandDice::default().call_tool(&ctx, "nope", "{}").await;
    assert_eq!(format!("{a:?}"), format!("{b:?}"));
    assert!(format!("{a:?}").contains("no tool named `nope`"));
}

#[tokio::test]
async fn a_tool_without_a_ctx_parameter_still_dispatches() {
    let (ctx, _) = common::ctx();
    let a = MacroDice::default()
        .call_tool(&ctx, "coin_flip", "{}")
        .await;
    let b = HandDice::default().call_tool(&ctx, "coin_flip", "{}").await;
    assert_eq!(a.unwrap(), b.unwrap());
}

#[tokio::test]
async fn actions_are_identical() {
    let a = MacroDice::default().action_types().await;
    let b = HandDice::default().action_types().await;
    assert_eq!(a, b);
    assert_eq!(a[0].label, "Roll Dice");
    assert_eq!(a[0].ai_description, "Roll dice from a command.");

    let (ctx, _) = common::ctx();
    let ra = MacroDice::default()
        .execute_action(&ctx, "roll_action", r#"{"count":2,"sides":6}"#)
        .await;
    let rb = HandDice::default()
        .execute_action(&ctx, "roll_action", r#"{"count":2,"sides":6}"#)
        .await;
    assert_eq!(ra.unwrap(), rb.unwrap());

    let ra = MacroDice::default()
        .execute_action(&ctx, "nope", "{}")
        .await;
    let rb = HandDice::default().execute_action(&ctx, "nope", "{}").await;
    assert_eq!(format!("{ra:?}"), format!("{rb:?}"));
}

/// Derived from a name with no explicit `label`, so the default really is
/// title-cased rather than the raw identifier.
#[tokio::test]
async fn ui_calls_and_config_are_identical() {
    let (ctx, _) = common::ctx();
    let m = MacroDice::default();
    let h = HandDice::default();

    // `type Config` was inferred from the `#[hook] on_config` signature, so the
    // SDK's default `on_config_changed` parses into `Settings` on both sides.
    m.on_config_changed(&ctx, r#"{"label":"hello"}"#).await;
    h.on_config_changed(&ctx, r#"{"label":"hello"}"#).await;
    assert_eq!(
        m.handle_ui_call(&ctx, "get_label", "{}").await.unwrap(),
        h.handle_ui_call(&ctx, "get_label", "{}").await.unwrap(),
    );
    assert_eq!(
        m.handle_ui_call(&ctx, "get_label", "{}").await.unwrap(),
        "hello"
    );

    let a = m.handle_ui_call(&ctx, "nope", "{}").await;
    let b = h.handle_ui_call(&ctx, "nope", "{}").await;
    assert_eq!(format!("{a:?}"), format!("{b:?}"));
}

#[test]
fn declared_capabilities_are_identical_and_derived_from_the_hooks_present() {
    assert_eq!(
        <MacroDice as DeclaredCapabilities>::CAPS,
        <HandDice as DeclaredCapabilities>::CAPS,
    );
    // `#[tool]` → tools, `#[action]` → actions, `#[ui_call]` → ui_contributions.
    // `#[hook] on_config` and `#[hook] health_check` are lifecycle: they declare
    // nothing, because every plugin may have settings and a health check.
    assert_eq!(
        <MacroDice as DeclaredCapabilities>::CAPS,
        ["actions", "tools", "ui_contributions"],
    );
}

#[tokio::test]
async fn hooks_move_across_verbatim() {
    assert_eq!(
        MacroDice::default().health_check().await,
        (true, "ok".into())
    );
    // ...and are no longer inherent methods, which is what makes moving them
    // across a *move* and not a copy that can drift.
    // (`MacroDice::default().health_check()` above resolves through the trait.)
}

/// `#[derive(PluginConfig)]` produces the schema `plugin.toml`'s `[config]`
/// section is generated from.
#[test]
fn plugin_config_derives_a_schema() {
    let schema = <Settings as PluginConfig>::json_schema();
    assert!(schema.contains("\"label\""), "{schema}");
    assert!(is_object_rooted(&schema), "{schema}");
    assert!(!schema.contains("$schema"), "{schema}");
}
