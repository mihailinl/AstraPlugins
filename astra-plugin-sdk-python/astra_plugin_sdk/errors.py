"""The plugin error taxonomy — eight ways a handler can fail, spelled in Python.

WHY THIS EXISTS (production plan §5.2)

A tool that fails because the user never pasted an API key is not the same event
as a tool that fails because the model sent nonsense, and neither is the same as
the remote service being down. Until now all three arrived at the daemon as one
`string error` and the UI could do nothing with any of them but print it. The
taxonomy below gives each failure a code the daemon can act on, plus the three
pieces of data that make a failure actionable rather than merely legible:

    config_field   which `[config]` key is missing — the UI deep-links to it
    retry_after    how long to wait — the AI loop can back off instead of
                   hammering a rate limiter
    doc_url        where the author documented this failure

IN-BAND, NOT A TRANSPORT ERROR. A failed tool call is *data the AI loop must
read*: "you have no API key configured" is a fact the model needs in order to
tell the user what to do. So `CallTool` still answers `success=false` with the
detail attached, and gRPC `Status` stays reserved for the transport (the plugin
died, the descriptor is wrong, the daemon hung up). `grpc_status()` gives the
fixed mapping for the places where a `Status` is genuinely the right answer —
the streaming hooks, which have no in-band failure slot at all.

BOTH HALVES ON THE WIRE. Every response this module fills in carries the legacy
`string error` *and* the structured field, so a daemon that predates the
structured half still shows a human sentence and a daemon that has it gets the
machine-readable one. That is the whole compatibility story; there is no
version negotiation to get wrong.

IDIOM. Python gets exceptions, because Python handlers already signal failure by
raising and `raise NotConfigured("api_key")` is the shortest correct thing an
author can type. The Rust SDK gets an enum and `?`; TypeScript gets narrowing
error classes (`errors.ts`). The three are the same eight variants with the same
codes on the wire — `spec/hooks.yaml` cannot enforce that for you, so it is
enforced by all three tables being generated from this same list of names.

USAGE

    from astra_plugin_sdk import NotConfigured, RateLimited, tool

    @tool("Look up the weather")
    async def weather(self, city: str):
        key = self.config.get("api_key")
        if not key:
            raise NotConfigured("api_key", "Set your OpenWeather API key")
        if self._budget_spent():
            raise RateLimited(retry_after=30.0)
        ...

The SDK catches `PluginError` around every tool, action and UI call and turns it
into the response above. An exception that is *not* a `PluginError` is still
caught, and reported as `INTERNAL` — an author who never reads this module keeps
exactly the behaviour they had.
"""

from __future__ import annotations

import enum
import math
import traceback
from typing import Any, ClassVar

import grpc

from astra_plugin_sdk.proto import plugin_pb2

__all__ = [
    "ErrorCode",
    "PluginError",
    "BadArguments",
    "NotFound",
    "NotConfigured",
    "Unauthorized",
    "RateLimited",
    "Unavailable",
    "Timeout",
    "InternalError",
    "ToolError",
    "ActionError",
    "structured_errors_supported",
]


class ErrorCode(str, enum.Enum):
    """The eight codes, byte-identical across the three SDKs.

    The value is the wire spelling: the suffix of the generated proto enum
    variant (`..._BAD_ARGUMENTS`), and the string TypeScript narrows on. Making
    it a `str` enum means `error.code == "NOT_CONFIGURED"` works without an
    import, which is what a test written by a plugin author will do.
    """

    BAD_ARGUMENTS = "BAD_ARGUMENTS"
    NOT_FOUND = "NOT_FOUND"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INTERNAL = "INTERNAL"


#: Transport mapping, fixed. Used only where there is no in-band failure slot —
#: the server-streaming hooks. A unary hook must NOT use this: turning a missing
#: API key into a gRPC `FAILED_PRECONDITION` hides it from the AI loop, which is
#: the reader that most needs it.
_GRPC_STATUS: dict[ErrorCode, grpc.StatusCode] = {
    ErrorCode.BAD_ARGUMENTS: grpc.StatusCode.INVALID_ARGUMENT,
    ErrorCode.NOT_FOUND: grpc.StatusCode.NOT_FOUND,
    ErrorCode.NOT_CONFIGURED: grpc.StatusCode.FAILED_PRECONDITION,
    ErrorCode.UNAUTHORIZED: grpc.StatusCode.PERMISSION_DENIED,
    ErrorCode.RATE_LIMITED: grpc.StatusCode.RESOURCE_EXHAUSTED,
    ErrorCode.UNAVAILABLE: grpc.StatusCode.UNAVAILABLE,
    ErrorCode.TIMEOUT: grpc.StatusCode.DEADLINE_EXCEEDED,
    ErrorCode.INTERNAL: grpc.StatusCode.INTERNAL,
}


