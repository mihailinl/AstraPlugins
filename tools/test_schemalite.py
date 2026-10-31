#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""tools/schemalite.py's own self-check and unit tests.

The self-check is the promise schemalite.py's module docstring makes: every
`spec/games/schemas/*.json` file uses only the keyword subset the validator
actually implements. Without it, a schema author could add `allOf` or
`patternProperties` to a schema file, have every *_games goldens run clean
(because `_validate`'s `NotImplementedError` only fires on documents that
actually reach that branch), and discover the gap only when a golden
happens to exercise it — which is exactly the kind of "looked green, was
not validating anything" failure this file exists to rule out structurally,
by walking every schema file directly rather than waiting for a golden to
stumble into the unsupported keyword.

    python3 tools/test_schemalite.py        # what the couplings job runs
"""

from __future__ import annotations

import glob
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import schemalite as S  # noqa: E402

_SUPPORTED = {
    "$ref", "$schema", "$id", "$defs", "$comment", "title", "description",
    "oneOf", "anyOf", "const", "enum", "type", "minLength", "maxLength",
    "pattern", "minimum", "maximum", "minItems", "maxItems", "items",
    "minProperties", "maxProperties", "required", "propertyNames",
    "properties", "additionalProperties",
}


def _walk(schema, path, out):
    """Walks a JSON Schema DOCUMENT, not a plain tree: a key under
    'properties' is a property NAME (arbitrary data, never checked against
    _SUPPORTED), while the key 'properties' itself is a keyword. Getting
    this distinction wrong is exactly how the first version of this test
    flagged every field name in every schema file as an "unsupported
    keyword" -- 'schema', 'engine', 'listed', and so on were never
    keywords to begin with."""
    if isinstance(schema, bool) or not isinstance(schema, dict):
        return
    for k, v in schema.items():
        if k not in _SUPPORTED:
            out.append(f"{path}/{k}")
            continue
        if k == "properties" and isinstance(v, dict):
            for pname, sub in v.items():
                _walk(sub, f"{path}/properties/{pname}", out)
        elif k == "$defs" and isinstance(v, dict):
            for dname, sub in v.items():
                _walk(sub, f"{path}/$defs/{dname}", out)
        elif k in ("additionalProperties", "propertyNames", "items") and isinstance(v, dict):
            _walk(v, f"{path}/{k}", out)
        elif k in ("oneOf", "anyOf") and isinstance(v, list):
            for i, sub in enumerate(v):
                _walk(sub, f"{path}/{k}[{i}]", out)
        # $ref, $schema, $id, $comment, title, description, const, enum,
        # type, minLength, maxLength, pattern, minimum, maximum, minItems,
        # maxItems, minProperties, maxProperties, required: plain values,
        # or (additionalProperties/items) a bool -- nothing to recurse into.


class SchemaFilesUseOnlySupportedKeywords(unittest.TestCase):
    def test_every_schema_in_spec_games_schemas(self):
        files = sorted(glob.glob(str(ROOT / "spec/games/schemas/*.json")))
        self.assertGreater(len(files), 0, "no schema files found -- the glob itself is broken")
        for f in files:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
            unsupported: list[str] = []
            _walk(doc, Path(f).name, unsupported)
            self.assertEqual(unsupported, [], f"{f} uses keyword(s) schemalite.py cannot check: {unsupported}")


class CoreSemantics(unittest.TestCase):
    def test_additional_properties_false_refuses_an_extra_key(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}
        S.validate({"a": "x"}, schema)
        with self.assertRaises(S.SchemaError):
            S.validate({"a": "x", "b": "y"}, schema)

    def test_one_of_is_exclusive_not_inclusive(self):
        schema = {"oneOf": [{"type": "string"}, {"type": "string", "minLength": 1}]}
        # Both branches match a non-empty string -> oneOf must refuse it,
        # proving this is really exclusive-or and not "any branch matches".
        with self.assertRaises(S.SchemaError):
            S.validate("hello", schema)

    def test_any_of_is_inclusive(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        S.validate("x", schema)
        S.validate(1, schema)
        with self.assertRaises(S.SchemaError):
            S.validate(1.5, schema)

    def test_local_ref_resolves_through_defs(self):
        schema = {"$defs": {"pos": {"type": "integer", "minimum": 0}}, "$ref": "#/$defs/pos"}
        S.validate(5, schema)
        with self.assertRaises(S.SchemaError):
            S.validate(-1, schema)

    def test_non_local_ref_is_refused_loudly_not_silently_skipped(self):
        schema = {"$ref": "https://example.com/other.json"}
        with self.assertRaises(NotImplementedError):
            S.validate({}, schema)

    def test_an_unsupported_keyword_raises_rather_than_passing_silently(self):
        schema = {"allOf": [{"type": "string"}]}
        with self.assertRaises(NotImplementedError):
            S.validate("x", schema)

    def test_false_schema_accepts_nothing(self):
        with self.assertRaises(S.SchemaError):
            S.validate("anything", False)

    def test_true_schema_accepts_everything(self):
        S.validate("anything", True)
        S.validate(None, True)


if __name__ == "__main__":
    unittest.main()
