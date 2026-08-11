// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Level 2 — the wire harness.
 *
 * A real `grpc.Server` serving `PluginHostService` on loopback, a real
 * `Register` handshake with a real spawn token, a real session-token check on
 * every later call, and a real `PluginCapabilityService` client dialling the
 * port the plugin bound. The plugin under test is the plugin: `run()` is what
 * starts it.
 *
 * Everything level 1 cannot see lives here, and each item is a bug this repo
 * has actually shipped:
 *
 * - **Handler registration.** grpc-js drops an implementation key the service
 *   definition does not know and answers a definition method the
 *   implementation lacks with `UNIMPLEMENTED`, both without a word. Three hooks
 *   were registered against a stale descriptor and never called for a release.
 * - **Descriptor mismatch.** `stub.SubmitUserMessage` on a stale descriptor is
 *   `undefined`, and calling it is a bare `TypeError` from inside grpc-js.
 * - **The session-token interceptor.** No SDK sent `x-session-token` for three
 *   releases, so every host RPC but `Register` was `unauthenticated` at
 *   runtime and green in every unit test.
 * - **`keepCase` casing.** `config_fields` is dropped by protobufjs without a
 *   word; the daemon sees an empty list. Only real encoding catches it.
 * - **500-slot back-pressure.** The SDK's inbound queue is bounded at
 *   `STT_AUDIO_CHANNEL_CAPACITY`; a smaller one silently truncated every
 *   utterance. Over a real bidi stream, with the real fixture, the whole
 *   utterance either arrives or it does not.
 */

import * as grpc from "@grpc/grpc-js";
import { randomBytes } from "node:crypto";
import type { Plugin } from "../plugin.js";
import { service } from "../proto-loader.js";
import { addServiceChecked, type HandlerMap } from "../service-contract.js";
import { PROTOCOL_VERSION } from "../protocol.js";
import { PLUGIN_TOKEN_HEADER } from "../capability-auth.js";
import { removeFatalHandlers, restoreConsole } from "../logging.js";
import type { AudioChunk, SttEvent, ToolDef, ToolResult } from "../types.js";
import type { Testable } from "./harness.js";

/** Header the daemon's auth interceptor reads on every host RPC but `Register`. */
const SESSION_TOKEN_HEADER = "x-session-token";

/** What the plugin sent to `Register`. */
export interface RegisterRecord {
  pluginId: string;
  port: number;
  capabilities: string[];
  authToken: string;
  protocolVersion: number;
  sdkName: string;
  sdkVersion: string;
}

/** One host RPC the plugin made, with the token it presented. */
export interface HostCall {
  method: string;
  request: Record<string, unknown>;
  sessionToken: string | undefined;
}

/** How the mock daemon should answer `Register`. */
export interface MockDaemonOptions {
  /** Config JSON handed back at registration. */
  config?: Record<string, unknown>;
  /** Language handed back at registration. */
  language?: string;
  /** Daemon version string. */
  daemonVersion?: string;
  /** Protocol the daemon claims. Lower it to test the mismatch path. */
  protocolVersion?: number;
  /** The daemon's protocol floor. */
  minSupportedProtocol?: number;
  /** Refuse the registration with this error. */
  refuseWith?: { error: string; code?: string; hint?: string };
  /**
   * Whether to demand `x-session-token` on non-`Register` calls. On by default:
   * the real daemon has demanded it since SECURITY(B1), and an SDK that does
   * not send it is broken in production and green everywhere else.
   */
  requireSessionToken?: boolean;
}

function plugin(target: Testable): Plugin {
  return "instance" in target ? target.instance : target;
}

function unauthenticated(details: string): grpc.ServiceError {
  return Object.assign(new Error(details), {
    code: grpc.status.UNAUTHENTICATED,
    details,
    metadata: new grpc.Metadata(),
  }) as grpc.ServiceError;
}

