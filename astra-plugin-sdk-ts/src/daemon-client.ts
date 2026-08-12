// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * DaemonClient — full daemon API access for client-capable plugins.
 *
 * Only available to plugins that override `isClient()` to return `true`.
 * The daemon issues a session token during registration, and this client
 * injects it as `x-session-token` metadata on every gRPC request.
 *
 * Every stub is built from the descriptor generated out of the repo's canonical
 * `proto/plugin.proto` (see `proto-loader.ts`). It used to be built from a
 * second inline copy of the protocol that predated the chat event-sourcing
 * migration, so `SubmitUserMessage`, `SubscribeEvents`, `RespondToConfirmation`
 * and `ClearConversation` were `undefined` on the stub and every call threw a
 * bare `TypeError`. `connect()` now asserts up front that each stub really
 * exposes the methods this class calls.
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
import { service } from "./proto-loader.js";
import { assertClientContract } from "./service-contract.js";
import { SESSION_TOKEN_HEADER } from "./generated/wire.js";

/** Methods this class calls, per service. Checked against the descriptor in `connect()`. */
const REQUIRED_METHODS: Record<string, readonly string[]> = {
  CoreService: ["GetState", "SubscribeEvents"],
  ChatService: [
    "SubmitUserMessage",
    "SubscribeEvents",
    "StopGeneration",
    "RespondToConfirmation",
    "ListConversations",
    "CreateConversation",
    "DeleteConversation",
    "ClearConversation",
  ],
  VoiceService: ["Speak", "StopSpeaking", "StartListening", "StopListening"],
  CommandService: ["List", "Execute"],
  ConfigService: ["GetSettings"],
  MediaService: ["GetMediaState", "ControlMedia", "GetMediaSessions"],
  MonitorService: ["GetSystemStats"],
};

type Stub = grpc.Client & Record<string, Function>;

export class DaemonClient {
  private metadata: grpc.Metadata;
  private coreClient!: Stub;
  private chatClient!: Stub;
  private voiceClient!: Stub;
  private commandClient!: Stub;
  private configClient!: Stub;
  private mediaClient!: Stub;
  private monitorClient!: Stub;

  constructor(
    private daemonAddr: string,
    sessionToken: string
  ) {
    if (!sessionToken) {
      throw new Error(
        "DaemonClient requires the client_session_token from PluginRegisterResponse; " +
          "without it every daemon RPC is rejected as `unauthenticated`."
      );
    }
    this.metadata = new grpc.Metadata();
    this.metadata.set(SESSION_TOKEN_HEADER, sessionToken);
  }

  /** Connect to the daemon and create service clients. */
  async connect(): Promise<void> {
    const creds = grpc.credentials.createInsecure();
    const stubs: Record<string, Stub> = {};
    for (const name of Object.keys(REQUIRED_METHODS)) {
      const stub = new (service(name))(this.daemonAddr, creds) as Stub;
      assertClientContract(name, stub, REQUIRED_METHODS[name]);
      stubs[name] = stub;
    }

    this.coreClient = stubs.CoreService;
    this.chatClient = stubs.ChatService;
    this.voiceClient = stubs.VoiceService;
    this.commandClient = stubs.CommandService;
    this.configClient = stubs.ConfigService;
    this.mediaClient = stubs.MediaService;
    this.monitorClient = stubs.MonitorService;
  }

  /** Close every underlying channel. */
  close(): void {
    for (const stub of [
      this.coreClient,
      this.chatClient,
      this.voiceClient,
      this.commandClient,
      this.configClient,
      this.mediaClient,
      this.monitorClient,
    ]) {
      stub?.close();
    }
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

  private _unary(client: Stub, method: string, request: any): Promise<any> {
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
