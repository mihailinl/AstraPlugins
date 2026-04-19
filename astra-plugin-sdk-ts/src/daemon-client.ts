/**
 * DaemonClient — full daemon API access for client-capable plugins.
 *
 * Only available to plugins that override `isClient()` to return `true`.
 * The daemon issues a session token during registration, and this client
 * injects it as `x-session-token` metadata on every gRPC request.
 *
 * @example
 * ```ts
 * class MyBot extends Plugin {
 *   isClient() { return true; }
 *
 *   async onDaemonClientReady(client: DaemonClient) {
 *     const state = await client.getState();
 *     console.log("Daemon state:", state.state);
 *   }
 * }
 * ```
 */

import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// Embedded proto for daemon services the DaemonClient needs.
// Kept separate from the plugin proto (proto-loader.ts) for clarity.
const DAEMON_PROTO_CONTENT = `syntax = "proto3";
package astra;

message Empty {}

message Timestamp {
    int64 seconds = 1;
    int32 nanos = 2;
}

// ============ Core Service ============

service CoreService {
    rpc GetState(Empty) returns (CoreStateResponse);
    rpc Start(Empty) returns (Empty);
    rpc Stop(Empty) returns (Empty);
    rpc SubscribeEvents(Empty) returns (stream AstraEvent);
}

message CoreStateResponse {
    int32 state = 1;
    bool stt_ready = 2;
    bool tts_ready = 3;
    bool ai_ready = 4;
    bool authenticated = 5;
    bool needs_oobe = 6;
    string version = 7;
    string startup_status = 8;
}

message AstraEvent {
    Timestamp timestamp = 1;
}

// ============ Chat Service ============

service ChatService {
    rpc SendMessage(SendMessageRequest) returns (stream ChatStreamChunk);
    rpc StopGeneration(StopGenerationRequest) returns (Empty);
    rpc GetHistory(GetHistoryRequest) returns (GetHistoryResponse);
    rpc ClearHistory(ClearHistoryRequest) returns (Empty);
    rpc ListConversations(Empty) returns (ListConversationsResponse);
    rpc CreateConversation(CreateConversationRequest) returns (Conversation);
    rpc DeleteConversation(DeleteConversationRequest) returns (Empty);
}

message SendMessageRequest {
    string text = 1;
    string conversation_id = 2;
    bool voice_enabled = 3;
    repeated string attachments = 4;
    string source_id = 5;
}

message StopGenerationRequest {
    string conversation_id = 1;
}

message ChatStreamChunk {
    oneof chunk {
        string text = 1;
        ToolExecution tool = 2;
        bool done = 3;
        string error = 4;
        string thinking = 6;
        string voice = 7;
    }
    string message_id = 5;
    string conversation_id = 8;
}

message ToolExecution {
    string name = 1;
    string arguments = 2;
    string result = 3;
    bool completed = 4;
}

message GetHistoryRequest {
    string conversation_id = 1;
    int32 limit = 2;
    int32 offset = 3;
}

message GetHistoryResponse {
    repeated ChatMessage messages = 1;
    int32 total_count = 2;
}

message ChatMessage {
    string id = 1;
    string conversation_id = 2;
    int32 role = 3;
    string content = 4;
    Timestamp created_at = 6;
}

message ClearHistoryRequest {
    string conversation_id = 1;
}

message ListConversationsResponse {
    repeated Conversation conversations = 1;
}

message Conversation {
    string id = 1;
    string title = 2;
    Timestamp created_at = 3;
    Timestamp updated_at = 4;
    int32 message_count = 5;
}

message CreateConversationRequest {
    string title = 1;
}

message DeleteConversationRequest {
    string id = 1;
}

// ============ Voice Service ============

service VoiceService {
    rpc StartListening(Empty) returns (Empty);
    rpc StopListening(Empty) returns (Empty);
    rpc Speak(SpeakRequest) returns (Empty);
    rpc StopSpeaking(Empty) returns (Empty);
}

message SpeakRequest {
    string text = 1;
    string voice_id = 2;
    bool interrupt = 3;
}

// ============ Command Service ============

service CommandService {
    rpc List(ListCommandsRequest) returns (CommandListResponse);
    rpc Execute(ExecuteCommandRequest) returns (ExecuteCommandResponse);
}

message ListCommandsRequest {
    bool include_disabled = 1;
}

message CommandListResponse {
    repeated CommandDefinition commands = 1;
}

message CommandDefinition {
    string id = 1;
    string name = 2;
    bool enabled = 5;
    string description = 8;
    repeated string tags = 9;
}

message ExecuteCommandRequest {
    string id = 1;
    map<string, string> variables = 2;
    string entry_node_id = 3;
}

message ExecuteCommandResponse {
    bool success = 1;
    string output = 2;
    string error = 3;
}

// ============ Config Service ============

service ConfigService {
    rpc GetSettings(Empty) returns (SettingsResponse);
}

message SettingsResponse {
    string settings_json = 1;
}

// ============ Media Service ============

service MediaService {
    rpc GetMediaState(GetMediaStateRequest) returns (MediaState);
    rpc ControlMedia(ControlMediaRequest) returns (Empty);
    rpc GetMediaSessions(GetMediaSessionsRequest) returns (GetMediaSessionsResponse);
}

message GetMediaStateRequest {
    string session_id = 1;
}

message MediaState {
    string title = 1;
    string artist = 2;
    string album = 3;
    int32 playback_status = 4;
    double position_seconds = 5;
    double duration_seconds = 6;
    bytes thumbnail = 7;
    string session_id = 8;
}

message ControlMediaRequest {
    int32 action = 1;
    string session_id = 2;
    double seek_position_seconds = 3;
}

message GetMediaSessionsRequest {}

message MediaSessionInfo {
    string session_id = 1;
    string source = 2;
    string title = 3;
    string artist = 4;
}

message GetMediaSessionsResponse {
    repeated MediaSessionInfo sessions = 1;
}

// ============ Monitor Service ============

service MonitorService {
    rpc GetSystemStats(GetSystemStatsRequest) returns (SystemStats);
}

message GetSystemStatsRequest {
    int32 interval_ms = 1;
}

message SystemStats {
    double cpu_usage = 1;
    double memory_used_gb = 2;
    double memory_total_gb = 3;
}
`;

