# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""**Which daemon call a trigger was fired from.**

A plugin action runs inside a command run a user started by typing in a chat.
The plugin fires a trigger, which starts a *second* command run — and that run
has no idea what caused it, so its output is filed into a freshly auto-created
conversation the user never sees. With two chats driving one plugin at once,
nothing on the wire even distinguishes them.

The daemon's answer is a per-invocation lease: an opaque token it mints when it
calls into a plugin, carried as gRPC call metadata under ``spec/wire.yaml``'s
``x-astra-cause``. The plugin echoes it on ``FireTrigger``, the daemon redeems
it, and the trigger's output goes where the user is looking.

This module is the ambient half of that: a :class:`contextvars.ContextVar` set
around every capability call and read by :meth:`HostClient.fire_trigger`.
Neither the plugin author nor the ``Plugin`` subclass writes a line for it.

Why a ``ContextVar`` here and a scoped handle in Rust
----------------------------------------------------

A ``ContextVar`` is copied into every task ``asyncio`` creates, so it survives
``await``, ``asyncio.create_task`` and ``asyncio.gather``. Rust has no
equivalent that survives ``tokio::spawn`` — which is exactly what the shipped
reference plugin does — so the Rust SDK carries the cause inside the host handle
instead. Same guarantee, opposite mechanism, because the two languages differ in
what "later" is allowed to mean.

Where it does NOT reach
-----------------------

**``loop.run_in_executor`` does not copy the context.** A handler that hands work
to a thread pool and fires from there gets no cause, and the daemon files the
trigger as a root event. That is stated rather than papered over: a wrong
conversation is worse than an unattributed one, and there is no way to guess
which of several in-flight calls a pool thread belongs to. An author who needs
the attribution should fire from the coroutine, or carry it across explicitly::

    ctx = contextvars.copy_context()
    await loop.run_in_executor(None, lambda: ctx.run(work))

The same applies to ``multiprocessing``, a raw ``threading.Thread``, and a
callback scheduled by a C extension on its own thread.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterable
from typing import Any

import grpc

from astra_plugin_sdk.wire import X_ASTRA_CAUSE

__all__ = ["CauseInterceptor", "current_cause", "cause_from_metadata", "set_cause"]

#: The lease for the daemon call being handled on this task, or ``None``.
_CAUSE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "astra_invocation_cause", default=None
)


def current_cause() -> str | None:
    """The invocation lease in scope, or ``None`` for a root event.

    ``None`` is a legal, common answer and must never be papered over: the
    daemon has to be able to tell "this plugin sent no lease" from "this plugin
    sent a lease I cannot resolve", and only the second is a bug.
    """
    return _CAUSE.get()


def set_cause(cause: str | None) -> None:
    """Bind the lease for the current context.

    Called by the capability servicer at the top of each handler coroutine. It
    deliberately does not restore a previous value: each RPC runs in its own
    task with its own copy of the context, so there is nothing to leak into and
    nothing to put back.
    """
    _CAUSE.set(cause)


def cause_from_metadata(metadata: Iterable[Any] | None) -> str | None:
    """The lease off an inbound call's metadata, or ``None``.

    gRPC metadata keys are lower-cased at the transport, so the generated
    constant matches as written. A binary (``-bin``) value would arrive as
    ``bytes``; the spec's grammar refuses that suffix, so anything that is not a
    non-empty ``str`` here is not a lease this daemon minted and is treated as
    no lease at all.
    """
    for key, value in metadata or ():
        if key == X_ASTRA_CAUSE:
            return value if isinstance(value, str) and value else None
    return None


def _with_cause(handler: grpc.RpcMethodHandler, cause: str) -> grpc.RpcMethodHandler:
    """`handler`, with `cause` bound before its body runs.

    The streaming shape has to be preserved exactly: grpc dispatches on the
    *returned* handler's ``request_streaming`` / ``response_streaming``, so
    wrapping a bidi RPC in a unary handler would leave the server waiting for a
    request message that will never come. This mirrors ``auth._deny_like``,
    which learned the same lesson.
    """
    if handler.request_streaming and handler.response_streaming:

        async def stream_stream(request_iterator, context):
            set_cause(cause)
            async for item in handler.stream_stream(request_iterator, context):
                yield item

        return grpc.stream_stream_rpc_method_handler(
            stream_stream, handler.request_deserializer, handler.response_serializer
        )

    if handler.request_streaming:

        async def stream_unary(request_iterator, context):
            set_cause(cause)
            return await handler.stream_unary(request_iterator, context)

        return grpc.stream_unary_rpc_method_handler(
            stream_unary, handler.request_deserializer, handler.response_serializer
        )

    if handler.response_streaming:

        async def unary_stream(request, context):
            set_cause(cause)
            async for item in handler.unary_stream(request, context):
                yield item

        return grpc.unary_stream_rpc_method_handler(
            unary_stream, handler.request_deserializer, handler.response_serializer
        )

    async def unary_unary(request, context):
        set_cause(cause)
        return await handler.unary_unary(request, context)

    return grpc.unary_unary_rpc_method_handler(
        unary_unary, handler.request_deserializer, handler.response_serializer
    )


class CauseInterceptor(grpc.aio.ServerInterceptor):
    """Binds the invocation lease around every capability call.

    One interceptor rather than a decorator on each of the twenty-odd servicer
    methods, and it covers every arm rather than only the three the daemon
    stamps today. A rule naming specific arms goes stale in silence: a fourth
    stamped call site would produce a lease this SDK receives and drops, with
    nothing anywhere reporting it.

    A call with no lease is returned untouched, so the common path — every
    daemon in the field — allocates nothing and rebuilds no handler.
    """

    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler
        cause = cause_from_metadata(handler_call_details.invocation_metadata)
        if cause is None:
            return handler
        return _with_cause(handler, cause)
