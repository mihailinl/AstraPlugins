// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * `console` → `PluginLog`, and a crash that leaves a record (§5.10).
 *
 * WHY
 *
 * A TypeScript plugin logs the way Node logs: `console.log`. None of that
 * reached Astra. It landed in the daemon's captured stdout with no level and no
 * plugin attribution, so the log pane a user is shown when a plugin misbehaves
 * was empty unless the author had remembered to `await this.logInfo(...)` — a
 * promise, therefore unusable from a synchronous helper or a library.
 *
 * Worse, a plugin that threw outside a handler simply vanished. Node prints an
 * unhandled rejection to a stderr nobody reads and, since Node 15, exits — with
 * no `PluginLog`, no fatal line, and (before this) exit code 1, which the daemon
 * cannot distinguish from an orderly stop.
 *
 * This module fixes both, and its shape mirrors the Python SDK's
 * `logging_bridge.py` because the two must behave the same:
 *
 * 1. **Logging never blocks on the network.** `console.log` appends to a queue
 *    and returns; a pump drains it into `PluginLog`.
 * 2. **The queue is bounded and dropping is visible.** An unbounded buffer in
 *    front of a daemon that stopped reading is a memory leak that ends as an
 *    OOM kill, reported to the user as "the plugin crashed". Overflow drops the
 *    OLDEST line and counts it; the count rides out with the next line that
 *    does get through.
 * 3. **Forwarding must not recurse.** grpc-js logs. A grpc log forwarded over a
 *    grpc call that logs again is a spin. A re-entrancy flag closes it.
 *
 * The original `console` methods are always called too — stdout remains the
 * daemon's readiness signal and the local dev loop's output.
 */

import type { Host } from "./host.js";

/**
 * Exit code for a crash outside any handler: `EX_SOFTWARE` from `sysexits.h`.
 *
 * Deliberately not 1, and deliberately not 0. The daemon records a plugin's
 * exit code; "an internal software error" is a different fact from "the process
 * was asked to stop", and only one of them should show the user a crash report.
 */
export const EXIT_UNCAUGHT = 70;

/** How many lines may wait for the daemon before the oldest are dropped. */
export const DEFAULT_CAPACITY = 512;

/** The four levels the daemon knows. */
export type LogLevel = "debug" | "info" | "warn" | "error";

/** The console methods the bridge replaces, and the level each maps to. */
const CONSOLE_LEVELS = {
  log: "info",
  info: "info",
  debug: "debug",
  warn: "warn",
  error: "error",
} as const satisfies Record<string, LogLevel>;

type ConsoleMethod = keyof typeof CONSOLE_LEVELS;

/** How long a fatal handler waits for its last log line to reach the daemon. */
const FATAL_FLUSH_MS = 1000;

/**
 * A bounded queue in front of `Host.log`.
 *
 * Constructed with a getter rather than with a host, on purpose: the host does
 * not exist until registration succeeds, and the lines produced before then —
 * a failed connect, a bad config — are exactly the ones worth keeping. They
 * queue and go out as soon as there is somewhere to send them.
 */
export class LogBridge {
  private readonly queue: { level: LogLevel; message: string }[] = [];
  private dropped = 0;
  private pumping = false;
  /** Set while a line is in flight, so a log emitted by the transport is dropped. */
  private forwarding = false;
  private stopped = false;

  constructor(
    private readonly getHost: () => Host | null,
    private readonly capacity: number = DEFAULT_CAPACITY
  ) {}

  /** Queue one line. Never throws, never blocks, never awaits. */
  emit(level: LogLevel, message: string): void {
    if (this.forwarding || this.stopped) return;
    if (this.queue.length >= this.capacity) {
      this.queue.shift();
      this.dropped++;
    }
    this.queue.push({ level, message });
    this.schedule();
  }

  /** Lines waiting to go out. For tests. */
  pending(): number {
    return this.queue.length;
  }

  /** Lines dropped to stay inside `capacity`. For tests. */
  droppedCount(): number {
    return this.dropped;
  }

  /** Stop forwarding. The original console is untouched by this. */
  stop(): void {
    this.stopped = true;
    this.queue.length = 0;
  }

  private schedule(): void {
    if (this.pumping) return;
    this.pumping = true;
    // `unref` so a queued log line cannot keep an otherwise finished process
    // alive — a plugin that logged on its way out should still exit.
    const timer = setTimeout(() => void this.pump(), 0);
    if (typeof timer.unref === "function") timer.unref();
  }

  private async pump(): Promise<void> {
    try {
      for (;;) {
        const host = this.getHost();
        if (!host) return; // No daemon yet: keep the lines, try again on the next emit.
        const line = this.queue.shift();
        if (!line) return;
        const dropped = this.dropped;
        this.dropped = 0;
        const message =
          dropped > 0
            ? `${line.message}  [${dropped} earlier log line(s) dropped: the daemon was not keeping up]`
            : line.message;
        this.forwarding = true;
        try {
          await host.log(line.level, message);
        } catch {
          // The daemon is gone or refusing. Losing the line is the only option;
          // retrying forever is how a log bridge becomes a busy loop.
        } finally {
          this.forwarding = false;
        }
      }
    } finally {
      this.pumping = false;
      if (this.queue.length > 0 && this.getHost()) this.schedule();
    }
  }

