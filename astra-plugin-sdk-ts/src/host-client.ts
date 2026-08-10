/**
 * HostClient — plugin-side gRPC client for `astra.PluginHostService`.
 *
 * SECURITY: the daemon exempts exactly one path from authentication,
 * `/astra.PluginHostService/Register`
 * (`astra-daemon/src/server/auth_interceptor.rs`, `EXEMPT_PATHS`). Register
 * proves the plugin with the spawn-time `auth_token` carried in the request
 * body and hands back a per-plugin `client_session_token`; every other host RPC
 * must present that token as the `x-session-token` metadata header or the
 * daemon answers `unauthenticated`.
 *
 * So the class is built around the token rather than around the connection:
 * the constructor is private and the only way to obtain a `HostClient` is
 * `HostClient.register()`, which performs the bootstrap call itself and returns
 * a client that already holds the token. There is no reachable state in which a
 * host RPC can be issued without one.
 */

import * as grpc from "@grpc/grpc-js";
import { service } from "./proto-loader";
import { assertClientContract } from "./service-contract";
import {
  evaluateProtocol,
  ProtocolMismatchError,
  PROTOCOL_VERSION,
  SDK_NAME,
  SDK_VERSION,
} from "./protocol";

/** Metadata header the daemon's auth interceptor reads. */
const SESSION_TOKEN_HEADER = "x-session-token";

/** Every host RPC this client issues. Verified against the descriptor at connect time. */
const REQUIRED_METHODS = [
  "Register",
  "SubscribeEvents",
  "FireTrigger",
  "GetPluginSelfConfig",
  "PluginLog",
  "GetDaemonInfo",
  "SetVariable",
  "PushToUi",
] as const;

/** Structured detail for a refused registration. Present only when `success` is false. */
export interface RegisterErrorDetail {
  /** `PluginErrorCode`. A proto name (`enums: String`), or a number. */
  code: string | number;
  /** What went wrong. One sentence. */
  message: string;
  /** What to DO about it. One sentence. */
  hint: string;
}

/** The daemon's answer to `Register`. */
export interface RegisterResponse {
  success: boolean;
  error: string;
  /** Plugin's persisted config, as JSON. */
  configJson: string;
  daemonVersion: string;
  /** Per-plugin session token. Required on every subsequent host RPC. */
  clientSessionToken: string;
  /** Daemon UI language ("en", "ru", "uk", …). */
  language: string;
  /**
   * The protocol generation this daemon speaks, and the oldest it accepts.
   * Optional because a daemon that predates the handshake sends neither — which
   * is itself the signal that it is too old (see `evaluateProtocol`).
   */
  protocolVersion?: number;
  minSupportedProtocol?: number;
  errorDetail?: RegisterErrorDetail;
}

/** Registration was rejected, or produced no usable session. */
export class RegistrationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RegistrationError";
  }
}

/** Info about the running daemon. */
export interface DaemonInfo {
  version: string;
  state: string;
  grpcPort: number;
}

export class HostClient {
  private constructor(
    private readonly stub: grpc.Client & Record<string, Function>,
    private readonly pluginId: string,
    /** Carries `x-session-token`; attached to every call but `Register`. */
    private readonly metadata: grpc.Metadata
  ) {}

