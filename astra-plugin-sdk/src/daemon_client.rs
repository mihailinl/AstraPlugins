//! DaemonClient — full daemon API access for client-capable plugins.
//!
//! Only available to plugins that declare [`PluginCapability::is_client()`] = true.
//! The daemon issues a session token during registration, and this client
//! injects it as `x-session-token` on every gRPC request.

use std::collections::HashMap;
use std::time::Duration;

use anyhow::{Context, Result};
use tonic::service::interceptor::InterceptedService;
use tonic::transport::Channel;

use crate::proto;

// ── Auth interceptor ──

#[derive(Clone)]
struct SessionInterceptor {
    token: String,
}

impl tonic::service::Interceptor for SessionInterceptor {
    fn call(&mut self, mut req: tonic::Request<()>) -> Result<tonic::Request<()>, tonic::Status> {
        if let Ok(val) = self.token.parse() {
            req.metadata_mut().insert("x-session-token", val);
        }
        Ok(req)
    }
}

type AuthChannel = InterceptedService<Channel, SessionInterceptor>;

// ── DaemonClient ──

/// Full-access client for daemon gRPC services.
///
/// Provides high-level methods for chat, voice, commands, media, and more.
/// Only available to plugins with the "client" capability — the SDK creates
/// one automatically after registration if the daemon grants a session token.
///
/// # Example
///
/// ```rust,no_run
/// use astra_plugin_sdk::prelude::*;
/// use std::sync::Arc;
/// use tokio::sync::Mutex;
///
/// struct MyBot {
///     daemon: Arc<Mutex<Option<DaemonClient>>>,
/// }
///
/// #[async_trait]
/// impl PluginCapability for MyBot {
///     fn is_client(&self) -> bool { true }
///
///     async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {
///         *self.daemon.lock().await = Some(client.lock().await.clone());
///     }
/// }
/// ```
#[derive(Clone)]
pub struct DaemonClient {
    core: proto::core_service_client::CoreServiceClient<AuthChannel>,
    chat: proto::chat_service_client::ChatServiceClient<AuthChannel>,
    voice: proto::voice_service_client::VoiceServiceClient<AuthChannel>,
    command: proto::command_service_client::CommandServiceClient<AuthChannel>,
    config: proto::config_service_client::ConfigServiceClient<AuthChannel>,
    media: proto::media_service_client::MediaServiceClient<AuthChannel>,
    monitor: proto::monitor_service_client::MonitorServiceClient<AuthChannel>,
}

impl DaemonClient {
    /// Connect to the daemon and create service clients with session token auth.
    pub(crate) async fn connect(daemon_addr: &str, session_token: String) -> Result<Self> {
        let channel = Channel::from_shared(format!("http://{daemon_addr}"))?
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(90))
            .connect()
            .await
            .context("DaemonClient: failed to connect")?;

        let interceptor = SessionInterceptor { token: session_token };

