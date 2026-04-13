mod web;

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::Mutex;
use tracing::info;

const SOURCE_ID: &str = "web-chat-client";

type SharedDaemon = Arc<Mutex<Option<DaemonClient>>>;

/// In-memory state shared between plugin + web server.
pub struct AppState {
    pub daemon: SharedDaemon,
    /// Broadcast channel for sync events → WebSocket clients
    pub event_tx: tokio::sync::broadcast::Sender<String>,
}

struct WebChatPlugin {
    daemon: SharedDaemon,
    state: Arc<AppState>,
}

impl WebChatPlugin {
    fn new() -> Self {
        let daemon: SharedDaemon = Arc::new(Mutex::new(None));
        let (event_tx, _) = tokio::sync::broadcast::channel::<String>(256);
        let state = Arc::new(AppState {
            daemon: daemon.clone(),
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

    fn subscribed_events(&self) -> Vec<String> {
        vec!["chat_message_sync".to_string()]
    }

    // Using typed handler — no manual JSON parsing, no source_id filtering needed
    async fn on_chat_sync(&self, event: ChatSyncEvent) {
        info!("Sync: role={} conv={} streaming={}", event.role, &event.conversation_id[..8.min(event.conversation_id.len())], event.is_streaming);
        let wrapped = serde_json::json!({
            "type": "sync",
            "data": {
                "id": event.id,
                "conversation_id": event.conversation_id,
                "role": event.role,
                "content": event.content,
                "source_id": event.source_id,
                "is_streaming": event.is_streaming,
                "is_complete": event.is_complete,
            }
        });
        let _ = self.state.event_tx.send(wrapped.to_string());
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