  /**
   * Connect, register, and return an authenticated client.
   *
   * The bootstrap `Register` call is the only one made without a session token.
   * Rejection — or a daemon that hands back no token — throws rather than
   * yielding a client whose every call would fail `unauthenticated`.
   */
  static async register(opts: {
    daemonAddr: string;
    pluginId: string;
    port: number;
    capabilities: string[];
    authToken?: string;
  }): Promise<{ host: HostClient; response: RegisterResponse }> {
    const PluginHostService = service("PluginHostService");
    const stub = new PluginHostService(
      opts.daemonAddr,
      grpc.credentials.createInsecure()
    ) as grpc.Client & Record<string, Function>;
    assertClientContract("PluginHostService", stub, REQUIRED_METHODS);

    let response: RegisterResponse;
    try {
      response = await new Promise<RegisterResponse>((resolve, reject) => {
        stub.Register(
          {
            pluginId: opts.pluginId,
            port: opts.port,
            capabilities: opts.capabilities,
            authToken: opts.authToken ?? "",
            // The handshake (production plan 1.3). Without this on the wire the
            // daemon cannot tell an old plugin from a new one, and its protocol
            // floor stops meaning anything.
            protocolVersion: PROTOCOL_VERSION,
            sdkName: SDK_NAME,
            sdkVersion: SDK_VERSION,
          },
          (err: grpc.ServiceError | null, res: RegisterResponse) => {
            if (err) reject(err);
            else resolve(res);
          }
        );
      });
    } catch (err) {
      stub.close();
      throw err;
    }

    // The protocol verdict comes BEFORE the generic refusal below: "your plugin
    // is too old for this Astra" is a different problem from "the daemon said
    // no", it has a different fix, and it gets its own exit code
    // (`EXIT_PROTOCOL_INCOMPATIBLE`) rather than being flattened into a message
    // the author has to interpret.
    const mismatch = evaluateProtocol(response);
    if (mismatch) {
      stub.close();
      throw new ProtocolMismatchError(mismatch);
    }

    if (!response.success) {
      stub.close();
      throw new RegistrationError(response.error || "daemon rejected the registration");
    }
    if (!response.clientSessionToken) {
      stub.close();
      throw new RegistrationError(
        "daemon returned an empty client_session_token — every host RPC would be rejected " +
          "as `unauthenticated`. This daemon predates the per-plugin session token; upgrade Astra."
      );
    }

    const metadata = new grpc.Metadata();
    metadata.set(SESSION_TOKEN_HEADER, response.clientSessionToken);
    return { host: new HostClient(stub, opts.pluginId, metadata), response };
  }

  /** Fire a trigger. */
  fireTrigger(triggerType: string, payloadJson: string = "{}"): Promise<void> {
    return this.unary("FireTrigger", { triggerType, payloadJson }).then(() => undefined);
  }

  /** Log a message to the daemon. */
  log(level: string, message: string): Promise<void> {
    return this.unary("PluginLog", {
      pluginId: this.pluginId,
      level,
      message,
    }).then(() => undefined);
  }

  /** Get this plugin's current config, as JSON. */
  async getConfig(): Promise<string> {
    const res = await this.unary<{ configJson: string }>("GetPluginSelfConfig", {
      pluginId: this.pluginId,
    });
    return res.configJson;
  }

  /** Get daemon info. */
  getDaemonInfo(): Promise<DaemonInfo> {
    return this.unary<DaemonInfo>("GetDaemonInfo", {});
  }

  /** Set a variable readable by commands and other plugins. */
  setVariable(name: string, value: string, scope: string = "global"): Promise<void> {
    return this.unary("SetVariable", {
      pluginId: this.pluginId,
      name,
      value,
      scope,
    }).then(() => undefined);
  }

  /** Push an event to this plugin's UI contributions. */
  pushToUi(event: string, payloadJson: string = "{}"): Promise<void> {
    return this.unary("PushToUi", {
      pluginId: this.pluginId,
      event,
      payloadJson,
    }).then(() => undefined);
  }

  /** Subscribe to daemon events. Returns a gRPC readable stream. */
  subscribeEvents(eventTypes: string[], excludeSourceId: string = ""): grpc.ClientReadableStream<any> {
    return this.stub.SubscribeEvents(
      { pluginId: this.pluginId, eventTypes, excludeSourceId },
      this.metadata
    );
  }

  /** Get the plugin ID. */
  getPluginId(): string {
    return this.pluginId;
  }

  /** Close the underlying channel. */
  close(): void {
    this.stub.close();
  }

  /** Every unary host RPC goes through here, so none can forget the token. */
  private unary<T>(method: string, request: object): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.stub[method](
        request,
        this.metadata,
        (err: grpc.ServiceError | null, response: T) => {
          if (err) reject(err);
          else resolve(response);
        }
      );
    });
  }
}
