// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * **Which daemon call a trigger was fired from.**
 *
 * A plugin action runs inside a command run a user started by typing in a chat.
 * The plugin fires a trigger, which starts a *second* command run — and that run
 * has no idea what caused it, so its output is filed into a freshly
 * auto-created conversation the user never sees. With two chats driving one
 * plugin at once, nothing on the wire even distinguishes them.
 *
 * The daemon's answer is a per-invocation lease: an opaque token it mints when
 * it calls into a plugin, carried as gRPC call metadata under
 * `spec/wire.yaml`'s `x-astra-cause`. The plugin echoes it on `FireTrigger`, the
 * daemon redeems it, and the trigger's output goes where the user is looking.
 *
 * This module is the ambient half of that: the capability server enters a store
 * around every handler, and the host client reads it when it fires. Neither the
 * plugin author nor the `Plugin` subclass writes a line for it.
 *
 * # Why `AsyncLocalStorage` here and not in Rust
 *
 * `AsyncLocalStorage` follows `await`, `setTimeout`, promise chains and
 * `queueMicrotask` — everything a JavaScript handler can do to defer work. Rust
 * has no equivalent that survives `tokio::spawn`, which is exactly what the
 * shipped reference plugin does, so the Rust SDK carries the cause in a scoped
 * handle instead. Same guarantee, opposite mechanism, because the languages
 * differ in what "later" is allowed to mean.
 *
 * # Where it does NOT reach
 *
 * A `child_process`, a `worker_threads` worker, and anything scheduled from a
 * native addon's own thread all start outside this store. So does a fire from a
 * timer the plugin started at construction rather than inside a handler. All of
 * them get no cause and become root events, which is the honest answer: the
 * daemon files an unattributed fire in the plugin's own thread rather than
 * guessing at a conversation.
 */

import * as grpc from "@grpc/grpc-js";
import { AsyncLocalStorage } from "node:async_hooks";

import { X_ASTRA_CAUSE } from "./generated/wire.js";

const CAUSE = new AsyncLocalStorage<string>();

/**
 * The lease for the daemon call being handled on this async stack, if any.
 *
 * `undefined` is a legal, common answer and must never be papered over: the
 * daemon has to be able to tell "this plugin sent no lease" from "this plugin
 * sent a lease I cannot resolve", and only the second is a bug.
 */
export function currentCause(): string | undefined {
  return CAUSE.getStore();
}

/**
 * Run `fn` with `cause` as the ambient lease.
 *
 * An absent cause runs `fn` untouched rather than entering a store holding
 * `undefined`, so a nested handler cannot accidentally shadow an outer lease
 * with a hole.
 */
export function withCause<T>(cause: string | undefined, fn: () => T): T {
  return cause === undefined ? fn() : CAUSE.run(cause, fn);
}

/**
 * The lease off an inbound call's metadata, or `undefined`.
 *
 * gRPC metadata keys are case-insensitive at the transport and `@grpc/grpc-js`
 * lower-cases them on the way in, so the generated constant matches as written.
 * A binary (`-bin`) value would arrive as a `Buffer`; the spec's grammar refuses
 * that suffix, so anything non-string here is not a lease this daemon minted and
 * is treated as no lease at all.
 */
export function causeFromCall(call: { metadata?: grpc.Metadata } | undefined): string | undefined {
  const values = call?.metadata?.get(X_ASTRA_CAUSE);
  const first = values?.[0];
  return typeof first === "string" && first !== "" ? first : undefined;
}
