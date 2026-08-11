"""Decorators and helpers for declarative plugin definitions.

Method decorators — ``@tool``, ``@action``, ``@trigger``, ``@ui_call`` — mark a
method as something Astra can call. Class decorators — ``@ui_page``,
``@ui_slot``, ``@ui_effect``, ``@ui_overlay``, ``@ui_inject`` — declare an iframe
the plugin contributes to the Astra window. The ``Field`` class builds the inputs
an action, a trigger or a config section renders.

REGISTERING, NOT RETURNING (production plan §5.8)

``ui_page`` and friends used to be ``@staticmethod``s on ``Plugin`` that *built*
a dict and gave it back, leaving the author to remember to return it from
``get_ui_contributions``. The SDK's own documented example did not::

    async def get_ui_contributions(self):
        self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
        self.ui_effect("http://localhost:8123/snow.html")
        # ...and returns None. No contribution is ever declared.

That example is in seven translations of ``docs/*/sdk-python.md``, and it has
never worked. A builder whose return value must be plumbed somewhere is a
builder that will be dropped, so these register instead::

    @ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    class MyPlugin(Plugin):
        @ui_call
        async def get_stats(self, **params):
            return {"operations": self.count}

``Plugin.get_ui_contributions`` returns what was registered, and
``Plugin.handle_ui_call`` dispatches to the ``@ui_call`` methods — so the page
above is reachable from its iframe with no further code. The old
``Plugin.ui_page(...)`` builders still exist and still return a value, for the
plugin that assembles its contributions at runtime.
"""

import inspect
import json
import typing
from typing import Any, Literal, Union, get_type_hints

from astra_plugin_sdk.capability_types import (
    ActionTypeDef,
    DropdownOption,
    FieldCondition,
    FieldDef,
    ToolDef,
    TriggerTypeDef,
    UiContribution,
)

__all__ = [
    "tool",
    "action",
    "trigger",
    "ui_call",
    "ui_page",
    "ui_slot",
    "ui_effect",
    "ui_overlay",
    "ui_inject",
    "Field",
]


# ---------------------------------------------------------------------------
# Type-hint -> JSON Schema mapping
# ---------------------------------------------------------------------------

_PY_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _type_to_schema(hint: Any) -> dict:
    """Convert a Python type hint to a JSON Schema fragment."""
    # Plain types
    if hint in _PY_TO_JSON_TYPE:
        return {"type": _PY_TO_JSON_TYPE[hint]}

    origin = typing.get_origin(hint)
    args = typing.get_args(hint)

    # Literal["a", "b"] -> enum
    if origin is Literal:
        return {"type": "string", "enum": list(args)}

    # Optional[X] (Union[X, None])
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_schema(non_none[0])

    # list[str] etc.
    if origin is list:
        schema: dict = {"type": "array"}
        if args:
            schema["items"] = _type_to_schema(args[0])
        return schema

    # Fallback
    return {"type": "string"}


def _build_json_schema(fn: Any) -> str:
    """Build a JSON Schema string from a function's type hints."""
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        hint = hints.get(name, str)  # default to string
        prop = _type_to_schema(hint)

        # Use parameter name as description placeholder if no docstring parsing
        properties[name] = prop

        # Required if no default
        if param.default is inspect.Parameter.empty:
            origin = typing.get_origin(hint)
            args = typing.get_args(hint)
            is_optional = (
                origin is Union
                and type(None) in args
            )
            if not is_optional:
                required.append(name)

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return json.dumps(schema)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def tool(description: str):
    """Mark a method as a plugin tool.

    The decorated method's type hints are used to auto-generate JSON Schema
    for the tool parameters.  The return value is automatically wrapped in
    ``{"success": True, "result": ...}`` by the SDK.

    Example::

        @tool("Count words in text")
        async def word_count(self, text: str):
            return {"words": len(text.split())}
    """
    def decorator(fn):
        fn._astra_tool_meta = ToolDef(
            name=fn.__name__,
            description=description,
            parameters_json=_build_json_schema(fn),
        )
        return fn
    return decorator


def action(
    label: str,
    *,
    icon_svg: str = "",
    fields: list[dict] | None = None,
    ai_available: bool = False,
    ai_description: str = "",
    ai_primary_field: str = "",
):
    """Mark a method as a plugin action type.

    Example::

        @action("Transform Text", fields=[
            Field.dropdown("op", "Operation", options=["upper", "lower"]),
        ])
        async def transform_text(self, op: str, input_text: str):
            ...
    """
    def decorator(fn):
        fn._astra_action_meta = ActionTypeDef(
            type=fn.__name__,
            label=label,
            icon_svg=icon_svg,
            fields=list(fields or []),
            ai_available=ai_available,
            ai_description=ai_description,
            ai_primary_field=ai_primary_field,
        )
        return fn
    return decorator


