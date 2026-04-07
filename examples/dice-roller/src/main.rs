use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::Mutex;
use tracing::info;

struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

impl DiceRoller {
    fn new() -> Self {
        Self {
            default_sides: AtomicU32::new(6),
            total_rolls: AtomicU64::new(0),
            host: Mutex::new(None),
        }
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
        self.total_rolls
            .fetch_add(count as u64, Ordering::Relaxed);
        results
    }

    fn parse_notation(&self, notation: &str) -> (u32, u32) {
        let notation = notation.trim().to_lowercase();
        if let Some(pos) = notation.find('d') {
            let count: u32 = if pos == 0 {
                1
            } else {
                notation[..pos].parse().unwrap_or(1)
            };
            let sides: u32 = notation[pos + 1..]
                .parse()
                .unwrap_or(self.default_sides.load(Ordering::Relaxed));
            (count.max(1).min(100), sides.max(2).min(1000))
        } else {
            (1, self.default_sides.load(Ordering::Relaxed))
        }
    }

    /// Fire on_roll_value trigger for each die result (non-blocking).
    fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
        let host = self.host.try_lock().ok().and_then(|g| g.clone());
        let host = match host {
            Some(h) => h,
            None => {
                info!("Cannot fire triggers: host client not available yet");
                return;
            }
        };

        tokio::spawn(async move {
            for v in results {
                let payload = serde_json::json!({
                    "value": v.to_string(),
                    "roll": format!("1d{}", sides),
                    "sum": v.to_string(),
                });
                info!("Firing on_roll_value trigger with value={}", v);
                let mut h = host.lock().await;
                if let Err(e) = h
                    .fire_trigger("on_roll_value", &payload.to_string())
                    .await
                {
                    tracing::warn!("Failed to fire on_roll_value trigger: {}", e);
                }
            }
        });
    }
}

#[async_trait]
impl PluginCapability for DiceRoller {
    // ── Host ──

    async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
        *self.host.lock().await = Some(host);
        info!("Host client received");
    }

    // ── Tools ──

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![
            ToolDef {
                name: "roll_dice".into(),
                description: "Roll dice. Specify count and sides (e.g., 3d6).".into(),
                parameters_json: r#"{"type":"object","properties":{"count":{"type":"number","description":"Number of dice","default":1},"sides":{"type":"number","description":"Sides per die","default":6}}}"#.into(),
            },
            ToolDef {
                name: "coin_flip".into(),
                description: "Flip one or more coins.".into(),
                parameters_json: r#"{"type":"object","properties":{"count":{"type":"number","description":"Number of coins","default":1}}}"#.into(),
            },
        ]
    }

    async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value =
            serde_json::from_str(arguments_json).unwrap_or_default();

        match name {
            "roll_dice" => {
                let count =
                    args.get("count").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
                let sides = args
                    .get("sides")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(self.default_sides.load(Ordering::Relaxed) as u64)
                    as u32;

                let count = count.max(1).min(100);
                let sides = sides.max(2).min(1000);
                let results = self.roll(count, sides);
                let sum: u32 = results.iter().sum();

                self.fire_roll_triggers_bg(results.clone(), sides);

                ToolResult::ok(format!("Rolled {}d{}: {:?} = {}", count, sides, results, sum))
            }
            "coin_flip" => {
                let count =
                    args.get("count").and_then(|v| v.as_u64()).unwrap_or(1) as u32;
                let count = count.max(1).min(100);
                let flips = self.roll(count, 2);
                let labels: Vec<&str> = flips
                    .iter()
                    .map(|&v| if v == 1 { "Heads" } else { "Tails" })
                    .collect();
                if count == 1 {
                    ToolResult::ok(format!("Flipped a coin: {}", labels[0]))
                } else {
                    ToolResult::ok(format!("Flipped {} coins: [{}]", count, labels.join(", ")))
                }
            }
            _ => ToolResult::err(format!("Unknown tool: {name}")),
        }
    }

    // ── Actions ──

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
        }]
    }

    async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult {
        info!("execute_action: type={}, params={}", action_type, params_json);
        match action_type {
            "roll_dice" => {
                let params: serde_json::Value =
                    serde_json::from_str(params_json).unwrap_or_default();
                let notation = params
                    .get("dice_notation")
                    .and_then(|v| v.as_str())
                    .unwrap_or("1d6");

                let (count, sides) = self.parse_notation(notation);
                let results = self.roll(count, sides);
                let sum: u32 = results.iter().sum();
                let result_str = format!("{}d{}: {:?} = {}", count, sides, results, sum);

                info!("Roll result: {}", result_str);
                self.fire_roll_triggers_bg(results.clone(), sides);

                ActionResult::ok(result_str)
            }
            _ => ActionResult::err(format!("Unknown action: {action_type}")),
        }
    }

    // ── Triggers ──

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

    // ── Lifecycle ──

    async fn on_config_changed(&self, config_json: &str) {
        if let Ok(config) = serde_json::from_str::<serde_json::Value>(config_json) {
            if let Some(sides) = config.get("default_sides").and_then(|v| v.as_u64()) {
                self.default_sides.store(sides as u32, Ordering::Relaxed);
                info!("Config updated: default_sides = {}", sides);
            }
        }
    }

    async fn health_check(&self) -> (bool, String) {
        let rolls = self.total_rolls.load(Ordering::Relaxed);
        (true, format!("ok — {} total rolls", rolls))
    }
}

#[tokio::main]
async fn main() {
    astra_plugin_sdk::run(DiceRoller::new()).await.unwrap();
}
