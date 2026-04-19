mod web;

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::Mutex;
use tracing::info;

const SOURCE_ID: &str = "web-chat-client";

type SharedDaemon = Arc<Mutex<Option<DaemonClient>>>;

/// In-memory state shared between plugin + web server.
///
/// `history` holds every JSON event the plugin has observed so far. WS clients
/// connecting mid-flight replay it before switching to the live broadcast.
pub struct AppState {
    pub daemon: SharedDaemon,
    pub history: tokio::sync::RwLock<Vec<String>>,
    pub event_tx: tokio::sync::broadcast::Sender<String>,
}

struct WebChatPlugin {
    daemon: SharedDaemon,
    state: Arc<AppState>,
}

impl WebChatPlugin {
    fn new() -> Self {
        let daemon: SharedDaemon = Arc::new(Mutex::new(None));
        let (event_tx, _) = tokio::sync::broadcast::channel::<String>(1024);
        let state = Arc::new(AppState {
            daemon: daemon.clone(),
            history: tokio::sync::RwLock::new(Vec::new()),
            event_tx,
        });
        Self { daemon, state }
    }
}

#[async_trait::async_trait]
impl PluginCapability for WebChatPlugin {
    fn is_client(&self) -> bool {
        true
    }

    async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {
        let dc = client.lock().await.clone();
        *self.daemon.lock().await = Some(dc);
        info!("DaemonClient connected");

        // Start web server
        let state = self.state.clone();
        tokio::spawn(async move {
            if let Err(e) = web::run_server(state).await {
                tracing::error!("Web server error: {e}");
            }
        });
    }

    fn source_id(&self) -> &str { SOURCE_ID }

    // Firehose: every chat event in every conversation is forwarded to the
    // web client as a JSON message. Conversion is 1:1 — clients parse the
    // tagged-union `event.kind` to decide rendering.
    async fn on_conversation_event(
        &self,
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
        // Buffer for late-arriving WS clients; broadcast for already-connected ones.
        self.state.history.write().await.push(serialized.clone());
        let _ = self.state.event_tx.send(serialized);
    }

    async fn on_shutdown(&self) {
        info!("Shutting down web chat");
    }

    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

#[tokio::main]
async fn main() {
    astra_plugin_sdk::run(WebChatPlugin::new()).await.unwrap();
}
