// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! DaemonClient — full daemon API access for client-capable plugins.
//!
//! Only reachable from plugins that declare `client = true` in `plugin.toml`
//! and return `true` from [`PluginCapability::is_client`](crate::PluginCapability::is_client).
//! The daemon issues a client session token during registration, and this
//! client injects it as `x-session-token` on every gRPC request.
//!
//! Handlers reach it as [`PluginContext::daemon`](crate::PluginContext::daemon),
//! typed as `Arc<dyn Daemon>` — so a test can substitute a fake, and so nobody
//! has to keep an `Arc<Mutex<Option<DaemonClient>>>` on their struct any more.

use std::collections::HashMap;
use std::time::Duration;

use anyhow::{Context, Result};
use tokio_stream::StreamExt;
use tonic::transport::Channel;

use crate::auth::{AuthChannel, SessionInterceptor};
use crate::context::{Daemon, EventStream, FirehoseStream};
use crate::proto;

// ── DaemonClient ──

/// Full-access client for daemon gRPC services.
///
/// Chat, voice, commands, config, media and monitor. Every method takes `&self`
/// and clones the underlying tonic client for the call, so this is `Clone`, has
/// no interior lock, and can be shared across tasks freely.
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

        let interceptor = SessionInterceptor::new(session_token);

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
}

/// The whole daemon surface, forwarded. See [`Daemon`] for the per-method docs.
#[async_trait::async_trait]
impl Daemon for DaemonClient {
    // ===== Core Service =====

