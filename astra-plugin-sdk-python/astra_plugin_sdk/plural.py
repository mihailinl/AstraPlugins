# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""CLDR cardinal plural rules, generated from spec/i18n.yaml.

AUTO-GENERATED — DO NOT EDIT.

Produced by `tools/gen-i18n.mjs` from `spec/i18n.yaml`.
Regenerate with `node tools/gen-i18n.mjs` at the repo root.

The CLDR cardinal rules `I18n::tn` selects with. They are generated because
the Russian and Ukrainian rules are four lines of modular arithmetic each,
and three hand-written copies is three chances to put the wrong noun form in
front of a user nobody in this repository can proof-read for. C17.

`n` is the ABSOLUTE VALUE of the count, as CLDR defines the operand: `%` is
truncated in Rust and JavaScript and floored in Python, so a signed `n`
would sort the same count into different categories in different SDKs.

Declared semantics, from the same file:
lookup_chain: <active language>, then en, then the key itself
fallback_granularity: per key
empty_value: a translation, not a miss
non_string_value: rejects the whole file, and load_errors() names it
load_failure: never fatal, always reachable through load_errors()
discover_chain: $ASTRA_PLUGIN_DIR/locales, else ./locales
tf_placeholder: {0} {1} … , every occurrence, missing index left intact
ta_placeholder: {name}, every occurrence, unknown name left intact
tn_key_chain: <key>.<category>, then <key>.other, then <key>, then the key
unknown_language_category: other
declared_plane_marker: key(k) returns "$" + k
"""

from __future__ import annotations

#: SHA-256 of the ``spec/i18n.yaml`` these rules were generated from.
SPEC_SHA256 = "15978cdce90926b3fa09a4701980d684c372f4b27692c5345c18e4d434469d32"

#: Every language's categories, in the order spec/i18n.yaml declares them.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "en": ("one", "other"),
    "ru": ("one", "few", "many", "other"),
    "uk": ("one", "few", "many", "other"),
    "de": ("one", "other"),
    "fr": ("one", "other"),
    "es": ("one", "other"),
    "pt": ("one", "other"),
    "ja": ("other",),
    "zh": ("other",),
    "ko": ("other",),
}


def categories(lang: str) -> tuple[str, ...]:
    """The categories ``lang`` uses, or ``("other",)`` if it is not declared."""
    return CATEGORIES.get(lang, ("other",))


def is_declared(lang: str) -> bool:
    """Is ``lang`` one of the languages Astra can be set to?

    The keys of :data:`CATEGORIES` are generated from ``spec/locales.yaml`` and
    the generator refuses to run unless the two files name exactly the same
    languages — so this table doubles as the vocabulary, and ``I18n`` uses it to
    say so when a plugin ships a ``locales/zh-CN.json`` that nothing can select.
    """
    return lang in CATEGORIES


def category(lang: str, n: int) -> str:
    """The CLDR cardinal category for ``n`` in ``lang``.

    ``n`` is taken as an absolute value: a count of -3 items is grammatically
    three items. A language this table does not name gets ``"other"``.
    """
    n = abs(int(n))
    if lang == "en":
        if n == 1:
            return "one"
        return "other"
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if (n % 10 >= 2 and n % 10 <= 4) and (n % 100 < 12 or n % 100 > 14):
            return "few"
        if n % 10 == 0 or (n % 10 >= 5 and n % 10 <= 9) or (n % 100 >= 11 and n % 100 <= 14):
            return "many"
        return "other"
    if lang == "uk":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if (n % 10 >= 2 and n % 10 <= 4) and (n % 100 < 12 or n % 100 > 14):
            return "few"
        if n % 10 == 0 or (n % 10 >= 5 and n % 10 <= 9) or (n % 100 >= 11 and n % 100 <= 14):
            return "many"
        return "other"
    if lang == "de":
        if n == 1:
            return "one"
        return "other"
    if lang == "fr":
        if n <= 1:
            return "one"
        return "other"
    if lang == "es":
        if n == 1:
            return "one"
        return "other"
    if lang == "pt":
        if n <= 1:
            return "one"
        return "other"
    if lang == "ja":
        return "other"
    if lang == "zh":
        return "other"
    if lang == "ko":
        return "other"
    return "other"


__all__ = ["SPEC_SHA256", "CATEGORIES", "categories", "category", "is_declared"]
