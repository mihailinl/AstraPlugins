"""Decorators and helpers for declarative plugin definitions.

Use ``@tool``, ``@action``, and ``@trigger`` to define capabilities with
minimal boilerplate.  The ``Field`` class provides builder methods for
action/trigger field definitions.
"""

import inspect
import json
import typing
from typing import Any, Literal, Optional, Union, get_type_hints


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
        fn._astra_tool_meta = {
            "name": fn.__name__,
            "description": description,
            "parameters_json": _build_json_schema(fn),
        }
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
        fn._astra_action_meta = {
            "type": fn.__name__,
            "label": label,
            "icon_svg": icon_svg,
            "fields": fields or [],
            "ai_available": ai_available,
            "ai_description": ai_description,
            "ai_primary_field": ai_primary_field,
        }
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
        fn._astra_trigger_meta = {
            "type": fn.__name__,
            "label": label,
            "icon_svg": icon_svg,
            "fields": fields or [],
        }
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Field builder
# ---------------------------------------------------------------------------

class Field:
    """Builder for action/trigger field definitions.

    Each static method returns a dict matching the proto ``FieldDefinitionMsg``
    structure, ready to pass into ``@action(fields=[...])`` or
    ``@trigger(fields=[...])``.
    """

    @staticmethod
    def text(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list[dict] | None = None,
    ) -> dict:
        return {
            "id": id, "label": label, "field_type": "text",
            "placeholder": placeholder, "default_value": default,
            "description": description, "conditions": conditions or [],
        }

    @staticmethod
    def textarea(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list[dict] | None = None,
    ) -> dict:
        return {
            "id": id, "label": label, "field_type": "textarea",
            "placeholder": placeholder, "default_value": default,
            "description": description, "conditions": conditions or [],
        }

    @staticmethod
    def textarea_with_variables(
        id: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        description: str = "",
        conditions: list[dict] | None = None,
    ) -> dict:
        return {
            "id": id, "label": label, "field_type": "textarea_with_variables",
            "placeholder": placeholder, "default_value": default,
            "description": description, "conditions": conditions or [],
        }

    @staticmethod
    def dropdown(
        id: str,
        label: str,
        *,
        options: list,
        default: str = "",
        description: str = "",
        conditions: list[dict] | None = None,
    ) -> dict:
        """Create a dropdown field.

        ``options`` accepts:
        - ``[("value", "Label"), ...]`` — tuple pairs
        - ``[{"value": ..., "label": ...}, ...]`` — explicit dicts
        - ``["value1", "value2"]`` — strings (value = label)
        """
        normalized = []
        for opt in options:
            if isinstance(opt, dict):
                normalized.append(opt)
            elif isinstance(opt, (tuple, list)) and len(opt) == 2:
                normalized.append({"value": opt[0], "label": opt[1]})
            else:
                normalized.append({"value": str(opt), "label": str(opt)})
        return {
            "id": id, "label": label, "field_type": "dropdown",
            "options": normalized, "default_value": default,
            "description": description, "conditions": conditions or [],
        }

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
        conditions: list[dict] | None = None,
    ) -> dict:
        return {
            "id": id, "label": label, "field_type": "number",
            "default_value": default, "description": description,
            "has_min": min is not None,
            "has_max": max is not None,
            "has_step": step is not None,
            "min": float(min) if min is not None else 0.0,
            "max": float(max) if max is not None else 0.0,
            "step": float(step) if step is not None else 0.0,
            "conditions": conditions or [],
        }

    @staticmethod
    def toggle(
        id: str,
        label: str,
        *,
        default: bool = False,
        description: str = "",
        conditions: list[dict] | None = None,
    ) -> dict:
        return {
            "id": id, "label": label, "field_type": "toggle",
            "default_value": "true" if default else "false",
            "description": description, "conditions": conditions or [],
        }

    @staticmethod
    def condition(field_id: str, operator: str, value: str = "") -> dict:
        """Build a field visibility condition."""
        return {"field_id": field_id, "operator": operator, "value": value}