    async fn get_state(&self) -> Result<proto::CoreStateResponse> {
        let resp = self.core.clone().get_state(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    async fn subscribe_events(&self) -> Result<EventStream> {
        let resp = self.core.clone().subscribe_events(proto::Empty {}).await?;
        Ok(Box::pin(
            resp.into_inner().map(|r| r.map_err(anyhow::Error::from)),
        ))
    }

    // ===== Chat Service (event-sourcing API) =====

    async fn submit_user_message(
        &self,
        text: &str,
        conversation_id: &str,
        voice_enabled: bool,
        source_id: &str,
    ) -> Result<proto::SubmitUserMessageResponse> {
        let resp = self
            .chat
            .clone()
            .submit_user_message(proto::SubmitUserMessageRequest {
                text: text.to_string(),
                conversation_id: conversation_id.to_string(),
                voice_enabled,
                source_id: source_id.to_string(),
                images: Vec::new(),
                attachments: Vec::new(),
                // Fields the daemon has that this SDK does not surface yet
                // (documents, and the scope a message is asked in). Their proto3
                // defaults are exactly "not specified", which is what a plugin
                // that never sets them means. Listed via `..Default::default()`
                // so the next daemon-side field is not a compile error here.
                ..Default::default()
            })
            .await?;
        Ok(resp.into_inner())
    }

    async fn subscribe_chat_events(
        &self,
        cursors: HashMap<String, u64>,
    ) -> Result<FirehoseStream> {
        let resp = self
            .chat
            .clone()
            .subscribe_events(proto::SubscribeEventsRequest { cursors })
            .await?;
        Ok(Box::pin(
            resp.into_inner().map(|r| r.map_err(anyhow::Error::from)),
        ))
    }

    async fn stop_generation(&self, conversation_id: &str) -> Result<()> {
        self.chat
            .clone()
            .stop_generation(proto::StopGenerationRequest {
                conversation_id: conversation_id.to_string(),
            })
            .await?;
        Ok(())
    }

    async fn respond_to_confirmation(
        &self,
        request_id: &str,
        allowed: bool,
        allow_like_this: bool,
    ) -> Result<()> {
        self.chat
            .clone()
            .respond_to_confirmation(proto::ConfirmationResponse {
                request_id: request_id.to_string(),
                allowed,
                allow_like_this,
            })
            .await?;
        Ok(())
    }

    async fn list_conversations(&self) -> Result<proto::ListConversationsResponse> {
        let resp = self.chat.clone().list_conversations(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    async fn create_conversation(&self, title: &str) -> Result<proto::Conversation> {
        let resp = self
            .chat
            .clone()
            .create_conversation(proto::CreateConversationRequest {
                title: title.to_string(),
                // See `submit_user_message`: the daemon's newer fields (which
                // client this conversation belongs to, its label, the reasoning
                // knobs) default to "unspecified", which is what a plugin that
                // does not set them means.
                ..Default::default()
            })
            .await?;
        Ok(resp.into_inner())
    }

    async fn delete_conversation(&self, conversation_id: &str) -> Result<()> {
        self.chat
            .clone()
            .delete_conversation(proto::DeleteConversationRequest {
                id: conversation_id.to_string(),
            })
            .await?;
        Ok(())
    }

    async fn clear_conversation(&self, conversation_id: &str) -> Result<()> {
        self.chat
            .clone()
            .clear_conversation(proto::ClearConversationRequest {
                conversation_id: conversation_id.to_string(),
            })
            .await?;
        Ok(())
    }

    // ===== Voice Service =====

    async fn speak(&self, text: &str, voice_id: &str, interrupt: bool) -> Result<()> {
        self.voice
            .clone()
            .speak(proto::SpeakRequest {
                text: text.to_string(),
                voice_id: voice_id.to_string(),
                interrupt,
            })
            .await?;
        Ok(())
    }

    async fn stop_speaking(&self) -> Result<()> {
        self.voice.clone().stop_speaking(proto::Empty {}).await?;
        Ok(())
    }

    async fn start_listening(&self) -> Result<()> {
        self.voice.clone().start_listening(proto::Empty {}).await?;
        Ok(())
    }

    async fn stop_listening(&self) -> Result<()> {
        self.voice.clone().stop_listening(proto::Empty {}).await?;
        Ok(())
    }

    // ===== Command Service =====

    async fn list_commands(&self, include_disabled: bool) -> Result<proto::CommandListResponse> {
        let resp = self
            .command
            .clone()
            .list(proto::ListCommandsRequest { include_disabled })
            .await?;
        Ok(resp.into_inner())
    }

    async fn execute_command(
        &self,
        id: &str,
        variables: HashMap<String, String>,
    ) -> Result<proto::ExecuteCommandResponse> {
        let resp = self
            .command
            .clone()
            .execute(proto::ExecuteCommandRequest {
                id: id.to_string(),
                variables,
                entry_node_id: String::new(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    // ===== Config Service =====

    async fn get_settings(&self) -> Result<proto::SettingsResponse> {
        let resp = self.config.clone().get_settings(proto::Empty {}).await?;
        Ok(resp.into_inner())
    }

    // ===== Media Service =====

    async fn get_media_state(&self, session_id: &str) -> Result<proto::MediaState> {
        let resp = self
            .media
            .clone()
            .get_media_state(proto::GetMediaStateRequest {
                session_id: session_id.to_string(),
            })
            .await?;
        Ok(resp.into_inner())
    }

    async fn control_media(&self, action: i32, session_id: &str) -> Result<()> {
        self.media
            .clone()
            .control_media(proto::ControlMediaRequest {
                action,
                session_id: session_id.to_string(),
                seek_position_seconds: 0.0,
            })
            .await?;
        Ok(())
    }

    async fn get_media_sessions(&self) -> Result<Vec<proto::MediaSessionInfo>> {
        let resp = self
            .media
            .clone()
            .get_media_sessions(proto::GetMediaSessionsRequest {})
            .await?;
        Ok(resp.into_inner().sessions)
    }

    // ===== Monitor Service =====

    async fn get_system_stats(&self) -> Result<proto::SystemStats> {
        let resp = self
            .monitor
            .clone()
            .get_system_stats(proto::GetSystemStatsRequest { interval_ms: 0 })
            .await?;
        Ok(resp.into_inner())
    }
}
