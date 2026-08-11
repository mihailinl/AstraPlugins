# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Startup assertion: no field this protocol RETIRED is live in the loaded proto.

WHY (production plan §5.8)

Phase 1 sliced `proto/plugin.proto` out of the daemon's `astra.proto` and carried
the daemon's `reserved` declarations across verbatim — field numbers *and* names.
A reserved name is a promise: `AiSettings.use_thinking` was deleted, its meaning
is gone, and nothing may ever reuse that name for something else.

The three SDKs learn about a broken promise very differently:

    Rust        `settings.use_thinking` does not compile. Caught at build time.
    Python      `settings.use_thinking` raises `AttributeError` — but only on the
                line that touches it, which is typically inside the one handler
                that runs when a user changes a setting. A plugin that builds,
                registers, reports healthy and then fails a week later, in the
                field, at the worst moment.
    TypeScript  yields `undefined`, and nothing raises at all.

This module closes the Python half. It runs once, before the plugin binds its
port, and refuses to start on a proto build where a retired name came back.

WHAT IT ACTUALLY CATCHES, GIVEN protoc REFUSES SUCH A FILE
`protoc` will not compile a `.proto` in which a field's name collides with that
message's own `reserved` list — so the checked-in pair cannot be inconsistent.
What is NOT guaranteed is that the `plugin_pb2` a plugin *loads at runtime* came
from the `plugin.proto` next to it:

  * a stale `plugin_pb2.py` left over from an 0.4-era generation, where
    `use_thinking` was still a live field, sitting earlier on `sys.path`;
  * a vendored copy of the SDK inside another package, generated from a
    different slice, winning the import;
  * a descriptor-pool collision where a *different* `astra.AiSettings` is
    registered first and the SDK binds to that one.

All three produce a process that starts, registers, and is wrong. The check is
against the loaded descriptors, so all three are caught the same way.

`REGISTRY` below is transcribed from the `reserved "..."` declarations in
`proto/plugin.proto`; `tests/test_reserved.py` re-derives it from that file and
fails if the two drift, which is what stops this list from quietly rotting into
a check of nothing.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Mapping

from astra_plugin_sdk.proto import plugin_pb2

__all__ = [
    "REGISTRY",
    "ReservedNameError",
    "assert_no_reserved_names",
    "parse_reserved_names",
]


#: message name -> the field names that message has retired forever.
#: Transcribed from `reserved "..."` in `proto/plugin.proto`.
REGISTRY: Mapping[str, frozenset[str]] = {
    "SemanticSettings": frozenset({"mode", "llm_model_id", "memory_enabled"}),
    "AiSettings": frozenset({"use_thinking"}),
    "HotkeySettings": frozenset({"toggle_listen", "stop_speaking", "open_chat"}),
}


class ReservedNameError(RuntimeError):
    """A retired field name is live in the protobuf module this process loaded."""


def _live_fields(message_name: str) -> frozenset[str] | None:
    """Field names of `message_name` in the loaded module, or None if absent."""
    cls = getattr(plugin_pb2, message_name, None)
    descriptor = getattr(cls, "DESCRIPTOR", None)
    if descriptor is None:
        return None
    return frozenset(f.name for f in descriptor.fields)


def assert_no_reserved_names(
    registry: Mapping[str, Iterable[str]] | None = None,
    live_fields: Callable[[str], frozenset[str] | None] | None = None,
) -> None:
    """Raise `ReservedNameError` if the loaded proto revives a retired name.

    Also raises when a message in `REGISTRY` is not in the loaded module at all.
    That is deliberate: a check that scans nothing reports success, and "the
    message was renamed and nobody updated this file" must not be the same
    outcome as "the promise holds". The registry is small and it is transcribed
    from a generated file — if a rename happens, this is the reminder.
    """
    # Resolved here rather than as default arguments: a default binds the
    # object at def time, so `reserved.REGISTRY = {...}` would silently have no
    # effect — and a check whose configuration cannot be changed is a check that
    # cannot be tested against a proto other than the one in front of it.
    registry = REGISTRY if registry is None else registry
    live_fields = _live_fields if live_fields is None else live_fields

    problems: list[str] = []
    for message_name, reserved in registry.items():
        fields = live_fields(message_name)
        if fields is None:
            problems.append(
                f"{message_name}: not present in the loaded protobuf module — "
                f"astra_plugin_sdk.reserved.REGISTRY needs updating for a proto "
                f"that renamed or dropped it"
            )
            continue
        revived = sorted(set(reserved) & fields)
        if revived:
            problems.append(
                f"{message_name}: reserved field name(s) {', '.join(revived)} are "
                f"live fields"
            )

    if not problems:
        return

    raise ReservedNameError(
        "The protobuf module this plugin loaded disagrees with the protocol "
        "about fields that were retired:\n  "
        + "\n  ".join(problems)
        + "\n\nThis is almost always a stale or foreign `plugin_pb2` winning the "
        "import: an older astra-plugin-sdk earlier on sys.path, or a copy "
        "vendored inside another package. Reading such a field would give the "
        "wrong answer rather than an error, so the plugin refuses to start.\n"
        f"Loaded from: {getattr(plugin_pb2, '__file__', '<unknown>')}"
    )


# ── keeping REGISTRY honest ──────────────────────────────────────────────────

_MESSAGE_RE = re.compile(r"^\s*message\s+(\w+)\s*\{")
_RESERVED_RE = re.compile(r'^\s*reserved\s+("(?:[^"]*"\s*,\s*")*[^"]*")\s*;')


def parse_reserved_names(proto_text: str) -> dict[str, frozenset[str]]:
    """Every `reserved "name", ...` in a .proto, by owning message.

    A deliberately small parser — the same reasoning as `tools/parity/spec.py`.
    It tracks the most recent top-level `message X {`, which is all the file
    needs: no `reserved` name declaration in `plugin.proto` sits inside a nested
    message, and `tests/test_reserved.py` asserts the count it finds so a parser
    that silently matches nothing fails instead of agreeing with everything.
    """
    found: dict[str, set[str]] = {}
    current = ""
    for line in proto_text.splitlines():
        m = _MESSAGE_RE.match(line)
        if m:
            current = m.group(1)
            continue
        r = _RESERVED_RE.match(line)
        if r and current:
            names = re.findall(r'"([^"]+)"', r.group(1))
            found.setdefault(current, set()).update(names)
    return {k: frozenset(v) for k, v in found.items()}


def vendored_proto_text() -> str:
    """The `plugin.proto` shipped inside this package."""
    from pathlib import Path

    return (Path(__file__).parent / "proto" / "plugin.proto").read_text(encoding="utf-8")
