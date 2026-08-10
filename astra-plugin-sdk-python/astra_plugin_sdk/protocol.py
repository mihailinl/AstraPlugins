"""The plugin wire-protocol handshake.

Before this existed there was no version anywhere in either direction, so an old
plugin meeting a new daemon (or the reverse) failed at the first RPC one side did
not have — with an error that named neither the cause nor the fix. Registration
now carries an integer both ways, and the mismatch is decided once, at the
handshake, by :func:`evaluate`.
"""

from astra_plugin_sdk.proto import plugin_pb2

#: The wire-protocol generation this SDK speaks.
#:
#: One integer, in four places that must agree: here, ``proto/PROTO_VERSION``
#: (``protocol=``), the ``// protocol: N`` header of the generated
#: ``plugin.proto``, and the daemon's ``PLUGIN_PROTOCOL_VERSION``. The Rust and
#: TypeScript SDKs carry the same constant under the same name.
PROTOCOL_VERSION = 1

#: The oldest daemon protocol this SDK will serve.
#:
#: The mirror image of the daemon's own floor. A daemon below this would have the
#: SDK calling host RPCs it does not implement, so the plugin says so once and
#: exits instead of running half-broken.
#:
#: **``0`` is allowed on purpose, and that is not the same as having no floor.**
#: Protocol 1 *is* the pre-handshake plugin surface: Astra v0.1.0 — the only
#: released Astra — has a byte-identical ``PluginHostService``, already carries
#: every plugin-facing field this SDK sends, and already issues a per-plugin
#: session token to *every* plugin (``host_service.rs``, ``SECURITY(B1)``). It
#: simply predates the ``protocol_version`` field, and proto3 delivers an absent
#: field as ``0``. A floor of 1 would therefore refuse the one daemon that can
#: serve this SDK perfectly, on the grounds that it never learned to say so.
#:
#: The capability this SDK genuinely needs is checked directly rather than
#: inferred from an integer: :mod:`astra_plugin_sdk.plugin` fails closed on an
#: empty ``client_session_token`` right after :func:`evaluate`, because that —
#: not a version number — is what decides whether any host RPC can succeed.
#:
#: Raise this to 2 in the release where the SDK starts calling something protocol
#: 1 does not have. The ``< floor`` branch below and its sentence stay live for
#: exactly that day; :func:`evaluate`'s ``floor`` argument rehearses it now.
MIN_SUPPORTED_DAEMON_PROTOCOL = 0

#: Reported to the daemon for support triage only; never gates anything.
SDK_NAME = "astra-plugin-sdk-python"

#: Exit code for a protocol mismatch: ``EX_CONFIG`` from ``sysexits.h``.
#:
#: Deliberately not 1. The daemon logs a plugin's exit code, and "the
#: configuration of this machine is wrong" is exactly the right category —
#: nothing about retrying, restarting or the plugin's own logic will change the
#: outcome until somebody installs a different build.
EXIT_PROTOCOL_INCOMPATIBLE = 78


def sdk_version() -> str:
    """This package's own release, alongside :data:`SDK_NAME`.

    Imported lazily from the package root: ``astra_plugin_sdk/__init__.py``
    imports this module's siblings, so a module-level import would be circular.
    """
    from astra_plugin_sdk import __version__

    return __version__


def evaluate(
    response: "plugin_pb2.PluginRegisterResponse",
    floor: int = MIN_SUPPORTED_DAEMON_PROTOCOL,
) -> str | None:
    """Decide whether this SDK can serve the daemon that just answered Register.

    Returns ``None`` to proceed, or the one sentence the plugin should print
    before exiting :data:`EXIT_PROTOCOL_INCOMPATIBLE`.

    ``floor`` defaults to :data:`MIN_SUPPORTED_DAEMON_PROTOCOL` and exists so a
    test can ask the real question — "what does an SDK whose floor is 2 see from
    a daemon that reports 0?" — without waiting for the release that raises the
    shipped floor. The mirror of the daemon's own ``check_protocol_against``.

    Pure, so the rule is testable without a daemon and a socket. Two ways it can
    fail, and they are not the same failure:

    * **The daemon refused us** for being too old. It told us its floor, so the
      sentence can name the number this plugin has to reach.
    * **The daemon is older than this SDK's floor.** Nothing refused anything —
      it is the SDK that would start calling RPCs the daemon lacks. Stop before
      doing that.

    Anything else (a refusal for a bad auth token, an unknown plugin id) is not a
    protocol matter and is left to the caller's ordinary error path.
    """
    detail = response.error_detail
    if detail.code == plugin_pb2.PLUGIN_ERROR_PROTOCOL_TOO_OLD:
        # The daemon's own words first — it knows its floor, and it is the side
        # that decided. The hint is what the author acts on.
        sentence = detail.message or (
            f"This plugin speaks Astra plugin protocol {PROTOCOL_VERSION}, which this Astra "
            f"no longer accepts (it needs {response.min_supported_protocol} or newer)."
        )
        if detail.hint:
            sentence = f"{sentence} {detail.hint}"
        return sentence

    if response.protocol_version < floor:
        reported = (
            "did not report a protocol version at all"
            if response.protocol_version == 0
            else f"speaks protocol {response.protocol_version}"
        )
        return (
            f"This Astra {reported}, and this plugin needs protocol {floor} or newer — update "
            f"Astra, or install a build of this plugin made for the Astra you have."
        )

    return None
