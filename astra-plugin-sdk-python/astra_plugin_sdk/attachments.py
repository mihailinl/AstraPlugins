# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""**The pictures the person attached to the message a tool call answers.**

A tool declared with ``@tool(..., wants_attachments=True)`` (or a
:class:`~astra_plugin_sdk.ToolDef` with ``wants_attachments=True``) can be
handed them on ``PluginCallToolRequest.attachments``; its handler reads them
with :func:`current_attachments`, beside
:func:`astra_plugin_sdk.current_invocation`.

When there are any
------------------

Astra sends them only when ALL of these hold, and nothing otherwise:

- the tool declared ``wants_attachments``;
- the plugin was granted the ``receive_attachments`` permission (high-risk, its
  own consent checkbox);
- the call was made while answering a message the person sent in a conversation
  (``current_invocation()`` names it) — never in a report wake, a command's AI
  step, a sub-agent's turn or a held context;
- the Astra in front of you was built with the ``plugin-provider-slots`` build
  feature, which no release has yet.

Only the pictures of the message being answered, never earlier ones and never
ones the model named: at most 4 (``limits.IMAGE_INPUT_MAX_IMAGES``) and 20 MiB,
the newest kept, each under its bare file name. When some were not sent, the
MODEL is told so after your result; you simply get fewer.

Where it does NOT reach
-----------------------

The boundary :mod:`astra_plugin_sdk.invocation` documents, for the same reason:
``loop.run_in_executor`` does not copy the context, so read the pictures in the
coroutine and pass them on as an argument.
"""

from __future__ import annotations

import contextvars
from typing import Any

from astra_plugin_sdk.types import AiImage

__all__ = ["current_attachments", "set_attachments", "attachments_from_request"]

#: The pictures handed to the tool call being handled on this task.
_ATTACHMENTS: contextvars.ContextVar[tuple[AiImage, ...]] = contextvars.ContextVar(
    "astra_attachments", default=()
)


def current_attachments() -> list[AiImage]:
    """The pictures handed to the tool call in scope, in the order attached.

    An empty list — never ``None`` — outside a tool call, inside one that
    carried none, and from a daemon that predates the field. A fresh list each
    time, so a handler may reorder or trim it freely; the ``AiImage`` objects in
    it are the call's own and shared by every read within that call.
    """
    return list(_ATTACHMENTS.get())


def set_attachments(attachments: list[AiImage] | tuple[AiImage, ...]) -> None:
    """Bind the pictures for the current context.

    Called by the capability servicer at the top of ``CallTool``. Like
    :func:`astra_plugin_sdk.invocation.set_invocation` it restores nothing: each
    RPC runs in its own task with its own copy of the context.
    """
    _ATTACHMENTS.set(tuple(attachments))


def attachments_from_request(request: Any) -> list[AiImage]:
    """The pictures off an inbound ``CallTool`` request, as :class:`AiImage`.

    A request type without the field — an older generated module, or a
    hand-built stub in a test — has none, which is the same answer as an empty
    list.
    """
    raw = getattr(request, "attachments", None)
    if not raw:
        return []
    return [AiImage.from_proto(i) for i in raw]
