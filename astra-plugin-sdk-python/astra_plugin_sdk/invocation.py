# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""**Which conversation made this call.**

A tool call or an action that a conversation's assistant turn triggered carries
that conversation's id. A plugin told "you were called from here" can answer
there later, as itself, by passing the id back as ``send_chat_message``'s
``conversation_id``.

Why this is a second store and not part of the cause lease
----------------------------------------------------------

They are different facts arriving by different routes, and one must never be
able to stand in for the other. The lease (:mod:`astra_plugin_sdk.causality`) is
gRPC METADATA and says *what run* is calling; the invocation is a field in the
request BODY and says *which conversation* that run belongs to. A call may carry
either, both or neither — a run that has a conversation but no lease is a real
case, not a contradiction: a nested sub-agent's model, or the model of a
command's "send to AI" step, hold no lease even when a chat matched them.

What ``None`` means, and what it does not
-----------------------------------------

``None`` means **this call was not made from a conversation**, and it is the
answer for several situations a plugin cannot tell apart and does not need to:

- nothing conversational caused the call — a trigger, a timer, your own UI;
- the call has a cause but the daemon holds no lease for it;
- the daemon predates the field.

It is never a cue to guess. There is no "the conversation the user is looking
at" API, deliberately, and a plugin posting into a chat nobody pointed at would
be doing something nobody asked for. Nothing here falls back to ``""``.

Where it does NOT reach
-----------------------

The same boundary :mod:`astra_plugin_sdk.causality` documents, for the same
reason and with the same fix. **``loop.run_in_executor`` does not copy the
context.** A handler that hands work to a thread pool and reads
:func:`current_invocation` from there gets ``None``. Read it in the coroutine
and pass the id as an argument, or carry the context across explicitly::

    ctx = contextvars.copy_context()
    await loop.run_in_executor(None, lambda: ctx.run(work))

The same applies to ``multiprocessing``, a raw ``threading.Thread``, and a
callback scheduled by a C extension on its own thread.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

__all__ = ["Invocation", "current_invocation", "set_invocation", "invocation_from_request"]


@dataclass(frozen=True)
class Invocation:
    """What the daemon said about the one call being handled.

    Frozen because it describes a call that has already arrived: nothing the
    plugin does can change where it was called from, and a mutable copy shared
    across tasks is a bug waiting for a concurrent handler.
    """

    #: The conversation whose turn made this call, or ``None``.
    #:
    #: A UUID. Safe to store, including across restarts, and to send back later
    #: as the conversation to post into. ``None`` covers several situations —
    #: see this module's documentation — none of which is a cue to guess.
    conversation_id: str | None = None


#: The invocation for the call being handled on this task, or ``None``.
_INVOCATION: contextvars.ContextVar[Invocation | None] = contextvars.ContextVar(
    "astra_invocation", default=None
)


def current_invocation() -> Invocation | None:
    """The invocation in scope, or ``None``.

    ``None`` outside a tool call or an action, and ``None`` inside one that no
    conversation made. Never returns an :class:`Invocation` whose
    ``conversation_id`` is the empty string — see
    :func:`invocation_from_request`.
    """
    return _INVOCATION.get()


def set_invocation(invocation: Invocation | None) -> None:
    """Bind the invocation for the current context.

    Called by the capability servicer at the top of the two handlers that have
    one. Like :func:`astra_plugin_sdk.causality.set_cause` it does not restore a
    previous value: each RPC runs in its own task with its own copy of the
    context, so there is nothing to leak into and nothing to put back.
    """
    _INVOCATION.set(invocation)


def invocation_from_request(request: Any) -> Invocation | None:
    """The invocation off an inbound request, or ``None``.

    Two shapes collapse to ``None`` and both must, because the wire spells "not
    from a conversation" both ways depending on the daemon's age: no
    ``invocation`` sub-message at all, and one whose ``conversation_id`` is
    ``""``. Handing a plugin ``Invocation(conversation_id="")`` would give it an
    id that can never resolve.

    ``HasField`` rather than truthiness on the sub-message, because protobuf
    returns a default-constructed message for an unset singular field rather
    than ``None`` — ``request.invocation`` is never falsy, and testing it
    directly would report every call as coming from a conversation.
    """
    try:
        present = request.HasField("invocation")
    except (AttributeError, ValueError):
        # A request type without the field at all — an older generated module,
        # or a hand-built stub in a test. Not an error: it is the same answer.
        return None
    if not present:
        return None
    conversation_id = request.invocation.conversation_id or None
    return Invocation(conversation_id=conversation_id) if conversation_id else None