        Ok(Self {
            core: proto::core_service_client::CoreServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            chat: proto::chat_service_client::ChatServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            voice: proto::voice_service_client::VoiceServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            command: proto::command_service_client::CommandServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            config: proto::config_service_client::ConfigServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            media: proto::media_service_client::MediaServiceClient::with_interceptor(
                channel.clone(), interceptor.clone(),
            ),
            monitor: proto::monitor_service_client::MonitorServiceClient::with_interceptor(
                channel, interceptor,
            ),
        })
    }

    // ===== Core Service =====

    /// Get the current state of the daemon.
    pub async fn get_state(&mut self) -> Result<proto::CoreStateResponse> {
        let resp = self.core.get_state(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    /// Subscribe to real-time daemon events.
    pub async fn subscribe_events(
        &mut self,
    ) -> Result<tonic::Streaming<proto::AstraEvent>> {
        let resp = self.core.subscribe_events(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    // ===== Chat Service =====

    /// Send a message and receive streaming response.
    pub async fn send_message(
        &mut self,
        text: &str,
        voice_enabled: bool,
    ) -> Result<tonic::Streaming<proto::ChatStreamChunk>> {
        self.send_message_full(text, voice_enabled, "", "").await
    }

    /// Send a message with conversation and source IDs.
    pub async fn send_message_full(
        &mut self,
        text: &str,
        voice_enabled: bool,
        source_id: &str,
        conversation_id: &str,
    ) -> Result<tonic::Streaming<proto::ChatStreamChunk>> {
        let resp = self
            .chat
            .send_message(proto::SendMessageRequest {
                text: text.to_string(),
                conversation_id: conversation_id.to_string(),
                voice_enabled,
                attachments: Vec::new(),
                source_id: source_id.to_string(),
                images: Vec::new(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    /// Stop the current AI generation.
    pub async fn stop_generation(&mut self) -> Result<()> {
        self.chat.stop_generation(proto::Empty {}).await?;
        Ok(())
    }

    /// Get chat history for a conversation.
    pub async fn get_history(
        &mut self,
        conversation_id: &str,
        limit: i32,
        offset: i32,
    ) -> Result<proto::GetHistoryResponse> {
        let resp = self
            .chat
            .get_history(proto::GetHistoryRequest {
                conversation_id: conversation_id.to_string(),
                limit,
                offset,
            })
            .await?;
        Ok(resp.into_inner())
    }

    /// Clear chat history for a conversation.
    pub async fn clear_history(&mut self, conversation_id: &str) -> Result<()> {
        self.chat
            .clear_history(proto::ClearHistoryRequest {
                conversation_id: conversation_id.to_string(),
            })
            .await?;
        Ok(())
    }

    /// List all conversations.
    pub async fn list_conversations(&mut self) -> Result<proto::ListConversationsResponse> {
        let resp = self.chat.list_conversations(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    /// Create a new conversation.
    pub async fn create_conversation(&mut self, title: &str) -> Result<proto::Conversation> {
        let resp = self
            .chat
            .create_conversation(proto::CreateConversationRequest {
                title: title.to_string(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    /// Delete a conversation.
    pub async fn delete_conversation(&mut self, conversation_id: &str) -> Result<()> {
        self.chat
            .delete_conversation(proto::DeleteConversationRequest {
                id: conversation_id.to_string(),
            })
            .await?;
        Ok(())
    }

    // ===== Voice Service =====

    /// Speak text using TTS.
    pub async fn speak(&mut self, text: &str, voice_id: &str, interrupt: bool) -> Result<()> {
        self.voice
            .speak(proto::SpeakRequest {
                text: text.to_string(),
                voice_id: voice_id.to_string(),
                interrupt,
            })
            .await?;
        Ok(())
    }

    /// Stop current speech.
    pub async fn stop_speaking(&mut self) -> Result<()> {
        self.voice.stop_speaking(proto::Empty {}).await?;
        Ok(())
    }

    /// Start listening for speech.
    pub async fn start_listening(&mut self) -> Result<()> {
        self.voice.start_listening(proto::Empty {}).await?;
        Ok(())
    }

    /// Stop listening for speech.
    pub async fn stop_listening(&mut self) -> Result<()> {
        self.voice.stop_listening(proto::Empty {}).await?;
        Ok(())
    }

    // ===== Command Service =====

    /// List all commands.
    pub async fn list_commands(&mut self, include_disabled: bool) -> Result<proto::CommandListResponse> {
        let resp = self
            .command
            .list(proto::ListCommandsRequest { include_disabled })
            .await?;
        Ok(resp.into_inner())
    }

    /// Execute a command by ID.
    pub async fn execute_command(
        &mut self,
        id: &str,
        variables: HashMap<String, String>,
    ) -> Result<proto::ExecuteCommandResponse> {
        let resp = self
            .command
            .execute(proto::ExecuteCommandRequest {
                id: id.to_string(),
                variables,
                entry_node_id: String::new(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    // ===== Config Service =====

    /// Get all settings.
    pub async fn get_settings(&mut self) -> Result<proto::SettingsResponse> {
        let resp = self.config.get_settings(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    // ===== Media Service =====

    /// Get current media playback state.
    pub async fn get_media_state(&mut self, session_id: &str) -> Result<proto::MediaState> {
        let resp = self
            .media
            .get_media_state(proto::GetMediaStateRequest {
                session_id: session_id.to_string(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    /// Control media playback.
    pub async fn control_media(
        &mut self,
        action: i32,
        session_id: &str,
    ) -> Result<()> {
        self.media
            .control_media(proto::ControlMediaRequest {
                action,
                session_id: session_id.to_string(),
                seek_position_seconds: 0.0,
            })
            .await?;
        Ok(())
    }

    /// Get all active media sessions.
    pub async fn get_media_sessions(&mut self) -> Result<Vec<proto::MediaSessionInfo>> {
        let resp = self
            .media
            .get_media_sessions(proto::GetMediaSessionsRequest {})
            .await?;
        Ok(resp.into_inner().sessions)
    }

    // ===== Monitor Service =====

    /// Get current system stats (CPU, RAM, GPU, etc.).
    pub async fn get_system_stats(&mut self) -> Result<proto::SystemStats> {
        let resp = self
            .monitor
            .get_system_stats(proto::GetSystemStatsRequest { interval_ms: 0 })
            .await?;
        Ok(resp.into_inner())
    }
}
