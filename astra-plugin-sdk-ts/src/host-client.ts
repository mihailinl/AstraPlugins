/**
 * HostClient — plugin-side gRPC client for calling the Astra daemon.
 */

import * as grpc from "@grpc/grpc-js";
import { astraProto } from "./proto-loader";

const pluginProto = astraProto;

export class HostClient {
  private client: any;
  private pluginId: string;

  constructor(
    private daemonAddr: string,
    pluginId: string
  ) {
    this.pluginId = pluginId;
  }

  /** Connect to the daemon's PluginHostService. */
  async connect(): Promise<void> {
    this.client = new pluginProto.PluginHostService(
      this.daemonAddr,
      grpc.credentials.createInsecure()
    );
  }

  /** Register this plugin with the daemon. */
  register(
    port: number,
    capabilities: string[],
    authToken: string = ""
  ): Promise<{
    success: boolean;
    error: string;
    configJson: string;
    daemonVersion: string;
    clientSessionToken: string;
    language: string;
  }> {
    return new Promise((resolve, reject) => {
      this.client.Register(
        { pluginId: this.pluginId, port, capabilities, authToken },
        (err: grpc.ServiceError | null, response: any) => {
          if (err) reject(err);
          else resolve(response);
        }
      );
    });
  }

  /** Fire a trigger. */
  fireTrigger(triggerType: string, payloadJson: string = "{}"): Promise<void> {
    return new Promise((resolve, reject) => {
      this.client.FireTrigger(
        { triggerType, payloadJson },
        (err: grpc.ServiceError | null) => {
          if (err) reject(err);
          else resolve();
        }
      );
    });
  }

  /** Log a message to the daemon. */
  log(level: string, message: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.client.PluginLog(
        { pluginId: this.pluginId, level, message },
        (err: grpc.ServiceError | null) => {
          if (err) reject(err);
          else resolve();
        }
      );
    });
  }

  /** Get this plugin's current config. */
  getConfig(): Promise<string> {
    return new Promise((resolve, reject) => {
      this.client.GetPluginSelfConfig(
        { pluginId: this.pluginId },
        (err: grpc.ServiceError | null, response: any) => {
          if (err) reject(err);
          else resolve(response.configJson);
        }
      );
    });
  }

  /** Get daemon info. */
  getDaemonInfo(): Promise<{
    version: string;
    state: string;
    grpcPort: number;
  }> {
    return new Promise((resolve, reject) => {
      this.client.GetDaemonInfo(
        {},
        (err: grpc.ServiceError | null, response: any) => {
          if (err) reject(err);
          else resolve(response);
        }
      );
    });
  }

  /** Subscribe to daemon events. Returns a gRPC readable stream. */
  subscribeEvents(eventTypes: string[], excludeSourceId: string = ""): any {
    return this.client.SubscribeEvents({
      pluginId: this.pluginId,
      eventTypes,
      excludeSourceId,
    });
  }

  /** Get the plugin ID. */
  getPluginId(): string {
    return this.pluginId;
  }
}