def trigger(
    label: str,
    *,
    icon_svg: str = "",
    fields: list[dict] | None = None,
):
    """Mark a method as a plugin trigger type definition.

    The method itself is not called automatically — it just holds metadata.
    Use ``self.fire_trigger(...)`` to fire the trigger from a background task.

    Example::

        @trigger("Scheduled Time", fields=[
            Field.text("time", "Time", default="09:00", placeholder="HH:MM"),
        ])
        def on_time(self):
            pass
    """
    def decorator(fn):
        fn._astra_trigger_meta = TriggerTypeDef(
            type=fn.__name__,
            label=label,
            icon_svg=icon_svg,
            fields=list(fields or []),
        )
        return fn
    return decorator


# ---------------------------------------------------------------------------
# UI: one decorator that registers a handler, five that register an iframe
# ---------------------------------------------------------------------------

def ui_call(arg=None, *, method: str | None = None):
    """Register a method as a handler for a call from this plugin's UI iframe.

    The iframe calls ``method`` over ``CallFromUi``; the SDK routes it here and
    turns whatever you return into the response. Arguments come from the
    iframe's JSON payload, by name::

        @ui_call
        async def get_stats(self, since: str = ""):
            return {"operations": self.count}

        @ui_call("reset-stats")          # a name the JSON can spell but Python cannot
        async def reset_stats(self):
            self.count = 0

    A handler that takes ``**params`` (or a single positional parameter) is given
    the whole payload instead of keyword arguments, which is what you want when
    the iframe sends a free-form object.

    Raising works the same as in a ``@tool``: ``raise NotConfigured("api_key")``
    reaches the panel as a link to that config field, because the daemon relays
    ``PluginUiCallResponse.error_detail`` on to it.
    """
    def decorator(fn):
        fn._astra_ui_call_meta = {"method": method or name or fn.__name__}
        return fn

    name = arg if isinstance(arg, str) else None
    if callable(arg):
        return decorator(arg)
    return decorator


def _register_contribution(contribution: UiContribution):
    """Make a class decorator that appends `contribution` to the class.

    Written against ``cls.__dict__`` rather than ``getattr``: a subclass must not
    append into its base class's list, or a second plugin subclassing the first
    would inherit — and then double — every page.
    """
    def decorator(cls):
        if not inspect.isclass(cls):
            raise TypeError(
                f"@{contribution.slot or 'ui'} contributions decorate the Plugin "
                f"CLASS, not a method — a page has no handler. Move the decorator "
                f"above `class {getattr(cls, '__qualname__', cls)}(Plugin):`, and "
                f"use @ui_call on the methods its iframe calls."
            )
        own = cls.__dict__.get("_astra_ui_contributions")
        if own is None:
            own = list(getattr(cls, "_astra_ui_contributions", ()))
            cls._astra_ui_contributions = own
        # Decorators apply bottom-up; inserting at the front restores the order
        # they are written in, which is the order they appear in the UI.
        own.insert(0, contribution)
        return cls
    return decorator


def ui_page(
    id: str,
    label: str,
    url: str,
    *,
    icon_svg: str = "",
    z_index: int = 0,
):
    """Register a full page in Astra's navigation, served from ``url``.

    A class decorator::

        @ui_page("stats", "Stats", "http://localhost:8123/stats.html")
        class MyPlugin(Plugin):
            ...

    ``url`` is either an absolute URL the plugin serves itself or a path
    relative to the bundle's ``ui/`` directory.
    """
    return _register_contribution(
        UiContribution(
            id=id,
            slot="page.custom",
            label=label,
            url=url,
            icon_svg=icon_svg,
            z_index=z_index,
            pointer_events=True,
        )
    )


def ui_slot(
    slot: str,
    url: str,
    *,
    id: str = "",
    label: str = "",
    width: int = 0,
    height: int = 0,
    z_index: int = 0,
):
    """Register an iframe in a named slot (``"page.custom"``, ``"sidebar.top"``…)."""
    return _register_contribution(
        UiContribution(
            id=id or slot,
            slot=slot,
            url=url,
            label=label,
            width=width,
            height=height,
            z_index=z_index,
            pointer_events=True,
        )
    )


def ui_effect(url: str, *, id: str = "effect", audio: bool = False):
    """Register a transparent, click-through iframe behind the whole window."""
    return _register_contribution(
        UiContribution(
            id=id,
            slot="background.behind",
            url=url,
            transparent=True,
            pointer_events=False,
            props={"audio": "true"} if audio else {},
        )
    )


