//! Plugin runner — handles CLI args, gRPC server setup, registration, and shutdown.

use std::net::SocketAddr;
use std::sync::Arc;

use anyhow::{Context, Result};
use clap::Parser;
use tokio::net::TcpListener;
use tokio::signal;
use tonic::transport::Server;
use tracing::info;

use crate::capability::PluginCapability;
use crate::host_client::HostClient;
use crate::proto;
use crate::proto::plugin_capability_service_server::PluginCapabilityServiceServer;

/// CLI arguments passed by the Astra daemon when spawning a plugin.
#[derive(Parser, Debug)]
#[command(name = "astra-plugin")]
struct Args {
    /// Daemon gRPC address (host:port).
    #[arg(long)]
    daemon_addr: String,

    /// Plugin ID (from manifest).
    #[arg(long)]
    plugin_id: String,
}

/// Run a plugin. Call this from your `main()`.
///
/// This function:
/// 1. Parses CLI args (`--daemon-addr`, `--plugin-id`)
/// 2. Starts a gRPC server on an OS-assigned port
/// 3. Registers with the daemon
/// 4. Serves PluginCapabilityService until shutdown
pub async fn run<P: PluginCapability>(plugin: P) -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let args = Args::parse();
    info!(
        "Starting plugin '{}', connecting to daemon at {}",
        args.plugin_id, args.daemon_addr
    );

    let plugin = Arc::new(plugin);

    // Bind to OS-assigned port (port 0)
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .context("Failed to bind to a local port")?;
    let local_addr: SocketAddr = listener.local_addr()?;
    let port = local_addr.port();
    info!("Plugin gRPC server listening on port {}", port);

    // Connect to daemon and register
    let mut host = HostClient::connect(&args.daemon_addr, args.plugin_id.clone()).await?;

    // Determine capabilities from the plugin implementation
    let capabilities = discover_capabilities(&*plugin).await;
    info!("Registering with capabilities: {:?}", capabilities);

    let reg_response = host.register(port, capabilities).await?;
    if !reg_response.success {
        anyhow::bail!("Registration failed: {}", reg_response.error);
    }
    info!(
        "Registered successfully. Daemon version: {}",
        reg_response.daemon_version
    );

    // Pass host client to the plugin so it can call daemon APIs
    let host = Arc::new(tokio::sync::Mutex::new(host));
    plugin.set_host(host.clone()).await;

    // Pass initial config to the plugin
    if !reg_response.config_json.is_empty() {
        plugin.on_config_changed(&reg_response.config_json).await;
    }

    // Start event subscription if plugin wants events
    let event_types = plugin.subscribed_events();
    if !event_types.is_empty() {
        info!("Subscribing to events: {:?}", event_types);
        let plugin_for_events = plugin.clone();
        let host_for_events = host.clone();
        tokio::spawn(async move {
            let stream = {
                let mut h = host_for_events.lock().await;
                h.subscribe_events(event_types).await
            };
            match stream {
                Ok(mut stream) => {
                    use tokio_stream::StreamExt;
                    while let Some(msg) = stream.next().await {
                        match msg {
                            Ok(event) => {
                                plugin_for_events
                                    .on_event(&event.event_type, &event.payload_json)
                                    .await;
                            }
                            Err(e) => {
                                tracing::warn!("Event stream error: {}", e);
                                break;
                            }
                        }
                    }
                    info!("Event subscription stream ended");
                }
                Err(e) => {
                    tracing::warn!("Event subscription failed: {}", e);
                }
            }
        });
    }

    // Build gRPC service
    let svc = CapabilityServiceImpl {
        plugin: plugin.clone(),
    };
    let server = Server::builder()
        .add_service(PluginCapabilityServiceServer::new(svc))
        .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(listener));

    // Run server until Ctrl+C or process kill
    let server_handle = tokio::spawn(server);

    // Wait for shutdown signal
    signal::ctrl_c().await.ok();
    info!("Shutdown signal received");

    plugin.on_shutdown().await;
    server_handle.abort();

    Ok(())
}

/// Discover which capabilities the plugin implements by probing methods.
/// Returns capability strings matching what the daemon expects.
async fn discover_capabilities<P: PluginCapability>(plugin: &P) -> Vec<String> {
    let mut caps = Vec::new();

    if !plugin.list_tools().await.is_empty() {
        caps.push("tools".into());
    }
    if !plugin.tts_voices().await.is_empty() {
        caps.push("tts".into());
    }
    if !plugin.stt_languages().await.is_empty() {
        caps.push("stt".into());
    }
    let (models, _) = plugin.ai_models().await;
    if !models.is_empty() {
        caps.push("ai_provider".into());
    }
    if !plugin.action_types().await.is_empty() {
        caps.push("actions".into());
    }
    if !plugin.trigger_types().await.is_empty() {
        caps.push("triggers".into());
    }
    if !plugin.ui_panels().await.is_empty() {
        caps.push("ui_panels".into());
    }

    caps
}

// ── gRPC service implementation that delegates to the PluginCapability trait ──

struct CapabilityServiceImpl<P: PluginCapability> {
    plugin: Arc<P>,
}