/** A plugin running against the mock daemon, dialled over real gRPC. */
export class WirePlugin {
  constructor(
    readonly plugin: Plugin,
    /** The `PluginCapabilityService` stub, already carrying the spawn token. */
    private readonly stub: grpc.Client & Record<string, Function>,
    private readonly metadata: grpc.Metadata,
    /** The port the plugin's own server bound. */
    readonly port: number
  ) {}

  /** Any unary capability RPC, by its proto name. */
  unary<T = Record<string, unknown>>(method: string, request: object = {}): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const fn = this.stub[method];
      if (typeof fn !== "function") {
        reject(new Error(`PluginCapabilityService stub has no method ${method}`));
        return;
      }
      fn.call(this.stub, request, this.metadata, (err: grpc.ServiceError | null, res: T) => {
        if (err) reject(err);
        else resolve(res);
      });
    });
  }

  /** Any unary RPC, without the spawn token — for testing the guard. */
  unaryUnauthenticated<T = Record<string, unknown>>(method: string, request: object = {}): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.stub[method].call(
        this.stub,
        request,
        new grpc.Metadata(),
        (err: grpc.ServiceError | null, res: T) => {
          if (err) reject(err);
          else resolve(res);
        }
      );
    });
  }

  async listTools(): Promise<ToolDef[]> {
    const res = await this.unary<{ tools: ToolDef[] }>("ListTools");
    return res.tools ?? [];
  }

  callTool(toolName: string, args: Record<string, unknown> | string = {}): Promise<ToolResult> {
    return this.unary<ToolResult>("CallTool", {
      toolName,
      argumentsJson: typeof args === "string" ? args : JSON.stringify(args),
    });
  }

  healthCheck(): Promise<{ healthy: boolean; status: string }> {
    return this.unary("HealthCheck");
  }

  /** Any server-streaming capability RPC. */
  serverStream<T = Record<string, unknown>>(method: string, request: object = {}): Promise<T[]> {
    return new Promise<T[]>((resolve, reject) => {
      const stream = this.stub[method].call(this.stub, request, this.metadata) as grpc.ClientReadableStream<T>;
      const out: T[] = [];
      stream.on("data", (m: T) => out.push(m));
      stream.on("error", reject);
      stream.on("end", () => resolve(out));
    });
  }

  /**
   * Drive `SttProcess` over the real bidi stream.
   *
   * The point of doing it here rather than at level 1 is encoding: the audio
   * makes a round trip through protobuf, so a chunk lost to back-pressure, a
   * `sample_rate` that did not survive `keepCase`, or an options message on the
   * wrong chunk all show up as different bytes coming back.
   */
  sttProcess(chunks: readonly AudioChunk[]): Promise<SttEvent[]> {
    return new Promise<SttEvent[]>((resolve, reject) => {
      const call = this.stub.SttProcess.call(this.stub, this.metadata) as grpc.ClientDuplexStream<
        unknown,
        SttEvent
      >;
      const events: SttEvent[] = [];
      call.on("data", (e: SttEvent) => events.push(e));
      call.on("error", reject);
      call.on("end", () => resolve(events));

      let i = 0;
      const writeNext = (): void => {
        while (i < chunks.length) {
          const c = chunks[i++];
          const message = {
            data: c.data,
            isLast: c.isLast ?? false,
            sampleRate: c.sampleRate ?? 0,
            options: c.options,
          };
          if (!call.write(message)) {
            // Real back-pressure from the transport. Wait for drain rather than
            // buffering the whole utterance in the client, which is exactly the
            // shortcut that hides a truncating receiver.
            call.once("drain", writeNext);
            return;
          }
        }
        call.end();
      };
      writeNext();
    });
  }

  /**
   * Close the client channel and stop the plugin.
   *
   * Both halves matter: the plugin's own listening socket and its host channel
   * keep the process alive, so a suite that forgot this hangs after its last
   * green test instead of exiting — a failure mode that looks like an infinite
   * loop in the code under test.
   */
  async close(): Promise<void> {
    this.stub.close();
    await this.plugin.stopServing();
  }
}