def ui_overlay(id: str, url: str, *, url_width: int = 200, url_height: int = 200):
    """Register a floating, interactive overlay iframe."""
    return _register_contribution(
        UiContribution(
            id=id,
            slot="overlay.floating",
            url=url,
            transparent=True,
            pointer_events=True,
            width=url_width,
            height=url_height,
        )
    )


def ui_inject(
    css_target: str,
    position: str,
    url: str,
    *,
    id: str = "inject",
    width: int = 0,
    height: int = 0,
):
    """Register an iframe injected relative to a CSS selector in Astra's own UI.

    ``position`` is ``"before"``, ``"after"``, ``"replace"``, ``"prepend"`` or
    ``"append"``. The fallback for a place with no named slot; a selector is a
    private detail of Astra's markup and can move between releases, so prefer a
    slot where one exists.
    """
    return _register_contribution(
        UiContribution(
            id=id,
            css_target=css_target,
            position=position,
            url=url,
            width=width,
            height=height,
            pointer_events=True,
        )
    )


# ---------------------------------------------------------------------------
# Field builder
# ---------------------------------------------------------------------------

class Field:
    """Builder for action, trigger and config field definitions.

    Each static method returns a
    :class:`~astra_plugin_sdk.capability_types.FieldDef`, ready to pass into
    ``@action(fields=[...])``, ``@trigger(fields=[...])`` or to return from
    ``tts_config_fields`` / ``stt_config_fields``.

    Use these rather than writing the dataclass by hand: proto3 has no optional
    scalars here, so ``min=0`` and "no minimum" are the same bytes, and the
    ``has_min`` / ``has_max`` / ``has_step`` flags that tell them apart are what
    a hand-built field always forgets.
    """

    @staticmethod
    def text(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        return FieldDef(
            id=id, label=label, field_type="text",
            placeholder=placeholder, default_value=default,
            description=description, conditions=list(conditions or []),
        )

    @staticmethod
    def textarea(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        return FieldDef(
            id=id, label=label, field_type="textarea",
            placeholder=placeholder, default_value=default,
            description=description, conditions=list(conditions or []),
        )

    @staticmethod
    def textarea_with_variables(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        return FieldDef(
            id=id, label=label, field_type="textarea_with_variables",
            placeholder=placeholder, default_value=default,
            description=description, conditions=list(conditions or []),
        )

    @staticmethod
    def dropdown(
        id: str,
        label: str,
        *,
        options: list,
        default: str = "",
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        """Create a dropdown field.

        ``options`` accepts:
        - ``[("value", "Label"), ...]`` — tuple pairs
        - ``[DropdownOption(value=..., label=...), ...]``
        - ``[{"value": ..., "label": ...}, ...]`` — explicit dicts
        - ``["value1", "value2"]`` — strings (value = label)
        """
        normalized: list[DropdownOption] = []
        for opt in options:
            if isinstance(opt, DropdownOption):
                normalized.append(opt)
            elif isinstance(opt, dict):
                normalized.append(DropdownOption(**opt))
            elif isinstance(opt, (tuple, list)) and len(opt) == 2:
                normalized.append(DropdownOption(value=opt[0], label=opt[1]))
            else:
                normalized.append(DropdownOption(value=str(opt), label=str(opt)))
        return FieldDef(
            id=id, label=label, field_type="dropdown",
            options=normalized, default_value=default,
            description=description, conditions=list(conditions or []),
        )

    @staticmethod
    def number(
        id: str,
        label: str,
        *,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        default: str = "",
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        return FieldDef(
            id=id, label=label, field_type="number",
            default_value=default, description=description,
            has_min=min is not None,
            has_max=max is not None,
            has_step=step is not None,
            min=float(min) if min is not None else 0.0,
            max=float(max) if max is not None else 0.0,
            step=float(step) if step is not None else 0.0,
            conditions=list(conditions or []),
        )

    @staticmethod
    def toggle(
        id: str,
        label: str,
        *,
        default: bool = False,
        description: str = "",
        conditions: list | None = None,
    ) -> FieldDef:
        return FieldDef(
            id=id, label=label, field_type="toggle",
            default_value="true" if default else "false",
            description=description, conditions=list(conditions or []),
        )

    @staticmethod
    def condition(field_id: str, operator: str, value: str = "") -> FieldCondition:
        """Build a field visibility condition."""
        return FieldCondition(field_id=field_id, operator=operator, value=value)
