# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Authentication for the daemon → plugin direction.

The plugin → daemon direction lives in :mod:`astra_plugin_sdk.host_client`:
every host RPC after ``Register`` carries an ``x-session-token``. This module is
the mirror image — the guard on the plugin's own ``PluginCapabilityService``.

SECURITY: that server listens on loopback TCP with an OS-assigned port and used
to accept anything that reached it. Loopback is not a boundary between processes
of the same user: any local process — including another installed plugin, which
the daemon's threat model explicitly treats as untrusted — can scan for the port
and call ``OnConfigChanged`` (repointing this plugin's API base URL at an
attacker-controlled host, after which it posts its real credentials there),
``CallTool`` / ``ExecuteAction`` / ``CallFromUi`` (arbitrary execution under this
plugin's identity), or ``Shutdown`` (a one-RPC denial of service).

The secret needed to close that hole already existed: the daemon mints
``--auth-token`` per spawn and passes it on argv, so it is shared by exactly the
daemon and this process. It was simply never checked on the way *in* — only
echoed once in the outbound ``Register`` body.

The daemon now presents it on every call and says so, by setting
``ASTRA_PLUGIN_CAPABILITY_AUTH=require`` in the plugin's environment. So a plugin
under a current daemon enforces without anyone configuring it. The stages remain
because enforcing unilaterally would break a plugin against a daemon that does
not send the header, and such a daemon has no way to announce itself:

==========  =====================  ==============
stage       header absent          header wrong
==========  =====================  ==============
``warn``    accepted, warned once  rejected
``require`` rejected               rejected
``off``     accepted               accepted
==========  =====================  ==============

``warn`` is the default, and what an older daemon leaves a plugin in — the
variable's *absence* is the only signal that such a daemon gives.
"""

import hmac
import os
import sys

import grpc

#: Metadata header the plugin reads the daemon's copy of the spawn token from.
#: Must stay identical to the header the daemon attaches in
#: ``astra-daemon/src/plugins/client.rs``.
PLUGIN_TOKEN_HEADER = "x-plugin-token"

#: How the daemon states the stage: ``off``, ``warn`` or ``require``. Set to
#: ``require`` on every spawn by ``prepare_spawn`` in
#: ``astra-daemon/src/plugins/instance.rs``; absent under a daemon too old to
#: send the header, which is what leaves a plugin in ``warn``. Overrides the
#: value passed in code, which is what makes it useful to both.
CAPABILITY_AUTH_ENV = "ASTRA_PLUGIN_CAPABILITY_AUTH"

OFF = "off"
WARN = "warn"
REQUIRE = "require"

_SPELLINGS = {
    "off": OFF,
    "0": OFF,
    "false": OFF,
    "warn": WARN,
    "require": REQUIRE,
    "1": REQUIRE,
    "true": REQUIRE,
}


def capability_auth_mode(default: str = WARN) -> str:
    """Resolve the stage from the environment.

    An unparseable value is a typo, not a request to weaken the check, so it
    warns and keeps `default` rather than falling back to ``off``.
    """
    raw = os.environ.get(CAPABILITY_AUTH_ENV)
    if raw is None:
        return default
    mode = _SPELLINGS.get(raw.strip().lower())
    if mode is None:
        print(
            f"{CAPABILITY_AUTH_ENV}={raw!r} is not one of off|warn|require — keeping {default}",
            file=sys.stderr,
            flush=True,
        )
        return default
    return mode


def _deny_like(handler: grpc.RpcMethodHandler, details: str) -> grpc.RpcMethodHandler:
    """A handler with the same streaming shape as `handler` that aborts at once.

    The shape has to match: grpc dispatches on the *returned* handler's
    ``request_streaming`` / ``response_streaming``, so denying a bidi RPC with a
    unary handler would make the server sit waiting for a request message that a
    hostile caller has no reason to send.
    """
    code = grpc.StatusCode.UNAUTHENTICATED

    async def deny_unary(request, context):
        await context.abort(code, details)

    async def deny_stream(request, context):
        await context.abort(code, details)
        yield  # unreachable — `abort` raises; present so this is an async generator

    if handler.request_streaming and handler.response_streaming:
        return grpc.stream_stream_rpc_method_handler(
            deny_stream, handler.request_deserializer, handler.response_serializer
        )
    if handler.request_streaming:
        return grpc.stream_unary_rpc_method_handler(
            deny_unary, handler.request_deserializer, handler.response_serializer
        )
    if handler.response_streaming:
        return grpc.unary_stream_rpc_method_handler(
            deny_stream, handler.request_deserializer, handler.response_serializer
        )
    return grpc.unary_unary_rpc_method_handler(
        deny_unary, handler.request_deserializer, handler.response_serializer
    )


class CapabilityAuthInterceptor(grpc.aio.ServerInterceptor):
    """Requires the spawn-time ``--auth-token`` on every capability call.

    Inert when the plugin was started without a token (standalone, or under
    ``astra-plugin dev --standalone``): there is no shared secret to compare
    against, and a plugin with no daemon must still be runnable.
    """

    def __init__(self, auth_token: str, mode: str = WARN):
        self._token = auth_token or None
        self._mode = mode
        self._warned = False

    @property
    def active(self) -> bool:
        """Whether this interceptor checks anything. For startup logging only."""
        return self._token is not None and self._mode != OFF

    def _reject(self, metadata) -> str | None:
        """The abort message, or ``None`` to let the call through."""
        if not self.active:
            return None

        presented = None
        for key, value in metadata or ():
            if key == PLUGIN_TOKEN_HEADER:
                presented = value
                break

        if presented is not None:
            if hmac.compare_digest(str(presented), self._token):
                return None
            # Deliberately says nothing about which part was wrong.
            return (
                "invalid plugin token — this RPC did not come from the daemon "
                "that spawned this plugin"
            )

        if self._mode == REQUIRE:
            return (
                f"missing {PLUGIN_TOKEN_HEADER} — this plugin requires the daemon "
                "to authenticate capability calls"
            )

        # Accept-and-warn. Once, not once per RPC: the daemon calls into a plugin
        # constantly and a per-call warning would bury the log.
        if not self._warned:
            self._warned = True
            print(
                f"WARNING: capability call arrived without {PLUGIN_TOKEN_HEADER}. "
                "This daemon predates bidirectional plugin auth, so any local "
                "process can reach this plugin's tools, config and shutdown. "
                "Accepting it for compatibility; set "
                f"{CAPABILITY_AUTH_ENV}=require to refuse instead.",
                file=sys.stderr,
                flush=True,
            )
        return None

    async def intercept_service(self, continuation, handler_call_details):
        details = self._reject(handler_call_details.invocation_metadata)
        handler = await continuation(handler_call_details)
        if details is None or handler is None:
            return handler
        return _deny_like(handler, details)