export class MockDaemon {
  private readonly server = new grpc.Server();
  private readonly hostCalls: HostCall[] = [];
  private readonly eventStreams: grpc.ServerWritableStream<unknown, unknown>[] = [];
  private readonly launched: WirePlugin[] = [];
  private registerResolve: ((r: RegisterRecord) => void) | null = null;
  private consoleWasBridged = false;

  /** Registrations seen, in order. */
  readonly registrations: RegisterRecord[] = [];
  /** The spawn token the daemon "passed on argv". The plugin must echo it. */
  readonly authToken = randomBytes(24).toString("hex");
  /** The per-plugin session token issued at registration. */
  readonly sessionToken = randomBytes(24).toString("hex");
  /** `127.0.0.1:<port>` once started. */
  address = "";
  /** Chunks the next `SendChatMessage` streams back. */
  chatReply: { text?: string; done?: boolean; error?: string }[] = [
    { text: "ok" },
    { done: true },
  ];

  private constructor(private readonly opts: MockDaemonOptions) {}

  /** Bind the mock daemon on an OS-assigned loopback port. */
  static async start(opts: MockDaemonOptions = {}): Promise<MockDaemon> {
    const daemon = new MockDaemon(opts);
    addServiceChecked(
      daemon.server,
      "PluginHostService",
      service("PluginHostService").service,
      daemon.handlers()
    );
    const port = await new Promise<number>((resolve, reject) => {
      daemon.server.bindAsync("127.0.0.1:0", grpc.ServerCredentials.createInsecure(), (err, p) => {
        if (err) reject(err);
        else resolve(p);
      });
    });
    daemon.address = `127.0.0.1:${port}`;
    return daemon;
  }

  // ── what the test reads ──

  /** Every host RPC the plugin made, in order. */
  calls(): readonly HostCall[] {
    return this.hostCalls;
  }
  /** Host RPCs of one kind. */
  callsTo(method: string): readonly HostCall[] {
    return this.hostCalls.filter((c) => c.method === method);
  }
  /** Log lines the plugin sent over `PluginLog`. */
  logs(): { level: string; message: string }[] {
    return this.callsTo("PluginLog").map((c) => ({
      level: String(c.request.level ?? ""),
      message: String(c.request.message ?? ""),
    }));
  }
  /** Triggers fired over `FireTrigger`. */
  firedTriggers(): { triggerType: string; payloadJson: string }[] {
    return this.callsTo("FireTrigger").map((c) => ({
      triggerType: String(c.request.triggerType ?? ""),
      payloadJson: String(c.request.payloadJson ?? ""),
    }));
  }
  /** Variables published over `SetVariable`. */
  variables(): { name: string; value: string; scope: string }[] {
    return this.callsTo("SetVariable").map((c) => ({
      name: String(c.request.name ?? ""),
      value: String(c.request.value ?? ""),
      scope: String(c.request.scope ?? ""),
    }));
  }

  /** Push an event to every subscribed plugin. */
  emitEvent(eventType: string, payload: Record<string, unknown> = {}): void {
    for (const stream of this.eventStreams) {
      stream.write({ eventType, payloadJson: JSON.stringify(payload) });
    }
  }

  // ── launching a plugin ──

