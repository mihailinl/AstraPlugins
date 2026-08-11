//! Dice Roller — the reference plugin for the macro layer.
//!
//! Everything here is written the way §3.1 of the production plan says a plugin
//! should be written: one dependency, `#[astra::plugin]`, `#[tool]`, and tool
//! schemas derived from the argument types rather than typed out by hand next
//! to a handler that may or may not still agree with them.
//!
//! The two impl blocks are deliberate. The plain one holds helpers — they are
//! ordinary methods and the macro never sees them. The annotated one holds what
//! Astra can call, and `#[hook]` inside it is the escape hatch: `action_types`
//! and `trigger_types` describe `FieldDef` rows with placeholders, defaults and
//! visibility conditions, which no `#[derive]` can invent from a Rust type, so
//! they are written out and moved into the trait impl verbatim.

use std::sync::atomic::{AtomicU64, Ordering};

use astra_plugin_sdk::prelude::*;

/// What the user sets in Astra → Plugins → Dice Roller.
///
/// `PluginConfig` is what makes `plugin.toml`'s `[config] schema` derivable
/// instead of hand-maintained; `Default` is required because the first payload
/// a freshly installed plugin receives is `{}`.
#[astra::args]
#[derive(PluginConfig)]
#[serde(default)]
pub struct DiceConfig {
    /// Sides per die when a roll does not say.
    default_sides: u32,
}

impl Default for DiceConfig {
    fn default() -> Self {
        Self { default_sides: 6 }
    }
}

/// `roll_dice` arguments. The doc comments below become the schema's field
/// descriptions, so the model is told what `sides` means in one place.
#[astra::args]
pub struct RollArgs {
    /// How many dice to roll (1-100).
    #[serde(default = "one")]
    count: u32,
    /// Sides per die. Omitted means "whatever the user configured".
    sides: Option<u32>,
}

/// `coin_flip` arguments.
#[astra::args]
pub struct FlipArgs {
    /// How many coins to flip (1-100).
    #[serde(default = "one")]
    count: u32,
}

fn one() -> u32 {
    1
}

#[derive(Default)]
pub struct DiceRoller {
    config: Config<DiceConfig>,
    total_rolls: AtomicU64,
}

// ── helpers: an ordinary inherent impl the macro never looks at ──────────────

impl DiceRoller {
    fn default_sides(&self) -> u32 {
        self.config.load().default_sides
    }

    fn roll(&self, count: u32, sides: u32) -> Vec<u32> {
        use std::time::SystemTime;
        let seed = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .subsec_nanos();

        let mut results = Vec::with_capacity(count as usize);
        let mut state = seed.wrapping_add(self.total_rolls.load(Ordering::Relaxed) as u32);
        for _ in 0..count {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            results.push((state % sides) + 1);
        }
        self.total_rolls.fetch_add(count as u64, Ordering::Relaxed);
        results
    }

    fn parse_notation(&self, notation: &str) -> (u32, u32) {
        let notation = notation.trim().to_lowercase();
        match notation.find('d') {
            Some(pos) => {
                let count: u32 = if pos == 0 {
                    1
                } else {
                    notation[..pos].parse().unwrap_or(1)
                };
                let sides: u32 = notation[pos + 1..].parse().unwrap_or(self.default_sides());
                (count.clamp(1, 100), sides.clamp(2, 1000))
            }
            None => (1, self.default_sides()),
        }
    }

    /// Fire `on_roll_value` for each die, without blocking the caller. One `Arc`
    /// clone off the handler's context — this used to be a
    /// `Mutex<Option<Arc<Mutex<HostClient>>>>` and a `try_lock` that, when it
    /// lost, logged "host client not available yet" and fired nothing.
    fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
        let host = ctx.host().clone();
        let results = results.to_vec();
        tokio::spawn(async move {
            for v in results {
                let payload = json!({
                    "value": v.to_string(),
                    "roll": format!("1d{sides}"),
                    "sum": v.to_string(),
                });
                if let Err(e) = host
                    .fire_trigger("on_roll_value", &payload.to_string())
                    .await
                {
                    let _ = host
                        .log_warn(&format!("failed to fire on_roll_value: {e}"))
                        .await;
                }
            }
        });
    }
}

// ── what Astra can call ──────────────────────────────────────────────────────

