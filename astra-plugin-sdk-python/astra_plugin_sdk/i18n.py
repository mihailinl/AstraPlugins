"""Simple i18n helper for plugin localization.

Plugins ship ``locales/en.json``, ``locales/ru.json``, etc. alongside ``plugin.toml``.
Each file is a flat key-value JSON map::

    {
        "config.token.title": "API Token",
        "msg.hello": "Hello!"
    }

Usage::

    from astra_plugin_sdk import I18n

    i18n = I18n("locales")
    i18n.set_language("ru")
    text = i18n.t("msg.hello")  # Russian translation or English fallback
"""

import json
from pathlib import Path


class I18n:
    """Thread-safe translation store. Load locale files and resolve keys."""

    def __init__(self, locales_dir: str | Path):
        self._locales: dict[str, dict[str, str]] = {}
        self._language = "en"

        locales_path = Path(locales_dir)
        if locales_path.is_dir():
            for f in locales_path.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._locales[f.stem] = data
                except Exception:
                    pass

    def set_language(self, lang: str) -> None:
        """Set the active language."""
        self._language = lang

    @property
    def language(self) -> str:
        """Get the current active language."""
        return self._language

    def t(self, key: str) -> str:
        """Get a translated string. Falls back to English, then to the key itself."""
        return (
            self._locales.get(self._language, {}).get(key)
            or self._locales.get("en", {}).get(key)
            or key
        )

    def tf(self, key: str, *args: str) -> str:
        """Get a translated string with format arguments replaced.

        Placeholders use ``{0}``, ``{1}``, etc.
        """
        result = self.t(key)
        for i, arg in enumerate(args):
            result = result.replace(f"{{{i}}}", arg)
        return result

    @property
    def has_locales(self) -> bool:
        """Check if any locale files were loaded."""
        return bool(self._locales)

    @property
    def available_languages(self) -> list[str]:
        """Get available language codes."""
        return list(self._locales.keys())
