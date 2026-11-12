# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""The seven types a capability hook answers with (production plan §5.8).

WHY THESE EXIST

Until now every one of the seven capability hooks returned a `list[dict]`, and
the servicer turned each dict into a protobuf message with `Msg(**d)`. That has
three failure modes, all of which shipped:

  * **A typo is a runtime error at the wrong moment.** `{"preview_ur": ...}`
    raises `ValueError: Protocol message PluginVoiceInfo has no "preview_ur"
    field` — from inside the gRPC servicer, on the daemon's first `TtsListVoices`
    call, which is well after the plugin reported itself healthy.
  * **`**d` does not build sub-messages.** A `FieldDefinitionMsg` with nested
    `options` / `conditions` needed a bespoke converter (`_field_dict_to_proto`)
    that the other six hooks did not have, so an `ActionTypeDefinitionMsg` with
    nested `fields` was quietly unbuildable.
  * **No editor could help.** No completion, no types, nothing for `py.typed` to
    export.

So each of the seven is a dataclass with `to_proto()` / `from_proto()`. The
author sees real attributes; the SDK owns the proto, exactly as in the Rust SDK,
and the day the slice grows a field the change lands here rather than in every
plugin.

DICTS STILL WORK, FOR ONE MINOR
`coerce()` accepts a dict and emits a `DeprecationWarning` naming the hook. Every
Python plugin in the field returns dicts; breaking them at import time to win a
type annotation would be a bad trade. The SDK's own `@tool` / `@action` /
`@trigger` decorators and the `Field` builder now produce these dataclasses, so
a plugin that uses the SDK's helpers never sees the warning — only a hand-rolled
`return [{...}]` does, which is precisely the code that has to change.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Iterable, TypeVar

from astra_plugin_sdk.proto import plugin_pb2

__all__ = [
    "ToolDef",
    "VoiceInfo",
    "AiModelHints",
    "AiModelInfo",
    "AiModelList",
    "DropdownOption",
    "FieldCondition",
    "FieldDef",
    "ActionTypeDef",
    "TriggerTypeDef",
    "UiContribution",
    "DesktopWidget", "WidgetFormat", "WidgetSurface", "WidgetContext",
    "coerce",
    "coerce_all",
]

T = TypeVar("T")


class _CapabilityType:
    """Shared conversion behaviour. Every subclass is a dataclass.

    `_PROTO` is the generated message class this type mirrors. Subclasses that
    hold nested capability types override `_from_dict` rather than reimplementing
    the whole thing.
    """

    #: The generated message this dataclass mirrors.
    _PROTO: Any = None

    def to_proto(self) -> Any:
        raise NotImplementedError

    @classmethod
    def from_proto(cls, msg: Any):
        raise NotImplementedError

    @classmethod
    def _from_dict(cls, data: dict):
        """Build from a legacy dict. Unknown keys are an error, not a shrug.

        Silently dropping `{"preview_ur": ...}` would turn a typo into a voice
        with no preview and no complaint, which is strictly worse than the
        `ValueError` this replaces — the point of the message below is to say
        *which* hook and *which* key, which the protobuf one never did.
        """
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = sorted(set(data) - known)
        if unknown:
            raise TypeError(
                f"{cls.__name__} has no field(s) {', '.join(unknown)}. "
                f"Valid keys: {', '.join(sorted(known))}"
            )
        return cls(**data)  # type: ignore[call-arg]


def coerce(value: Any, cls: type[T], hook: str) -> T:
    """One value from a capability hook, as `cls`.

    Accepts the dataclass, the raw generated message, or — deprecated — a dict.
    """
    if isinstance(value, cls):
        return value
    proto_cls = getattr(cls, "_PROTO", None)
    if proto_cls is not None and isinstance(value, proto_cls):
        return cls.from_proto(value)  # type: ignore[attr-defined]
    if isinstance(value, dict):
        warnings.warn(
            f"{hook}() returned a dict; return "
            f"astra_plugin_sdk.{cls.__name__} instead. Dicts are accepted for "
            f"one more minor release and then removed.",
            DeprecationWarning,
            stacklevel=3,
        )
        return cls._from_dict(value)  # type: ignore[attr-defined]
    raise TypeError(
        f"{hook}() returned {type(value).__name__}; expected {cls.__name__} "
        f"(or a dict, deprecated)"
    )