# ── the generated structured message, if this proto slice carries one ────────
#
# The structured half of §5.2 is `astra.PluginError`, a message owned by
# `astra-proto/src/astra.proto` in the Astra repo; `proto/plugin.proto` here is
# a GENERATED slice of it and this SDK does not get to add fields to either. So
# the binding is resolved by SHAPE, not by name: the message that carries every
# field this taxonomy sets — `code`, `message`, `hint`, `config_field`,
# `retry_after_ms`, `doc_url` — with an enum variant for each of the eight
# codes, is the taxonomy's message.
#
# Resolving it by shape rather than by `plugin_pb2.PluginError` is what keeps
# this file honest about the one thing it cannot control. The taxonomy's codes
# (4-11) share an enum with the registration refusals (1-3) — a deliberate proto
# decision — so a name lookup would happily bind to a build of the proto that
# has the message and none of the eight codes, and produce `code: 0` on the
# wire. The shape test cannot: it requires all eight or it binds nothing, and
# then `to_proto()` answers None and only the legacy `string error` goes out.
# That fallback is not a degraded mode invented here — it is exactly what an
# older daemon sees forever, so it is a path that has to work anyway.

_STRUCTURED_FIELDS = frozenset({"code", "message", "hint", "config_field", "retry_after_ms", "doc_url"})


def _resolve_structured() -> tuple[Any, dict[str, int]] | tuple[None, dict[str, int]]:
    for name in dir(plugin_pb2):
        cls = getattr(plugin_pb2, name, None)
        desc = getattr(cls, "DESCRIPTOR", None)
        fields = getattr(desc, "fields", None)
        if not fields:
            continue
        names = {f.name for f in fields}
        if not _STRUCTURED_FIELDS <= names:
            continue
        code_field = desc.fields_by_name["code"]
        enum_type = getattr(code_field, "enum_type", None)
        if enum_type is None:
            continue
        # Match each taxonomy code to the enum variant whose name ends with it.
        # A generated variant is prefixed (`PLUGIN_ERROR_CODE_NOT_FOUND`), and
        # which prefix the proto settles on is not this SDK's decision to make.
        values: dict[str, int] = {}
        for code in ErrorCode:
            for v in enum_type.values:
                if v.name.endswith(code.value):
                    values[code.value] = v.number
                    break
        if len(values) == len(ErrorCode):
            return cls, values
    return None, {}


_STRUCTURED_CLS, _STRUCTURED_CODES = _resolve_structured()


def structured_errors_supported() -> bool:
    """True when this build's proto carries the structured error message.

    A plugin never needs to ask — `to_response()` fills in whatever is there.
    It is public so the conformance harness (5.7) can assert on it instead of
    inferring it from an empty field.
    """
    return _STRUCTURED_CLS is not None


def _find_detail_field(message_cls: Any) -> str | None:
    """Name of `message_cls`'s field holding the structured error, if any."""
    if _STRUCTURED_CLS is None:
        return None
    wanted = _STRUCTURED_CLS.DESCRIPTOR.full_name
    for field in message_cls.DESCRIPTOR.fields:
        if field.message_type is not None and field.message_type.full_name == wanted:
            return field.name
    return None


def _traceback_for(exc: BaseException) -> str:
    """The formatted traceback of `exc`, or "" when it has none.

    `traceback.format_exception` on the exception object rather than
    `format_exc()` on the ambient one: a handler that catches, wraps and
    re-raises would otherwise attach the wrong stack, and the whole point of
    this string is that it names the line that actually failed.
    """
    if exc.__traceback__ is None:
        return ""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()


# ── the taxonomy ─────────────────────────────────────────────────────────────


