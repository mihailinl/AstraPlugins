// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Fake gRPC call objects, so a level-1 test drives the SDK's real dispatch.
 *
 * The alternative — calling `plugin.callTool(...)` directly — tests the
 * author's code and nothing else. Everything between the author's method and
 * the wire is where this SDK's bugs have actually been: the camelCase wire
 * projections (`config_fields` silently dropped by protobufjs), the
 * `HookUnimplemented` → `UNIMPLEMENTED` mapping, the in-band-versus-transport
 * decision on each hook, and the bounded queue in `SttProcess`.
 *
 * These objects are the smallest thing those handlers accept: an `EventEmitter`
 * with `write`/`end`/`pause`/`resume`. The pause and resume are not decoration —
 * the STT bridge calls them at `STT_AUDIO_CHANNEL_CAPACITY`, and a fake that
 * ignored them would report a green test for the exact bug the bound exists to
 * prevent.
 */

import { EventEmitter } from "node:events";

/** A gRPC status as a handler reports it. */
export interface FakeStatus {
  code: number;
  details?: string;
}

/** What a unary handler produced: a response, or a status. */
export interface UnaryOutcome<T = Record<string, unknown>> {
  response?: T;
  error?: FakeStatus;
}

/** A `ServerUnaryCall` as the handlers use it: `request` and nothing else. */
export function unaryCall(request: unknown): { request: unknown; metadata: undefined } {
  return { request, metadata: undefined };
}

/** Run a unary handler and settle when it calls back. */
export function invokeUnary<T = Record<string, unknown>>(
  handler: (call: unknown, callback: (err: FakeStatus | null, res?: T) => void) => void,
  request: unknown
): Promise<UnaryOutcome<T>> {
  return new Promise((resolve) => {
    handler(unaryCall(request), (err, res) => {
      resolve(err ? { error: err } : { response: res });
    });
  });
}

/** A server-streaming call: collects writes, records the terminating status. */
export class FakeWritableCall extends EventEmitter {
  readonly written: unknown[] = [];
  status: FakeStatus | null = null;
  private readonly finished: Promise<void>;
  private settle!: () => void;

  constructor(readonly request: unknown) {
    super();
    this.finished = new Promise<void>((resolve) => {
      this.settle = resolve;
    });
    // grpc-js installs this listener itself; a handler emitting 'error' on an
    // EventEmitter with no listener would throw instead of failing the call.
    this.on("error", (status: FakeStatus) => {
      this.status = status;
      this.settle();
    });
  }

  write(message: unknown): boolean {
    this.written.push(message);
    return true;
  }

  end(): void {
    this.settle();
  }

  /** Resolves when the handler has called `end()` or emitted an error. */
  done(): Promise<void> {
    return this.finished;
  }
}

/** Run a server-streaming handler to completion. */
export async function invokeServerStream(
  handler: (call: FakeWritableCall) => unknown,
  request: unknown
): Promise<FakeWritableCall> {
  const call = new FakeWritableCall(request);
  void handler(call);
  await call.done();
  return call;
}

/**
 * A bidi call: feeds inbound messages, honours `pause()`/`resume()`, collects
 * outbound ones.
 *
 * The feeder emits as fast as the receiver will take it — synchronously, in one
 * turn, until the handler calls `pause()` — and only then yields the loop. That
 * is how the real thing behaves and it is the only way the bound is reachable:
 * a feeder that delivered one message per macrotask would stay in lockstep with
 * any consumer that yields, the queue would never pass a couple of entries, and
 * a test asserting "the utterance survived back-pressure" would be green
 * against an SDK where back-pressure had never engaged at all.
 *
 * The daemon really does arrive in bursts — the wake-word seed dump is ~8 s of
 * audio handed over at once, which is precisely why the channel is 500 slots.
 */
export class FakeDuplexCall extends EventEmitter {
  readonly written: unknown[] = [];
  status: FakeStatus | null = null;
  /** Messages actually handed to the handler. */
  delivered = 0;
  /** How many times `pause()` was called. Zero means back-pressure never engaged. */
  pauses = 0;
  private paused = false;
  private readonly inbound: unknown[];
  private sent = 0;
  private readonly finished: Promise<void>;
  private settle!: () => void;

  constructor(messages: readonly unknown[]) {
    super();
    this.inbound = [...messages];
    this.finished = new Promise<void>((resolve) => {
      this.settle = resolve;
    });
    this.on("error", (status: FakeStatus) => {
      this.status = status;
      this.settle();
    });
  }

  /** Start feeding. Call after the handler has attached its listeners. */
  begin(): void {
    this.pump();
  }

  private pump(): void {
    while (!this.paused && this.sent < this.inbound.length) {
      const message = this.inbound[this.sent++];
      this.delivered = this.sent;
      this.emit("data", message);
    }
    if (this.paused) return; // `resume()` restarts us.
    // Everything delivered. `end` goes out on the next turn so a handler that
    // finishes its own work in a microtask sees the same ordering it would on
    // a real stream.
    setImmediate(() => this.emit("end"));
  }

  pause(): void {
    this.paused = true;
    this.pauses++;
  }

  resume(): void {
    if (!this.paused) return;
    this.paused = false;
    setImmediate(() => this.pump());
  }

  write(message: unknown): boolean {
    this.written.push(message);
    return true;
  }

  end(): void {
    this.settle();
  }

  done(): Promise<void> {
    return this.finished;
  }
}

/** Run a bidi handler over `messages` and wait for it to finish. */
export async function invokeBidi(
  handler: (call: FakeDuplexCall) => unknown,
  messages: readonly unknown[]
): Promise<FakeDuplexCall> {
  const call = new FakeDuplexCall(messages);
  void handler(call);
  call.begin();
  await call.done();
  return call;
}