def coerce_all(values: Iterable[Any] | None, cls: type[T], hook: str) -> list[T]:
    """The whole list a capability hook answered with, as `cls`."""
    return [coerce(v, cls, hook) for v in values or []]


# ── tools ────────────────────────────────────────────────────────────────────


@dataclass
class ToolDef(_CapabilityType):
    """One tool the assistant may call. Answered by `list_tools`."""

    _PROTO = plugin_pb2.PluginToolDef

    name: str = ""
    description: str = ""
    #: JSON Schema for the arguments. Must have an object root — the daemon's
    #: conformance check (§5.7) asserts it, and a model given a non-object root
    #: produces arguments no plugin can parse.
    parameters_json: str = "{}"
    #: This tool wants the pictures the person attached to the message a call
    #: answers; the handler reads them with
    #: :func:`astra_plugin_sdk.current_attachments`. Honoured only for a plugin
    #: granted the ``receive_attachments`` permission, and only by an Astra
    #: built with the ``plugin-provider-slots`` build feature (in no release
    #: yet); ignored otherwise.
    wants_attachments: bool = False

    def to_proto(self) -> Any:
        return plugin_pb2.PluginToolDef(
            name=self.name,
            description=self.description,
            parameters_json=self.parameters_json,
            wants_attachments=bool(self.wants_attachments),
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "ToolDef":
        return cls(
            name=msg.name,
            description=msg.description,
            parameters_json=msg.parameters_json,
            # getattr: a stub older than the field degrades to "does not ask".
            wants_attachments=bool(getattr(msg, "wants_attachments", False)),
        )


# ── TTS ──────────────────────────────────────────────────────────────────────


@dataclass
class VoiceInfo(_CapabilityType):
    """One voice a TTS plugin offers. Answered by `tts_list_voices`."""

    _PROTO = plugin_pb2.PluginVoiceInfo

    id: str = ""
    name: str = ""
    language: str = ""
    #: "male" | "female" | "neutral"
    gender: str = ""
    preview_url: str = ""

    def to_proto(self) -> Any:
        return plugin_pb2.PluginVoiceInfo(
            id=self.id,
            name=self.name,
            language=self.language,
            gender=self.gender,
            preview_url=self.preview_url,
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "VoiceInfo":
        return cls(
            id=msg.id,
            name=msg.name,
            language=msg.language,
            gender=msg.gender,
            preview_url=msg.preview_url,
        )


# ── AI provider ──────────────────────────────────────────────────────────────


@dataclass
class AiModelHints(_CapabilityType):
    """What an AI-provider plugin says about driving one of its models.

    On one model (`AiModelInfo.hints`) or for the whole provider
    (`AiModelList.provider_hints`). A hint changes only a turn Astra runs on
    that model, never the person's settings, and only in a daemon built with the
    `plugin-provider-slots` feature; any other daemon drives the model like
    every other one.
    """

    _PROTO = plugin_pb2.PluginAiModelHints

    #: How the turn's tools reach this model. ``""`` = Astra decides, as for any
    #: model. ``"all"`` = this model does better with every tool in the request
    #: than with discovering them through Tool Search: Astra then sends every
    #: tool directly whenever they fit a larger budget (a quarter of the window,
    #: at most 32k tokens). Never in the Max mode.
    tool_loading: str = ""
    #: This model reads images: only then do the conversation's pictures reach
    #: it, on ``AiMessage.images``. A request can then carry up to 20 MiB of
    #: pictures; this SDK's capability server receives messages up to
    #: ``limits.PLUGIN_MAX_MESSAGE_BYTES`` (64 MiB).
    accepts_images: bool = False
    #: The model's context window in tokens; 0 = unknown.
    context_window: int = 0

    def to_proto(self) -> Any:
        return plugin_pb2.PluginAiModelHints(
            # A value the protocol does not know is sent as "" — which is what
            # the daemon would read it as anyway.
            tool_loading="all" if self.tool_loading == "all" else "",
            accepts_images=bool(self.accepts_images),
            context_window=max(0, min(int(self.context_window or 0), 0xFFFFFFFF)),
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "AiModelHints":
        return cls(
            tool_loading=msg.tool_loading,
            accepts_images=msg.accepts_images,
            context_window=msg.context_window,
        )


def _hints(value: Any, hook: str) -> "AiModelHints | None":
    """`None`, an `AiModelHints`, the generated message, or a dict — as hints."""
    if value is None:
        return None
    if isinstance(value, dict):
        # A nested dict is how a dict-returning `ai_get_models` spells hints;
        # the model's own dict has already drawn the deprecation warning once.
        return AiModelHints._from_dict(value)
    return coerce(value, AiModelHints, hook)


@dataclass
class AiModelInfo(_CapabilityType):
    """One model an AI-provider plugin offers in Astra's model picker.

    Answered by `ai_get_models`, which Astra calls when the plugin starts and
    whenever the AI page refreshes. The model the person picks arrives on
    `AiCompleteRequest.model`.
    """

    _PROTO = plugin_pb2.PluginAiModelInfo

    id: str = ""
    name: str = ""
    #: How this model wants to be driven. ``None`` = the provider's
    #: (`AiModelList.provider_hints`).
    hints: "AiModelHints | None" = None

    def to_proto(self) -> Any:
        msg = plugin_pb2.PluginAiModelInfo(id=self.id, name=self.name)
        hints = _hints(self.hints, "ai_get_models")
        if hints is not None:
            # Set only when present: an absent message is "the provider's
            # hints", an empty one would say "Astra decides" for this model.
            msg.hints.CopyFrom(hints.to_proto())
        return msg

    @classmethod
    def from_proto(cls, msg: Any) -> "AiModelInfo":
        return cls(
            id=msg.id,
            name=msg.name,
            hints=AiModelHints.from_proto(msg.hints) if msg.HasField("hints") else None,
        )


def _is_model_iterable(value: Any) -> bool:
    """The first item of an ``ai_get_models`` tuple: ``None`` or any iterable of
    models — a generator or ``map(...)`` too, as the old servicer's ``for m in
    models`` took — but never a string, a dict or one model."""
    if value is None:
        return True
    if isinstance(value, (str, bytes, dict, AiModelInfo)):
        return False
    try:
        iter(value)
    except TypeError:
        return False
    return True


@dataclass
class AiModelList(_CapabilityType):
    """What `ai_get_models` answers: the models Astra's picker offers.

    The model the person picks arrives on `AiCompleteRequest.model`; an empty
    ``model`` there means `default_model` (``""`` = the first in `models`).
    `provider_hints` applies to every model that carries no hints of its own —
    whole: a model's own hints replace the provider's, field by field nothing is
    merged — and its ``tool_loading`` and ``accepts_images`` to a model id the
    person typed (a typed id gets no ``context_window``: Astra sizes it as it
    sizes any model it has no window for).

    `ai_get_models` may still answer the ``(models, default_model)`` tuple it
    always has; this is the shape that can also carry `provider_hints` (as can
    a three-tuple, ``(models, default_model, provider_hints)``).
    """

    _PROTO = plugin_pb2.PluginAiModelsResponse

    models: "list[AiModelInfo]" = field(default_factory=list)
    default_model: str = ""
    provider_hints: "AiModelHints | None" = None

    def to_proto(self) -> Any:
        msg = plugin_pb2.PluginAiModelsResponse(
            models=[coerce(m, AiModelInfo, "ai_get_models").to_proto() for m in self.models or []],
            default_model=self.default_model or "",
        )
        hints = _hints(self.provider_hints, "ai_get_models")
        if hints is not None:
            msg.provider_hints.CopyFrom(hints.to_proto())
        return msg

    @classmethod
    def from_proto(cls, msg: Any) -> "AiModelList":
        return cls(
            models=[AiModelInfo.from_proto(m) for m in msg.models],
            default_model=msg.default_model,
            provider_hints=(
                AiModelHints.from_proto(msg.provider_hints)
                if msg.HasField("provider_hints")
                else None
            ),
        )

    @classmethod
    def of(cls, value: Any) -> "AiModelList":
        """Whatever `ai_get_models` answered, as an `AiModelList`.

        An `AiModelList`, the ``(models, default_model)`` tuple, or
        ``(models, default_model, provider_hints)``. ``None`` is no list.
        """
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, plugin_pb2.PluginAiModelsResponse):
            return cls.from_proto(value)
        # A list too: the old servicer unpacked `models, default = ...`, which a
        # two-item list satisfied as well as a tuple does.
        if (
            isinstance(value, (tuple, list))
            and len(value) in (2, 3)
            and _is_model_iterable(value[0])
        ):
            return cls(
                models=list(value[0] or []),
                default_model=value[1] or "",
                provider_hints=value[2] if len(value) == 3 else None,
            )
        raise TypeError(
            f"ai_get_models() returned {type(value).__name__}; expected an AiModelList "
            f"or a (models, default_model[, provider_hints]) tuple"
        )


# ── config fields, and the two things they nest ──────────────────────────────


@dataclass
class DropdownOption(_CapabilityType):
    """One choice in a `dropdown` field."""

    _PROTO = plugin_pb2.DropdownOptionMsg

    value: str = ""
    label: str = ""

    def to_proto(self) -> Any:
        return plugin_pb2.DropdownOptionMsg(value=self.value, label=self.label)

    @classmethod
    def from_proto(cls, msg: Any) -> "DropdownOption":
        return cls(value=msg.value, label=msg.label)


@dataclass
class FieldCondition(_CapabilityType):
    """When a field is shown, in terms of another field's value."""

    _PROTO = plugin_pb2.FieldVisibilityCondition

    field_id: str = ""
    #: "equals" | "not_equals" | "is_true" | "is_false" | "not_empty"
    operator: str = ""
    value: str = ""

    def to_proto(self) -> Any:
        return plugin_pb2.FieldVisibilityCondition(
            field_id=self.field_id, operator=self.operator, value=self.value
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "FieldCondition":
        return cls(field_id=msg.field_id, operator=msg.operator, value=msg.value)


@dataclass
class FieldDef(_CapabilityType):
    """One input the daemon renders with its generic `DynamicField` component.

    Answered by `tts_config_fields` / `stt_config_fields`, and nested inside
    `ActionTypeDef` / `TriggerTypeDef`. Prefer the `Field` builder in
    :mod:`astra_plugin_sdk.decorators`, which fills in the `has_min` /
    `has_max` / `has_step` flags that a hand-built one always forgets — proto3
    has no optional scalars here, so `min=0` and "no minimum" are the same bytes
    without them.
    """

    _PROTO = plugin_pb2.FieldDefinitionMsg

    id: str = ""
    label: str = ""
    #: "text" | "textarea" | "textarea_with_variables" | "number" | "toggle" |
    #: "dropdown" | "keys" | "file_picker" | "hotkey_recorder" | "slider"
    field_type: str = "text"
    placeholder: str = ""
    default_value: str = ""
    min: float = 0.0
    max: float = 0.0
    step: float = 0.0
    options: list[DropdownOption] = field(default_factory=list)
    has_min: bool = False
    has_max: bool = False
    has_step: bool = False
    conditions: list[FieldCondition] = field(default_factory=list)
    description: str = ""
    group: str = ""
    group_label: str = ""
    storage_path: str = ""
    #: A tuning knob: Astra folds it behind "Advanced settings" (Voice page).
    advanced: bool = False

    def to_proto(self) -> Any:
        return plugin_pb2.FieldDefinitionMsg(
            id=self.id,
            label=self.label,
            field_type=self.field_type,
            placeholder=self.placeholder,
            default_value=self.default_value,
            min=self.min,
            max=self.max,
            step=self.step,
            options=[coerce(o, DropdownOption, "options").to_proto() for o in self.options],
            has_min=self.has_min,
            has_max=self.has_max,
            has_step=self.has_step,
            conditions=[
                coerce(c, FieldCondition, "conditions").to_proto() for c in self.conditions
            ],
            description=self.description,
            group=self.group,
            group_label=self.group_label,
            storage_path=self.storage_path,
            advanced=self.advanced,
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "FieldDef":
        return cls(
            id=msg.id,
            label=msg.label,
            field_type=msg.field_type,
            placeholder=msg.placeholder,
            default_value=msg.default_value,
            min=msg.min,
            max=msg.max,
            step=msg.step,
            options=[DropdownOption.from_proto(o) for o in msg.options],
            has_min=msg.has_min,
            has_max=msg.has_max,
            has_step=msg.has_step,
            conditions=[FieldCondition.from_proto(c) for c in msg.conditions],
            description=msg.description,
            group=msg.group,
            group_label=msg.group_label,
            storage_path=msg.storage_path,
            advanced=msg.advanced,
        )

    @classmethod
    def _from_dict(cls, data: dict) -> "FieldDef":
        data = dict(data)
        data["options"] = [
            coerce(o, DropdownOption, "options") for o in data.get("options") or []
        ]
        data["conditions"] = [
            coerce(c, FieldCondition, "conditions") for c in data.get("conditions") or []
        ]
        return super()._from_dict(data)  # type: ignore[return-value]


# ── actions and triggers ─────────────────────────────────────────────────────


@dataclass
class ActionTypeDef(_CapabilityType):
    """One step this plugin contributes to the command editor."""

    _PROTO = plugin_pb2.ActionTypeDefinitionMsg

    type: str = ""
    label: str = ""
    icon_svg: str = ""
    fields: list[FieldDef] = field(default_factory=list)
    ai_available: bool = False
    ai_description: str = ""
    ai_primary_field: str = ""
    platforms: list[str] = field(default_factory=list)
    hidden: bool = False

    def to_proto(self) -> Any:
        return plugin_pb2.ActionTypeDefinitionMsg(
            type=self.type,
            label=self.label,
            icon_svg=self.icon_svg,
            fields=[coerce(f, FieldDef, "fields").to_proto() for f in self.fields],
            ai_available=self.ai_available,
            ai_description=self.ai_description,
            ai_primary_field=self.ai_primary_field,
            platforms=list(self.platforms),
            hidden=self.hidden,
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "ActionTypeDef":
        return cls(
            type=msg.type,
            label=msg.label,
            icon_svg=msg.icon_svg,
            fields=[FieldDef.from_proto(f) for f in msg.fields],
            ai_available=msg.ai_available,
            ai_description=msg.ai_description,
            ai_primary_field=msg.ai_primary_field,
            platforms=list(msg.platforms),
            hidden=msg.hidden,
        )

    @classmethod
    def _from_dict(cls, data: dict) -> "ActionTypeDef":
        data = dict(data)
        data["fields"] = [coerce(f, FieldDef, "fields") for f in data.get("fields") or []]
        return super()._from_dict(data)  # type: ignore[return-value]


@dataclass
class TriggerTypeDef(_CapabilityType):
    """One way this plugin can start a user's command."""

    _PROTO = plugin_pb2.TriggerTypeDefinitionMsg

    type: str = ""
    label: str = ""
    icon_svg: str = ""
    fields: list[FieldDef] = field(default_factory=list)

    def to_proto(self) -> Any:
        return plugin_pb2.TriggerTypeDefinitionMsg(
            type=self.type,
            label=self.label,
            icon_svg=self.icon_svg,
            fields=[coerce(f, FieldDef, "fields").to_proto() for f in self.fields],
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "TriggerTypeDef":
        return cls(
            type=msg.type,
            label=msg.label,
            icon_svg=msg.icon_svg,
            fields=[FieldDef.from_proto(f) for f in msg.fields],
        )

    @classmethod
    def _from_dict(cls, data: dict) -> "TriggerTypeDef":
        data = dict(data)
        data["fields"] = [coerce(f, FieldDef, "fields") for f in data.get("fields") or []]
        return super()._from_dict(data)  # type: ignore[return-value]


# ── UI ───────────────────────────────────────────────────────────────────────


@dataclass
class WidgetFormat(_CapabilityType):
    """One desktop layout format. Grid dimensions are cells, readable dimensions pixels."""
    _PROTO = plugin_pb2.PluginWidgetFormat
    id: str = ""
    label: str = ""
    url: str = ""
    preview_url: str = ""
    appearance: str = "card"
    default_w: int = 2
    default_h: int = 2
    min_w: int = 1
    min_h: int = 1
    max_w: int = 0
    max_h: int = 0
    fixed_size: bool = False
    min_pixel_width: int = 0
    min_pixel_height: int = 0

    def to_proto(self):
        return self._PROTO(**{key: getattr(self, key) for key in self.__dataclass_fields__})

    @classmethod
    def from_proto(cls, msg):
        return cls(**{key: getattr(msg, key) for key in cls.__dataclass_fields__})


@dataclass
class WidgetSurface(_CapabilityType):
    """A host popover or modal. All sizes are pixels, zero means host defaults."""
    _PROTO = plugin_pb2.PluginWidgetSurface
    id: str = ""
    label: str = ""
    url: str = ""
    kind: str = "popover"
    width: int = 0
    height: int = 0
    min_width: int = 0
    min_height: int = 0
    max_width: int = 0
    max_height: int = 0

    def to_proto(self):
        return self._PROTO(**{key: getattr(self, key) for key in self.__dataclass_fields__})

    @classmethod
    def from_proto(cls, msg):
        return cls(**{key: getattr(msg, key) for key in cls.__dataclass_fields__})

    @classmethod
    def popover(cls, id: str, label: str, url: str, **sizes):
        return cls(id=id, label=label, url=url, kind="popover", **sizes)

    @classmethod
    def modal(cls, id: str, label: str, url: str, **sizes):
        return cls(id=id, label=label, url=url, kind="modal", **sizes)


@dataclass
class DesktopWidget(_CapabilityType):
    _PROTO = plugin_pb2.PluginDesktopWidget
    repeatable: bool = False
    formats: list[WidgetFormat] = field(default_factory=list)
    surfaces: list[WidgetSurface] = field(default_factory=list)
    config_fields: list[FieldDef] = field(default_factory=list)
    settings_surface: str = ""

    def to_proto(self):
        return self._PROTO(repeatable=self.repeatable,
            formats=[coerce(v, WidgetFormat, "formats").to_proto() for v in self.formats],
            surfaces=[coerce(v, WidgetSurface, "surfaces").to_proto() for v in self.surfaces],
            config_fields=[coerce(v, FieldDef, "config_fields").to_proto() for v in self.config_fields],
            settings_surface=self.settings_surface)

    @classmethod
    def from_proto(cls, msg):
        return cls(repeatable=msg.repeatable, formats=[WidgetFormat.from_proto(v) for v in msg.formats],
            surfaces=[WidgetSurface.from_proto(v) for v in msg.surfaces],
            config_fields=[FieldDef.from_proto(v) for v in msg.config_fields], settings_surface=msg.settings_surface)


@dataclass
class WidgetContext(_CapabilityType):
    """Presentation metadata attached by Astra; confers no host permissions."""
    _PROTO = plugin_pb2.PluginWidgetContext
    widget_id: str = ""
    instance_id: str = ""
    format_id: str = ""
    view_id: str = ""
    preview: bool = False
    active: bool = False
    width: int = 0
    height: int = 0
    config_json: str = "{}"

    def to_proto(self):
        return self._PROTO(**{key: getattr(self, key) for key in self.__dataclass_fields__})

    @classmethod
    def from_proto(cls, msg):
        return cls(**{key: getattr(msg, key) for key in cls.__dataclass_fields__})


@dataclass
class UiContribution(_CapabilityType):
    """One iframe this plugin puts into the Astra window.

    Build these with the `@ui_page` / `@ui_slot` / `@ui_effect` / `@ui_overlay` /
    `@ui_inject` class decorators rather than by hand — they register the
    contribution, which is the half that used to be missing.
    """

    _PROTO = plugin_pb2.PluginUiContribution

    id: str = ""
    slot: str = ""
    css_target: str = ""
    position: str = ""
    url: str = ""
    label: str = ""
    icon_svg: str = ""
    width: int = 0
    height: int = 0
    transparent: bool = False
    pointer_events: bool = True
    z_index: int = 0
    props: dict[str, str] = field(default_factory=dict)
    desktop_widget: DesktopWidget | None = None

    @classmethod
    def widget(cls, id: str, label: str, widget: DesktopWidget) -> "UiContribution":
        return cls(id=id, label=label, slot="desktop.widget", url=widget.formats[0].url if widget.formats else "",
                   transparent=True, pointer_events=True, desktop_widget=widget)

    def to_proto(self) -> Any:
        return plugin_pb2.PluginUiContribution(
            id=self.id,
            slot=self.slot,
            css_target=self.css_target,
            position=self.position,
            url=self.url,
            label=self.label,
            icon_svg=self.icon_svg,
            width=self.width,
            height=self.height,
            transparent=self.transparent,
            pointer_events=self.pointer_events,
            z_index=self.z_index,
            props=dict(self.props),
            desktop_widget=coerce(self.desktop_widget, DesktopWidget, "desktop_widget").to_proto() if self.desktop_widget else None,
        )

    @classmethod
    def from_proto(cls, msg: Any) -> "UiContribution":
        return cls(
            id=msg.id,
            slot=msg.slot,
            css_target=msg.css_target,
            position=msg.position,
            url=msg.url,
            label=msg.label,
            icon_svg=msg.icon_svg,
            width=msg.width,
            height=msg.height,
            transparent=msg.transparent,
            pointer_events=msg.pointer_events,
            z_index=msg.z_index,
            props=dict(msg.props),
            desktop_widget=DesktopWidget.from_proto(msg.desktop_widget) if msg.HasField("desktop_widget") else None,
        )