class PluginError(Exception):
    """Base of the eight. Catch this to catch every taxonomy failure.

    Raising `PluginError` directly is legal and means `INTERNAL`; prefer a
    subclass, because the subclass is what the daemon can act on.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL
    #: Default sentence when the author gives none. One line, no trailing dot —
    #: the daemon composes it into its own copy.
    default_message: ClassVar[str] = "The plugin failed"

    def __init__(
        self,
        message: str = "",
        *,
        config_field: str = "",
        retry_after: float | None = None,
        doc_url: str = "",
        detail: str = "",
    ):
        self.message = message or self.default_message
        #: Diagnostics for the plugin's author — the Python traceback, when this
        #: error was adopted from an exception (§5.10). Deliberately NOT part of
        #: `to_dict()`, `to_error_string()` or `to_proto()`: `astra.PluginError`
        #: has no field for it, and the legacy `string error` is read by the AI
        #: loop, which must not be fed a stack trace. It travels to the daemon as
        #: a `PluginLog` line at error level, which is what the per-plugin log
        #: file and the "Copy diagnostics" button are for.
        self.detail = detail
        #: The `[config]` key the user has to fill in. Only meaningful for
        #: `NOT_CONFIGURED`, where it is a deep-link target in the settings UI.
        self.config_field = config_field
        #: Seconds to wait before retrying, or None. Only meaningful for
        #: `RATE_LIMITED`.
        self.retry_after = retry_after
        #: Where the author documented this failure. Rendered as a link.
        self.doc_url = doc_url
        super().__init__(self.message)

    # ── projections ──

    @property
    def retry_after_ms(self) -> int:
        """`retry_after` in whole milliseconds; 0 when unset.

        Rounded UP: a floor would tell a caller to retry fractionally before the
        window it was told to wait for, which is the one thing a retry hint must
        never do.
        """
        if self.retry_after is None or self.retry_after <= 0:
            return 0
        return int(math.ceil(self.retry_after * 1000.0))

    def to_dict(self) -> dict[str, Any]:
        """The structured half as plain data — always available, proto or not.

        Same key spelling as the proto fields, so a test can assert on one shape
        whether or not the daemon build in front of it has the message.
        """
        return {
            "code": self.code.value,
            "message": self.message,
            "hint": self.hint(),
            "config_field": self.config_field,
            "retry_after_ms": self.retry_after_ms,
            "doc_url": self.doc_url,
        }

    def to_proto(self) -> Any | None:
        """The structured error as its generated protobuf message.

        Returns None when this build's `proto/plugin.proto` has no such message
        — see the note above `_resolve_structured`. Callers should use
        :meth:`to_response` instead, which does the right thing either way.
        """
        if _STRUCTURED_CLS is None:
            return None
        return _STRUCTURED_CLS(
            code=_STRUCTURED_CODES[self.code.value],
            message=self.message,
            hint=self.hint(),
            config_field=self.config_field,
            retry_after_ms=self.retry_after_ms,
            doc_url=self.doc_url,
        )

    def hint(self) -> str:
        """What to DO about it, or "" when there is nothing useful to say.

        Only two of the eight can say anything an actor could follow, and
        inventing sentences for the rest would be noise in a log pane.
        """
        if self.config_field:
            return f"Set `{self.config_field}` in this plugin's settings, then try again."
        if self.retry_after is not None and self.retry_after > 0:
            return f"Retry in {max(1, int(self.retry_after))} s."
        return ""

    def to_error_string(self) -> str:
        """The legacy `string error` — the whole signal on an older daemon.

        `CODE: message (hint)`, byte-for-byte the shape the Rust SDK's
        `ToolError::wire_string` produces, because the AI loop reads this string
        and a plugin's language must not change what the model sees. The code is
        prefixed on purpose: `NOT_CONFIGURED: …` tells the loop to stop retrying,
        which a bare sentence does not.
        """
        text = f"{self.code.value}: {self.message}"
        hint = self.hint()
        if hint:
            text = f"{text} ({hint})"
        return text

    def to_response(self, message_cls: Any, **fields: Any) -> Any:
        """Build a failure response of `message_cls`, both halves populated.

        `success=False` and the legacy string are always set; the structured
        field is set when the response message has one.
        """
        kwargs: dict[str, Any] = dict(fields)
        names = {f.name for f in message_cls.DESCRIPTOR.fields}
        if "success" in names:
            kwargs.setdefault("success", False)
        if "error" in names:
            kwargs["error"] = self.to_error_string()
        detail_field = _find_detail_field(message_cls)
        if detail_field is not None:
            kwargs[detail_field] = self.to_proto()
        return message_cls(**kwargs)

    def grpc_status(self) -> grpc.StatusCode:
        """The transport status for this code. Fixed table; see `_GRPC_STATUS`.

        Use it only where the hook has no in-band failure slot — the streaming
        hooks. On a unary hook, prefer :meth:`to_response`.
        """
        return _GRPC_STATUS[self.code]

    def abort(self, context: grpc.aio.ServicerContext) -> None:
        """Fail a streaming RPC with this error's status and message."""
        context.set_code(self.grpc_status())
        context.set_details(self.to_error_string())

    # ── adoption ──

    @classmethod
    def from_exception(cls, exc: BaseException) -> "PluginError":
        """Adopt any exception into the taxonomy.

        Already-taxonomy errors pass through untouched. The four built-ins that
        have an obvious code get it — a `ValueError` out of `json.loads` or a
        `TypeError` from calling a tool with the wrong arguments really is
        `BAD_ARGUMENTS`, and reporting it as `INTERNAL` sends the reader to the
        wrong half of the system. Everything else is `INTERNAL`, which is the
        honest answer for an exception nobody classified.

        `BaseException`, not `Exception`, in the annotation and in fact: §5.10
        has every handler catch the wider type, and `sys.exit()` inside a tool —
        which raises `SystemExit`, not an `Exception` — used to escape the
        servicer and take the whole gRPC handler with it.

        The traceback lands in :attr:`detail`, formatted here rather than at each
        call site so that every catch site gets it without remembering to.
        """
        if isinstance(exc, PluginError):
            if not exc.detail:
                exc.detail = _traceback_for(exc)
            return exc
        detail = _traceback_for(exc)
        if isinstance(exc, (ValueError, TypeError)):
            return BadArguments(str(exc) or type(exc).__name__, detail=detail)
        if isinstance(exc, KeyError):
            return NotFound(str(exc) or "not found", detail=detail)
        if isinstance(exc, TimeoutError):
            return Timeout(str(exc) or "the operation timed out", detail=detail)
        if isinstance(exc, PermissionError):
            return Unauthorized(str(exc) or "permission denied", detail=detail)
        return InternalError(str(exc) or type(exc).__name__, detail=detail)