  /** Drain what is queued, giving up after `ms`. Used by the fatal handlers. */
  async flush(ms = FATAL_FLUSH_MS): Promise<void> {
    const deadline = Date.now() + ms;
    while (this.queue.length > 0 && Date.now() < deadline && this.getHost()) {
      await this.pump();
      if (this.queue.length > 0) await new Promise((r) => setTimeout(r, 5));
    }
  }
}

/** Format `console.log("a", 1, {b: 2})` the way Node's console would. */
export function formatArgs(args: readonly unknown[]): string {
  return args
    .map((a) => {
      if (typeof a === "string") return a;
      if (a instanceof Error) return a.stack || `${a.name}: ${a.message}`;
      try {
        return JSON.stringify(a) ?? String(a);
      } catch {
        return String(a);
      }
    })
    .join(" ");
}

interface Installed {
  bridge: LogBridge;
  original: Pick<Console, ConsoleMethod>;
}

let installed: Installed | null = null;

/**
 * Route `console.*` into `PluginLog`, keeping the original output.
 *
 * Idempotent: a second call returns the bridge from the first rather than
 * wrapping the wrapper, which would double every line.
 */
export function installConsoleBridge(
  getHost: () => Host | null,
  opts: { capacity?: number; console?: Console } = {}
): LogBridge {
  if (installed) return installed.bridge;

  const target = (opts.console ?? console) as Console & Record<ConsoleMethod, (...a: unknown[]) => void>;
  const bridge = new LogBridge(getHost, opts.capacity);
  const original = {} as Record<ConsoleMethod, (...a: unknown[]) => void>;

  for (const [name, level] of Object.entries(CONSOLE_LEVELS) as [ConsoleMethod, LogLevel][]) {
    const previous = target[name].bind(target);
    original[name] = previous;
    target[name] = (...args: unknown[]) => {
      previous(...args);
      bridge.emit(level, formatArgs(args));
    };
  }

  installed = { bridge, original: original as Pick<Console, ConsoleMethod> };
  return bridge;
}

/** Undo {@link installConsoleBridge}. Exists so a test can leave no trace. */
export function restoreConsole(target: Console = console): void {
  if (!installed) return;
  for (const name of Object.keys(CONSOLE_LEVELS) as ConsoleMethod[]) {
    (target as unknown as Record<ConsoleMethod, unknown>)[name] = installed.original[name];
  }
  installed.bridge.stop();
  installed = null;
}

/** The live bridge, if `installConsoleBridge` has run. */
export function consoleBridge(): LogBridge | null {
  return installed?.bridge ?? null;
}

/** The two listeners `installFatalHandlers` registers, returned so a test can
 * invoke them directly — `process.emit("uncaughtException", …)` runs the test
 * runner's own listener too, which fails the test rather than exercising ours. */
export type FatalHandlers = {
  uncaughtException: (err: unknown) => void;
  unhandledRejection: (reason: unknown) => void;
};

let fatal: FatalHandlers | null = null;

/**
 * Turn a crash outside any handler into a fatal log line and a non-zero exit.
 *
 * Node's own behaviour is a stderr dump and `exit(1)` for an uncaught
 * exception, and — since Node 15 — the same for an unhandled rejection. Both
 * are invisible to the daemon, which sees only a process that stopped. These
 * handlers write the payload and stack at `error` level over `PluginLog`, give
 * it {@link FATAL_FLUSH_MS} to reach the daemon, and exit {@link EXIT_UNCAUGHT}
 * so the exit code itself says "this was a crash".
 *
 * Deliberately does NOT keep the process running. An uncaught exception leaves
 * a plugin in a state nobody reasoned about; the daemon's restart path is the
 * thing that knows how to recover, and it can only act on a process that exits.
 */
export function installFatalHandlers(
  getHost: () => Host | null,
  opts: { exit?: (code: number) => void } = {}
): FatalHandlers {
  if (fatal) return fatal;
  const exit = opts.exit ?? ((code: number) => process.exit(code));

  const report = (kind: string, thrown: unknown): void => {
    const detail =
      thrown instanceof Error
        ? `${thrown.name}: ${thrown.message}\n${thrown.stack ?? ""}`
        : String(thrown);
    const line = `FATAL ${kind}: ${detail}`;
    // stderr first and unconditionally: it is the one channel that works when
    // the daemon is the thing that broke.
    process.stderr.write(`${line}\n`);

    const host = getHost();
    if (!host) {
      exit(EXIT_UNCAUGHT);
      return;
    }
    const timeout = new Promise<void>((resolve) => {
      const t = setTimeout(resolve, FATAL_FLUSH_MS);
      if (typeof t.unref === "function") t.unref();
    });
    void Promise.race([host.log("error", line).catch(() => undefined), timeout]).finally(() => {
      exit(EXIT_UNCAUGHT);
    });
  };

  fatal = {
    uncaughtException: (err) => report("uncaughtException", err),
    unhandledRejection: (reason) => report("unhandledRejection", reason),
  };
  process.on("uncaughtException", fatal.uncaughtException);
  process.on("unhandledRejection", fatal.unhandledRejection);
  return fatal;
}

/** Undo {@link installFatalHandlers}. Exists so a test can leave no trace. */
export function removeFatalHandlers(): void {
  if (!fatal) return;
  process.off("uncaughtException", fatal.uncaughtException);
  process.off("unhandledRejection", fatal.unhandledRejection);
  fatal = null;
}
