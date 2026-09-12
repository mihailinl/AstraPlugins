// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * **Which conversation made this call.**
 *
 * A tool call or an action that a conversation's assistant turn triggered
 * carries the conversation's id. A plugin told "you were called from here" can
 * answer there later, as itself, by passing that id back to
 * `sendChatMessage(text, { conversationId })`.
 *
 * # Why this is a second store and not part of the cause lease
 *
 * They are different facts that arrive by different routes, and one must never
 * be able to stand in for the other. The lease (`./causality.js`) is gRPC
 * METADATA and says *what run* is calling; the invocation is a field in the
 * request BODY and says *which conversation* that run belongs to. A call can
 * carry either, both or neither — a run that has a conversation but no lease is
 * a real case, not a contradiction.
 *
 * # What `undefined` means, and what it does not
 *
 * `undefined` means **this call was not made from a conversation**, and it is
 * the answer for several situations a plugin cannot tell apart and does not
 * need to:
 *
 * - nothing conversational caused the call — a trigger, a timer, your own UI;
 * - the call has a cause but the daemon holds no lease for it: a nested
 *   sub-agent's model, or the model of a command's "send to AI" step, even one
 *   matched in a chat;
 * - the daemon predates the field.
 *
 * It is never a cue to guess. There is no "the conversation the user is looking
 * at" API, deliberately, and a plugin posting into a chat nobody pointed at
 * would be doing something nobody asked for.
 */

import { AsyncLocalStorage } from "node:async_hooks";

/** What the daemon said about the one call being handled. */
export interface Invocation {
  /**
   * The conversation whose turn made this call.
   *
   * A UUID you MAY store, including across restarts, and send back later as
   * `sendChatMessage`'s `conversationId`. Absent when the call was not made
   * from a conversation — see this module's documentation for everything that
   * covers.
   */
  readonly conversationId?: string;
}

const INVOCATION = new AsyncLocalStorage<Invocation>();

/**
 * The invocation for the call being handled on this async stack, if any.
 *
 * `undefined` outside a tool call or an action, and `undefined` inside one that
 * no conversation made. Never returns an `Invocation` whose `conversationId` is
 * the empty string.
 */
export function currentInvocation(): Invocation | undefined {
  return INVOCATION.getStore();
}

/**
 * Run `fn` with `invocation` as the ambient one.
 *
 * An absent invocation runs `fn` untouched rather than entering a store holding
 * `undefined`, matching `withCause` — a nested handler must not be able to
 * shadow an outer invocation with a hole.
 */
export function withInvocation<T>(invocation: Invocation | undefined, fn: () => T): T {
  return invocation === undefined ? fn() : INVOCATION.run(invocation, fn);
}

/**
 * The invocation off an inbound call's request body, or `undefined`.
 *
 * Three shapes collapse to `undefined`, and they must, because the wire spells
 * "not from a conversation" all three ways depending on the daemon's age:
 * no `invocation` message at all, one whose `conversationId` is `""`, and — the
 * one worth naming — `null`. The descriptor is loaded with `keepCase: false`
 * and an absent sub-message arrives as `null` rather than as `undefined`, so a
 * plain `?.` chain would hand a caller `null` where the type says `undefined`.
 *
 * Reading it generically, off any call, is deliberate. The daemon stamps two
 * arms today; a rule naming those two goes stale in silence the moment a third
 * is stamped, and the cost here is one property lookup on a request that has no
 * such field.
 */
export function invocationFromCall(call: { request?: unknown } | undefined): Invocation | undefined {
  const request = call?.request as { invocation?: { conversationId?: unknown } | null } | undefined;
  const id = request?.invocation?.conversationId;
  return typeof id === "string" && id !== "" ? { conversationId: id } : undefined;
}
