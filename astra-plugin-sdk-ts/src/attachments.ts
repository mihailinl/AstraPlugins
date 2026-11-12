// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * **The pictures the person attached to the message a tool call answers.**
 *
 * A tool that declares `wantsAttachments` can be handed them on
 * `PluginCallToolRequest.attachments`, and its handler reads them as
 * `ctx.attachments` (or `currentAttachments()` where no context is to hand).
 *
 * # When there are any
 *
 * Astra sends them only when ALL of these hold, and an empty list otherwise:
 *
 * - the tool declared `wantsAttachments: true` in its `ListTools` answer;
 * - the plugin was granted the `receive_attachments` permission (high-risk,
 *   its own consent checkbox);
 * - the call was made while answering a message the person sent in a
 *   conversation (`ctx.invocation?.conversationId` is set) — never in a report
 *   wake, a command's AI step, a sub-agent's turn or a held context;
 * - the Astra in front of you was built with the `plugin-provider-slots` build
 *   feature, which no release has yet.
 *
 * Only the pictures of the message being answered, never earlier ones, and
 * never ones the model named: at most 4 (`limits.IMAGE_INPUT_MAX_IMAGES`) and
 * 20 MiB, the newest kept, each under its bare file name. When some were not
 * sent, the MODEL is told so after your result; you simply get fewer.
 *
 * # Why a store and not a field on the context
 *
 * The same reason as `./invocation.js`: one `PluginContext` is built per plugin
 * and handed to every hook, so a field would be shared by two concurrent calls
 * from two chats. `AsyncLocalStorage` follows the await chain of the one call
 * being handled.
 */

import { AsyncLocalStorage } from "node:async_hooks";
import type { AiImage } from "./types.js";

const NONE: readonly AiImage[] = Object.freeze([]);

const ATTACHMENTS = new AsyncLocalStorage<readonly AiImage[]>();

/**
 * The pictures handed to the tool call being handled on this async stack.
 *
 * Empty — never `undefined` — outside a tool call, inside one that carried
 * none, and from a daemon that predates the field.
 */
export function currentAttachments(): readonly AiImage[] {
  return ATTACHMENTS.getStore() ?? NONE;
}

/**
 * Run `fn` with `attachments` as the ambient ones.
 *
 * Always enters the store, an empty list included, so a nested call can never
 * read the pictures of the call around it.
 */
export function withAttachments<T>(attachments: readonly AiImage[], fn: () => T): T {
  return ATTACHMENTS.run(attachments, fn);
}

/**
 * The pictures off an inbound `CallTool` request, as the SDK's own type.
 *
 * Read defensively: an older daemon sends no field (`undefined`), the
 * descriptor's `keepCase: false` loader may hand `null` for an empty repeated
 * field, and `data` is a `Buffer` off the wire but may be a `Uint8Array` or a
 * plain array from a test.
 */
export function attachmentsFromCall(call: { request?: unknown } | undefined): readonly AiImage[] {
  const request = call?.request as { attachments?: unknown } | undefined;
  const raw = request?.attachments;
  if (!Array.isArray(raw) || raw.length === 0) return NONE;
  return Object.freeze(
    raw.map((i: any) => ({
      mimeType: typeof i?.mimeType === "string" ? i.mimeType : "",
      data: Buffer.isBuffer(i?.data) ? i.data : Buffer.from(i?.data ?? []),
      filename: typeof i?.filename === "string" ? i.filename : "",
    }))
  );
}