#[astra::plugin]
impl DiceRoller {
    /// Roll dice. Specify count and sides (e.g. 3d6).
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: RollArgs) -> Result<String, ToolError> {
        let sides = a.sides.unwrap_or_else(|| self.default_sides());
        if sides < 2 {
            return Err(ToolError::BadArguments("sides must be >= 2".into()));
        }
        let (count, sides) = (a.count.clamp(1, 100), sides.min(1000));
        let results = self.roll(count, sides);
        let sum: u32 = results.iter().sum();
        self.fire_roll_values(ctx, &results, sides);
        Ok(format!("Rolled {count}d{sides}: {results:?} = {sum}"))
    }

    /// Flip one or more coins.
    #[tool]
    async fn coin_flip(&self, a: FlipArgs) -> Result<String, ToolError> {
        let count = a.count.clamp(1, 100);
        let labels: Vec<&str> = self
            .roll(count, 2)
            .iter()
            .map(|&v| if v == 1 { "Heads" } else { "Tails" })
            .collect();
        Ok(match count {
            1 => format!("Flipped a coin: {}", labels[0]),
            _ => format!("Flipped {count} coins: [{}]", labels.join(", ")),
        })
    }

    /// Hand-written, because `fields` is the point: placeholders, defaults and
    /// a visibility condition are command-editor UI, not a Rust type.
    #[hook]
    async fn action_types(&self) -> Vec<ActionTypeDef> {
        vec![ActionTypeDef {
            r#type: "roll_dice".into(),
            label: "Roll Dice".into(),
            icon_svg: r#"<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="16" cy="16" r="1.5" fill="currentColor"/></svg>"#.into(),
            fields: vec![
                FieldDef::text("dice_notation", "Dice Notation")
                    .with_placeholder("3d6")
                    .with_default("1d6")
                    .with_description("Dice notation like 2d10, d20, 4d6"),
                FieldDef::text("store_in", "Store Result In")
                    .with_placeholder("roll_result")
                    .with_description("Variable name to store the result")
                    .with_condition("dice_notation", "not_empty", ""),
            ],
            ai_available: true,
            ai_description: "Roll dice and store the result in a variable".into(),
            ai_primary_field: "dice_notation".into(),
            // Rolling dice is arithmetic — nothing here is OS-specific, so leave
            // `platforms` empty (which the daemon reads as "every platform")
            // rather than listing the three and having to remember a fourth.
            platforms: vec![],
            // The action is finished: offer it in the command editor's add-node
            // menus. Set this while an action is still half-built and the daemon
            // keeps serving it to commands that already use it, but stops
            // offering it to new ones.
            hidden: false,
        }]
    }

    #[hook]
    async fn execute_action(
        &self,
        ctx: &PluginContext,
        kind: &str,
        params_json: &str,
    ) -> Result<String, ActionError> {
        if kind != "roll_dice" {
            return Err(ActionError::NotFound(format!("Unknown action: {kind}")));
        }
        let params: serde_json::Value = serde_json::from_str(params_json)?;
        let notation = params
            .get("dice_notation")
            .and_then(|v| v.as_str())
            .unwrap_or("1d6");

        let (count, sides) = self.parse_notation(notation);
        let results = self.roll(count, sides);
        let sum: u32 = results.iter().sum();
        self.fire_roll_values(ctx, &results, sides);
        Ok(format!("{count}d{sides}: {results:?} = {sum}"))
    }

    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "on_roll_value".into(),
            label: "Dice Roll Value".into(),
            icon_svg: r#"<svg viewBox="0 0 24 24"><polygon points="12,2 15,9 22,9 16,14 18,22 12,17 6,22 8,14 2,9 9,9" fill="none" stroke="currentColor" stroke-width="2"/></svg>"#.into(),
            fields: vec![
                FieldDef::text("value", "Trigger on Value")
                    .with_placeholder("20")
                    .with_default("20")
                    .with_description("The die value that triggers this (e.g. 20 for nat 20, 1 for fumble). Leave empty for any roll."),
                FieldDef::textarea_with_variables("message", "Message")
                    .with_placeholder("Natural 20!")
                    .with_default("Natural 20! Critical success!"),
            ],
        }]
    }

    /// The whole of config handling: the SDK parsed it, and told the user if it
    /// did not fit, so this only ever runs with a value.
    ///
    /// `type Config = DiceConfig` is inferred from this signature.
    #[hook]
    async fn on_config(&self, ctx: &PluginContext, config: DiceConfig) {
        let _ = ctx
            .host()
            .log_info(&format!("config: default_sides = {}", config.default_sides))
            .await;
        self.config.store(config);
    }

    #[hook]
    async fn health_check(&self) -> (bool, String) {
        let rolls = self.total_rolls.load(Ordering::Relaxed);
        (true, format!("ok — {rolls} total rolls"))
    }
}

astra::main!(DiceRoller::default());