#[tonic::async_trait]
impl<P: PluginCapability> proto::plugin_capability_service_server::PluginCapabilityService
    for CapabilityServiceImpl<P>
{
    // ── Tools ──

    async fn list_tools(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginToolListResponse>, tonic::Status> {
        let tools = self.plugin.list_tools().await;
        Ok(tonic::Response::new(proto::PluginToolListResponse {
            tools: tools.into_iter().map(Into::into).collect(),
        }))
    }

    async fn call_tool(
        &self,
        request: tonic::Request<proto::PluginCallToolRequest>,
    ) -> Result<tonic::Response<proto::PluginCallToolResponse>, tonic::Status> {
        let req = request.into_inner();
        let result = self.plugin.call_tool(&req.tool_name, &req.arguments_json).await;
        Ok(tonic::Response::new(result.into()))
    }

    // ── TTS ──

    async fn tts_synthesize(
        &self,
        request: tonic::Request<proto::PluginTtsSynthesizeRequest>,
    ) -> Result<tonic::Response<proto::PluginTtsSynthesizeResponse>, tonic::Status> {
        let req = request.into_inner();
        match self
            .plugin
            .tts_synthesize(&req.text, &req.voice_id, req.speed, req.pitch)
            .await
        {
            Ok(audio) => Ok(tonic::Response::new(audio.into())),
            Err(e) => Err(tonic::Status::internal(e.to_string())),
        }
    }

    type TtsSynthesizeStreamStream = std::pin::Pin<
        Box<dyn tokio_stream::Stream<Item = Result<proto::PluginAudioChunk, tonic::Status>> + Send>,
    >;

    async fn tts_synthesize_stream(
        &self,
        _request: tonic::Request<proto::PluginTtsSynthesizeRequest>,
    ) -> Result<tonic::Response<Self::TtsSynthesizeStreamStream>, tonic::Status> {
        Err(tonic::Status::unimplemented("Streaming TTS not implemented"))
    }

    async fn tts_list_voices(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginTtsVoicesResponse>, tonic::Status> {
        let voices = self.plugin.tts_voices().await;
        Ok(tonic::Response::new(proto::PluginTtsVoicesResponse {
            voices: voices.into_iter().map(Into::into).collect(),
        }))
    }

    // ── STT ──

    type SttProcessStream = std::pin::Pin<
        Box<dyn tokio_stream::Stream<Item = Result<proto::PluginSttEvent, tonic::Status>> + Send>,
    >;

    async fn stt_process(
        &self,
        _request: tonic::Request<tonic::Streaming<proto::PluginAudioChunk>>,
    ) -> Result<tonic::Response<Self::SttProcessStream>, tonic::Status> {
        Err(tonic::Status::unimplemented("STT not implemented"))
    }

    async fn stt_get_languages(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginSttLanguagesResponse>, tonic::Status> {
        let langs = self.plugin.stt_languages().await;
        Ok(tonic::Response::new(proto::PluginSttLanguagesResponse {
            languages: langs,
        }))
    }

    // ── AI Provider ──

    type AiCompleteStream = std::pin::Pin<
        Box<
            dyn tokio_stream::Stream<Item = Result<proto::PluginAiStreamChunk, tonic::Status>>
                + Send,
        >,
    >;

    async fn ai_complete(
        &self,
        _request: tonic::Request<proto::PluginAiCompleteRequest>,
    ) -> Result<tonic::Response<Self::AiCompleteStream>, tonic::Status> {
        Err(tonic::Status::unimplemented("AI provider not implemented"))
    }

    async fn ai_get_models(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginAiModelsResponse>, tonic::Status> {
        let (models, default) = self.plugin.ai_models().await;
        Ok(tonic::Response::new(proto::PluginAiModelsResponse {
            models: models.into_iter().map(Into::into).collect(),
            default_model: default,
        }))
    }

    // ── Actions ──

    async fn execute_action(
        &self,
        request: tonic::Request<proto::PluginExecuteActionRequest>,
    ) -> Result<tonic::Response<proto::PluginExecuteActionResponse>, tonic::Status> {
        let req = request.into_inner();
        let result = self
            .plugin
            .execute_action(&req.action_type, &req.params_json)
            .await;
        Ok(tonic::Response::new(result.into()))
    }

    async fn get_plugin_action_types(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginActionTypesResponse>, tonic::Status> {
        let types = self.plugin.action_types().await;
        Ok(tonic::Response::new(proto::PluginActionTypesResponse {
            types,
        }))
    }

    // ── Triggers ──

    async fn get_plugin_trigger_types(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginTriggerTypesResponse>, tonic::Status> {
        let types = self.plugin.trigger_types().await;
        Ok(tonic::Response::new(proto::PluginTriggerTypesResponse {
            types,
        }))
    }

    // ── UI ──

    async fn get_ui_panels(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginUiPanelsResponse>, tonic::Status> {
        let panels = self.plugin.ui_panels().await;
        Ok(tonic::Response::new(proto::PluginUiPanelsResponse {
            panels,
        }))
    }

    // ── Lifecycle ──

    async fn on_config_changed(
        &self,
        request: tonic::Request<proto::PluginConfigChangedMsg>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        let config_json = request.into_inner().config_json;
        self.plugin.on_config_changed(&config_json).await;
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn on_active_triggers(
        &self,
        request: tonic::Request<proto::PluginActiveTriggersMsg>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        let types = request.into_inner().trigger_types;
        self.plugin.on_active_triggers(types).await;
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn shutdown(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        info!("Shutdown requested by daemon");
        self.plugin.on_shutdown().await;
        // Give a moment for the response to send, then exit
        tokio::spawn(async {
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            std::process::exit(0);
        });
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn health_check(
        &self,
        _request: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginHealthResponse>, tonic::Status> {
        let (healthy, status) = self.plugin.health_check().await;
        Ok(tonic::Response::new(proto::PluginHealthResponse {
            healthy,
            status,
        }))
    }
}
