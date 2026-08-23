# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Plugin localization: ``locales/<code>.json``, and the two planes it serves.

A plugin ships one flat JSON file per language beside ``plugin.toml``::

    {
        "config.token.title": "API Token",
        "msg.done.one": "Handled {n} item",
        "msg.done.other": "Handled {n} items"
    }

THE TWO PLANES, WHICH IS THE THING TO GET RIGHT

**Runtime plane** — anything *this process* produces: chat text, notifications,
anything with a count in it. Resolve it here, at the moment you produce it::

    text = self.i18n.tn("msg.done", n, n=str(n))

**Declared plane** — anything the *daemon* renders: config-field titles, action
and trigger labels, ``[ui]`` contribution labels. Emit a marker with :func:`key`
and let the daemon resolve it per request, from the same ``locales/`` directory,
in whatever language the user has set *now*::

    key("action.roll.label")        # -> "$action.roll.label"

Never ``t()`` on the declared plane. The daemon caches a definition unresolved
and resolves it per request, so a label you resolved once is frozen in whatever
language won the race at startup — and a user who switches language keeps
reading it.

WHAT THIS LOADER WILL AND WILL NOT ACCEPT

The daemon deserialises a locale file as ``HashMap<String, String>`` and drops
the **whole file** on any non-string value, silently, at install time. This
loader does the same, on purpose: a version that accepted a nested object would
let a plugin's own tests pass on a file the user's machine never loads.
Everything it could not use is reachable through :attr:`I18n.load_errors`,
which ``astra-plugin test`` prints. Nothing here is fatal — a plugin must start.

Until 0.7 this module also treated ``""`` as a miss, because its lookup was an
``or`` chain. An absent key is how a locale says "not translated"; ``""`` is
the only way to blank a string in one language, and it is now a translation
that wins.

The declared semantics are ``spec/i18n.yaml``, the shared cases are
``testdata/i18n/vectors.json``, and all three SDKs are held to them by one test
each. This is coupling C17.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from astra_plugin_sdk import plural

__all__ = ["I18n", "key", "PLUGIN_DIR_ENV"]

#: Environment variable naming the plugin's own install directory.
#:
#: The daemon does not set it yet — it is Ask 6 to the Astra half — which is
#: why :meth:`I18n.discover` falls through to ``./locales``. That works today
#: only because the daemon spawns a plugin with its working directory set to
#: the install directory, a load-bearing fact stated in no repository and one
#: ``[entry] cwd`` from stopping being true.
PLUGIN_DIR_ENV = "ASTRA_PLUGIN_DIR"


def key(k: str) -> str:
    """Mark a string as a **declared-plane** locale key for the daemon.

    Returns ``"$" + k``. Use it for anything the daemon renders rather than
    this process. A key that matches nothing is shown to the user exactly as it
    stands, so every key passed here must exist in ``locales/en.json`` —
    ``astra-plugin check`` is what tells you when one does not.
    """
    return "$" + k