class BadArguments(PluginError):
    """The caller's arguments were wrong — bad JSON, missing key, bad value.

    The model is a caller. This is the code that tells it to try again with
    different arguments, so the message should say what was wrong with them.
    """

    code = ErrorCode.BAD_ARGUMENTS
    default_message = "Invalid arguments"


class NotFound(PluginError):
    """The thing named by the arguments does not exist."""

    code = ErrorCode.NOT_FOUND
    default_message = "Not found"


class NotConfigured(PluginError):
    """A required setting is missing or empty.

    The one variant whose first argument is the field, not the message:
    `NotConfigured("api_key")` is the whole call, and the field is what makes
    the UI able to link straight at the input the user has to fill in.
    """

    code = ErrorCode.NOT_CONFIGURED
    default_message = "Not configured"

    def __init__(
        self,
        config_field: str = "",
        message: str = "",
        *,
        doc_url: str = "",
        detail: str = "",
    ):
        super().__init__(
            # Same sentence the Rust SDK's `ToolError::not_configured` produces.
            # The model reads this string; it must not depend on which language
            # the plugin happens to be written in.
            message or (f"required setting `{config_field}` is not set" if config_field else ""),
            config_field=config_field,
            doc_url=doc_url,
            detail=detail,
        )


class Unauthorized(PluginError):
    """The credentials the plugin holds were refused by whatever it called.

    Distinct from `NOT_CONFIGURED`: the key is there, and it is wrong or
    expired. The user's next action is different, so the code is different.
    """

    code = ErrorCode.UNAUTHORIZED
    default_message = "Unauthorized"


class RateLimited(PluginError):
    """A quota was exhausted. `retry_after` is in seconds and may be fractional."""

    code = ErrorCode.RATE_LIMITED
    default_message = "Rate limited"

    def __init__(
        self,
        message: str = "",
        *,
        retry_after: float | None = None,
        doc_url: str = "",
        detail: str = "",
    ):
        super().__init__(
            message, retry_after=retry_after, doc_url=doc_url, detail=detail
        )


class Unavailable(PluginError):
    """A dependency the plugin needs is down. Transient by claim; retry may work."""

    code = ErrorCode.UNAVAILABLE
    default_message = "Temporarily unavailable"


class Timeout(PluginError):
    """The operation did not finish in time."""

    code = ErrorCode.TIMEOUT
    default_message = "The operation timed out"


class InternalError(PluginError):
    """A bug in the plugin. Not the user's fault and not the model's.

    Named `InternalError` rather than `Internal` because a bare `Internal` in an
    author's `except` clause reads like a namespace, not an error.
    """

    code = ErrorCode.INTERNAL
    default_message = "Internal plugin error"


#: The plan spells the tool-facing alias `ToolError` and defines
#: `ActionError = ToolError`. In Python there is one hierarchy and these are the
#: names an author reaches for in an `except` clause.
ToolError = PluginError
ActionError = PluginError
