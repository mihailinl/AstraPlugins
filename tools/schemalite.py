#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""A JSON Schema (2020-12) validator, deliberately a SUBSET.

`tools/check-games-goldens.py` is this repository's only consumer. It runs in
the `games-spec` CI job (`.github/workflows/ci.yml`), which — like the hand-
parsed `spec/limits.yaml` and `spec/wire.yaml` — installs nothing: a checker
that needs `pip install jsonschema` is a checker that stops running the first
time a runner image's network access or Python version changes under it, and
`spec/games/schemas/*.json` were all written, by hand, against exactly the
keyword set below (verified by `tools/test_schemalite.py`'s self-check that
walks every schema file and confirms it uses no other keyword).

Supported keywords: `type`, `const`, `enum`, `required`, `properties`,
`additionalProperties` (bool or schema), `propertyNames`, `minProperties`,
`maxProperties`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`,
`pattern`, `minimum`, `maximum`, `oneOf`, `anyOf`, `$ref` (LOCAL only, a
JSON Pointer into the same document — never fetched over the network, the
same restriction link-v1.md §6 puts on an author's own data schemas).

Deliberately NOT supported, because nothing here needs it: `allOf`, `not`,
`if/then/else`, `patternProperties`, `format`, `$dynamicRef`, a remote `$ref`.
A schema file that needs one of these is a schema file for a different job
than validating this spec's own goldens, and should not quietly start being
skipped — `validate()` raises `NotImplementedError` naming the keyword
instead of pretending to check it.
"""

from __future__ import annotations

import re
from typing import Any


class SchemaError(Exception):
    """A document does not match its schema. `.path` is a slash-joined trail."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path or '$'}: {message}")
        self.path = path
        self.message = message


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _check_type(instance: Any, type_name: str) -> bool:
    if type_name == "integer":
        # bool is a subclass of int in Python; JSON Schema's "integer" must
        # not accept true/false, and a JSON number with no fractional part
        # (parsed as float by json.load only via parse_float, never the
        # default) is still int here because json.load gives ints for
        # integer literals already.
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    py_type = _TYPE_MAP.get(type_name)
    if py_type is None:
        raise NotImplementedError(f"unknown schema type {type_name!r}")
    if py_type is bool:
        return isinstance(instance, bool)
    if py_type is dict and isinstance(instance, bool):
        return False
    return isinstance(instance, py_type)


def _resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise NotImplementedError(f"non-local $ref: {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaError("", f"$ref {ref!r} does not resolve")
        node = node[part]
    return node


def _validate(instance: Any, schema: Any, root: dict, path: str) -> None:
    if isinstance(schema, bool):
        if schema is False:
            raise SchemaError(path, "this location accepts nothing")
        return  # `True` accepts anything

    if "$ref" in schema:
        _validate(instance, _resolve_ref(schema["$ref"], root), root, path)
        # A $ref in this validator's schemas is always used as the WHOLE
        # value of a keyword (never alongside sibling keywords at the same
        # level) — every schema file in spec/games/schemas/ was written that
        # way on purpose, so there is nothing else to check here.
        return

    if "oneOf" in schema:
        matches = 0
        errors = []
        for i, sub in enumerate(schema["oneOf"]):
            try:
                _validate(instance, sub, root, path)
                matches += 1
            except SchemaError as e:
                errors.append(f"  branch {i}: {e}")
        if matches != 1:
            detail = "\n".join(errors)
            raise SchemaError(
                path, f"matched {matches} of {len(schema['oneOf'])} oneOf branches:\n{detail}"
            )

    if "anyOf" in schema:
        if not any(_try(instance, sub, root, path) for sub in schema["anyOf"]):
            raise SchemaError(path, "matched none of the anyOf branches")

    if "const" in schema:
        if instance != schema["const"]:
            raise SchemaError(path, f"expected the constant {schema['const']!r}, got {instance!r}")

    if "enum" in schema:
        if instance not in schema["enum"]:
            raise SchemaError(path, f"{instance!r} is not one of {schema['enum']!r}")

    if "type" in schema:
        types = schema["type"]
        types = [types] if isinstance(types, str) else types
        if not any(_check_type(instance, t) for t in types):
            raise SchemaError(path, f"expected type {schema['type']!r}, got {type(instance).__name__}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise SchemaError(path, f"shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaError(path, f"longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise SchemaError(path, f"does not match pattern {schema['pattern']!r}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaError(path, f"less than minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaError(path, f"greater than maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaError(path, f"fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaError(path, f"more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(instance):
                _validate(item, schema["items"], root, f"{path}/{i}")

    if isinstance(instance, dict):
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            raise SchemaError(path, f"fewer than minProperties {schema['minProperties']}")
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            raise SchemaError(path, f"more than maxProperties {schema['maxProperties']}")
        for key in schema.get("required", []):
            if key not in instance:
                raise SchemaError(path, f"missing required property {key!r}")
        if "propertyNames" in schema:
            for key in instance:
                _validate(key, schema["propertyNames"], root, f"{path}/{key}")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                _validate(value, props[key], root, f"{path}/{key}")
            elif "additionalProperties" in schema:
                _validate(value, schema["additionalProperties"], root, f"{path}/{key}")

    for unknown in schema:
        if unknown not in (
            "$ref", "$schema", "$id", "$defs", "$comment", "title", "description",
            "oneOf", "anyOf", "const", "enum", "type", "minLength", "maxLength",
            "pattern", "minimum", "maximum", "minItems", "maxItems", "items",
            "minProperties", "maxProperties", "required", "propertyNames",
            "properties", "additionalProperties",
        ):
            raise NotImplementedError(f"unsupported schema keyword {unknown!r} at {path or '$'}")


def _try(instance: Any, schema: Any, root: dict, path: str) -> bool:
    try:
        _validate(instance, schema, root, path)
        return True
    except SchemaError:
        return False


def validate(instance: Any, schema: dict) -> None:
    """Raises `SchemaError` on the first violation found. `schema` is also its
    own root document, so every `$ref` in it resolves against itself —
    exactly the "local $ref only" restriction this spec places on an
    author's own data schemas (link-v1.md §6), applied here to the spec's
    own schema files too."""
    _validate(instance, schema, schema, "")