// Load the daemon proto
function loadDaemonProto(): any {
  const tmpPath = path.join(os.tmpdir(), `astra-daemon-${process.pid}.proto`);
  fs.writeFileSync(tmpPath, DAEMON_PROTO_CONTENT);

  const packageDefinition = protoLoader.loadSync(tmpPath, {
    keepCase: false,
    longs: String,
    enums: String,
    defaults: true,
    oneofs: true,
  });

  try {
    fs.unlinkSync(tmpPath);
  } catch {
    // Ignore cleanup errors
  }

  const descriptor = grpc.loadPackageDefinition(packageDefinition) as any;
  return descriptor.astra;
}

export class DaemonClient {
  private metadata: grpc.Metadata;
  private coreClient: any;
  private chatClient: any;
  private voiceClient: any;
  private commandClient: any;
  private configClient: any;
  private mediaClient: any;
  private monitorClient: any;

  constructor(
    private daemonAddr: string,
    sessionToken: string
  ) {
    this.metadata = new grpc.Metadata();
    this.metadata.set("x-session-token", sessionToken);
  }

  /** Connect to the daemon and create service clients. */
  async connect(): Promise<void> {
    const proto = loadDaemonProto();
    const creds = grpc.credentials.createInsecure();

    this.coreClient = new proto.CoreService(this.daemonAddr, creds);
    this.chatClient = new proto.ChatService(this.daemonAddr, creds);
    this.voiceClient = new proto.VoiceService(this.daemonAddr, creds);
    this.commandClient = new proto.CommandService(this.daemonAddr, creds);
    this.configClient = new proto.ConfigService(this.daemonAddr, creds);
    this.mediaClient = new proto.MediaService(this.daemonAddr, creds);
    this.monitorClient = new proto.MonitorService(this.daemonAddr, creds);
  }

  // ===== Core Service =====

  /** Get the current state of the daemon. */
  getState(): Promise<any> {
    return this._unary(this.coreClient, "GetState", {});
  }

  /** Subscribe to real-time daemon events. Returns a readable stream. */
  subscribeEvents(): grpc.ClientReadableStream<any> {
    return this.coreClient.SubscribeEvents({}, this.metadata);
  }

  // ===== Chat Service (event-sourcing API) =====