  /**
   * Start `target` against this daemon and wait for it to register.
   *
   * `process.argv` is swapped for the duration of `run()` — the same argv the
   * daemon spawns a plugin with, including the `--capabilities` the daemon
   * added in Phase 4, so an argument parser that chokes on an unknown flag
   * fails here.
   */
  async launch(
    target: Testable,
    opts: { pluginId?: string; extraArgs?: string[]; timeoutMs?: number } = {}
  ): Promise<WirePlugin> {
    const instance = plugin(target);
    const pluginId = opts.pluginId ?? "test-plugin";

    const registered = new Promise<RegisterRecord>((resolve, reject) => {
      this.registerResolve = resolve;
      const timer = setTimeout(
        () => reject(new Error(`plugin did not register within ${opts.timeoutMs ?? 10000} ms`)),
        opts.timeoutMs ?? 10000
      );
      if (typeof timer.unref === "function") timer.unref();
    });

    // The plugin must not take the test runner down with it.
    instance.exitProcess = (code: number) => {
      throw new Error(`plugin called process.exit(${code}) during a level-2 test`);
    };

    const savedArgv = process.argv;
    process.argv = [
      savedArgv[0],
      savedArgv[1],
      `--daemon-addr=${this.address}`,
      `--plugin-id=${pluginId}`,
      `--auth-token=${this.authToken}`,
      // The daemon passes this and no SDK reads it. Python's argparse used to
      // EXIT on it, which killed every plugin of that era; keep it here so the
      // day an SDK starts parsing argv strictly, a test says so.
      "--capabilities=tools,actions",
      ...(opts.extraArgs ?? []),
    ];
    try {
      instance.run();
    } finally {
      process.argv = savedArgv;
    }
    // `run()` installs both process-wide hooks synchronously. Take the fatal
    // handlers back immediately: an in-process plugin that installed
    // `uncaughtException` would swallow the test runner's own failures and exit
    // the suite with the plugin's crash code.
    removeFatalHandlers();
    this.consoleWasBridged = true;

    const record = await registered;
    // `Register` answering is not the plugin being ready: the config and
    // language from the response are applied afterwards, and `onStart` runs
    // after those. Waiting here is what keeps every assertion below
    // deterministic instead of occasionally right.
    await instance.ready;

    const Capability = service("PluginCapabilityService");
    const stub = new Capability(
      `127.0.0.1:${record.port}`,
      grpc.credentials.createInsecure()
    ) as grpc.Client & Record<string, Function>;
    const metadata = new grpc.Metadata();
    metadata.set(PLUGIN_TOKEN_HEADER, this.authToken);

    const wire = new WirePlugin(instance, stub, metadata, record.port);
    this.launched.push(wire);
    return wire;
  }

  /** Shut the daemon and every plugin client down. */
  async stop(): Promise<void> {
    for (const wire of this.launched) await wire.close();
    this.launched.length = 0;
    for (const stream of this.eventStreams) stream.end();
    this.eventStreams.length = 0;
    if (this.consoleWasBridged) {
      restoreConsole();
      this.consoleWasBridged = false;
    }
    removeFatalHandlers();
    await new Promise<void>((resolve) => {
      this.server.tryShutdown(() => resolve());
    });
  }

  // ── the service ──

  private record(method: string, call: { request: unknown; metadata: grpc.Metadata }): void {
    this.hostCalls.push({
      method,
      request: (call.request ?? {}) as Record<string, unknown>,
      sessionToken: call.metadata.get(SESSION_TOKEN_HEADER)[0] as string | undefined,
    });
  }

  /** `null` to proceed, or the rejection. Mirrors the daemon's interceptor. */
  private authorize(call: { metadata: grpc.Metadata }): grpc.ServiceError | null {
    if (this.opts.requireSessionToken === false) return null;
    const presented = call.metadata.get(SESSION_TOKEN_HEADER)[0];
    if (presented === this.sessionToken) return null;
    return unauthenticated(
      presented === undefined
        ? `missing ${SESSION_TOKEN_HEADER} — the daemon rejects every host RPC but Register without it`
        : `invalid ${SESSION_TOKEN_HEADER}`
    );
  }

  private unary(
    method: string,
    body: (request: Record<string, unknown>) => object
  ): grpc.handleUnaryCall<unknown, unknown> {
    return ((call: { request: unknown; metadata: grpc.Metadata }, callback: grpc.sendUnaryData<unknown>) => {
      this.record(method, call);
      const rejection = this.authorize(call);
      if (rejection) {
        callback(rejection, null);
        return;
      }
      callback(null, body((call.request ?? {}) as Record<string, unknown>));
    }) as unknown as grpc.handleUnaryCall<unknown, unknown>;
  }