def _kind_of(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    return "a nested object"


def _parse_locale(text: str) -> dict[str, str]:
    """A locale file's bytes as a flat string map.

    Raises ``ValueError`` with a message the daemon has no way to produce. As
    strict as the daemon deliberately: same accept/reject set, better sentence.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"the top level is {_kind_of(data)}, not an object. A locale file is a "
            "flat map of key to string."
        )
    for k, v in data.items():
        if not isinstance(v, str):
            raise ValueError(
                f"the value of `{k}` is {_kind_of(v)}, not a string. The daemon "
                "deserialises a locale file as a flat map of string to string and drops "
                "the WHOLE file on the first value that is not one — so on a user's "
                "machine every key in this file would render as itself while this "
                f'plugin\'s own tests passed. Flatten it: "{k}.title": "…".'
            )
    return data


class I18n:
    """Translation store. Load locale files and resolve keys."""

    def __init__(self, locales_dir: str | Path | None):
        self._locales: dict[str, dict[str, str]] = {}
        self._language = "en"
        self._errors: list[str] = []
        self._source: Path | None = None

        if locales_dir is None:
            return

        path = Path(locales_dir)
        self._source = path
        if not path.is_dir():
            self._errors.append(
                f"{path}: not a directory. No locale file was loaded, so every t() call "
                "returns its key."
            )
            return

        for f in sorted(path.glob("*.json")):
            try:
                data = _parse_locale(f.read_text(encoding="utf-8"))
            # JSONDecodeError is a ValueError, so it has to be caught FIRST or
            # a syntax error is reported without the sentence that explains it.
            except json.JSONDecodeError as e:
                self._errors.append(
                    f"{f}: not valid JSON ({e}). The daemon drops this file whole."
                )
                continue
            except ValueError as e:
                self._errors.append(f"{f}: {e}")
                continue
            except OSError as e:
                self._errors.append(f"{f}: not readable ({e})")
                continue
            if not plural.is_declared(f.stem):
                # Not a refusal: the daemon loads this file too, keys it by this
                # stem, and never selects it. Saying so is the only signal the
                # author will ever get — otherwise the file is packed, digested,
                # signed, shipped, and read by nothing.
                self._errors.append(
                    f"{f}: `{f.stem}` is not a language Astra can be set to "
                    "(spec/locales.yaml). The file loaded, and nothing will ever "
                    "select it."
                )
            self._locales[f.stem] = data

    # ── construction ──

    @classmethod
    def discover(cls) -> "I18n":
        """Load the plugin's ``locales/`` without depending on the process CWD.

        ``$ASTRA_PLUGIN_DIR/locales`` when that variable names a directory, else
        ``./locales``. Two candidates, both owned by the plugin, and no third: a
        Python plugin is started as ``python -m src.plugin``, so an
        executable-relative chain would stat ``/usr/bin/locales`` — a directory
        the plugin does not own and has no business reading.

        Never raises. :attr:`source_dir` says where it looked and
        :attr:`load_errors` says what it could not use.
        """
        base = os.environ.get(PLUGIN_DIR_ENV)
        if base:
            candidate = Path(base) / "locales"
            if candidate.is_dir():
                return cls(candidate)
        return cls("locales")

    @classmethod
    def empty(cls) -> "I18n":
        """An I18n with no locale files loaded and nothing to report."""
        return cls(None)

    # ── what could not be used ──

    @property
    def load_errors(self) -> list[str]:
        """Every file this loader could not use, and why.

        Never fatal — see the module docstring. ``astra-plugin test`` prints
        these, so a misnamed or malformed locale file is a line an author reads
        before they ship rather than a settings page that is quietly English.
        """
        return list(self._errors)

    @property
    def source_dir(self) -> Path | None:
        """The directory this instance read, or ``None`` for :meth:`empty`."""
        return self._source

    # ── language ──

    def set_language(self, lang: str) -> None:
        """Set the active language. The SDK calls this for you; see ``Plugin.i18n``."""
        self._language = lang

    @property
    def language(self) -> str:
        """Get the current active language."""
        return self._language

    # ── lookup ──

    def _lookup(self, key: str) -> str | None:
        """Active language, then ``en``, PER KEY — not per file.

        ``""`` is a translation and wins. ``None`` means no locale carries it.
        """
        for lang in (self._language, "en"):
            value = self._locales.get(lang, {}).get(key)
            if value is not None:
                return value
        return None

    def t(self, key: str) -> str:
        """Get a translated string. Falls back to English, then to the key itself."""
        value = self._lookup(key)
        return key if value is None else value

    def has(self, key: str) -> bool:
        """Is this key translated in the active language or in English?"""
        return self._lookup(key) is not None

    def tf(self, key: str, *args: str) -> str:
        """Get a translated string with positional arguments substituted.

        Placeholders are ``{0}``, ``{1}``, … and **every** occurrence is
        replaced. Russian and Ukrainian repeat a noun in two cases routinely.
        """
        result = self.t(key)
        for i, arg in enumerate(args):
            result = result.replace("{" + str(i) + "}", arg)
        return result

    def ta(self, key: str, /, **args: str) -> str:
        """Get a translated string with **named** arguments substituted.

        Placeholders are ``{name}``. A name with no argument is left exactly as
        it stands — a half-formatted sentence is easier to see than a blank.

        ``key`` is positional-only: a placeholder called ``{key}`` is a
        perfectly ordinary thing to write, and it must not collide with this
        method's own parameter.
        """
        return _substitute(self.t(key), args)

    def tn(self, key: str, n: int, /, **args: str) -> str:
        """Get the plural form of ``key`` for ``n``, with named arguments substituted.

        Resolves ``<key>.<category>``, where the category comes from the active
        language's CLDR cardinal rules (``spec/i18n.yaml``, generated into
        :mod:`astra_plugin_sdk.plural`), then falls back to ``<key>.other``,
        then ``<key>``, then the key text.

        ``{n}`` is **not** substituted for you. Pass it: a count that formats
        itself is a count the author cannot localise — and ``key`` and ``n``
        are positional-only precisely so that ``i18n.tn("msg.done", 3, n="3")``
        works, which is the call every plural string in this system makes.
        """
        category = plural.category(self._language, n)
        for candidate in (f"{key}.{category}", f"{key}.other", key):
            value = self._lookup(candidate)
            if value is not None:
                return _substitute(value, args)
        return _substitute(key, args)

    def count_prefixed(self, prefix: str) -> int:
        """How many distinct keys begin with ``prefix``, across the UNION of every
        loaded locale.

        Union, not the active language: a locale the author has not finished
        translating must not change a count the plugin's own logic depends on.
        """
        seen: set[str] = set()
        for table in self._locales.values():
            seen.update(k for k in table if k.startswith(prefix))
        return len(seen)

    @property
    def has_locales(self) -> bool:
        """Check if any locale files were loaded."""
        return bool(self._locales)

    @property
    def available_languages(self) -> list[str]:
        """Get available language codes, sorted."""
        return sorted(self._locales)


def _substitute(text: str, args: dict[str, str]) -> str:
    for name, value in args.items():
        text = text.replace("{" + name + "}", value)
    return text