  /** Submit a user message. Daemon auto-creates a conversation when
   * `conversationId` is empty, drives the AI turn asynchronously, and emits
   * every event through `subscribeChatEvents`. */
  submitUserMessage(
    text: string,
    opts?: {
      conversationId?: string;
      voiceEnabled?: boolean;
      sourceId?: string;
    }
  ): Promise<any> {
    return this._unary(this.chatClient, "SubmitUserMessage", {
      text,
      conversationId: opts?.conversationId ?? "",
      voiceEnabled: opts?.voiceEnabled ?? false,
      sourceId: opts?.sourceId ?? "",
    });
  }

  /** Subscribe to the chat firehose — events from every conversation. */
  subscribeChatEvents(
    cursors: Record<string, number> = {}
  ): grpc.ClientReadableStream<any> {
    return this.chatClient.SubscribeEvents({ cursors }, this.metadata);
  }

  /** Stop AI generation. Empty `conversationId` cancels every active turn. */
  stopGeneration(conversationId: string = ""): Promise<void> {
    return this._unary(this.chatClient, "StopGeneration", { conversationId });
  }

  /** Respond to a pending tool confirmation request. */
  respondToConfirmation(
    requestId: string,
    allowed: boolean,
    allowLikeThis: boolean = false
  ): Promise<void> {
    return this._unary(this.chatClient, "RespondToConfirmation", {
      requestId,
      allowed,
      allowLikeThis,
    });
  }

  listConversations(): Promise<any> {
    return this._unary(this.chatClient, "ListConversations", {});
  }

  createConversation(title: string): Promise<any> {
    return this._unary(this.chatClient, "CreateConversation", { title });
  }

  deleteConversation(conversationId: string): Promise<void> {
    return this._unary(this.chatClient, "DeleteConversation", {
      id: conversationId,
    });
  }

  clearConversation(conversationId: string): Promise<void> {
    return this._unary(this.chatClient, "ClearConversation", { conversationId });
  }

  // ===== Voice Service =====

  /** Speak text using TTS. */
  speak(
    text: string,
    voiceId: string = "",
    interrupt: boolean = false
  ): Promise<void> {
    return this._unary(this.voiceClient, "Speak", {
      text,
      voiceId,
      interrupt,
    });
  }

  /** Stop current speech. */
  stopSpeaking(): Promise<void> {
    return this._unary(this.voiceClient, "StopSpeaking", {});
  }

  /** Start listening for speech. */
  startListening(): Promise<void> {
    return this._unary(this.voiceClient, "StartListening", {});
  }

  /** Stop listening for speech. */
  stopListening(): Promise<void> {
    return this._unary(this.voiceClient, "StopListening", {});
  }

  // ===== Command Service =====

  /** List all commands. */
  listCommands(includeDisabled: boolean = false): Promise<any> {
    return this._unary(this.commandClient, "List", { includeDisabled });
  }

  /** Execute a command by ID. */
  executeCommand(
    id: string,
    variables?: Record<string, string>
  ): Promise<any> {
    return this._unary(this.commandClient, "Execute", {
      id,
      variables: variables ?? {},
    });
  }

  // ===== Config Service =====

  /** Get all settings. */
  getSettings(): Promise<any> {
    return this._unary(this.configClient, "GetSettings", {});
  }

  // ===== Media Service =====

  /** Get current media playback state. */
  getMediaState(sessionId: string = ""): Promise<any> {
    return this._unary(this.mediaClient, "GetMediaState", { sessionId });
  }

  /** Control media playback. action: 0=play_pause, 1=next, 2=prev, 3=stop. */
  controlMedia(action: number, sessionId: string = ""): Promise<void> {
    return this._unary(this.mediaClient, "ControlMedia", {
      action,
      sessionId,
    });
  }

  /** Get all active media sessions. */
  getMediaSessions(): Promise<any> {
    return this._unary(this.mediaClient, "GetMediaSessions", {});
  }

  // ===== Monitor Service =====

  /** Get current system stats (CPU, RAM, GPU, etc.). */
  getSystemStats(): Promise<any> {
    return this._unary(this.monitorClient, "GetSystemStats", {
      intervalMs: 0,
    });
  }

  // ===== Internal =====

  private _unary(client: any, method: string, request: any): Promise<any> {
    return new Promise((resolve, reject) => {
      client[method](
        request,
        this.metadata,
        (err: grpc.ServiceError | null, response: any) => {
          if (err) reject(err);
          else resolve(response);
        }
      );
    });
  }
}