  private handlers(): HandlerMap {
    const map: Record<string, unknown> = {
      Register: (
        call: { request: Record<string, unknown>; metadata: grpc.Metadata },
        callback: grpc.sendUnaryData<unknown>
      ) => {
        this.record("Register", call);
        const req = call.request ?? {};
        const record: RegisterRecord = {
          pluginId: String(req.pluginId ?? ""),
          port: Number(req.port ?? 0),
          capabilities: (req.capabilities as string[]) ?? [],
          authToken: String(req.authToken ?? ""),
          protocolVersion: Number(req.protocolVersion ?? 0),
          sdkName: String(req.sdkName ?? ""),
          sdkVersion: String(req.sdkVersion ?? ""),
        };
        this.registrations.push(record);

        if (this.opts.refuseWith) {
          callback(null, {
            success: false,
            error: this.opts.refuseWith.error,
            errorDetail: {
              code: this.opts.refuseWith.code ?? "PLUGIN_ERROR_INTERNAL",
              message: this.opts.refuseWith.error,
              hint: this.opts.refuseWith.hint ?? "",
            },
            protocolVersion: this.opts.protocolVersion ?? PROTOCOL_VERSION,
            minSupportedProtocol: this.opts.minSupportedProtocol ?? 0,
          });
          return;
        }
        // The spawn token is what proves this process is the one the daemon
        // started. A wrong one is a refusal, not a warning.
        if (record.authToken !== this.authToken) {
          callback(null, {
            success: false,
            error: "invalid auth token",
            protocolVersion: this.opts.protocolVersion ?? PROTOCOL_VERSION,
            minSupportedProtocol: this.opts.minSupportedProtocol ?? 0,
          });
          return;
        }

        callback(null, {
          success: true,
          error: "",
          configJson: JSON.stringify(this.opts.config ?? {}),
          daemonVersion: this.opts.daemonVersion ?? "0.0.0-mock",
          clientSessionToken: this.sessionToken,
          language: this.opts.language ?? "en",
          protocolVersion: this.opts.protocolVersion ?? PROTOCOL_VERSION,
          minSupportedProtocol: this.opts.minSupportedProtocol ?? 0,
        });
        const resolve = this.registerResolve;
        this.registerResolve = null;
        resolve?.(record);
      },

      PluginLog: this.unary("PluginLog", () => ({ success: true })),
      FireTrigger: this.unary("FireTrigger", () => ({ success: true, error: "" })),
      GetPluginSelfConfig: this.unary("GetPluginSelfConfig", () => ({
        configJson: JSON.stringify(this.opts.config ?? {}),
      })),
      GetDaemonInfo: this.unary("GetDaemonInfo", () => ({
        version: this.opts.daemonVersion ?? "0.0.0-mock",
        state: "running",
        grpcPort: 0,
      })),
      SetVariable: this.unary("SetVariable", () => ({ success: true, error: "" })),
      PushToUi: this.unary("PushToUi", () => ({ success: true, error: "" })),
      SetThemeContribution: this.unary("SetThemeContribution", () => ({ success: true, error: "" })),

      SubscribeEvents: (call: grpc.ServerWritableStream<unknown, unknown>) => {
        this.record("SubscribeEvents", call as unknown as { request: unknown; metadata: grpc.Metadata });
        const rejection = this.authorize(call as unknown as { metadata: grpc.Metadata });
        if (rejection) {
          call.emit("error", rejection);
          return;
        }
        this.eventStreams.push(call);
        call.on("cancelled", () => {
          const i = this.eventStreams.indexOf(call);
          if (i >= 0) this.eventStreams.splice(i, 1);
        });
      },

      SendChatMessage: (call: grpc.ServerWritableStream<unknown, unknown>) => {
        this.record("SendChatMessage", call as unknown as { request: unknown; metadata: grpc.Metadata });
        const rejection = this.authorize(call as unknown as { metadata: grpc.Metadata });
        if (rejection) {
          call.emit("error", rejection);
          return;
        }
        for (const chunk of this.chatReply) call.write(chunk);
        call.end();
      },
    };
    return map as unknown as HandlerMap;
  }
}
