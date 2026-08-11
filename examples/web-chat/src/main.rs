mod web;

use std::collections::VecDeque;
use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tracing::info;

const SOURCE_ID: &str = "web-chat-client";
/// Max events kept in the replay buffer. Older events are dropped on insert;
/// reconnecting browsers see only the tail, but for a daemon with ever-growing
/// streams this keeps the plugin's memory footprint bounded.
const HISTORY_CAP: usize = 10_000;

/// In-memory state shared between plugin + web server.
///
/// `daemon` used to be an `Arc<Mutex<Option<DaemonClient>>>` that the web
/// handlers locked, unwrapped and matched on for every request. It is now the
/// `Arc<dyn Daemon>` off the plugin context: no lock, no `Option`, and no state
/// where the server is up and the client is not there yet.
///
/// `history` keeps the most recent `HISTORY_CAP` JSON events so WS clients
/// connecting mid-flight can replay before switching to the live broadcast.
pub struct AppState {
    pub daemon: Arc<dyn Daemon>,
    pub history: tokio::sync::RwLock<VecDeque<String>>,
    pub event_tx: tokio::sync::broadcast::Sender<String>,
}

#[derive(Default)]
struct WebChatPlugin;

#[async_trait]
impl PluginCapability for WebChatPlugin {
    type Config = NoConfig;

    fn is_client(&self) -> bool {
        true
    }

    /// The daemon client exists by the time `on_start` runs, so the web server
    /// never observes a half-built plugin — and if the client is missing (the
    /// `client` capability was not granted), startup fails here with a sentence
    /// instead of serving a UI whose every button errors.
    async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
        let daemon = ctx
            .daemon()
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("web-chat needs the `client` capability"))?;
        let (event_tx, _) = tokio::sync::broadcast::channel::<String>(1024);
        let state = Arc::new(AppState {
            daemon,
            history: tokio::sync::RwLock::new(VecDeque::with_capacity(HISTORY_CAP)),
            event_tx,
        });
        STATE.set(state.clone()).ok();
        tokio::spawn(async move {
            if let Err(e) = web::run_server(state).await {
                tracing::error!("Web server error: {e}");
            }
        });
        info!("Web chat started");
        Ok(())
    }

    // Firehose: every chat event in every conversation is forwarded to the
    // web client as a JSON message. Conversion is 1:1 — clients parse the
    // tagged-union `event.kind` to decide rendering.
    async fn on_conversation_event(
        &self,
        _ctx: &PluginContext,
        conv_id: &str,
        event: &astra_plugin_sdk::proto::ConversationEventMsg,
    ) {
        use astra_plugin_sdk::proto::conversation_event_msg::Event;
        let short_conv = &conv_id[..8.min(conv_id.len())];
        let (kind, body) = match &event.event {
            Some(Event::UserMessage(e)) => ("user_message", serde_json::json!({
                "message_id": e.message_id, "content": e.content,
            })),
            Some(Event::AssistantStart(e)) => ("assistant_start", serde_json::json!({
                "message_id": e.message_id,
            })),
            Some(Event::AssistantTextDelta(e)) => ("assistant_text_delta", serde_json::json!({
                "message_id": e.message_id, "delta": e.delta,
            })),
            Some(Event::AssistantComplete(e)) => ("assistant_complete", serde_json::json!({
                "message_id": e.message_id,
            })),
            Some(Event::ToolCallStart(e)) => ("tool_call_start", serde_json::json!({
                "message_id": e.message_id, "call_id": e.call_id, "name": e.name, "arguments": e.arguments,
            })),
            Some(Event::ToolCallResult(e)) => ("tool_call_result", serde_json::json!({
                "call_id": e.call_id, "output": e.output, "status": e.status,
            })),
            Some(Event::Error(e)) => ("error", serde_json::json!({
                "message_id": e.message_id, "content": e.content,
            })),
            _ => return,
        };
        info!("Firehose: {} on conv={}", kind, short_conv);
        let wrapped = serde_json::json!({
            "type": "event",
            "conversation_id": conv_id,
            "seq": event.seq,
            "kind": kind,
            "body": body,
        });
        let serialized = wrapped.to_string();
        let Some(state) = STATE.get() else { return };
        // Buffer for late-arriving WS clients; broadcast for already-connected ones.
        {
            let mut history = state.history.write().await;
            if history.len() >= HISTORY_CAP {
                history.pop_front();
            }
            history.push_back(serialized.clone());
        }
        let _ = state.event_tx.send(serialized);
    }

    async fn health_check(&self) -> (bool, String) {
        (STATE.get().is_some(), "ok".into())
    }
}

/// The web server is spawned in `on_start` and the firehose hook needs the same
/// state; a `OnceLock` is the whole of the sharing, because `on_start` runs
/// exactly once and strictly before anything can call a hook.
static STATE: std::sync::OnceLock<Arc<AppState>> = std::sync::OnceLock::new();

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(WebChatPlugin).await
}
